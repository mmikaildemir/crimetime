"""The sentencing decision engine.

resolve(offense, case_facts) -> SentencingOutput

This is the main entry point. Given an offense (by section) and the case
facts, it produces a structured sentencing output covering all 21 output
types from the reference example.
"""

from __future__ import annotations

from typing import Optional

from . import reference
from .exceptions import generate_all_exceptions
from .financial import generate_all_financial, generate_collateral_requirements
from .models import (
    CaseFacts,
    CollateralRequirement,
    Disposition,
    DispositionType,
    ModifierApplied,
    PostReleaseSupervision,
    PriorRecordStatus,
    SentencingOutput,
    TermRange,
    TermUnit,
)
from .resolvers import (
    is_felony,
    is_hatecrime_eligible,
    is_misdemeanor,
    is_smf_eligible,
    is_violation,
    is_vfo,
    resolve_attempt_classification,
    resolve_vfo_of_attempt,
)


# ---------------------------------------------------------------------------
# Prior-record-status key mapping
# ---------------------------------------------------------------------------

_STATUS_TABLE_KEY_NONVFO = {
    PriorRecordStatus.FIRST_OFFENDER: "firstOffender",
    PriorRecordStatus.SECOND_FELONY_OFFENDER_70_06: "secondFelonyOffender_70_06",
    PriorRecordStatus.PERSISTENT_FELONY_OFFENDER_70_10: "persistentFelonyOffender_70_10",
}

_STATUS_TABLE_KEY_VFO = {
    PriorRecordStatus.FIRST_OFFENDER: "firstVFOffender_70_02",
    PriorRecordStatus.SECOND_VIOLENT_FELONY_OFFENDER_70_04: "secondViolentFelonyOffender_70_04",
    PriorRecordStatus.PERSISTENT_VIOLENT_FELONY_OFFENDER_70_08: "persistentViolentFelonyOffender_70_08",
}

_CLASS_KEY_MAP = {
    "ClassA_I_Felony": "ClassA_I",
    "ClassA_II_Felony": "ClassA_II",
    "ClassB_Felony": "ClassB",
    "ClassC_Felony": "ClassC",
    "ClassD_Felony": "ClassD",
    "ClassE_Felony": "ClassE",
    # Violent variants map to same class letter
    "ClassB_Violent_Felony": "ClassB",
    "ClassC_Violent_Felony": "ClassC",
    "ClassD_Violent_Felony": "ClassD",
    "ClassE_Violent_Felony": "ClassE",
}


def _class_key(classification: str) -> str:
    """Map a classification to its sentencing-table class key (e.g. 'ClassD')."""
    return _CLASS_KEY_MAP.get(classification, classification)


# ---------------------------------------------------------------------------
# Primary disposition (determinate / indeterminate / definite)
# ---------------------------------------------------------------------------


