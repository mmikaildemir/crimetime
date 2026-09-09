"""
CrimeTime — Sentencing Decision Console (Streamlit)

A simple form-driven UI for the sentencing engine:
  1. Pick an offense
  2. Fill in case facts
  3. See the structured sentencing output

Run:
    streamlit run app.py
"""

import json

import streamlit as st

from crimetime import reference
from crimetime.models import AgeCategory, CaseFacts, PriorRecordStatus
from crimetime.sentencing import resolve

st.set_page_config(page_title="CrimeTime", page_icon="⚖️", layout="wide")


# ---------------------------------------------------------------------------
# Offense picker
# ---------------------------------------------------------------------------

@st.cache_data
def _offense_options() -> dict[str, dict]:
    """Return {display_label: offense_dict} sorted by article then section."""
    offenses = reference.get_all_offenses()
    result = {}
    for section, off in sorted(
        offenses.items(), key=lambda kv: (str(kv[1].get("article", "")), kv[0])
    ):
        label = f"§{section} — {off.get('name', '?')} ({off.get('classification', '?')})"
        result[label] = off
    return result


def _offense_picker() -> tuple[str, dict]:
    """Render the offense picker and return (section, offense_dict)."""
    options = _offense_options()
    labels = list(options.keys())
    selected = st.selectbox("Offense", labels, index=0)
    off = options[selected]
    return off["section"], off


# ---------------------------------------------------------------------------
# Case facts form
# ---------------------------------------------------------------------------

def _case_facts_form(section: str, offense: dict) -> CaseFacts:
    """Render the case-facts form and return a CaseFacts instance."""
    with st.form("case_facts"):
        col1, col2 = st.columns(2)

        with col1:
            prior = st.selectbox(
                "Prior record status",
                [p.value for p in PriorRecordStatus],
                format_func=lambda v: PriorRecordStatus(v).name.replace("_", " ").title(),
                help="Defendant's prior conviction status — selects the sentencing table row",
            )
            age = st.selectbox(
                "Age category",
                [a.value for a in AgeCategory],
                format_func=lambda v: AgeCategory(v).name.replace("_", " ").title(),
            )

        with col2:
            st.markdown("**Exception triggers**")
            plea_armed = st.checkbox(
                "Plea from armed felony indictment",
                help="CPL 1.20(41) — conviction resulted from plea in satisfaction of armed felony indictment",
            )
            mitigating = st.checkbox("Armed felony — mitigating circumstances", help="Factor (i)")
            minor_part = st.checkbox("Armed felony — minor participation", help="Factor (ii)")
            proof_def = st.checkbox("Armed felony — proof deficiencies", help="Factor (iii)")

        st.markdown("**Additional case facts**")
        col3, col4, col5 = st.columns(3)
        with col3:
            dv = st.checkbox(
                "Domestic violence by victim was a factor",
                help="PL 60.12 — allows indeterminate sentence instead of determinate",
            )
        with col4:
            dwi = st.checkbox("DWI-related offense", help="PL 60.21 — split sentence imprisonment up to 1 year")
        with col5:
            restitution = st.checkbox("Victim seeking restitution", help="PL 60.27 — court must consider")

        st.mark("**Derived flags (read-only)**")
        flags = reference.get_offense(section) or {}
        classification = offense.get("classification", "?")
        from crimetime.resolvers import (
            is_vfo, is_smf_eligible, is_hatecrime_eligible,
            has_predicate_exposure, is_yo_eligible,
        )
        flag_cols = st.columns(5)
        flag_cols[0].metric("VFO", str(is_vfo(section, classification)))
        flag_cols[1].metric("SMF", str(is_smf_eligible(section, classification)))
        flag_cols[2].metric("Hate Crime", str(is_hatecrime_eligible(section)))
        flag_cols[3].metric("Pred Exposure", str(has_predicate_exposure(classification)))
        flag_cols[4].metric("YO Eligible", str(is_yo_eligible(classification)))

        submitted = st.form_submit_button("Resolve Sentencing", type="primary")

    if not submitted:
        return None

    return CaseFacts(
        section=section,
        prior_record_status=PriorRecordStatus(prior),
        defendant_age_category=AgeCategory(age),
        plea_from_armed_felony_indictment=plea_armed,
        armed_felony_mitigating_factor=mitigating,
        armed_felony_minor_participation=minor_part,
        armed_felony_proof_deficiencies=proof_def,
        domestic_violence_by_victim=dv,
        is_dwi=dwi,
        victim_seeking_restitution=restitution,
    )


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------

def _render_term(term) -> str:
    if term is None:
        return ""
    unit = term.unit.value
    return f"{term.min_value}–{term.max_value} {unit}"


def _render_disposition(d) -> None:
    label = d.label
    if d.term:
        label += f"  →  **{_render_term(d.term)}**"
    if d.prs:
        label += f"  + PRS {d.prs.min_years}–{d.prs.max_years} yrs"
    st.markdown(f"- **{d.type.value.title()}**: {label}")
    if d.statute_refs:
        st.caption(", ".join(d.statute_refs))
    if d.conditions:
        st.caption(f"_{d.conditions}_")
    if d.record_statement_required:
        st.caption("⚠️ Record statement required (felony)")


def _render_exception(e) -> None:
    st.markdown(f"- **{e.type.value.replace('_', ' ').title()}**: {e.label}")
    if e.description:
        st.caption(e.description)
    if e.statute_refs:
        st.caption(", ".join(e.statute_refs))
    if e.triggering_factors:
        st.caption(f"Triggered by: {', '.join(e.triggering_factors)}")
    if e.resulting_disposition:
        st.caption(f"→ {_render_term(e.resulting_disposition.term)}")


def _render_financial(f) -> None:
    label = f.label
    if f.amount is not None:
        label += f"  (${f.amount:,.0f})"
    st.markdown(f"- {label}")
    if f.statute_refs:
        st.caption(", ".join(f.statute_refs))


def _render_collateral(c) -> None:
    st.markdown(f"- **{c.type.value.replace('_', ' ').title()}**: {c.label}")
    if c.statute_refs:
        st.caption(", ".join(c.statute_refs))


def _render_output(output) -> None:
    st.divider()
    st.subheader(f"§{output.section} — {output.offense_name}")
    st.markdown(f"**Classification:** `{output.classification}`  |  **VFO:** `{output.is_vfo}`")

    # Dispositions
    st.markdown("### Available Dispositions")
    if not output.available_dispositions:
        st.info("No dispositions available.")
    for d in output.available_dispositions:
        _render_disposition(d)

    # Exceptions
    if output.exception_paths:
        st.markdown("### Exception Paths")
        for e in output.exception_paths:
            _render_exception(e)

    # Financial
    st.markdown("### Financial Obligations")
    for f in output.financial_obligations:
        _render_financial(f)

    # Collateral
    if output.collateral_requirements:
        st.markdown("### Collateral Requirements")
        for c in output.collateral_requirements:
            _render_collateral(c)

    # Raw JSON (for debugging / export)
    with st.expander("Raw output (JSON)"):
        st.json(output.model_dump())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.title("CrimeTime")
    st.caption("NYS criminal sentencing decision engine — pick an offense, fill in case facts, see the output.")

    section, offense = _offense_picker()
    facts = _case_facts_form(section, offense)

    if facts is not None:
        try:
            output = resolve(section, facts)
            _render_output(output)
        except Exception as exc:
            st.error(f"Resolution failed: {exc}")


if __name__ == "__main__":
    main()
