"""Exception paths that can override or modify the primary sentencing disposition.

Covers outputs #3, #4, #5, #9 from the reference example:
  - Armed felony override (PL 70.02(4)(b))
  - Record statement requirement (when determinate not imposed)
  - Domestic violence indeterminate (PL 60.12) — class-specific determinate alternatives
  - DWI split sentence variant (PL 60.21)
  - For-hire vehicle enhancement judicial escape hatch (PL 60.07(1))
"""

from __future__ import annotations

from . import reference
from .models import Disposition, DispositionType, ExceptionPath, ExceptionType, TermRange, TermUnit
from .resolvers import is_felony, is_for_hire_eligible


# Offenses excluded from the DV alternative per PL 60.12(1)
_DV_EXCLUDED_SECTIONS = {
    "125.25",  # murder 2nd (subd 5 specifically, but section-level exclusion)
    "125.26",  # aggravated murder
    "125.27",  # murder 1st
    # Article 490 terrorism sections excluded
    "490.05", "490.10", "490.15", "490.20", "490.25", "490.30", "490.35",
    "490.37", "490.40", "490.45", "490.47", "490.50", "490.55",
}

# Class-specific determinate ranges for DV alternative per PL 60.12(2)
_DV_DETERMINATE_RANGES = {
    "ClassB_Felony": [1, 5],
    "ClassC_Felony": [1, 3.5],
    "ClassD_Felony": [1, 2],
    "ClassE_Felony": [1, 1.5],
    "ClassB_Violent_Felony": [1, 5],
    "ClassC_Violent_Felony": [1, 3.5],
    "ClassD_Violent_Felony": [1, 2],
    "ClassE_Violent_Felony": [1, 1.5],
}


def generate_armed_felony_exception(
    classification: str,
    plea_from_armed_felony_indictment: bool,
    mitigating_factor: bool = False,
    minor_participation: bool = False,
    proof_deficiencies: bool = False,
) -> ExceptionPath | None:
    """Generate the armed-felony override exception (PL 70.02(4)(b); CPL 1.20(41)).

    If the conviction resulted from a plea in satisfaction of an armed felony
    indictment, the court must impose a determinate sentence UNLESS one of three
    mitigating factors is found AND the court finds the alternate sentence is
    consistent with public safety and does not deprecate the seriousness of the crime.
    """
    if not plea_from_armed_felony_indictment:
        return None
    if not is_felony(classification):
        return None

    exc = reference.get_exceptions_table()["armedFelonyOverride"]

    factors_found = mitigating_factor or minor_participation or proof_deficiencies
    factor_labels = []
    if mitigating_factor:
        factor_labels.append("mitigating circumstances bearing directly on manner of commission")
    if minor_participation:
        factor_labels.append("defendant's participation was relatively minor")
    if proof_deficiencies:
        factor_labels.append("possible deficiencies in proof of armed felony")

    return ExceptionPath(
        type=ExceptionType.ARMED_FELONY_OVERRIDE,
        label="Armed felony exception — court may impose alternate sentence",
        description=exc["description"],
        statute_refs=[exc["statuteRef"]],
        triggering_factors=factor_labels if factors_found else [],
        resulting_disposition=None,  # the exception *allows* an alternate; doesn't define what
    )


def generate_record_statement_exception(
    determinate_imposed: bool,
) -> ExceptionPath | None:
    """Generate the record-statement requirement when a determinate sentence is not imposed."""
    if determinate_imposed:
        return None

    return ExceptionPath(
        type=ExceptionType.RECORD_STATEMENT_REQUIRED,
        label="Record statement required — court must state on record the facts and circumstances",
        description="If the court determines that a determinate sentence should not be imposed, it must make a statement on the record of the facts and circumstances upon which the determination is based.",
        statute_refs=["PL 70.02(4)(b)"],
        triggering_factors=[],
    )


