"""
CrimeTime — Data Entry Console (Streamlit)

Edit reference data through forms instead of hand-editing JSON:
  Tab 1: Offenses      — add/edit/delete offenses (data/lists.json)
  Tab 2: Lists         — manage VFO/SMF/HATECRIME section lists (data/lists.json)
  Tab 3: Sentencing    — edit sentencing range tables (data/sentencing_tables.json)

Run:
    streamlit run app.py
"""

import json
from pathlib import Path
from copy import deepcopy

import streamlit as st

from crimetime.legislation import (
    CLASSIFICATIONS,
    fetch_section,
    parse_article,
    parse_classification,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
LISTS_PATH = DATA_DIR / "lists.json"
SENTENCING_PATH = DATA_DIR / "sentencing_tables.json"


# ---------------------------------------------------------------------------
# JSON load/save helpers
# ---------------------------------------------------------------------------

def _load(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _save(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)




# ---------------------------------------------------------------------------
# Tab 1: Offenses
# ---------------------------------------------------------------------------

def offenses_tab():
    st.header("Offenses")
    data = _load(LISTS_PATH)
    offenses = data.get("offenses", {})

    # --- Add new offense ---
    with st.expander("Add new offense", expanded=False):
        # Auto-resolve: process button click BEFORE widgets are created
        # so we can set session_state values that the widgets will pick up
        if st.session_state.get("_auto_resolve_triggered"):
            section_to_resolve = st.session_state.pop("_auto_resolve_triggered")
            result = fetch_section(section_to_resolve)
            if result:
                name = result.get("title", "")
                text = result.get("text", "")
                classification = parse_classification(text)
                article = parse_article(section_to_resolve)
                st.session_state["add_name"] = name
                st.session_state["add_article"] = article
                if classification:
                    st.session_state["add_class"] = classification
                st.session_state["_auto_resolve_msg"] = f"Resolved: {name} — {classification or 'classification not found'}"
            else:
                st.session_state["_auto_resolve_msg"] = "Could not fetch statute. Check section number or API key."

        col1, col2 = st.columns(2)
        with col1:
            new_section = st.text_input("Section *", placeholder="e.g. 120.02", key="add_section")
            new_name = st.text_input("Name", placeholder="Auto-filled on resolve, or type manually", key="add_name")
        with col2:
            new_article = st.number_input("Article", min_value=0, value=120, key="add_article")

        # Auto-resolve button — sets a flag, triggers rerun, values applied before widgets
        col_resolve, col_info = st.columns([1, 3])
        with col_resolve:
            if st.button("Auto-resolve §", help="Fetch name + classification from NYS Open Legislation API", key="auto_resolve_btn"):
                if new_section:
                    st.session_state["_auto_resolve_triggered"] = new_section
                    st.rerun()
                else:
                    st.warning("Enter a section number first.")
        with col_info:
            if st.session_state.get("_auto_resolve_msg"):
                st.info(st.session_state.pop("_auto_resolve_msg"))
            st.caption("Click to auto-fill name + classification from the NYS legislature API. Works for straightforward offenses (not attempts/conspiracies).")

        new_attempt = st.checkbox("Is this an attempt of another offense?", key="add_attempt")
        new_attempt_of = None
        if new_attempt:
            new_attempt_of = st.text_input("Attempt of (target section) *", placeholder="e.g. 125.25", key="add_attempt_of")

        # Classification: auto-resolved if attempt, manual otherwise
        from crimetime.resolvers import resolve_attempt_classification
        if new_attempt and new_attempt_of:
            target_off = offenses.get(new_attempt_of)
            if target_off:
                target_cls = target_off.get("classification", "Violation")
                resolved_cls = resolve_attempt_classification(new_attempt_of, target_cls)
                new_class = resolved_cls
                st.info(f"**Auto-resolved classification:** `{resolved_cls}` (from target §{new_attempt_of} — {target_off.get('name', '?')})")
            else:
                st.warning(f"Target §{new_attempt_of} not found in offenses. Add the target offense first.")
                new_class = st.selectbox("Classification (manual — target not found)", CLASSIFICATIONS, key="add_class_fallback")
        else:
            new_class = st.selectbox("Classification *", CLASSIFICATIONS, key="add_class")

        # Live preview of derived flags (auto-resolved from section + classification)
        if new_section and new_class:
            from crimetime.resolvers import (
                is_vfo, is_smf_eligible, is_hatecrime_eligible,
                has_predicate_exposure, is_yo_eligible,
            )
            st.caption("**Auto-resolved flags** (computed from lists.json — no manual entry needed):")
            pcol1, pcol2, pcol3, pcol4, pcol5 = st.columns(5)
            pcol1.metric("VFO", str(is_vfo(new_section, new_class)))
            pcol2.metric("SMF", str(is_smf_eligible(new_section, new_class)))
            pcol3.metric("Hate Crime", str(is_hatecrime_eligible(new_section)))
            pcol4.metric("Predicate Exposure", str(has_predicate_exposure(new_class)))
            pcol5.metric("YO Eligible", str(is_yo_eligible(new_class)))

        new_elements = st.text_area("Elements", placeholder="Describe the elements of the offense...", key="add_elements")
        new_conspiracy = st.checkbox("Is this a conspiracy of another offense?", key="add_conspiracy")
        new_conspiracy_of = st.text_input("Conspiracy of (section)", placeholder="e.g. 125.25", key="add_conspiracy_of") if new_conspiracy else ""

        # Conditional classification (optional — for offenses like §130.86, §225.90)
        with st.expander("Conditional classification (optional)", expanded=False):
            st.caption("For offenses whose classification changes based on a case fact (e.g. §130.86 luring a child, §225.90 gaming manipulation)")
            has_conditional = st.checkbox("This offense has conditional classification", key="add_has_conditional")
            conditional_rules = []
            conditional_fallback = new_class if new_class else "Violation"
            if has_conditional:
                conditional_fallback = st.selectbox("Fallback classification (default)", CLASSIFICATIONS, key="add_cond_fallback")
                num_rules = st.number_input("Number of rules", min_value=1, max_value=10, value=1, key="add_cond_num")
                for i in range(int(num_rules)):
                    st.markdown(f"**Rule {i+1}**")
                    rc_col1, rc_col2 = st.columns(2)
                    with rc_col1:
                        rc_field = st.selectbox(
                            "Field (case fact to check)",
                            [
                                "intended_underlying_offense_class",
                                "prior_conviction_same_section_within_years",
                            ],
                            key=f"add_cond_field_{i}",
                        )
                        rc_condition = st.selectbox("Condition", ["in", "true", "gt"], key=f"add_cond_cond_{i}")
                    with rc_col2:
                        rc_values = st.text_input("Values (comma-separated)", placeholder="e.g. ClassA_I_Felony, ClassA_II_Felony", key=f"add_cond_vals_{i}")
                        rc_result = st.selectbox("Resulting classification", CLASSIFICATIONS, key=f"add_cond_result_{i}")
                    conditional_rules.append({
                        "field": rc_field,
                        "condition": rc_condition,
                        "values": [v.strip() for v in rc_values.split(",") if v.strip()] if rc_values else [],
                        "resulting_classification": rc_result,
                    })
                st.caption(f"Prompt fields: {[r['field'] for r in conditional_rules]}")

        if st.button("Add offense", type="primary", key="add_btn"):
            if not new_section:
                st.error("Section is required.")
            elif new_section in offenses:
                st.error(f"Section {new_section} already exists.")
            else:
                entry = {
                    "article": int(new_article),
                    "section": new_section,
                    "name": new_name if new_name else "",
                    "classification": new_class,
                    "elements": new_elements if new_elements else None,
                    "isAttempt": new_attempt,
                    "attemptOf": new_attempt_of if new_attempt else None,
                    "isConspiracy": new_conspiracy,
                    "conspiracyOf": new_conspiracy_of if new_conspiracy else None,
                }
                if has_conditional and conditional_rules:
                    entry["conditionalClassification"] = {
                        "rules": conditional_rules,
                        "fallback": conditional_fallback,
                        "prompt_fields": [r["field"] for r in conditional_rules],
                    }
                offenses[new_section] = entry
                _save(LISTS_PATH, data)
                st.success(f"Added §{new_section}")
                st.rerun()

    # --- List existing offenses ---
    st.subheader(f"Existing offenses ({len(offenses)})")
    search = st.text_input("Search", placeholder="Filter by section or name...")

    sorted_offenses = sorted(offenses.items(), key=lambda kv: (str(kv[1].get("article", "")), kv[0]))
    if search:
        s_lower = search.lower()
        sorted_offenses = [
            (s, o) for s, o in sorted_offenses
            if s_lower in s.lower() or s_lower in o.get("name", "").lower()
        ]

    for section, off in sorted_offenses:
        label = f"§{section} — {off.get('name', '?')} ({off.get('classification', '?')})"
        if off.get("conditionalClassification"):
            label += " [conditional]"
        with st.expander(label):
            # Show current auto-resolved flags (read-only)
            _classification = off.get("classification", "Violation")
            from crimetime.resolvers import (
                is_vfo, is_smf_eligible, is_hatecrime_eligible,
                has_predicate_exposure, is_yo_eligible,
            )
            fcol1, fcol2, fcol3, fcol4, fcol5 = st.columns(5)
            fcol1.metric("VFO", str(is_vfo(section, _classification)))
            fcol2.metric("SMF", str(is_smf_eligible(section, _classification)))
            fcol3.metric("Hate Crime", str(is_hatecrime_eligible(section)))
            fcol4.metric("Predicate", str(has_predicate_exposure(_classification)))
            fcol5.metric("YO Elig.", str(is_yo_eligible(_classification)))
            st.caption("Flags above auto-resolve from lists.json — no manual entry needed.")

            # Show conditional classification if present
            cond = off.get("conditionalClassification")
            if cond:
                st.info("**Conditional classification rules:**")
                for rule in cond.get("rules", []):
                    st.caption(f"  If `{rule['field']}` {rule.get('condition', 'in')} {rule.get('values', [])} → `{rule['resulting_classification']}`")
                st.caption(f"  Fallback: `{cond.get('fallback', '?')}`")

            with st.form(f"edit_{section}"):
                col1, col2 = st.columns(2)
                with col1:
                    name = st.text_input("Name", value=off.get("name", ""))
                    article = st.number_input("Article", min_value=0, value=off.get("article", 0))
                with col2:
                    classification = st.selectbox(
                        "Classification",
                        CLASSIFICATIONS,
                        index=CLASSIFICATIONS.index(off.get("classification", "Violation")) if off.get("classification") in CLASSIFICATIONS else 0,
                    )
                    is_attempt = st.checkbox("Is attempt", value=off.get("isAttempt", False))

                attempt_of = st.text_input("Attempt of (target section)", value=off.get("attemptOf") or "") if is_attempt else ""
                if is_attempt and attempt_of:
                    from crimetime.resolvers import resolve_attempt_classification
                    target_off = offenses.get(attempt_of)
                    if target_off:
                        target_cls = target_off.get("classification", "Violation")
                        resolved = resolve_attempt_classification(attempt_of, target_cls)
                        st.info(f"**Auto-resolved classification:** `{resolved}` (from target §{attempt_of} — {target_off.get('name', '?')}) — select this on the left.")
                is_conspiracy = st.checkbox("Is conspiracy", value=off.get("isConspiracy", False))
                conspiracy_of = st.text_input("Conspiracy of (section)", value=off.get("conspiracyOf") or "") if is_conspiracy else ""
                elements = st.text_area("Elements", value=off.get("elements") or "")

                col_save, col_delete = st.columns([3, 1])
                with col_save:
                    saved = st.form_submit_button("Save changes", type="primary")
                with col_delete:
                    deleted = st.form_submit_button("Delete")

                if saved:
                    # Auto-resolve classification for attempts
                    if is_attempt and attempt_of:
                        target_off = offenses.get(attempt_of)
                        if target_off:
                            target_cls = target_off.get("classification", "Violation")
                            classification = resolve_attempt_classification(attempt_of, target_cls)
                    off["name"] = name
                    off["article"] = int(article)
                    off["classification"] = classification
                    off["isAttempt"] = is_attempt
                    off["attemptOf"] = attempt_of if is_attempt else None
                    off["isConspiracy"] = is_conspiracy
                    off["conspiracyOf"] = conspiracy_of if is_conspiracy else None
                    off["elements"] = elements if elements else None
                    _save(LISTS_PATH, data)
                    st.success("Saved.")
                    st.rerun()

                if deleted:
                    del offenses[section]
                    _save(LISTS_PATH, data)
                    st.success(f"Deleted §{section}.")
                    st.rerun()


# ---------------------------------------------------------------------------
# Tab 2: Statutory Lists
# ---------------------------------------------------------------------------

def lists_tab():
    st.header("Statutory Lists")
    data = _load(LISTS_PATH)
    lists = data.get("lists", {})

    # --- VFO_LIST ---
    st.subheader("VFO List (PL 70.02(1))")
    vfo = lists.get("VFO_LIST", {})
    vfo_classes = ["classB", "classC", "classD", "classE"]

    for cls in vfo_classes:
        if cls not in vfo:
            continue
        cls_data = vfo[cls]
        sections = cls_data.get("sections", [])
        st.markdown(f"**{cls.replace('class', 'Class ')}** ({len(sections)} sections)")

        # Show sections as removable tags
        cols_per_row = 6
        for i in range(0, len(sections), cols_per_row):
            row_cols = st.columns(cols_per_row)
            for j, sec in enumerate(sections[i:i + cols_per_row]):
                if row_cols[j].button(f"§{sec} ✕", key=f"vfo_{cls}_{sec}"):
                    sections.remove(sec)
                    _save(LISTS_PATH, data)
                    st.rerun()

        with st.form(f"vfo_add_{cls}"):
            new_sec = st.text_input(f"Add section to {cls}", placeholder="e.g. 125.20", key=f"vfo_input_{cls}")
            if st.form_submit_button("Add"):
                if new_sec and new_sec not in sections:
                    sections.append(new_sec)
                    sections.sort()
                    _save(LISTS_PATH, data)
                    st.success(f"Added §{new_sec} to {cls}")
                    st.rerun()
                elif new_sec in sections:
                    st.warning(f"§{new_sec} already in {cls}")

        # Show subdivision restrictions if any
        subds = cls_data.get("sectionSubdivisions", {})
        if subds:
            st.caption(f"Subdivision restrictions: {subds}")
        st.markdown("---")

    # --- SMF_LIST ---
    st.subheader("SMF List (PL 130.91(2))")
    smf = lists.get("SMF_LIST", {})
    smf_sections = smf.get("sections", [])
    st.caption(f"{len(smf_sections)} sections")
    for i in range(0, len(smf_sections), 6):
        row_cols = st.columns(6)
        for j, sec in enumerate(smf_sections[i:i + 6]):
            if row_cols[j].button(f"§{sec} ✕", key=f"smf_{sec}"):
                smf_sections.remove(sec)
                _save(LISTS_PATH, data)
                st.rerun()

    with st.form("smf_add"):
        new_sec = st.text_input("Add section to SMF list", placeholder="e.g. 125.25")
        if st.form_submit_button("Add"):
            if new_sec and new_sec not in smf_sections:
                smf_sections.append(new_sec)
                smf_sections.sort()
                _save(LISTS_PATH, data)
                st.success(f"Added §{new_sec}")
                st.rerun()

    if smf.get("sectionSubdivisions"):
        st.caption(f"Subdivision restrictions: {smf['sectionSubdivisions']}")
    st.caption(f"Includes attempts/conspiracy: {smf.get('includesAttemptsAndConspiracy', False)}")

    st.markdown("---")

    # --- HATECRIME_LIST ---
    st.subheader("Hate Crime List (PL 485.05(3))")
    hc = lists.get("HATECRIME_LIST", {})
    hc_sections = hc.get("sections", [])
    st.caption(f"{len(hc_sections)} sections")
    for i in range(0, len(hc_sections), 6):
        row_cols = st.columns(6)
        for j, sec in enumerate(hc_sections[i:i + 6]):
            if row_cols[j].button(f"§{sec} ✕", key=f"hc_{sec}"):
                hc_sections.remove(sec)
                _save(LISTS_PATH, data)
                st.rerun()

    with st.form("hc_add"):
        new_sec = st.text_input("Add section to Hate Crime list", placeholder="e.g. 120.05")
        if st.form_submit_button("Add"):
            if new_sec and new_sec not in hc_sections:
                hc_sections.append(new_sec)
                hc_sections.sort()
                _save(LISTS_PATH, data)
                st.success(f"Added §{new_sec}")
                st.rerun()

    if hc.get("sectionSubdivisions"):
        st.caption(f"Subdivision restrictions: {hc['sectionSubdivisions']}")
    st.caption(f"Includes attempts/conspiracy: {hc.get('includesAttemptsAndConspiracy', False)}")


# ---------------------------------------------------------------------------
# Tab 3: Sentencing Tables
# ---------------------------------------------------------------------------

def sentencing_tab():
    st.header("Sentencing Tables")
    data = _load(SENTENCING_PATH)

    section = st.selectbox("Section", [
        "violation",
        "misdemeanor",
        "nonViolentFelony",
        "violentFelony",
        "dispositions",
        "financial",
        "collateral",
        "exceptions",
        "restitution",
        "hateCrimeBump",
    ])

    if section == "violation":
        _edit_violation(data)
    elif section == "misdemeanor":
        _edit_misdemeanor(data)
    elif section == "nonViolentFelony":
        _edit_nonviolent_felony(data)
    elif section == "violentFelony":
        _edit_violent_felony(data)
    elif section == "dispositions":
        _edit_dispositions(data)
    elif section == "financial":
        _edit_financial(data)
    elif section == "collateral":
        _edit_collateral(data)
    elif section == "exceptions":
        _edit_exceptions(data)
    elif section == "restitution":
        _edit_restitution(data)
    elif section == "hateCrimeBump":
        _edit_hatecrime_bump(data)

    if st.button("Save all changes", type="primary"):
        _save(SENTENCING_PATH, data)
        st.success("Saved to data/sentencing_tables.json")


def _edit_violation(data):
    st.subheader("Violation")
    viol = data.get("violation", {})
    row = viol.get("allOffenders", {})
    col1, col2 = st.columns(2)
    with col1:
        row["maxImprisonmentDays"] = st.number_input("Max imprisonment (days)", value=row.get("maxImprisonmentDays", 15))
        row["fineMax"] = st.number_input("Fine max ($)", value=row.get("fineMax", 250))
    with col2:
        row["probationEligible"] = st.checkbox("Probation eligible", value=row.get("probationEligible", False))
    viol["allOffenders"] = row
    data["violation"] = viol


def _edit_misdemeanor(data):
    st.subheader("Misdemeanor")
    misd = data.get("misdemeanor", {})
    for cls_key in ["ClassB", "ClassA"]:
        if cls_key not in misd:
            continue
        st.markdown(f"**{cls_key}**")
        row = misd[cls_key].get("firstOffender", {})
        row["maxTermMonths"] = st.number_input(f"{cls_key} — max term (months)", value=row.get("maxTermMonths", 3))
        if "probationEligibleYears" in row:
            row["probationEligibleYears"] = st.number_input(f"{cls_key} — probation eligible (years)", value=row.get("probationEligibleYears", 3))
        misd[cls_key]["firstOffender"] = row
    data["misdemeanor"] = misd


def _edit_nonviolent_felony(data):
    st.subheader("Non-Violent Felony")
    nvf = data.get("nonViolentFelony", {})
    statuses = nvf.get("statuses", {})

    status = st.selectbox("Offender status", list(statuses), format_func=lambda k: statuses[k].get("label", k))
    if status:
        status_data = statuses[status]["rows"]
        if status == "persistent_felony_offender_70_10":
            st.info("Discretionary — court MAY sentence as Class A-I.")
            ac = status_data.get("allClasses", {})
            ac["possibleMinYears"] = [
                st.number_input("Possible min years (lower)", value=ac.get("possibleMinYears", [15, 25])[0]),
                st.number_input("Possible min years (upper)", value=ac.get("possibleMinYears", [15, 25])[1]),
            ]
            status_data["allClasses"] = ac
        else:
            for cls in ["ClassE", "ClassD", "ClassC", "ClassB"]:
                if cls not in status_data:
                    continue
                row = status_data[cls]
                st.markdown(f"**{cls}**")
                col1, col2 = st.columns(2)
                with col1:
                    years = row.get("maxTermYears", [3, 4])
                    row["maxTermYears"] = [
                        st.number_input(f"{cls} — max term floor (years)", value=years[0], key=f"nvf_{status}_{cls}_lo"),
                        st.number_input(f"{cls} — max term cap (years)", value=years[1], key=f"nvf_{status}_{cls}_hi"),
                    ]
                with col2:
                    row["altDefiniteMax1yr"] = st.checkbox(f"{cls} — alt definite max 1yr", value=row.get("altDefiniteMax1yr", False))
                    row["probationEligibleYears"] = st.number_input(f"{cls} — probation (years)", value=row.get("probationEligibleYears", 5))
                with st.expander(f"{cls} — minimum period rule", expanded=False):
                    floor_val = row.get("minPeriodFloor")
                    floor_str = st.text_input(
                        f"{cls} — min period floor",
                        value=str(floor_val) if floor_val is not None else "",
                        placeholder="1 (number) or max/2 (formula)",
                        key=f"nvf_{status}_{cls}_mpf",
                    )
                    ceiling_val = row.get("minPeriodCeiling")
                    ceiling_str = st.text_input(
                        f"{cls} — min period ceiling",
                        value=str(ceiling_val) if ceiling_val is not None else "",
                        placeholder="max/3 (formula) or empty",
                        key=f"nvf_{status}_{cls}_mpc",
                    )
                    row["minPeriodFloor"] = floor_str.strip() if floor_str.strip() else None
                    row["minPeriodCeiling"] = ceiling_str.strip() if ceiling_str.strip() else None
                    row["minPeriodRef"] = st.text_input(
                        f"{cls} — min period statute ref",
                        value=row.get("minPeriodRef", ""),
                        placeholder="PL 70.00(3)(b)",
                        key=f"nvf_{status}_{cls}_mpr",
                    )
                    row["maxTermRef"] = st.text_input(
                        f"{cls} — max term statute ref",
                        value=row.get("maxTermRef", ""),
                        placeholder="PL 70.00(2)(e)",
                        key=f"nvf_{status}_{cls}_mtr",
                    )
                    row.pop("minTermRule", None)
        statuses[status]["rows"] = status_data
    data["nonViolentFelony"] = nvf


def _edit_violent_felony(data):
    st.subheader("Violent Felony")
    vf = data.get("violentFelony", {})
    statuses = vf.get("statuses", {})

    status = st.selectbox("Offender status", list(statuses), format_func=lambda k: statuses[k].get("label", k))
    if status:
        block = statuses[status]
        if status == "persistent_violent_felony_offender_70_08":
            st.warning("70.08 has pre-sunset and post-sunset versions.")
            version = st.selectbox("Version", list(block.get("versions", {})))
            ver_data = block["versions"].get(version, {})
            for cls in ["ClassA_II", "ClassB", "ClassC", "ClassD"]:
                if cls not in ver_data:
                    continue
                row = ver_data[cls]
                st.markdown(f"**{cls}**")
                if isinstance(row.get("minYears"), list):
                    mys = row["minYears"]
                    row["minYears"] = [
                        st.number_input(f"{cls} — min years (lower)", value=mys[0], key=f"vf_{version}_{cls}_lo"),
                        st.number_input(f"{cls} — min years (upper)", value=mys[1], key=f"vf_{version}_{cls}_hi"),
                    ]
                else:
                    row["minYearsFixed"] = st.number_input(f"{cls} — min years (fixed)", value=row.get("minYearsFixed", 25))
            block["versions"][version] = ver_data
        else:
            status_data = block["rows"]
            for cls in ["ClassB", "ClassC", "ClassD", "ClassE"]:
                if cls not in status_data:
                    continue
                row = status_data[cls]
                st.markdown(f"**{cls}**")
                col1, col2 = st.columns(2)
                with col1:
                    years = row.get("termYears", [2, 7])
                    row["termYears"] = [
                        st.number_input(f"{cls} — term (lower)", value=years[0], key=f"vf_{status}_{cls}_lo"),
                        st.number_input(f"{cls} — term (upper)", value=years[1], key=f"vf_{status}_{cls}_hi"),
                    ]
                with col2:
                    prs = row.get("prsYears", [1.5, 3])
                    row["prsYears"] = [
                        st.number_input(f"{cls} — PRS (lower)", value=prs[0], key=f"vf_{status}_{cls}_prs_lo"),
                        st.number_input(f"{cls} — PRS (upper)", value=prs[1], key=f"vf_{status}_{cls}_prs_hi"),
                    ]
                row["wholeOrHalfYears"] = st.checkbox(f"{cls} — whole or half years", value=row.get("wholeOrHalfYears", True))
    data["violentFelony"] = vf


def _edit_dispositions(data):
    st.subheader("Dispositions (alternative sentencing options)")
    disp = data.get("dispositions", {})
    level = st.selectbox("Level", ["felony", "misdemeanor", "violation"])
    level_data = disp.get(level, {})

    if level == "felony":
        for dtype in ["definiteSentence", "intermittentImprisonment", "splitSentence", "probation", "conditionalDischarge", "unconditionalDischarge"]:
            if dtype not in level_data:
                continue
            row = level_data[dtype]
            st.markdown(f"**{dtype}**")
            if "maxMonths" in row:
                row["maxMonths"] = st.number_input("Max months", value=row["maxMonths"])
            if "probationYears" in row:
                row["probationYears"] = [st.number_input("Probation years (comma-separated shown as max)", value=row["probationYears"][-1])]
            if "conditionalDischargeYears" in row:
                row["conditionalDischargeYears"] = st.number_input("CD years", value=row["conditionalDischargeYears"])
            if "imprisonmentMaxMonths" in row:
                row["imprisonmentMaxMonths"] = st.number_input("Split imprisonment max months", value=row["imprisonmentMaxMonths"])
            if "intermittentMaxMonths" in row:
                row["intermittentMaxMonths"] = st.number_input("Split intermittent max months", value=row["intermittentMaxMonths"])
            row["eligible"] = st.checkbox("Eligible", value=row.get("eligible", True))
            row["statuteRef"] = st.text_input("Statute ref", value=row.get("statuteRef", ""))
            if "recordStatementRequired" in row:
                row["recordStatementRequired"] = st.checkbox("Record statement required", value=row.get("recordStatementRequired", False))
            st.markdown("---")
    elif level == "misdemeanor":
        sub = st.selectbox("Subclass", ["classA", "classB", "unclassified"])
        sub_data = level_data.get(sub, {})
        for dtype in ["definiteSentence", "intermittentImprisonment", "splitSentence", "probation", "conditionalDischarge", "unconditionalDischarge"]:
            if dtype not in sub_data:
                continue
            row = sub_data[dtype]
            st.markdown(f"**{dtype}**")
            if "maxMonths" in row:
                row["maxMonths"] = st.number_input("Max months", value=row["maxMonths"], key=f"misd_{dtype}_mm")
            row["eligible"] = st.checkbox("Eligible", value=row.get("eligible", True), key=f"misd_{dtype}_elig")
            row["statuteRef"] = st.text_input("Statute ref", value=row.get("statuteRef", ""), key=f"misd_{dtype}_ref")
            st.markdown("---")
    else:
        st.json(level_data)

    disp[level] = level_data
    data["dispositions"] = disp


def _edit_financial(data):
    st.subheader("Financial Obligations")
    fin = data.get("financial", {})
    level = st.selectbox("Level", ["felony", "misdemeanor", "violation"])
    level_data = fin.get(level, {})

    if level == "felony":
        st.markdown("**Fine**")
        fine = level_data.get("fine", {})
        fine["maxAmount"] = st.number_input("Fine max ($)", value=fine.get("maxAmount", 5000))
        fine["altDoubleGain"] = st.checkbox("Alt: double gain", value=fine.get("altDoubleGain", True))
        fine["canStandAlone"] = st.checkbox("Can stand alone", value=fine.get("canStandAlone", False))
        fine["statuteRef"] = st.text_input("Statute ref", value=fine.get("statuteRef", ""))
        level_data["fine"] = fine

        st.markdown("**Mandatory surcharge**")
        ms = level_data.get("mandatorySurcharge", {})
        ms["amount"] = st.number_input("Surcharge ($)", value=ms.get("amount", 300))
        ms["statuteRef"] = st.text_input("Statute ref", value=ms.get("statuteRef", ""))
        level_data["mandatorySurcharge"] = ms

        st.markdown("**Crime victim assistance fee**")
        cvaf = level_data.get("crimeVictimAssistanceFee", {})
        cvaf["amount"] = st.number_input("CVAF ($)", value=cvaf.get("amount", 25))
        cvaf["statuteRef"] = st.text_input("Statute ref", value=cvaf.get("statuteRef", ""))
        level_data["crimeVictimAssistanceFee"] = cvaf

        st.markdown("**DNA databank fee**")
        dna = level_data.get("dnaDatabankFee", {})
        dna["amount"] = st.number_input("DNA fee ($)", value=dna.get("amount", 50))
        dna["statuteRef"] = st.text_input("Statute ref", value=dna.get("statuteRef", ""))
        level_data["dnaDatabankFee"] = dna
    elif level == "misdemeanor":
        sub = st.selectbox("Subclass", ["classA", "classB", "unclassified"])
        sub_data = level_data.get(sub, {})
        st.markdown("**Fine**")
        fine = sub_data.get("fine", {})
        fine["maxAmount"] = st.number_input("Fine max ($)", value=fine.get("maxAmount", 1000))
        fine["altDoubleGain"] = st.checkbox("Alt: double gain", value=fine.get("altDoubleGain", True))
        fine["canStandAlone"] = st.checkbox("Can stand alone", value=fine.get("canStandAlone", True))
        fine["statuteRef"] = st.text_input("Statute ref", value=fine.get("statuteRef", ""))
        sub_data["fine"] = fine

        st.markdown("**Mandatory surcharge**")
        ms = sub_data.get("mandatorySurcharge", {})
        ms["amount"] = st.number_input("Surcharge ($)", value=ms.get("amount", 175))
        ms["statuteRef"] = st.text_input("Statute ref", value=ms.get("statuteRef", ""))
        sub_data["mandatorySurcharge"] = ms

        st.markdown("**Crime victim assistance fee**")
        cvaf = sub_data.get("crimeVictimAssistanceFee", {})
        cvaf["amount"] = st.number_input("CVAF ($)", value=cvaf.get("amount", 25))
        cvaf["statuteRef"] = st.text_input("Statute ref", value=cvaf.get("statuteRef", ""))
        sub_data["crimeVictimAssistanceFee"] = cvaf
        level_data[sub] = sub_data
    else:
        st.markdown("**Violation**")
        st.markdown("**Fine**")
        fine = level_data.get("fine", {})
        fine["maxAmount"] = st.number_input("Fine max ($)", value=fine.get("maxAmount", 250))
        fine["altDoubleGain"] = st.checkbox("Alt: double gain", value=fine.get("altDoubleGain", True))
        fine["canStandAlone"] = st.checkbox("Can stand alone", value=fine.get("canStandAlone", True))
        fine["statuteRef"] = st.text_input("Statute ref", value=fine.get("statuteRef", ""))
        level_data["fine"] = fine

        st.markdown("**Mandatory surcharge**")
        ms = level_data.get("mandatorySurcharge", {})
        ms["amount"] = st.number_input("Surcharge ($)", value=ms.get("amount", 75))
        ms["statuteRef"] = st.text_input("Statute ref", value=ms.get("statuteRef", ""))
        level_data["mandatorySurcharge"] = ms

        st.markdown("**Crime victim assistance fee**")
        cvaf = level_data.get("crimeVictimAssistanceFee", {})
        cvaf["amount"] = st.number_input("CVAF ($)", value=cvaf.get("amount", 25))
        cvaf["statuteRef"] = st.text_input("Statute ref", value=cvaf.get("statuteRef", ""))
        level_data["crimeVictimAssistanceFee"] = cvaf

    fin[level] = level_data
    data["financial"] = fin


def _edit_collateral(data):
    st.subheader("Collateral Requirements")
    collat = data.get("collateral", {})
    level = st.selectbox("Level", ["felony", "misdemeanor", "violation"])
    level_data = collat.get(level, {})
    dna = level_data.get("dnaSampleRequired", {})
    dna["required"] = st.checkbox("DNA sample required", value=dna.get("required", False))
    dna["statuteRef"] = st.text_input("Statute ref", value=dna.get("statuteRef", "Exec Law 995-c(3)"))
    if "note" in dna:
        st.caption(f"Note: {dna['note']}")
    level_data["dnaSampleRequired"] = dna
    collat[level] = level_data
    data["collateral"] = collat


def _edit_exceptions(data):
    st.subheader("Exception Paths")
    exc = data.get("exceptions", {})
    for key in ["armedFelonyOverride", "domesticViolenceIndeterminate", "dwiSplitSentenceVariant"]:
        if key not in exc:
            continue
        row = exc[key]
        st.markdown(f"**{key}**")
        row["statuteRef"] = st.text_input("Statute ref", value=row.get("statuteRef", ""))
        row["description"] = st.text_area("Description", value=row.get("description", ""))
        if "maxTermYears" in row:
            row["maxTermYears"] = [
                st.number_input("Max term (lower)", value=row["maxTermYears"][0], key=f"exc_{key}_lo"),
                st.number_input("Max term (upper)", value=row["maxTermYears"][1], key=f"exc_{key}_hi"),
            ]
        if "recordStatementRequired" in row:
            row["recordStatementRequired"] = st.checkbox("Record statement required", value=row.get("recordStatementRequired", False))
        exc[key] = row
        st.markdown("---")
    data["exceptions"] = exc


def _edit_restitution(data):
    st.subheader("Restitution")
    rest = data.get("restitution", {})
    rest["statuteRef"] = st.text_input("Statute ref", value=rest.get("statuteRef", "PL 60.27(1); CPL 420.10(8)"))
    rest["considerationRequired"] = st.checkbox("Consideration required", value=rest.get("considerationRequired", True))
    rest["collectionSurchargePercent"] = st.number_input("Collection surcharge (%)", value=rest.get("collectionSurchargePercent", 5))
    rest["additionalSurchargeMaxPercent"] = st.number_input("Additional surcharge max (%)", value=rest.get("additionalSurchargeMaxPercent", 10))
    rest["description"] = st.text_area("Description", value=rest.get("description", ""))
    data["restitution"] = rest


def _edit_hatecrime_bump(data):
    st.subheader("Hate Crime Bump (PL 485.10)")
    hcb = data.get("hateCrimeBump", {})
    st.markdown("**Misdemeanor or Class C/D/E**")
    mcde = hcb.get("misdemeanorOrClassCDE", {})
    mcde["effect"] = st.text_input("Effect", value=mcde.get("effect", "one category higher than base offense classification"))
    mcde["isSimpleBump"] = st.checkbox("Is simple bump", value=mcde.get("isSimpleBump", True))
    hcb["misdemeanorOrClassCDE"] = mcde

    st.markdown("**Class B**")
    cb = hcb.get("ClassB", {})
    cb["effect"] = st.text_input("Class B effect", value=cb.get("effect", ""))
    cb["isSimpleBump"] = st.checkbox("Class B — simple bump", value=cb.get("isSimpleBump", False))
    cb["requiresPredicateStatus"] = st.checkbox("Class B — requires predicate status", value=cb.get("requiresPredicateStatus", True))
    hcb["ClassB"] = cb

    st.markdown("**Class A-I**")
    cai = hcb.get("ClassA_I", {})
    cai["effect"] = st.text_input("Class A-I effect", value=cai.get("effect", ""))
    cai["isSimpleBump"] = st.checkbox("Class A-I — simple bump", value=cai.get("isSimpleBump", False))
    hcb["ClassA_I"] = cai
    data["hateCrimeBump"] = hcb


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="CrimeTime", page_icon="⚖️", layout="wide")
    st.title("CrimeTime — Data Entry")
    st.caption("Edit reference data through forms. Changes write back to data/*.json")

    tab1, tab2, tab3 = st.tabs(["Offenses", "Lists", "Sentencing Tables"])

    with tab1:
        offenses_tab()
    with tab2:
        lists_tab()
    with tab3:
        sentencing_tab()


if __name__ == "__main__":
    main()
