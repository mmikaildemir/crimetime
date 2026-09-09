"""Exception paths that can override or modify the primary sentencing disposition.

Covers outputs #3, #4, #5, #9 from the reference example:
  - Armed felony override (PL 70.02(4)(b))
  - Record statement requirement (when determinate not imposed)
  - Domestic violence indeterminate (PL 60.12)
  - DWI split sentence variant (PL 60.21)
"""

from __future__ import annotations

from . import reference
from .models import Disposition, DispositionType, ExceptionPath, ExceptionType, TermRange, TermUnit
from .resolvers import is_felony


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
    domestic_violence_by_victim: bool,
) -> ExceptionPath | None:
    """Generate the domestic-violence indeterminate exception (PL 60.12).

    If DV by the victim was a factor in causing the offense, the court may
    impose an indeterminate sentence instead of a determinate one.
    Max term: 3–7 years; min term: one-half the maximum.
    """
    if not domestic_violence_by_victim:
        return None
    if not is_felony(classification):
        return None

    exc = reference.get_exceptions_table()["domesticViolenceIndeterminate"]

    return ExceptionPath(
        type=ExceptionType.DOMESTIC_VIOLENCE_INDETERMINATE,
        label="Domestic violence exception — court may impose indeterminate sentence",
        description=exc["description"],
        statute_refs=[exc["statuteRef"]],
        triggering_factors=["domestic_violence_by_victim"],
        resulting_disposition=Disposition(
            type=DispositionType.INDETERMINATE,
            label="Indeterminate sentence per domestic violence exception",
            statute_refs=[exc["statuteRef"]],
            term=TermRange(min_value=3, max_value=7, unit=TermUnit.YEARS),
            conditions="Minimum term must be one-half the maximum term; max term not less than 3 nor more than 7 years",
        ),
    )


def generate_dwi_exception(
    is_dwi: bool,
) -> ExceptionPath | None:
    """Generate the DWI split-sentence variant exception (PL 60.21).

    For DWI sentences, the imprisonment portion of a split sentence may be
    up to 1 year instead of the standard 6 months.
    """
    if not is_dwi:
        return None

    exc = reference.get_exceptions_table()["dwiSplitSentenceVariant"]

    return ExceptionPath(
        type=ExceptionType.DWI_SPLIT_SENTENCE_VARIANT,
        label="DWI split sentence variant — imprisonment up to 1 year",
        description=exc["description"],
        statute_refs=[exc["statuteRef"]],
        triggering_factors=["is_dwi"],
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

    # Domestic violence exception
    dv = generate_domestic_violence_exception(
        classification=classification,
        domestic_violence_by_victim=case_facts.domestic_violence_by_victim,
    )
    if dv is not None:
        exceptions.append(dv)

    # DWI split sentence variant
    dwi = generate_dwi_exception(is_dwi=case_facts.is_dwi)
    if dwi is not None:
        exceptions.append(dwi)

    return exceptions