def generate_domestic_violence_exception(
    classification: str,
    section: str,
    domestic_violence_by_victim: bool,
) -> list[ExceptionPath]:
    """Generate the domestic-violence alternative sentence exception (PL 60.12).

    Per 60.12(1): excludes §125.25, §125.26, §125.27, Article 490, and
    sex-offender-registration offenses. Per 60.12(2): court may impose any one
    of three alternatives — a class-specific determinate term (B 1-5, C 1-3.5,
    D 1-2, E 1-1.5), a definite sentence ≤1yr, or probation under PL 65.00.
    Each alternative is emitted as a sibling ExceptionPath so downstream
    consumers see all three as first-class structured dispositions.
    """
    if not domestic_violence_by_victim:
        return []
    if not is_felony(classification):
        return []
    if section in _DV_EXCLUDED_SECTIONS:
        return []

    exc = reference.get_exceptions_table()["domesticViolenceIndeterminate"]
    statute_ref = exc["statuteRef"]
    triggers = ["domestic_violence_by_victim"]
    eligibility = "Excludes 125.25/26/27, Art 490, sex registration offenses per 60.12(1)."

    # Class-specific determinate range per 60.12(2)
    det_range = _DV_DETERMINATE_RANGES.get(classification)
    if det_range is None:
        # Class A felonies (60.12(3)): 5-15yr determinate alternative
        if classification in ("ClassA_I_Felony", "ClassA_II_Felony"):
            det_range = [5, 15]
        else:
            return []

    # 60.12(2): three alternative dispositions of equal dignity.
    return [
        ExceptionPath(
            type=ExceptionType.DOMESTIC_VIOLENCE_INDETERMINATE,
            label="Domestic violence exception — alternative determinate sentence",
            description=exc["description"],
            statute_refs=[statute_ref],
            triggering_factors=triggers,
            resulting_disposition=Disposition(
                type=DispositionType.DETERMINATE,
                label=f"Determinate sentence of {det_range[0]}–{det_range[1]} years (DV alternative per 60.12(2))",
                statute_refs=[statute_ref],
                term=TermRange(min_value=det_range[0], max_value=det_range[1], unit=TermUnit.YEARS),
                conditions=eligibility,
            ),
        ),
        ExceptionPath(
            type=ExceptionType.DOMESTIC_VIOLENCE_INDETERMINATE,
            label="Domestic violence exception — alternative definite sentence",
            description=exc["description"],
            statute_refs=[statute_ref],
            triggering_factors=triggers,
            resulting_disposition=Disposition(
                type=DispositionType.DEFINITE,
                label="Definite sentence of one year or less (DV alternative per 60.12(2))",
                statute_refs=[statute_ref],
                term=TermRange(min_value=0, max_value=1, unit=TermUnit.YEARS),
                conditions=eligibility,
            ),
        ),
        ExceptionPath(
            type=ExceptionType.DOMESTIC_VIOLENCE_INDETERMINATE,
            label="Domestic violence exception — alternative probation",
            description=exc["description"],
            statute_refs=[statute_ref],
            triggering_factors=triggers,
            resulting_disposition=Disposition(
                type=DispositionType.PROBATION,
                label="Probation under PL 65.00 (DV alternative per 60.12(2))",
                statute_refs=[statute_ref, "PL 65.00"],
                conditions=eligibility,
            ),
        ),
    ]


def generate_dwi_exception(
    is_dwi: bool,
) -> ExceptionPath | None:
    """Generate the DWI disposition exception (PL 60.21).

    For VTL 1192(2)/(2-a)/(3) DWI convictions, the court may impose imprisonment
    per Article 70 AND must impose probation or conditional discharge per 65.00
    AND must order ignition interlock device installation. The probation/CD runs
    consecutively to any imprisonment and commences upon release.
    """
    if not is_dwi:
        return None

    return ExceptionPath(
        type=ExceptionType.DWI_SPLIT_SENTENCE_VARIANT,
        label="DWI sentence — imprisonment + probation/CD + ignition interlock",
        description="Per PL 60.21: court may impose imprisonment per Art 70, must impose probation or conditional discharge per 65.00, and must order ignition interlock device. Probation/CD runs consecutively to imprisonment and commences upon release.",
        statute_refs=["PL 60.21"],
        triggering_factors=["is_dwi"],
        resulting_disposition=Disposition(
            type=DispositionType.PROBATION,
            label="Probation or conditional discharge consecutive to imprisonment + ignition interlock",
            statute_refs=["PL 60.21, 65.00"],
            conditions="Must run consecutively to any imprisonment; ignition interlock device required",
        ),
    )