def _resolve_primary_felony_disposition(
    classification: str,
    section: str,
    vfo: bool,
    prior_status: PriorRecordStatus,
) -> tuple[Disposition, Optional[PostReleaseSupervision]]:
    """Resolve the primary disposition for a felony offense.

    VFOs get determinate sentences (PL 70.02 / 70.04 / 70.08).
    Non-VFOs get indeterminate sentences (PL 70.00 / 70.06 / 70.10).
    """
    cls_key = _class_key(classification)

    if vfo:
        tables = reference.get_violent_felony_table()
        status_key = _STATUS_TABLE_KEY_VFO[prior_status]

        # 70.02 and 70.04 use "termYears" (determinate); 70.08 uses indeterminate
        if status_key in ("firstVFOffender_70_02", "secondViolentFelonyOffender_70_04"):
            status_table = tables[status_key]
            row = status_table.get(cls_key)
            if row is None:
                raise ValueError(
                    f"No {status_key} table entry for {cls_key} "
                    f"(section {section}, classification {classification})"
                )
            term = row["termYears"]
            disp = Disposition(
                type=DispositionType.DETERMINATE,
                label=f"Determinate sentence of {term[0]}–{term[1]} years",
                statute_refs=[f"PL 70.0{'2' if status_key == 'firstVFOffender_70_02' else '4'}(3)"],
                term=TermRange(min_value=term[0], max_value=term[1]),
            )
            prs = None
            if "prsYears" in row:
                prs = PostReleaseSupervision(
                    min_years=row["prsYears"][0],
                    max_years=row["prsYears"][1],
                    statute_refs=["PL 70.00(6), 70.45(2)"],
                )
            return disp, prs

        elif status_key == "persistentViolentFelonyOffender_70_08":
            # 70.08 is indeterminate — handled differently
            # For now, route through the 70.08 table
            pvo = tables.get("persistentViolentFelonyOffender_70_08", {})
            pre_sunset = pvo.get("preSunset_until_2027_09_01", {})
            row = pre_sunset.get(cls_key)
            if row is None:
                raise ValueError(
                    f"No 70.08 table entry for {cls_key} (section {section})"
                )
            disp = Disposition(
                type=DispositionType.INDETERMINATE,
                label=f"Indeterminate sentence — {row.get('minYears', 'life')} to life",
                statute_refs=["PL 70.08(2), 70.08(3)"],
                term=TermRange(
                    min_value=row.get("minYears", [20, 25])[0] if isinstance(row.get("minYears"), list) else row.get("minYearsFixed", 20),
                    max_value=999,
                ),
            )
            return disp, None

    else:
        # Non-violent felony — indeterminate per PL 70.00 / 70.06 / 70.10
        tables = reference.get_nonviolent_felony_table()
        status_key = _STATUS_TABLE_KEY_NONVFO[prior_status]

        # Map persistent felony offender to the persistent table
        if status_key == "persistentFelonyOffender_70_10":
            pfo = tables.get("persistentFelonyOffender_70_10", {})
            all_classes = pfo.get("allClasses", {})
            disp = Disposition(
                type=DispositionType.INDETERMINATE,
                label="Indeterminate sentence — court MAY sentence as Class A-I (discretionary)",
                statute_refs=["PL 70.10"],
                term=TermRange(
                    min_value=all_classes.get("possibleMinYears", [15, 25])[0],
                    max_value=999,
                ),
                conditions="Discretionary — requires separate judicial finding, not automatic from 2 priors alone",
            )
            return disp, None

        status_table = tables.get(status_key, {})
        row = status_table.get(cls_key)
        if row is None:
            raise ValueError(
                f"No {status_key} table entry for {cls_key} "
                f"(section {section}, classification {classification})"
            )

        max_years = row["maxTermYears"]
        statute = "PL 70.00(3)" if status_key == "firstOffender" else "PL 70.06"
        if max_years == "life":
            min_period = row.get("minYears", [15, 25])
            disp = Disposition(
                type=DispositionType.INDETERMINATE,
                label=f"Indeterminate sentence — {min_period[0]}–{min_period[1]} years to life",
                statute_refs=[statute],
                term=TermRange(min_value=min_period[0], max_value=999),
                conditions=row.get("minTermRule"),
            )
        else:
            disp = Disposition(
                type=DispositionType.INDETERMINATE,
                label=f"Indeterminate sentence — {max_years[0]}–{max_years[1]} years max",
                statute_refs=[statute],
                term=TermRange(min_value=max_years[0], max_value=max_years[1]),
                conditions=row.get("minTermRule"),
            )
        return disp, None

    raise ValueError(f"Could not resolve primary disposition for {section}")


