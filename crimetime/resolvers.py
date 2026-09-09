"""Classification and enhancement resolvers — A1–A17 as Python functions.

These functions encode the branching/exception logic that was previously
documented as axioms in ny_penal_ontology.json. The JSON axioms remain as
documentation; these functions are the executable truth.

Key concepts:
  - isCrime:           A1 — misdemeanor or felony (violations are not crimes)
  - isVFO:             A3 — Class B/C/D/E felony in VFO_LIST
  - hasPredicateExposure: A6 — felony, not Class A-I (A-II retains it)
  - is70_04Reachable:   A7 — VFO AND has predicate exposure
  - is70_06Reachable:   A8 — predicate exposure AND NOT VFO
  - resolveAttempt:    A9 — ordered branching per PL 110.05
  - resolveVFOOfAttempt: A11 — three-way resolution against VFO_LIST
"""

from __future__ import annotations

from typing import Optional

from . import reference


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

FELONY_CLASSIFICATIONS = {
    "ClassA_I_Felony",
    "ClassA_II_Felony",
    "ClassB_Felony",
    "ClassC_Felony",
    "ClassD_Felony",
    "ClassE_Felony",
}

VIOLENT_FELONY_CLASSIFICATIONS = {
    "ClassB_Violent_Felony",
    "ClassC_Violent_Felony",
    "ClassD_Violent_Felony",
    "ClassE_Violent_Felony",
}

MISDEMEANOR_CLASSIFICATIONS = {
    "ClassA_Misdemeanor",
    "ClassB_Misdemeanor",
    "Unclassified_Misdemeanor",
}

ALL_FELONY_CLASSIFICATIONS = FELONY_CLASSIFICATIONS | VIOLENT_FELONY_CLASSIFICATIONS


def is_felony(classification: str) -> bool:
    """True if classification is any felony (violent or non-violent)."""
    return classification in ALL_FELONY_CLASSIFICATIONS


def is_misdemeanor(classification: str) -> bool:
    return classification in MISDEMEANOR_CLASSIFICATIONS


def is_violation(classification: str) -> bool:
    return classification == "Violation"


def get_felony_class_letter(classification: str) -> Optional[str]:
    """Extract the class letter from a felony classification.

    'ClassD_Violent_Felony' -> 'D', 'ClassB_Felony' -> 'B'
    """
    for letter in ("A_I", "A_II", "B", "C", "D", "E"):
        if f"Class{letter}" in classification:
            return letter
    return None


def normalize_violent_to_base(classification: str) -> str:
    """Map a violent-felony classification to its base felony class.

    'ClassD_Violent_Felony' -> 'ClassD_Felony'
    'ClassD_Felony' -> 'ClassD_Felony' (no-op)
    """
    for letter in ("A_I", "A_II", "B", "C", "D", "E"):
        if classification == f"Class{letter}_Violent_Felony":
            return f"Class{letter}_Felony"
    return classification


# ---------------------------------------------------------------------------
# A1 — isCrime
# ---------------------------------------------------------------------------


def is_crime(classification: str) -> bool:
    """A1: A classification is a 'crime' if it is a misdemeanor or felony."""
    return is_misdemeanor(classification) or is_felony(classification)


# ---------------------------------------------------------------------------
# A2 — isYOEligible
# ---------------------------------------------------------------------------


def is_yo_eligible(classification: str) -> bool:
    """A2: YO-eligible if crime AND not Class A-I or A-II felony."""
    if not is_crime(classification):
        return False
    return classification not in ("ClassA_I_Felony", "ClassA_II_Felony")


# ---------------------------------------------------------------------------
# A3 — isVFO
# ---------------------------------------------------------------------------


def is_vfo(section: str, classification: str) -> bool:
    """A3: True if Class B/C/D/E felony AND section in VFO_LIST for that class."""
    if not is_felony(classification):
        return False
    letter = get_felony_class_letter(classification)
    if letter is None or letter in ("A_I", "A_II"):
        return False
    return reference.is_vfo_section(section, letter)


# ---------------------------------------------------------------------------
# A4 — isSMFEligible
# ---------------------------------------------------------------------------


def is_smf_eligible(section: str, classification: str) -> bool:
    """A4: SMF-eligible if felony AND section in SMF_LIST."""
    if not is_felony(classification):
        return False
    return reference.is_smf_section(section)


