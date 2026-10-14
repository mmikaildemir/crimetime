"""Pydantic models for the CrimeTime sentencing decision engine.

These models define:
1. CaseFacts — the input parameters the system asks about a case
2. SentencingOutput — the structured output the engine produces
3. Supporting enums and sub-models for dispositions, exceptions, financials

The 21 outputs from the reference example (PL 120.02) map to:
  - available_dispositions: items 1, 6, 7, 8, 10, 11, 12, 13 (fine)
  - exception_paths: items 3, 4, 5, 9
  - financial_obligations: items 14, 15, 16, 17, 18, 19, 20
  - collateral_requirements: items 21, and the felony record-statement notes
  - prs: item 2 (attached to the determinate disposition)
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PriorRecordStatus(str, Enum):
    """Defendant's prior-record status — the selector that routes to sentencing tables."""

    FIRST_OFFENDER = "first_offender"
    SECOND_FELONY_OFFENDER_70_06 = "second_felony_offender_70_06"
    SECOND_VIOLENT_FELONY_OFFENDER_70_04 = "second_violent_felony_offender_70_04"
    PERSISTENT_FELONY_OFFENDER_70_10 = "persistent_felony_offender_70_10"
    PERSISTENT_VIOLENT_FELONY_OFFENDER_70_08 = "persistent_violent_felony_offender_70_08"


class AgeCategory(str, Enum):
    """Defendant age category — gates youthful-offender and juvenile-offender sentencing."""

    ADULT = "adult"
    YOUTHFUL_OFFENDER_ELIGIBLE = "youthful_offender_eligible"
    JUVENILE_OFFENDER = "juvenile_offender"


class DispositionType(str, Enum):
    """Types of sentencing dispositions the engine can output."""

    DETERMINATE = "determinate"
    INDETERMINATE = "indeterminate"
    DEFINITE = "definite"
    INTERMITTENT = "intermittent"
    SPLIT = "split"
    PROBATION = "probation"
    CONDITIONAL_DISCHARGE = "conditional_discharge"
    UNCONDITIONAL_DISCHARGE = "unconditional_discharge"
    FINE = "fine"
    LIFE_WITHOUT_PAROLE = "life_without_parole"


class ExceptionType(str, Enum):
    """Exception paths that can override the primary sentencing disposition."""

    ARMED_FELONY_OVERRIDE = "armed_felony_override"
    DOMESTIC_VIOLENCE_INDETERMINATE = "domestic_violence_indeterminate"
    DWI_SPLIT_SENTENCE_VARIANT = "dwi_split_sentence_variant"
    RECORD_STATEMENT_REQUIRED = "record_statement_required"
    FOR_HIRE_ENHANCEMENT = "for_hire_enhancement"


class FinancialType(str, Enum):
    """Types of financial obligations the court must impose or consider."""

    FINE = "fine"
    MANDATORY_SURCHARGE = "mandatory_surcharge"
    CRIME_VICTIM_ASSISTANCE_FEE = "crime_victim_assistance_fee"
    DNA_DATABANK_FEE = "dna_databank_fee"
    RESTITUTION_CONSIDERATION = "restitution_consideration"
    RESTITUTION_COLLECTION_SURCHARGE = "restitution_collection_surcharge"
    RESTITUTION_ADDITIONAL_SURCHARGE = "restitution_additional_surcharge"


class CollateralType(str, Enum):
    """Collateral requirements beyond sentencing and financials."""

    DNA_SAMPLE = "dna_sample"
    FELONY_RECORD_STATEMENT = "felony_record_statement"
    SURCHARGE_SUMMONS = "surcharge_summons"


class TermUnit(str, Enum):
    YEARS = "years"
    MONTHS = "months"
    DAYS = "days"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class TermRange(BaseModel):
    """A range of time (e.g., 2–7 years)."""

    min_value: float
    max_value: float
    unit: TermUnit = TermUnit.YEARS


class PostReleaseSupervision(BaseModel):
    """Post-release supervision attached to determinate sentences."""

    min_years: float
    max_years: float
    statute_refs: list[str] = Field(default_factory=list)


class Disposition(BaseModel):
    """A single available sentencing disposition."""

    type: DispositionType
    label: str
    statute_refs: list[str] = Field(default_factory=list)
    term: Optional[TermRange] = None
    prs: Optional[PostReleaseSupervision] = None
    probation_years: Optional[list[int]] = None
    conditional_discharge_years: Optional[int] = None
    split_imprisonment_max_months: Optional[float] = None
    split_intermittent_max_months: Optional[float] = None
    fine_max_amount: Optional[float] = None
    fine_alt_double_gain: bool = False
    conditions: Optional[str] = None
    record_statement_required: bool = False


class ExceptionPath(BaseModel):
    """An exception path that can override or modify the primary disposition."""

    type: ExceptionType
    label: str
    description: str
    statute_refs: list[str] = Field(default_factory=list)
    triggering_factors: list[str] = Field(default_factory=list)
    resulting_disposition: Optional[Disposition] = None


class FinancialObligation(BaseModel):
    """A financial obligation the court must impose or consider."""

    type: FinancialType
    label: str
    amount: Optional[float] = None
    statute_refs: list[str] = Field(default_factory=list)
    conditions: Optional[str] = None