def _resolve_primary_misdemeanor_disposition(
    classification: str,
) -> Disposition:
    """Resolve the primary disposition for a misdemeanor."""
    tables = reference.get_misdemeanor_table()
    if classification == "ClassA_Misdemeanor":
        row = tables.get("ClassA", {})
        return Disposition(
            type=DispositionType.DEFINITE,
            label=f"Definite sentence up to {row.get('firstOffender', {}).get('maxTermMonths', 12)} months",
            statute_refs=["PL 70.15(1)"],
            term=TermRange(
                min_value=0,
                max_value=row.get("firstOffender", {}).get("maxTermMonths", 12),
                unit=TermUnit.MONTHS,
            ),
        )
    elif classification == "ClassB_Misdemeanor":
        row = tables.get("ClassB", {})
        return Disposition(
            type=DispositionType.DEFINITE,
            label=f"Definite sentence up to {row.get('firstOffender', {}).get('maxTermMonths', 3)} months",
            statute_refs=["PL 70.15(2)"],
            term=TermRange(
                min_value=0,
                max_value=row.get("firstOffender", {}).get("maxTermMonths", 3),
                unit=TermUnit.MONTHS,
            ),
        )
    else:
        return Disposition(
            type=DispositionType.DEFINITE,
            label="Definite sentence as provided in the law creating the offense (max 1 year)",
            statute_refs=["PL 70.15(3)"],
            term=TermRange(min_value=0, max_value=12, unit=TermUnit.MONTHS),
        )


def _resolve_primary_violation_disposition() -> Disposition:
    """Resolve the primary disposition for a violation."""
    row = reference.get_violation_table().get("allOffenders", {})
    return Disposition(
        type=DispositionType.DEFINITE,
        label=f"Definite sentence up to {row.get('maxImprisonmentDays', 15)} days",
        statute_refs=["PL 70.15(4)"],
        term=TermRange(
            min_value=0,
            max_value=row.get("maxImprisonmentDays", 15),
            unit=TermUnit.DAYS,
        ),
    )


# ---------------------------------------------------------------------------
# Alternative dispositions from the dispositions table
# ---------------------------------------------------------------------------


def _generate_felony_alternatives(
    classification: str,
    is_vfo: bool,
    case_facts: CaseFacts,
) -> list[Disposition]:
    """Generate alternative dispositions for a felony from the dispositions table."""
    disp_table = reference.get_dispositions_table()
    fel = disp_table.get("felony", {})
    alternatives: list[Disposition] = []

    # Definite sentence (PL 70.00(4)) — available for all felonies
    definite = fel.get("definiteSentence", {})
    if definite.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.DEFINITE,
                label=f"Definite sentence up to {definite['maxMonths']} months",
                statute_refs=[definite["statuteRef"]],
                term=TermRange(
                    min_value=0, max_value=definite["maxMonths"], unit=TermUnit.MONTHS
                ),
                conditions=definite.get("conditions"),
            )
        )

    # Intermittent imprisonment (PL 85.00)
    intermittent = fel.get("intermittentImprisonment", {})
    if intermittent.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.INTERMITTENT,
                label="Intermittent imprisonment for any term that could be imposed as a definite sentence",
                statute_refs=[intermittent["statuteRef"]],
                conditions=intermittent.get("conditions"),
            )
        )

    # Split sentence (PL 60.01(2)(d))
    split = fel.get("splitSentence", {})
    if split.get("eligible"):
        imprisonment_months = split["imprisonmentMaxMonths"]
        if case_facts.is_dwi:
            imprisonment_months = split.get("dwiImprisonmentMaxMonths", 12)
        alternatives.append(
            Disposition(
                type=DispositionType.SPLIT,
                label=f"Split sentence — imprisonment up to {imprisonment_months} months + probation or conditional discharge",
                statute_refs=[split["statuteRef"]],
                split_imprisonment_max_months=imprisonment_months,
                split_intermittent_max_months=split.get("intermittentMaxMonths"),
                probation_years=split.get("probationYears", [3, 4, 5]),
                conditional_discharge_years=split.get("conditionalDischargeYears"),
            )
        )

    # Probation (PL 65.00)
    probation = fel.get("probation", {})
    if probation.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.PROBATION,
                label=f"Probation for {', '.join(str(y) for y in probation['years'])} years",
                statute_refs=[probation["statuteRef"]],
                probation_years=probation["years"],  # full list of options
                conditions=probation.get("conditions"),
            )
        )

    # Conditional Discharge (PL 65.05)
    cd = fel.get("conditionalDischarge", {})
    if cd.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.CONDITIONAL_DISCHARGE,
                label=f"Conditional discharge for {cd['years']} years",
                statute_refs=[cd["statuteRef"]],
                conditional_discharge_years=cd["years"],
                record_statement_required=cd.get("recordStatementRequired", False),
                conditions=cd.get("conditions"),
            )
        )

    # Unconditional Discharge (PL 65.20)
    ud = fel.get("unconditionalDischarge", {})
    if ud.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.UNCONDITIONAL_DISCHARGE,
                label="Unconditional discharge",
                statute_refs=[ud["statuteRef"]],
                record_statement_required=ud.get("recordStatementRequired", False),
                conditions=ud.get("conditions"),
            )
        )

    return alternatives