# ---------------------------------------------------------------------------
# A5 — isHateCrimeEligible
# ---------------------------------------------------------------------------


def is_hatecrime_eligible(section: str) -> bool:
    """A5: Hate-crime-eligible if section in HATECRIME_LIST (not felony-gated)."""
    return reference.is_hatecrime_section(section)


# ---------------------------------------------------------------------------
# A6 — hasPredicateExposure
# ---------------------------------------------------------------------------


def has_predicate_exposure(classification: str) -> bool:
    """A6: Predicate exposure if felony AND not Class A-I. (A-II retains it.)"""
    if not is_felony(classification):
        return False
    return classification != "ClassA_I_Felony"


# ---------------------------------------------------------------------------
# A7 — is70_04Reachable
# ---------------------------------------------------------------------------


def is_70_04_reachable(section: str, classification: str) -> bool:
    """A7: PL 70.04 reachable if isVFO AND hasPredicateExposure."""
    return is_vfo(section, classification) and has_predicate_exposure(classification)


# ---------------------------------------------------------------------------
# A8 — is70_06Reachable
# ---------------------------------------------------------------------------


def is_70_06_reachable(section: str, classification: str) -> bool:
    """A8: PL 70.06 reachable if hasPredicateExposure AND NOT isVFO."""
    return has_predicate_exposure(classification) and not is_vfo(
        section, classification
    )


# ---------------------------------------------------------------------------
# A9 — classification of attempt
# ---------------------------------------------------------------------------

_STAYS_A_I_SECTIONS = {"125.27", "220.21", "220.43", "490.45", "490.55"}

_DOWNGRADE_TABLE = {
    "ClassB_Felony": "ClassC_Felony",
    "ClassC_Felony": "ClassD_Felony",
    "ClassD_Felony": "ClassE_Felony",
    "ClassE_Felony": "ClassA_Misdemeanor",
    "ClassA_Misdemeanor": "ClassB_Misdemeanor",
}

_BRIBERY_OVERRIDES = {
    "200.00": "ClassD_Felony",
    "200.03": "ClassC_Felony",
}


def resolve_attempt_classification(
    target_section: str,
    target_classification: str,
    target_subdivision: Optional[str] = None,
) -> str:
    """A9: Resolve the classification of an attempt per PL 110.05 ordered branching.

    Branches (in order):
      1. section in STAYS_A_I_LIST -> ClassA_I_Felony (no downgrade)
      2. classification == ClassA_II_Felony -> ClassA_II_Felony (no downgrade)
      3. classification == ClassA_I_Felony -> ClassB_Felony
      4. section == '200.00' -> ClassD_Felony (bribery 3rd override)
      5. section == '200.03' -> ClassC_Felony (bribery 2nd override)
      6. section == '200.04' AND subdivision == '2' -> ClassB_Felony (bribery 1st subd.2)
      7. else -> standard one-class downgrade per STANDARD_DOWNGRADE_TABLE
    """
    # Branch 1: stays Class A-I
    if target_section in _STAYS_A_I_SECTIONS:
        return "ClassA_I_Felony"

    # Branch 2: Class A-II stays Class A-II
    if target_classification == "ClassA_II_Felony":
        return "ClassA_II_Felony"

    # Branch 3: Class A-I (not in stays list) -> Class B
    if target_classification == "ClassA_I_Felony":
        return "ClassB_Felony"

    # Branches 4-5: bribery overrides
    if target_section in _BRIBERY_OVERRIDES:
        return _BRIBERY_OVERRIDES[target_section]

    # Branch 6: bribery 1st degree, subdivision 2
    if target_section == "200.04" and target_subdivision == "2":
        return "ClassB_Felony"

    # Branch 7: standard downgrade
    base = normalize_violent_to_base(target_classification)
    if base in _DOWNGRADE_TABLE:
        return _DOWNGRADE_TABLE[base]

    raise ValueError(
        f"Cannot resolve attempt classification for {target_section} "
        f"(classification={target_classification})"
    )


# ---------------------------------------------------------------------------
# A11 — VFO status of attempt
# ---------------------------------------------------------------------------


