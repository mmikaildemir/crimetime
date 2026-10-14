"""
CrimeTime — Sentencing Engine UI (Streamlit)

Pick an offense, set the case facts, and run the sentencing decision engine.
Displays the structured SentencingOutput: dispositions, exceptions,
financials, collateral, and modifier tracking.

Run:
    streamlit run sentencing_ui.py
"""

from __future__ import annotations

import json
from copy import deepcopy

import streamlit as st

from crimetime import sentencing
from crimetime.exceptions import _DV_EXCLUDED_SECTIONS
from crimetime.models import (
    AgeCategory,
    CaseFacts,
    PriorRecordStatus,
    TermUnit,
)
from crimetime.reference import get_all_offenses
from crimetime.report import render_report
from crimetime.resolvers import (
    has_predicate_exposure,
    is_felony,
    is_hatecrime_eligible,
    is_misdemeanor,
    is_smf_eligible,
    is_vfo,
    is_violation,
    is_yo_eligible,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _offense_options() -> list[tuple[str, str]]:
    """Return sorted (section, label) tuples for the selectbox."""
    offenses = get_all_offenses()
    items = []
    for section, off in offenses.items():
        name = off.get("name", "")
        cls = off.get("classification", "")
        items.append((section, f"§{section} — {name} ({cls})"))
    items.sort(key=lambda t: (int(t[0].split(".")[0]) if t[0].split(".")[0].isdigit() else 9999, t[0]))
    return items


def _format_term(term) -> str:
    if term is None:
        return "—"
    unit = term.unit.value if hasattr(term.unit, "value") else str(term.unit)
    if term.max_value >= 999:
        return f"{term.min_value} {unit} to life"
    return f"{term.min_value}–{term.max_value} {unit}"


def _disposition_color(dtype: str) -> str:
    return {
        "determinate": "#1f77b4",
        "indeterminate": "#ff7f0e",
        "definite": "#2ca02c",
        "life_without_parole": "#d62728",
        "probation": "#9467bd",
        "conditional_discharge": "#8c564b",
        "unconditional_discharge": "#7f7f7f",
        "split": "#e377c2",
        "intermittent": "#bcbd22",
        "fine": "#17becf",
    }.get(dtype, "#444")


# ---------------------------------------------------------------------------
# Case-facts form (sidebar)
# ---------------------------------------------------------------------------


def case_facts_form(section: str, offense: dict) -> CaseFacts:
    """Render a context-aware case-facts form in the sidebar.

    Only fields that can actually affect the selected offense are shown.
    Eligibility is computed from the offense via the resolvers.
    """
    classification = offense.get("classification", "Violation")
    is_fel = is_felony(classification)
    is_misd = is_misdemeanor(classification)
    is_viol = is_violation(classification)
    vfo = is_vfo(section, classification)
    smf_elig = is_smf_eligible(section, classification)
    hc_elig = is_hatecrime_eligible(section)
    terror_elig = is_fel and hc_elig  # engine gates terrorism on hate-crime list + felony
    dv_elig = is_fel and section not in _DV_EXCLUDED_SECTIONS
    armed_elig = is_fel  # armed-felony override applies to felonies
    yo_elig = is_yo_eligible(classification)

    # --- Eligibility badges (read-only context) ---
    st.sidebar.header("Eligibility")
    badges = []
    if vfo:
        badges.append(("VFO", "#1f77b4"))
    if smf_elig:
        badges.append(("SMF", "#9467bd"))
    if hc_elig:
        badges.append(("Hate Crime", "#e377c2"))
    if terror_elig:
        badges.append(("Terrorism", "#d62728"))
    if has_predicate_exposure(classification):
        badges.append(("Predicate Exposure", "#ff7f0e"))
    if yo_elig:
        badges.append(("YO Eligible", "#2ca02c"))
    if not badges:
        st.sidebar.caption("No enhancements apply to this offense.")
    else:
        badge_html = " ".join(
            f"<span style='background:{c};color:#fff;padding:2px 8px;border-radius:8px;"
            f"font-size:0.8em;font-weight:600'>{lbl}</span>"
            for lbl, c in badges
        )
        st.sidebar.markdown(badge_html, unsafe_allow_html=True)

    # Defaults that get filled conditionally
    prior_status = PriorRecordStatus.FIRST_OFFENDER
    is_attempt = False
    attempt_of_section = None
    is_conspiracy = False
    conspiracy_of_section = None
    subdivision = None
    hate_crime_motivated = False
    sexually_motivated = False
    terrorism_motivated = False
    plea_from_armed_felony_indictment = False
    armed_felony_mitigating = False
    armed_felony_minor = False
    armed_felony_proof = False
    domestic_violence_by_victim = False
    is_dwi = False
    under_other_sentence = False
    victim_restitution = False
    intended_underlying_class = None
    prior_same_section_years = None
    age_category = AgeCategory.ADULT

    # --- Prior record status (felonies only — table selector) ---
    if is_fel:
        st.sidebar.header("Defendant prior record")
        prior_status_options = [
            (PriorRecordStatus.FIRST_OFFENDER, "First offender"),
            (PriorRecordStatus.SECOND_FELONY_OFFENDER_70_06, "Second felony offender (PL 70.06)"),
            (PriorRecordStatus.SECOND_VIOLENT_FELONY_OFFENDER_70_04, "Second violent felony offender (PL 70.04)"),
            (PriorRecordStatus.PERSISTENT_FELONY_OFFENDER_70_10, "Persistent felony offender (PL 70.10)"),
            (PriorRecordStatus.PERSISTENT_VIOLENT_FELONY_OFFENDER_70_08, "Persistent violent felony offender (PL 70.08)"),
        ]
        # Filter to statuses that can actually route for this offense
        valid = []
        for ps, lbl in prior_status_options:
            if ps == PriorRecordStatus.SECOND_VIOLENT_FELONY_OFFENDER_70_04 and not vfo:
                continue
            if ps == PriorRecordStatus.PERSISTENT_VIOLENT_FELONY_OFFENDER_70_08 and not vfo:
                continue
            if ps in (PriorRecordStatus.SECOND_FELONY_OFFENDER_70_06,
                      PriorRecordStatus.PERSISTENT_FELONY_OFFENDER_70_10) and not has_predicate_exposure(classification):
                continue
            valid.append((ps, lbl))
        prior_label = st.sidebar.selectbox(
            "Prior record status", options=[lbl for _, lbl in valid], index=0
        )
        prior_status = next(ps for ps, lbl in valid if lbl == prior_label)

    # --- Offense shape: attempt / conspiracy ---
    # Always ask — the engine downgrades classification (PL 110.05) and
    # re-derives VFO status when is_attempt is set, so this affects every
    # crime, not just pre-seeded attempt entries.
    if is_fel or is_misd:
        st.sidebar.header("Offense shape")
        is_attempt = st.sidebar.checkbox(
            "Is this an attempt?",
            value=bool(offense.get("isAttempt")),
            help="If yes, the classification is downgraded one tier per PL 110.05 "
                 "and VFO status is re-derived. Enter the target (completed) offense section.",
        )
        if is_attempt:
            attempt_of_section = st.sidebar.text_input(
                "Attempt of (target section) *",
                value=offense.get("attemptOf") or section,
                placeholder="e.g. 125.25",
            )
            subdivision = st.sidebar.text_input(
                "Target subdivision", value="", placeholder="e.g. 2"
            ) or None
            if attempt_of_section:
                try:
                    from crimetime.resolvers import resolve_attempt_classification
                    target_off = get_all_offenses().get(attempt_of_section)
                    target_cls = target_off["classification"] if target_off else "Unknown"
                    resolved = resolve_attempt_classification(
                        attempt_of_section, target_cls, subdivision
                    )
                    st.sidebar.info(
                        f"**Downgraded classification:** `{resolved}`  \n"
                        f"(from `{target_cls}` per PL 110.05)"
                    )
                except Exception as e:
                    st.sidebar.warning(f"Cannot resolve attempt: {e}")

        is_conspiracy = st.sidebar.checkbox(
            "Is this a conspiracy?",
            value=bool(offense.get("isConspiracy")),
        )
        if is_conspiracy:
            conspiracy_of_section = st.sidebar.text_input(
                "Conspiracy of (section)",
                value=offense.get("conspiracyOf") or section,
            )

    # --- Conditional classification prompts (offense-intrinsic) ---
    conditional = offense.get("conditionalClassification")
    if conditional:
        st.sidebar.header("Conditional classification")
        prompt_fields = conditional.get("prompt_fields", [])
        if "intended_underlying_offense_class" in prompt_fields:
            intended_underlying_class = st.sidebar.selectbox(
                "Intended underlying offense class",
                options=["", "ClassA_I_Felony", "ClassA_II_Felony", "ClassB_Felony",
                         "ClassB_Violent_Felony", "ClassC_Felony", "ClassD_Felony", "ClassE_Felony"],
            ) or None
        if "prior_conviction_same_section_within_years" in prompt_fields:
            val = st.sidebar.number_input(
                "Prior conviction of same section within (years)", min_value=0, value=0, step=1
            )
            prior_same_section_years = val if val else None

    # --- Enhancements (only eligible ones) ---
    if hc_elig or smf_elig or terror_elig:
        st.sidebar.header("Enhancements")
        if hc_elig:
            hate_crime_motivated = st.sidebar.checkbox("Hate crime motivated (PL 485)")
        if smf_elig:
            sexually_motivated = st.sidebar.checkbox("Sexually motivated felony (PL 130.91)")
        if terror_elig:
            terrorism_motivated = st.sidebar.checkbox("Terrorism motivated (PL 490.25)")

    # --- Exception triggers (gated by relevance) ---
    if armed_elig or dv_elig:
        st.sidebar.header("Exception triggers")
        if armed_elig:
            plea_from_armed_felony_indictment = st.sidebar.checkbox(
                "Plea from armed-felony indictment"
            )
            if plea_from_armed_felony_indictment:
                armed_felony_mitigating = st.sidebar.checkbox("…mitigating factor")
                armed_felony_minor = st.sidebar.checkbox("…minor participation")
                armed_felony_proof = st.sidebar.checkbox("…proof deficiencies")
        if dv_elig:
            domestic_violence_by_victim = st.sidebar.checkbox(
                "Domestic violence by victim (PL 60.12)"
            )

    # --- Advanced / niche triggers (collapsed) ---
    with st.sidebar.expander("Advanced", expanded=False):
        is_dwi = st.checkbox("DWI offense (PL 60.21)")
        under_other_sentence = st.checkbox("Defendant under other sentence > 15 days")
        victim_restitution = st.checkbox("Victim seeking restitution")
        if is_fel or is_misd:
            age_label = st.selectbox(
                "Age category",
                options=["Adult", "Youthful offender eligible"] if yo_elig else ["Adult"],
                index=0,
            )
            age_category = AgeCategory.ADULT if age_label == "Adult" else AgeCategory.YOUTHFUL_OFFENDER_ELIGIBLE

    return CaseFacts(
        section=section,
        subdivision=subdivision,
        is_attempt=is_attempt,
        attempt_of_section=attempt_of_section,
        is_conspiracy=is_conspiracy,
        conspiracy_of_section=conspiracy_of_section,
        prior_record_status=prior_status,
        plea_from_armed_felony_indictment=plea_from_armed_felony_indictment,
        armed_felony_mitigating_factor=armed_felony_mitigating,
        armed_felony_minor_participation=armed_felony_minor,
        armed_felony_proof_deficiencies=armed_felony_proof,
        domestic_violence_by_victim=domestic_violence_by_victim,
        is_dwi=is_dwi,
        defendant_under_other_sentence_over_15_days=under_other_sentence,
        victim_seeking_restitution=victim_restitution,
        hate_crime_motivated=hate_crime_motivated,
        sexually_motivated=sexually_motivated,
        terrorism_motivated=terrorism_motivated,
        intended_underlying_offense_class=intended_underlying_class,
        prior_conviction_same_section_within_years=prior_same_section_years,
        defendant_age_category=age_category,
    )


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def render_header(out):
    st.header(f"§{out.section} — {out.offense_name}")
    cols = st.columns([2, 2, 1, 1])
    cols[0].metric("Final classification", out.classification)
    cols[1].metric("Base classification", out.base_classification or "(no modifier)")
    cols[2].metric("VFO", "Yes" if out.is_vfo else "No")
    cols[3].metric("Dispositions", len(out.available_dispositions))


def render_modifiers(out):
    if not out.modifiers_applied:
        return
    st.subheader("Modifiers applied")
    for m in out.modifiers_applied:
        st.info(
            f"**{m.modifier_type}** — branch `{m.branch or '—'}`  \n"
            f"{m.base_classification} → **{m.resulting_classification}**"
        )


def render_dispositions(out):
    st.subheader("Available dispositions")
    primary = out.available_dispositions[0] if out.available_dispositions else None
    alternatives = out.available_dispositions[1:] if len(out.available_dispositions) > 1 else []

    if primary:
        _render_disposition_card(primary, is_primary=True)

    if alternatives:
        st.markdown("**Alternatives**")
        for d in alternatives:
            _render_disposition_card(d, is_primary=False)


def _render_disposition_card(d, is_primary: bool):
    color = _disposition_color(d.type.value if hasattr(d.type, "value") else str(d.type))
    label_prefix = "PRIMARY" if is_primary else "ALT"
    with st.container(border=True):
        st.markdown(
            f"<span style='color:{color};font-weight:bold'>{label_prefix} · "
            f"{d.type.value.upper()}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{d.label}**")
        if d.term:
            st.write(f"Term: `{_format_term(d.term)}`")
        if d.prs:
            st.write(f"Post-release supervision: `{d.prs.min_years}–{d.prs.max_years} years`")
        if d.probation_years:
            st.write(f"Probation years: `{d.probation_years}`")
        if d.conditional_discharge_years is not None:
            st.write(f"Conditional discharge (years): `{d.conditional_discharge_years}`")
        if d.split_imprisonment_max_months is not None:
            st.write(f"Split imprisonment max (months): `{d.split_imprisonment_max_months}`")
        if d.fine_max_amount is not None:
            st.write(f"Fine max ($): `{d.fine_max_amount}`  ·  alt double gain: `{d.fine_alt_double_gain}`")
        if d.record_statement_required:
            st.write("Record statement required: `yes`")
        if d.conditions:
            st.caption(f"Conditions: {d.conditions}")
        if d.statute_refs:
            st.caption(f"Refs: {', '.join(d.statute_refs)}")


def render_exceptions(out):
    if not out.exception_paths:
        return
    st.subheader("Exception paths")
    for e in out.exception_paths:
        with st.container(border=True):
            st.markdown(f"**{e.label}**  `{e.type.value}`")
            st.write(e.description)
            if e.triggering_factors:
                st.caption(f"Triggers: {', '.join(e.triggering_factors)}")
            if e.statute_refs:
                st.caption(f"Refs: {', '.join(e.statute_refs)}")
            if e.resulting_disposition:
                st.write(f"→ {e.resulting_disposition.label}")


def render_financials(out):
    if not out.financial_obligations:
        return
    st.subheader("Financial obligations")
    rows = []
    for f in out.financial_obligations:
        rows.append({
            "Type": f.type.value,
            "Label": f.label,
            "Amount": f"$ {f.amount:,.0f}" if f.amount is not None else "—",
            "Refs": ", ".join(f.statute_refs),
            "Conditions": f.conditions or "",
        })
    st.table(rows)


def render_collateral(out):
    if not out.collateral_requirements:
        return
    st.subheader("Collateral requirements")
    for c in out.collateral_requirements:
        with st.container(border=True):
            st.markdown(f"**{c.label}**  `{c.type.value}`")
            st.write(c.description)
            if c.statute_refs:
                st.caption(f"Refs: {', '.join(c.statute_refs)}")


def render_raw_json(out):
    with st.expander("Raw JSON output", expanded=False):
        st.json(json.loads(out.model_dump_json()))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    st.set_page_config(page_title="CrimeTime — Sentencing Engine", page_icon="⚖️", layout="wide")
    st.title("CrimeTime — Sentencing Engine")
    st.caption("Resolve the full sentencing output for a NYS offense given case facts.")

    options = _offense_options()
    labels = [lbl for _, lbl in options]
    section_map = {lbl: sec for sec, lbl in options}

    selected_label = st.selectbox("Select offense", options=labels)
    section = section_map[selected_label]
    offense = get_all_offenses()[section]

    st.caption(f"**Article {offense.get('article', '?')}** · classification: `{offense.get('classification', '?')}`")
    if offense.get("elements"):
        st.caption(offense["elements"])

    case_facts = case_facts_form(section, offense)

    run = st.button("Resolve sentencing", type="primary")

    if run:
        try:
            with st.spinner("Resolving…"):
                out = sentencing.resolve(section, case_facts)
        except Exception as e:
            st.error(f"Engine error: {e}")
            return
        st.session_state["_last_output"] = out

    out = st.session_state.get("_last_output")
    if out is not None:
        st.divider()

        view = st.radio("View", options=["Structured", "Memorandum"], horizontal=True)
        if view == "Memorandum":
            st.markdown(render_report(out))
            st.download_button(
                "Download .md",
                data=render_report(out),
                file_name=f"sentencing_{out.section}.md",
                mime="text/markdown",
            )
        else:
            render_header(out)
            render_modifiers(out)
            render_dispositions(out)
            render_exceptions(out)
            render_financials(out)
            render_collateral(out)
            render_raw_json(out)


if __name__ == "__main__":
    main()