def _generate_misdemeanor_alternatives(
    classification: str,
    case_facts: CaseFacts,
) -> list[Disposition]:
    """Generate alternative dispositions for a misdemeanor."""
    disp_table = reference.get_dispositions_table()
    misd = disp_table.get("misdemeanor", {})

    # Pick the subclass
    if classification == "ClassA_Misdemeanor":
        sub = misd.get("classA", {})
    elif classification == "ClassB_Misdemeanor":
        sub = misd.get("classB", {})
    else:
        sub = misd.get("unclassified", {})

    alternatives: list[Disposition] = []

    # Intermittent
    intermittent = sub.get("intermittentImprisonment", {})
    if intermittent.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.INTERMITTENT,
                label="Intermittent imprisonment for any term that could be imposed as a definite sentence",
                statute_refs=[intermittent.get("statuteRef", "PL 85.00")],
                conditions=intermittent.get("conditions"),
            )
        )

    # Split sentence
    split = sub.get("splitSentence", {})
    if split.get("eligible"):
        imprisonment_months = split["imprisonmentMaxMonths"]
        if case_facts.is_dwi:
            imprisonment_months = split.get("dwiImprisonmentMaxMonths", 12)
        alternatives.append(
            Disposition(
                type=DispositionType.SPLIT,
                label=f"Split sentence — imprisonment up to {imprisonment_months} months + probation or conditional discharge",
                statute_refs=[split["statuteRef"]],
                split_imprisonment_max_months=imprisonment_months,
                probation_years=split.get("probationYears", [3]),
                conditional_discharge_years=split.get("conditionalDischargeYears"),
            )
        )

    # Probation
    probation = sub.get("probation", {})
    if probation.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.PROBATION,
                label=f"Probation for {', '.join(str(y) for y in probation['years'])} years",
                statute_refs=[probation["statuteRef"]],
                probation_years=probation["years"],
                conditions=probation.get("conditions"),
            )
        )

    # Conditional Discharge
    cd = sub.get("conditionalDischarge", {})
    if cd.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.CONDITIONAL_DISCHARGE,
                label=f"Conditional discharge for {cd['years']} years",
                statute_refs=[cd["statuteRef"]],
                conditional_discharge_years=cd["years"],
                record_statement_required=cd.get("recordStatementRequired", False),
                conditions=cd.get("conditions"),
            )
        )

    # Unconditional Discharge
    ud = sub.get("unconditionalDischarge", {})
    if ud.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.UNCONDITIONAL_DISCHARGE,
                label="Unconditional discharge",
                statute_refs=[ud.get("statuteRef", "PL 65.20(1)")],
                record_statement_required=ud.get("recordStatementRequired", False),
                conditions=ud.get("conditions"),
            )
        )

    return alternatives