class CollateralRequirement(BaseModel):
    """A collateral requirement (DNA sample, record statements, etc.)."""

    type: CollateralType
    label: str
    description: str
    statute_refs: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Conditional classification (offense-intrinsic escalation rules)
# ---------------------------------------------------------------------------


class ConditionalClassificationRule(BaseModel):
    """A single rule: if `field` matches `condition`, use `resulting_classification`."""

    field: str
    condition: str = "in"  # "in", "true", "gt"
    values: list[str] = Field(default_factory=list)
    resulting_classification: str


class ConditionalClassification(BaseModel):
    """Offense-intrinsic conditional classification rules.

    Example (§130.86 Luring a child):
      base classification = ClassE_Felony
      if intended_underlying_offense_class in [ClassA_I, ClassA_II] → ClassC_Felony
      if intended_underlying_offense_class in [ClassB, ClassB_Violent] → ClassD_Felony
      fallback → ClassE_Felony

    Example (§225.90 Manipulation of gaming):
      base classification = ClassA_Misdemeanor
      if prior_conviction_same_section_within_years is true → ClassE_Felony
      fallback → ClassA_Misdemeanor
    """

    rules: list[ConditionalClassificationRule]
    fallback: str
    prompt_fields: list[str] = Field(
        default_factory=list,
        description="Which CaseFacts fields the form should prompt for when this offense is selected",
    )


class SentenceOverride(BaseModel):
    """A sentence parameter override (e.g., max imprisonment cap).

    Example (§260.35 Misrepresentation by caregiver):
      classification stays ClassA_Misdemeanor, but max imprisonment = 6 months.
    """

    field: str  # which disposition parameter to override
    value: float
    reason: str = ""


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


class CaseFacts(BaseModel):
    """The case facts the system prompts for before resolving sentencing.

    These are NOT offense-derived — they are facts about the specific case
    that the system needs to know to select the correct outputs.
    """

    # Offense identification
    section: str = Field(description="NYS Penal Law section number, e.g. '120.02'")
    subdivision: Optional[str] = Field(
        default=None, description="Subdivision if applicable, e.g. '1'"
    )
    is_attempt: bool = False
    attempt_of_section: Optional[str] = None
    is_conspiracy: bool = False
    conspiracy_of_section: Optional[str] = None

    # Defendant prior-record status — the primary sentencing-table selector
    prior_record_status: PriorRecordStatus = PriorRecordStatus.FIRST_OFFENDER

    # Exception triggers
    plea_from_armed_felony_indictment: bool = False
    armed_felony_mitigating_factor: bool = False
    armed_felony_minor_participation: bool = False
    armed_felony_proof_deficiencies: bool = False
    domestic_violence_by_victim: bool = False
    is_dwi: bool = False
    defendant_under_other_sentence_over_15_days: bool = False
    victim_seeking_restitution: bool = False
    hate_crime_motivated: bool = False
    sexually_motivated: bool = False
    terrorism_motivated: bool = False
    victim_is_for_hire_operator: bool = False

    # Conditional classification triggers (offense-intrinsic)
    intended_underlying_offense_class: Optional[str] = Field(
        default=None, description="Classification of the intended offense (for §130.86 luring a child)"
    )
    prior_conviction_same_section_within_years: Optional[int] = Field(
        default=None, description="If prior conviction of same offense within N years (for §225.90, §225.95)"
    )

    # Age
    defendant_age_category: AgeCategory = AgeCategory.ADULT


# ---------------------------------------------------------------------------
# Modifier tracking
# ---------------------------------------------------------------------------


class ModifierApplied(BaseModel):
    """Records a single modifier (enhancement) that was applied during sentencing.

    Modifiers are applied in order: SMF → hate crime → terrorism. Each modifier
    sees the classification resulting from the previous one. The for-hire
    enhancement (PL 60.07) is a post-disposition minimum-term adjustment, not a
    classification modifier, and is tracked separately.
    """

    modifier_type: str
    """One of: 'hate_crime', 'terrorism', 'sexually_motivated_felony'."""

    branch: Optional[str] = None
    """Which sub-rule matched. e.g. 'misdemeanorOrClassCDE', 'ClassB',
    'ClassA_I' for hate crime; 'ClassCDE', 'ClassB_to_A_I', 'life_without_parole'
    for terrorism; 'violent_redesignation' for SMF."""

    base_classification: str
    """Classification before this modifier was applied."""

    resulting_classification: str
    """Classification after this modifier was applied."""


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class SentencingOutput(BaseModel):
    """The structured sentencing output the engine produces.

    Each field corresponds to a category of outputs from the reference example.
    The engine populates all fields based on (offense, case_facts).

    Modifier tracking:
      - base_classification: the pre-any-modifier classification (None if no
        modifier fired).
      - modifiers_applied: list of ModifierApplied records, one per modifier
        that fired (SMF, hate crime, terrorism). Empty if none fired.
    The `classification` field always holds the final post-modifier value.
    """

    section: str
    offense_name: str
    classification: str
    is_vfo: bool

    available_dispositions: list[Disposition] = Field(default_factory=list)
    exception_paths: list[ExceptionPath] = Field(default_factory=list)
    financial_obligations: list[FinancialObligation] = Field(default_factory=list)
    collateral_requirements: list[CollateralRequirement] = Field(
        default_factory=list
    )

    base_classification: Optional[str] = None
    modifiers_applied: list[ModifierApplied] = Field(default_factory=list)
