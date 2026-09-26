"""Financial obligations and collateral requirements generator.

Produces the FinancialObligation and CollateralRequirement entries
in the SentencingOutput. Covers outputs #13–21 from the reference example.
"""

from __future__ import annotations

from . import reference
from .models import (
    CollateralRequirement,
    CollateralType,
    FinancialObligation,
    FinancialType,
)
from .resolvers import is_felony, is_misdemeanor, is_violation


# Sex offense sections for supplemental fee (PL 60.35(1)(b))
_SEX_OFFENSE_FEE_SECTIONS = {
    # Article 130 sex offenses
    **{f"130.{s}": True for s in ["25", "30", "35", "40", "45", "50", "55", "60",
                                  "65", "65-a", "66", "67", "70", "75", "80",
                                  "85", "90", "95", "96"]},
    # Incest (255.25/26/27)
    "255.25": True, "255.26": True, "255.27": True,
    # Article 263 (child sexual performance)
    **{f"263.{s}": True for s in ["05", "10", "11", "12", "15", "16"]},
}


def _is_sex_offense_for_fee(section: str) -> bool:
    """Check if a section triggers the supplemental sex-offender victim fee
    per PL 60.35(1)(b)."""
    return section in _SEX_OFFENSE_FEE_SECTIONS


def _classify_level(classification: str) -> str:
    """Map a classification string to a level key: 'felony', 'misdemeanor', or 'violation'."""
    if is_felony(classification):
        return "felony"
    if is_misdemeanor(classification):
        return "misdemeanor"
    if is_violation(classification):
        return "violation"
    raise ValueError(f"Unknown classification: {classification}")


def _misdemeanor_subclass(classification: str) -> str:
    """Map a misdemeanor classification to its subclass key."""
    if classification == "ClassA_Misdemeanor":
        return "classA"
    if classification == "ClassB_Misdemeanor":
        return "classB"
    return "unclassified"


def generate_fine(classification: str) -> FinancialObligation:
    """Generate the fine obligation for a classification level.

    Felony:     up to $5,000 or double gain (PL 80.00)
    Class A misd: up to $1,000 or double gain (PL 80.05(1))
    Class B misd: up to $500 or double gain (PL 80.05(2))
    Violation:  up to $250 or double gain (PL 80.05(4))
    """
    level = _classify_level(classification)
    fin = reference.get_financial_table()

    if level == "felony":
        data = fin["felony"]["fine"]
    elif level == "misdemeanor":
        sub = _misdemeanor_subclass(classification)
        data = fin["misdemeanor"][sub]["fine"]
    else:
        data = fin["violation"]["fine"]

    return FinancialObligation(
        type=FinancialType.FINE,
        label=f"Fine up to ${data['maxAmount']:,} or double defendant's gain from the crime",
        amount=data["maxAmount"],
        statute_refs=[data["statuteRef"]],
        conditions="May be imposed by itself or in addition to imprisonment, probation, or conditional discharge"
        if not data.get("canStandAlone")
        else None,
    )


def generate_mandatory_surcharge(classification: str) -> FinancialObligation:
    """Generate the mandatory surcharge obligation."""
    level = _classify_level(classification)
    fin = reference.get_financial_table()

    if level == "felony":
        data = fin["felony"]["mandatorySurcharge"]
    elif level == "misdemeanor":
        sub = _misdemeanor_subclass(classification)
        data = fin["misdemeanor"][sub]["mandatorySurcharge"]
    else:
        data = fin["violation"]["mandatorySurcharge"]

    return FinancialObligation(
        type=FinancialType.MANDATORY_SURCHARGE,
        label=f"Mandatory surcharge of ${data['amount']}",
        amount=data["amount"],
        statute_refs=[data["statuteRef"]],
        conditions="Unless restitution or reparation has been made",
    )


def generate_crime_victim_assistance_fee(classification: str) -> FinancialObligation:
    """Generate the crime victim assistance fee obligation."""
    level = _classify_level(classification)
    fin = reference.get_financial_table()

    if level == "felony":
        data = fin["felony"]["crimeVictimAssistanceFee"]
    elif level == "misdemeanor":
        sub = _misdemeanor_subclass(classification)
        data = fin["misdemeanor"][sub]["crimeVictimAssistanceFee"]
    else:
        data = fin["violation"]["crimeVictimAssistanceFee"]

    return FinancialObligation(
        type=FinancialType.CRIME_VICTIM_ASSISTANCE_FEE,
        label=f"Crime victim assistance fee of ${data['amount']}",
        amount=data["amount"],
        statute_refs=[data["statuteRef"]],
    )


def generate_dna_databank_fee(classification: str) -> FinancialObligation | None:
    """Generate the DNA databank fee obligation (felony only currently)."""
    level = _classify_level(classification)
    fin = reference.get_financial_table()

    if level == "felony":
        data = fin["felony"]["dnaDatabankFee"]
    elif level == "misdemeanor":
        data = fin["misdemeanor"].get("classA", {}).get("dnaDatabankFee", {})
        if not data:
            return None
    else:
        return None

    return FinancialObligation(
        type=FinancialType.DNA_DATABANK_FEE,
        label=f"DNA databank fee of ${data['amount']}",
        amount=data["amount"],
        statute_refs=[data["statuteRef"]],
    )