def _generate_violation_alternatives() -> list[Disposition]:
    """Generate alternative dispositions for a violation."""
    disp_table = reference.get_dispositions_table()
    viol = disp_table.get("violation", {})
    alternatives: list[Disposition] = []

    cd = viol.get("conditionalDischarge", {})
    if cd.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.CONDITIONAL_DISCHARGE,
                label=f"Conditional discharge for {cd['years']} year(s)",
                statute_refs=[cd["statuteRef"]],
                conditional_discharge_years=cd["years"],
            )
        )

    ud = viol.get("unconditionalDischarge", {})
    if ud.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.UNCONDITIONAL_DISCHARGE,
                label="Unconditional discharge",
                statute_refs=[ud.get("statuteRef", "PL 65.20(1)")],
            )
        )

    return alternatives


# ---------------------------------------------------------------------------
# Conditional classification resolver (offense-intrinsic escalation)
# ---------------------------------------------------------------------------


def _resolve_conditional_classification(
    conditional: dict, case_facts: CaseFacts
) -> str:
    """Resolve conditional classification rules from an offense's conditionalClassification block.

    Supports conditions: "in" (field value in list), "true" (field is truthy), "gt" (field > value)
    Falls back to conditional["fallback"] if no rule matches.
    """
    for rule in conditional.get("rules", []):
        field_name = rule["field"]
        condition = rule.get("condition", "in")
        field_value = getattr(case_facts, field_name, None)

        if condition == "in":
            if field_value in rule.get("values", []):
                return rule["resulting_classification"]
        elif condition == "true":
            if field_value:
                return rule["resulting_classification"]
        elif condition == "gt":
            threshold = rule.get("values", [0])[0]
            if field_value is not None and field_value > threshold:
                return rule["resulting_classification"]

    return conditional.get("fallback", "Violation")


# ---------------------------------------------------------------------------
# Modifier bumps: SMF (§130.91), hate crime (§485.10), terrorism (§490.25)
# ---------------------------------------------------------------------------
# Applied in order: SMF → hate crime → terrorism. Each modifier sees the
# classification resulting from the previous one. Each returns a tuple:
#   (new_classification, vfo_override, branch, applied)
# vfo_override: None = keep existing vfo; True/False = set vfo to this value.

# --- Hate crime upgrade ladder (§485.10(2)) ---
# One-tier escalation for misdemeanors and Class C/D/E felonies. Violent
# variants stay violent; non-violent stay non-violent. VFO status is
# re-derived via is_vfo() after the bump (statute does not "deem" non-VFO
# hate crimes as VFOs — only already-VFO underlying offenses per §485.10(1)).
_HATECRIME_UPGRADE_TABLE = {
    "ClassA_Misdemeanor": "ClassE_Felony",
    "ClassB_Misdemeanor": "ClassA_Misdemeanor",
    "Unclassified_Misdemeanor": "ClassA_Misdemeanor",
    "ClassE_Felony": "ClassD_Felony",
    "ClassD_Felony": "ClassC_Felony",
    "ClassC_Felony": "ClassB_Felony",
    "ClassE_Violent_Felony": "ClassD_Violent_Felony",
    "ClassD_Violent_Felony": "ClassC_Violent_Felony",
    "ClassC_Violent_Felony": "ClassB_Violent_Felony",
}

_SIMPLE_BUMP_CLASSIFICATIONS = set(_HATECRIME_UPGRADE_TABLE.keys())

# --- SMF violent redesignation (§130.91) ---
# Maps non-violent felony classes to their violent variants. No tier shift —
# only redesignates as a violent felony, routing through VFO tables.
# NOTE: statutory basis for "violent redesignation" not explicit in §130.91
# text itself; derived from DB classification_resolution (unverified —
# flagged for legal review per TODO.md).
_SMF_VIOLENT_REDESIGNATION = {
    "ClassB_Felony": "ClassB_Violent_Felony",
    "ClassC_Felony": "ClassC_Violent_Felony",
    "ClassD_Felony": "ClassD_Violent_Felony",
    "ClassE_Felony": "ClassE_Violent_Felony",
}