def resolve_vfo_of_attempt(
    target_section: str,
    target_classification: str,
) -> tuple[bool, Optional[str]]:
    """A11: Resolve VFO status + class of an attempt.

    Returns (is_vfo, vfo_class_letter).

    Three resolution paths:
      (a) target section appears in some VFO class's attemptOfSection array
      (b) target's VFO class has attemptOfClass containing the target's VFO class
      (c) target section appears in classE's attemptOfSection_lesserIncluded
    """
    # Path (a): named carve-out
    attempt_of_sections = reference.get_vfo_attempt_of_sections()
    for cls_key, sections in attempt_of_sections.items():
        if target_section in sections:
            return True, cls_key.replace("class", "")

    # Path (b): class-level downgrade rule
    target_vfo_class = reference.get_vfo_class_for_section(target_section)
    if target_vfo_class is not None:
        attempt_of_class_rules = reference.get_vfo_attempt_of_class_rules()
        for cls_key, source_classes in attempt_of_class_rules.items():
            if f"class{target_vfo_class}" in source_classes:
                return True, cls_key.replace("class", "")

    # Path (c): lesser-included carve-out
    lesser_included = reference.get_vfo_lesser_included()
    if target_section in lesser_included:
        return True, "E"

    return False, None


# ---------------------------------------------------------------------------
# A12 — SMF of derivative (attempt/conspiracy)
# ---------------------------------------------------------------------------


def is_smf_of_derivative(
    target_section: str,
    target_classification: str,
    is_attempt: bool,
    is_conspiracy: bool,
) -> bool:
    """A12: An attempt or conspiracy is SMF-eligible if the target is SMF-eligible
    and the SMF_LIST includes attempts and conspiracies."""
    if not (is_attempt or is_conspiracy):
        return False
    if not reference.get_smf_list().get("includesAttemptsAndConspiracy", False):
        return False
    return is_smf_eligible(target_section, target_classification)


# ---------------------------------------------------------------------------
# A13 — Hate Crime of derivative
# ---------------------------------------------------------------------------


def is_hatecrime_of_derivative(
    target_section: str,
    is_attempt: bool,
    is_conspiracy: bool,
) -> bool:
    """A13: An attempt or conspiracy is HC-eligible if the target is HC-eligible
    and the HATECRIME_LIST includes attempts and conspiracies."""
    if not (is_attempt or is_conspiracy):
        return False
    if not reference.get_hatecrime_list().get("includesAttemptsAndConspiracy", False):
        return False
    return is_hatecrime_eligible(target_section)


# ---------------------------------------------------------------------------
# Convenience: resolve all derived flags for an offense
# ---------------------------------------------------------------------------


def resolve_derived_flags(
    section: str,
    classification: str,
    is_attempt: bool = False,
    attempt_of_section: Optional[str] = None,
    attempt_of_classification: Optional[str] = None,
    attempt_of_subdivision: Optional[str] = None,
    is_conspiracy: bool = False,
    conspiracy_of_section: Optional[str] = None,
    conspiracy_of_classification: Optional[str] = None,
) -> dict[str, bool]:
    """Compute all derived flags for an offense given its metadata and case facts.

    For attempts, the classification should already be the *resolved* attempt
    classification (via resolve_attempt_classification). The VFO status is
    resolved via resolve_vfo_of_attempt.
    """
    vfo = is_vfo(section, classification)
    smf = is_smf_eligible(section, classification)
    hc = is_hatecrime_eligible(section)

    if is_attempt and attempt_of_section:
        vfo, _ = resolve_vfo_of_attempt(attempt_of_section, attempt_of_classification or "")
        smf = is_smf_of_derivative(
            attempt_of_section, attempt_of_classification or "", True, False
        )
        hc = is_hatecrime_of_derivative(attempt_of_section, True, False)

    if is_conspiracy and conspiracy_of_section:
        smf = is_smf_of_derivative(
            conspiracy_of_section, conspiracy_of_classification or "", False, True
        )
        hc = is_hatecrime_of_derivative(conspiracy_of_section, False, True)

    return {
        "isCrime": is_crime(classification),
        "isYOEligible": is_yo_eligible(classification),
        "isVFO": vfo,
        "isSMFEligible": smf,
        "isHateCrimeEligible": hc,
        "hasPredicateExposure": has_predicate_exposure(classification),
        "is70_04Reachable": vfo and has_predicate_exposure(classification),
        "is70_06Reachable": (not vfo) and has_predicate_exposure(classification),
    }