def generate_restitution(victim_seeking_restitution: bool) -> list[FinancialObligation]:
    """Generate restitution-related obligations if a victim is seeking restitution."""
    if not victim_seeking_restitution:
        return []

    rest = reference.get_restitution_table()
    return [
        FinancialObligation(
            type=FinancialType.RESTITUTION_CONSIDERATION,
            label="Restitution consideration — court must consider ordering restitution",
            statute_refs=[rest["statuteRef"]],
            conditions="If not ordered, court must state reasons on record",
        ),
        FinancialObligation(
            type=FinancialType.RESTITUTION_COLLECTION_SURCHARGE,
            label=f"Restitution collection surcharge of {rest['collectionSurchargePercent']}% added to restitution amount",
            statute_refs=[rest["statuteRef"]],
        ),
        FinancialObligation(
            type=FinancialType.RESTITUTION_ADDITIONAL_SURCHARGE,
            label=f"Additional restitution surcharge of up to {rest['additionalSurchargeMaxPercent']}% upon filing by collection agency",
            statute_refs=[rest["statuteRef"]],
        ),
    ]


def generate_sex_offender_registration_fee(classification: str, section: str = "") -> FinancialObligation | None:
    """Generate the sex offender registration fee (PL 60.35(1)(a)(iv)).

    Levied on sex offenders required to register under Correction Law art 6-C.
    Felony-level only, sex offenses only.
    """
    level = _classify_level(classification)
    if level != "felony":
        return None
    if not _is_sex_offense_for_fee(section):
        return None
    fin = reference.get_financial_table()
    data = fin.get("felony", {}).get("sexOffenderRegistrationFee", {})
    if not data:
        return None
    return FinancialObligation(
        type=FinancialType.MANDATORY_SURCHARGE,
        label=f"Sex offender registration fee of ${data['amount']}",
        amount=data["amount"],
        statute_refs=[data["statuteRef"]],
    )


def generate_supplemental_sex_offender_victim_fee(section: str) -> FinancialObligation | None:
    """Generate the supplemental sex-offender victim fee (PL 60.35(1)(b)).

    $1,000 levied on convictions for Art 130 felonies, incest (255.25/26/27),
    and Art 263 offenses.
    """
    if not _is_sex_offense_for_fee(section):
        return None
    fin = reference.get_financial_table()
    data = fin.get("felony", {}).get("supplementalSexOffenderVictimFee", {})
    if not data:
        return None
    return FinancialObligation(
        type=FinancialType.MANDATORY_SURCHARGE,
        label=f"Supplemental sex-offender victim fee of ${data['amount']}",
        amount=data["amount"],
        statute_refs=[data["statuteRef"]],
    )


def generate_collateral_requirements(
    classification: str,
    jail_term_days: float | None = None,
) -> list[CollateralRequirement]:
    """Generate collateral requirements (DNA sample, surcharge summons, record statements).

    jail_term_days: if known, used to determine surcharge summons eligibility.
    """
    level = _classify_level(classification)
    collat = reference.get_collateral_table()
    requirements: list[CollateralRequirement] = []

    # DNA sample
    dna = collat.get(level, {}).get("dnaSampleRequired", {})
    if dna.get("required"):
        requirements.append(
            CollateralRequirement(
                type=CollateralType.DNA_SAMPLE,
                label="DNA sample — defendant must provide a DNA sample for the state DNA identification index",
                description="Required after sentencing for the state DNA identification index.",
                statute_refs=[dna["statuteRef"]],
            )
        )

    # Surcharge summons
    fin = reference.get_financial_table()
    if level == "felony":
        summons = fin["felony"].get("surchargeSummons", {})
    elif level == "misdemeanor":
        sub = _misdemeanor_subclass(classification)
        summons = fin["misdemeanor"].get(sub, {}).get("surchargeSummons", {})
    else:
        summons = fin["violation"].get("surchargeSummons", {})

    if summons and jail_term_days is not None and jail_term_days <= summons.get("thresholdJailDays", 60):
        requirements.append(
            CollateralRequirement(
                type=CollateralType.SURCHARGE_SUMMONS,
                label=f"Summons for unpaid surcharge — if jail term does not exceed {summons['thresholdJailDays']} days, court must issue summons directing defendant to appear within 60 days",
                description=summons.get("description", ""),
                statute_refs=[summons["statuteRef"]],
            )
        )

    return requirements


def generate_all_financial(
    classification: str,
    victim_seeking_restitution: bool = False,
    jail_term_days: float | None = None,
    section: str = "",
) -> list[FinancialObligation]:
    """Generate all applicable financial obligations for a classification."""
    obligations: list[FinancialObligation] = []

    obligations.append(generate_fine(classification))
    obligations.append(generate_mandatory_surcharge(classification))
    obligations.append(generate_crime_victim_assistance_fee(classification))

    dna_fee = generate_dna_databank_fee(classification)
    if dna_fee is not None:
        obligations.append(dna_fee)

    # Sex-offender fees (PL 60.35(1)(a)(iv) + (1)(b))
    if section:
        sex_reg_fee = generate_sex_offender_registration_fee(classification, section)
        if sex_reg_fee is not None:
            obligations.append(sex_reg_fee)
        supplemental_fee = generate_supplemental_sex_offender_victim_fee(section)
        if supplemental_fee is not None:
            obligations.append(supplemental_fee)

    obligations.extend(generate_restitution(victim_seeking_restitution))

    return obligations