# --- Terrorism upgrade ladder (§490.25(2)(b)) ---
# Same one-tier escalation as hate crime, but terrorism explicitly "deems"
# the offense a VFO per §490.25(2)(a). So vfo is always set to True for
# C/D/E bumped felonies.
_TERRORISM_UPGRADE_TABLE = {
    "ClassE_Felony": "ClassD_Violent_Felony",
    "ClassD_Felony": "ClassC_Violent_Felony",
    "ClassC_Felony": "ClassB_Violent_Felony",
    "ClassE_Violent_Felony": "ClassD_Violent_Felony",
    "ClassD_Violent_Felony": "ClassC_Violent_Felony",
    "ClassC_Violent_Felony": "ClassB_Violent_Felony",
}


def _apply_smf_bump(
    classification: str,
    section: str,
    case_facts: CaseFacts,
) -> tuple[str, bool | None, str | None, bool]:
    """Apply the SMF bump (§130.91) — violent redesignation only, no tier shift.

    If the offense is SMF-eligible and sexually_motivated, a non-violent
    felony is redesignated to its violent variant (routes through VFO tables).
    Already-violent felonies are unchanged but the modifier is still recorded.
    """
    if not case_facts.sexually_motivated:
        return classification, None, None, False
    if not is_smf_eligible(section, classification):
        return classification, None, None, False

    if classification in _SMF_VIOLENT_REDESIGNATION:
        return _SMF_VIOLENT_REDESIGNATION[classification], True, "violent_redesignation", True
    if classification in ("ClassB_Violent_Felony", "ClassC_Violent_Felony",
                         "ClassD_Violent_Felony", "ClassE_Violent_Felony"):
        return classification, None, "violent_redesignation", True
    return classification, None, None, False


def _apply_hatecrime_bump(
    classification: str,
    section: str,
    case_facts: CaseFacts,
) -> tuple[str, bool | None, str | None, bool]:
    """Apply the hate crime bump (PL 485.10).

    Returns (new_classification, vfo_override, branch, applied).
    - Simple branch (misdemeanorOrClassCDE): one-tier upgrade, vfo re-derived.
    - ClassB branch: no reclassification, floors applied post-disposition.
    - ClassA_I branch: no reclassification, 20-year min applied post-disposition.
    """
    if not case_facts.hate_crime_motivated:
        return classification, None, None, False
    if not is_hatecrime_eligible(section):
        return classification, None, None, False

    if classification in _SIMPLE_BUMP_CLASSIFICATIONS:
        upgraded = _HATECRIME_UPGRADE_TABLE[classification]
        return upgraded, None, "misdemeanorOrClassCDE", True

    if classification in ("ClassB_Felony", "ClassB_Violent_Felony"):
        return classification, None, "ClassB", True

    if classification == "ClassA_I_Felony":
        return classification, None, "ClassA_I", True

    return classification, None, None, False


def _apply_terrorism_bump(
    classification: str,
    section: str,
    case_facts: CaseFacts,
) -> tuple[str, bool | None, str | None, bool]:
    """Apply the terrorism bump (PL 490.25).

    Returns (new_classification, vfo_override, branch, applied).
    - Class C/D/E felony: one tier higher + deemed VFO (vfo=True).
    - Class B felony: deemed Class A-I felony (sentenced per 70.00).
    - Class A-I felony: life without parole (no reclassification; disposition
      override handled post-computation — TODO).
    """
    if not case_facts.terrorism_motivated:
        return classification, None, None, False
    if not is_hatecrime_eligible(section):
        return classification, None, None, False
    if not is_felony(classification):
        return classification, None, None, False

    if classification in _TERRORISM_UPGRADE_TABLE:
        return _TERRORISM_UPGRADE_TABLE[classification], True, "ClassCDE", True

    if classification in ("ClassB_Felony", "ClassB_Violent_Felony"):
        return "ClassA_I_Felony", False, "ClassB_to_A_I", True

    if classification == "ClassA_I_Felony":
        return classification, None, "life_without_parole", True

    return classification, None, None, False