def generate_for_hire_exception(
    section: str,
    victim_is_for_hire_operator: bool,
    is_attempt: bool = False,
    attempt_of_section: str | None = None,
) -> ExceptionPath | None:
    """Generate the for-hire vehicle enhancement judicial escape hatch (PL 60.07(1)).

    PL 60.07(1) provides that the court MAY decline to impose the 3-5 year
    minimum-term enhancement if it finds on the record that:
      (a) the enhancement would be unduly harsh, AND
      (b) not imposing it would be consistent with public safety, AND
      (c) not imposing it would not deprecate the seriousness of the crime.
    All three findings must be made on the record.

    This exception path documents that the court has discretion to decline
    the enhancement. The enhancement itself is applied post-disposition in
    sentencing.py via _apply_for_hire_enhancement().
    """
    if not victim_is_for_hire_operator:
        return None
    if not is_for_hire_eligible(section, is_attempt, attempt_of_section):
        return None

    return ExceptionPath(
        type=ExceptionType.FOR_HIRE_ENHANCEMENT,
        label="For-hire vehicle enhancement — court may decline the 3-5yr minimum increase",
        description=(
            "Per PL 60.07(1): when the victim was operating a for-hire vehicle "
            "and the offense is a specified offense per 60.07(2)(a), the minimum "
            "term is increased by 3-5 years. The court may decline this enhancement "
            "if it finds on the record that (a) it would be unduly harsh, AND "
            "(b) not imposing it would be consistent with public safety, AND "
            "(c) not imposing it would not deprecate the seriousness of the crime."
        ),
        statute_refs=["PL 60.07"],
        triggering_factors=["victim_is_for_hire_operator"],
        resulting_disposition=None,
    )


def generate_all_exceptions(
    classification: str,
    is_vfo: bool,
    case_facts,
) -> list[ExceptionPath]:
    """Generate all applicable exception paths for a case."""
    exceptions: list[ExceptionPath] = []

    # Armed felony override (only for VFOs / felonies with armed-felony plea)
    armed = generate_armed_felony_exception(
        classification=classification,
        plea_from_armed_felony_indictment=case_facts.plea_from_armed_felony_indictment,
        mitigating_factor=case_facts.armed_felony_mitigating_factor,
        minor_participation=case_facts.armed_felony_minor_participation,
        proof_deficiencies=case_facts.armed_felony_proof_deficiencies,
    )
    if armed is not None:
        exceptions.append(armed)

    # Record statement (when VFO determinate is the primary but court opts out)
    if is_vfo:
        record_stmt = generate_record_statement_exception(
            determinate_imposed=not case_facts.plea_from_armed_felony_indictment
            or not any([
                case_facts.armed_felony_mitigating_factor,
                case_facts.armed_felony_minor_participation,
                case_facts.armed_felony_proof_deficiencies,
            ])
        )
        # Only add if the armed felony exception path is active
        if armed is not None and record_stmt is not None:
            exceptions.append(record_stmt)

    # Domestic violence exception — 60.12(2) emits three sibling alternatives
    dv = generate_domestic_violence_exception(
        classification=classification,
        section=case_facts.section,
        domestic_violence_by_victim=case_facts.domestic_violence_by_victim,
    )
    exceptions.extend(dv)

    # DWI split sentence variant
    dwi = generate_dwi_exception(is_dwi=case_facts.is_dwi)
    if dwi is not None:
        exceptions.append(dwi)

    # For-hire vehicle enhancement judicial escape hatch (PL 60.07(1))
    for_hire = generate_for_hire_exception(
        section=case_facts.section,
        victim_is_for_hire_operator=case_facts.victim_is_for_hire_operator,
        is_attempt=case_facts.is_attempt,
        attempt_of_section=case_facts.attempt_of_section,
    )
    if for_hire is not None:
        exceptions.append(for_hire)

    return exceptions
