"""Typed accessors over the JSON reference data.

Loads data/lists.json and data/sentencing_tables.json and exposes
typed lookup functions used by the resolvers and sentencing engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

_lists: dict[str, Any] | None = None
_sentencing: dict[str, Any] | None = None


def _load_lists() -> dict[str, Any]:
    global _lists
    if _lists is None:
        with open(_DATA_DIR / "lists.json") as f:
            _lists = json.load(f)
    return _lists


def _load_sentencing() -> dict[str, Any]:
    global _sentencing
    if _sentencing is None:
        with open(_DATA_DIR / "sentencing_tables.json") as f:
            _sentencing = json.load(f)
    return _sentencing


# ---------------------------------------------------------------------------
# Lists accessors
# ---------------------------------------------------------------------------


def get_offense(section: str) -> Optional[dict[str, Any]]:
    """Return offense metadata by section number (e.g. '120.02'), or None."""
    return _load_lists().get("offenses", {}).get(section)


def get_all_offenses() -> dict[str, dict[str, Any]]:
    """Return the full offense metadata dict."""
    return _load_lists().get("offenses", {})


def get_axioms() -> dict[str, str]:
    """Return the axiom documentation dict (for reference, not execution)."""
    return _load_lists().get("schema", {}).get("axioms", {})


def get_constants() -> dict[str, Any]:
    """Return the constants dict (STAYS_A_I_LIST, STANDARD_DOWNGRADE_TABLE, etc.)."""
    return _load_lists().get("schema", {}).get("constants", {})


# --- VFO_LIST --------------------------------------------------------------


def get_vfo_list() -> dict[str, Any]:
    return _load_lists()["lists"]["VFO_LIST"]


def is_vfo_section(section: str, vfo_class: str) -> bool:
    """Check if a section is in the VFO list for a given class (B/C/D/E)."""
    vfo = get_vfo_list()
    cls = vfo.get(f"class{vfo_class}", vfo.get(vfo_class.lower(), {}))
    return section in cls.get("sections", [])


def get_vfo_class_for_section(section: str) -> Optional[str]:
    """Return the VFO class ('B', 'C', 'D', 'E') for a section, or None."""
    vfo = get_vfo_list()
    for cls_key in ("classB", "classC", "classD", "classE"):
        if section in vfo[cls_key].get("sections", []):
            return cls_key.replace("class", "")
    return None


def get_vfo_attempt_of_sections() -> dict[str, list[str]]:
    """Return mapping: vfo_class -> list of sections whose attempt is that VFO class."""
    vfo = get_vfo_list()
    result = {}
    for cls_key in ("classB", "classC", "classD", "classE"):
        cls = vfo[cls_key]
        if "attemptOfSection" in cls:
            result[cls_key] = cls["attemptOfSection"]
    return result


def get_vfo_attempt_of_class_rules() -> dict[str, list[str]]:
    """Return mapping: vfo_class -> list of classes whose attempt resolves to this class."""
    vfo = get_vfo_list()
    result = {}
    for cls_key in ("classB", "classC", "classD", "classE"):
        cls = vfo[cls_key]
        if "attemptOfClass" in cls:
            result[cls_key] = cls["attemptOfClass"]
    return result


def get_vfo_lesser_included() -> list[str]:
    """Return sections in classE's attemptOfSection_lesserIncluded."""
    vfo = get_vfo_list()
    return vfo.get("classE", {}).get("attemptOfSection_lesserIncluded", [])


# --- SMF_LIST ---------------------------------------------------------------


def get_smf_list() -> dict[str, Any]:
    return _load_lists()["lists"]["SMF_LIST"]


def is_smf_section(section: str) -> bool:
    return section in get_smf_list().get("sections", [])


# --- HATECRIME_LIST --------------------------------------------------------


def get_hatecrime_list() -> dict[str, Any]:
    return _load_lists()["lists"]["HATECRIME_LIST"]


def is_hatecrime_section(section: str) -> bool:
    return section in get_hatecrime_list().get("sections", [])


# ---------------------------------------------------------------------------
# Sentencing tables accessors
# ---------------------------------------------------------------------------


def get_sentencing_tables() -> dict[str, Any]:
    return _load_sentencing()


def get_violation_table() -> dict[str, Any]:
    return _load_sentencing().get("violation", {})


def get_misdemeanor_table() -> dict[str, Any]:
    return _load_sentencing().get("misdemeanor", {})


def get_nonviolent_felony_table() -> dict[str, Any]:
    return _load_sentencing().get("nonViolentFelony", {})


def get_violent_felony_table() -> dict[str, Any]:
    return _load_sentencing().get("violentFelony", {})


def get_hatecrime_bump_table() -> dict[str, Any]:
    return _load_sentencing().get("hateCrimeBump", {})


def get_dispositions_table() -> dict[str, Any]:
    return _load_sentencing().get("dispositions", {})


def get_exceptions_table() -> dict[str, Any]:
    return _load_sentencing().get("exceptions", {})


def get_financial_table() -> dict[str, Any]:
    return _load_sentencing().get("financial", {})


def get_collateral_table() -> dict[str, Any]:
    return _load_sentencing().get("collateral", {})


def get_restitution_table() -> dict[str, Any]:
    return _load_sentencing().get("restitution", {})


def get_offense_overrides() -> dict[str, Any]:
    """Return offense-specific sentencing overrides (e.g. §125.27 20-25yr min,
    §125.26 life without parole). Keyed by section number."""
    return _load_sentencing().get("offenseOverrides", {})


def get_drug_felony_table() -> dict[str, Any]:
    """Return the drug felony sentencing tables (PL 70.70 / 70.71)."""
    return _load_sentencing().get("drugFelony", {})