def _apply_hatecrime_floors(
    dispositions: list[Disposition],
    vfo: bool,
    prior_status: PriorRecordStatus,
    branch: str,
) -> None:
    """Apply hate crime minimum floors (§485.10(3)/(4)) to the primary
    disposition in-place. Called post-disposition when the ClassB or ClassA_I
    hate crime branch fired.
    """
    if not dispositions:
        return
    primary = dispositions[0]
    bump_table = reference.get_hatecrime_bump_table()

    if branch == "ClassB":
        floors = bump_table.get("ClassB", {}).get("floors", {})
        # Determine which sentencing statute applied based on vfo + prior status
        if vfo and prior_status == PriorRecordStatus.FIRST_OFFENDER:
            floor = floors.get("70.02", {})
            if "termMin" in floor and primary.term:
                primary.term = TermRange(
                    min_value=max(primary.term.min_value, floor["termMin"]),
                    max_value=primary.term.max_value,
                    unit=primary.term.unit,
                )
        elif vfo and prior_status == PriorRecordStatus.SECOND_VIOLENT_FELONY_OFFENDER_70_04:
            floor = floors.get("70.04", {})
            if "termMin" in floor and primary.term:
                primary.term = TermRange(
                    min_value=max(primary.term.min_value, floor["termMin"]),
                    max_value=primary.term.max_value,
                    unit=primary.term.unit,
                )
        elif not vfo and prior_status == PriorRecordStatus.FIRST_OFFENDER:
            floor = floors.get("70.00", {})
            if "maxTermMin" in floor and primary.term:
                primary.term = TermRange(
                    min_value=primary.term.min_value,
                    max_value=max(primary.term.max_value, floor["maxTermMin"]),
                    unit=primary.term.unit,
                )
        elif not vfo and prior_status == PriorRecordStatus.SECOND_FELONY_OFFENDER_70_06:
            floor = floors.get("70.06", {})
            if "maxTermMin" in floor and primary.term:
                primary.term = TermRange(
                    min_value=primary.term.min_value,
                    max_value=max(primary.term.max_value, floor["maxTermMin"]),
                    unit=primary.term.unit,
                )
        # 70.05 (juvenile) and 70.08 (persistent VFO) not yet handled — TODO

    elif branch == "ClassA_I":
        min_period = bump_table.get("ClassA_I", {}).get("minPeriod", 20)
        if primary.term:
            primary.term = TermRange(
                min_value=max(primary.term.min_value, min_period),
                max_value=primary.term.max_value,
                unit=primary.term.unit,
            )





# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def resolve(section: str, case_facts: CaseFacts) -> SentencingOutput:
    """Resolve the full sentencing output for an offense given case facts.

    Args:
        section: NYS Penal Law section number (e.g. '120.02')
        case_facts: CaseFacts instance with the case-specific parameters

    Returns:
        SentencingOutput with all available dispositions, exceptions,
        financial obligations, and collateral requirements.
    """
    offense = reference.get_offense(section)
    if offense is None:
        raise ValueError(f"Unknown offense section: {section}")

    classification = offense["classification"]
    offense_name = offense.get("name", section)

    # Handle attempts — resolve the effective classification
    if case_facts.is_attempt and case_facts.attempt_of_section:
        target_offense = reference.get_offense(case_facts.attempt_of_section)
        target_classification = (
            target_offense["classification"] if target_offense else "Unknown"
        )
        effective_classification = resolve_attempt_classification(
            case_facts.attempt_of_section,
            target_classification,
            case_facts.subdivision,
        )
        vfo, _ = resolve_vfo_of_attempt(
            case_facts.attempt_of_section, target_classification
        )
    else:
        effective_classification = classification
        vfo = is_vfo(section, effective_classification)

    # Handle conditional classification (offense-intrinsic escalation)
    # e.g. §130.86 luring a child: E→C/D based on intended offense class
    # e.g. §225.90 gaming manipulation: A misdemeanor→E felony if prior within 5 years
    conditional = offense.get("conditionalClassification")
    if conditional:
        effective_classification = _resolve_conditional_classification(
            conditional, case_facts
        )
        vfo = is_vfo(section, effective_classification)

    # Apply modifier bumps in order: SMF → hate crime → terrorism.
    # Each modifier sees the classification resulting from the previous one.
    base_classification = effective_classification
    modifiers_applied: list[ModifierApplied] = []
    any_modifier_fired = False

    for mod_type, bump_fn in (
        ("sexually_motivated_felony", _apply_smf_bump),
        ("hate_crime", _apply_hatecrime_bump),
        ("terrorism", _apply_terrorism_bump),
    ):
        pre_class = effective_classification
        effective_classification, vfo_override, branch, applied = bump_fn(
            effective_classification, section, case_facts
        )
        if applied:
            any_modifier_fired = True
            if vfo_override is not None:
                vfo = vfo_override
            elif branch == "misdemeanorOrClassCDE":
                vfo = is_vfo(section, effective_classification)
            modifiers_applied.append(ModifierApplied(
                modifier_type=mod_type,
                branch=branch,
                base_classification=pre_class,
                resulting_classification=effective_classification,
            ))

    if not any_modifier_fired:
        base_classification = None

    # Primary disposition + PRS
    dispositions: list[Disposition] = []

    if is_felony(effective_classification):
        primary, prs = _resolve_primary_felony_disposition(
            effective_classification, section, vfo, case_facts.prior_record_status
        )
        if prs:
            primary.prs = prs
        dispositions.append(primary)

        # Add alternatives
        dispositions.extend(
            _generate_felony_alternatives(
                effective_classification, vfo, case_facts
            )
        )
    elif is_misdemeanor(effective_classification):
        primary = _resolve_primary_misdemeanor_disposition(effective_classification)
        dispositions.append(primary)
        dispositions.extend(
            _generate_misdemeanor_alternatives(effective_classification, case_facts)
        )
    elif is_violation(effective_classification):
        primary = _resolve_primary_violation_disposition()
        dispositions.append(primary)
        dispositions.extend(_generate_violation_alternatives())
    else:
        raise ValueError(f"Unknown classification: {effective_classification}")

    # Apply hate crime minimum floors (§485.10(3)/(4)) post-disposition
    for mod in modifiers_applied:
        if mod.modifier_type == "hate_crime" and mod.branch in ("ClassB", "ClassA_I"):
            _apply_hatecrime_floors(
                dispositions, vfo, case_facts.prior_record_status, mod.branch
            )

    # Exceptions
    exceptions = generate_all_exceptions(
        effective_classification, vfo, case_facts
    )

    # Financial obligations
    financial = generate_all_financial(
        effective_classification,
        victim_seeking_restitution=case_facts.victim_seeking_restitution,
    )

    # Collateral requirements (estimate jail term for surcharge summons)
    jail_term_days = None
    for d in dispositions:
        if d.term and d.term.unit == TermUnit.DAYS:
            jail_term_days = d.term.max_value
        elif d.term and d.term.unit == TermUnit.MONTHS:
            jail_term_days = d.term.max_value * 30
        elif d.term and d.term.unit == TermUnit.YEARS:
            jail_term_days = d.term.max_value * 365

    collateral = generate_collateral_requirements(
        effective_classification, jail_term_days=jail_term_days
    )

    return SentencingOutput(
        section=section,
        offense_name=offense_name,
        classification=effective_classification,
        is_vfo=vfo,
        available_dispositions=dispositions,
        exception_paths=exceptions,
        financial_obligations=financial,
        collateral_requirements=collateral,
        base_classification=base_classification,
        modifiers_applied=modifiers_applied,
    )
