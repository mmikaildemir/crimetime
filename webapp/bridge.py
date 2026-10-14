"""CrimeTime 2.0 — framework-free bridge to the sentencing engine.

Pure functions (dict in, dict out) shared by the FastAPI dev server
(webapp/api.py) and the static GitHub Pages site, where this module is
loaded into Pyodide and called from site/engine.js. No FastAPI imports.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from crimetime import sentencing
from crimetime.exceptions import _DV_EXCLUDED_SECTIONS
from crimetime.models import (
    AgeCategory,
    CaseFacts,
    PriorRecord,
    PriorRecordStatus,
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
    resolve_attempt_classification,
)


class UnknownSection(KeyError):
    pass


class ResolveRequest(BaseModel):
    section: str
    subdivision: str | None = None
    is_attempt: bool = False
    attempt_of_section: str | None = None
    is_conspiracy: bool = False
    conspiracy_of_section: str | None = None
    predicate_felonies: int = 0
    predicate_vfos: int = 0
    prior_record_status: str | None = None  # deprecated; used only if no predicate counts are sent
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
    intended_underlying_offense_class: str | None = None
    prior_conviction_same_section_within_years: int | None = None
    defendant_age_category: str = "adult"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _eligibility(section: str, classification: str) -> dict:
    is_fel = is_felony(classification)
    return {
        "is_felony": is_fel,
        "is_misdemeanor": is_misdemeanor(classification),
        "is_violation": is_violation(classification),
        "vfo": is_vfo(section, classification),
        "smf_eligible": is_smf_eligible(section, classification),
        "hatecrime_eligible": is_hatecrime_eligible(section),
        "terrorism_eligible": is_fel and is_hatecrime_eligible(section),
        "dv_eligible": is_fel and section not in _DV_EXCLUDED_SECTIONS,
        "armed_eligible": is_fel,
        "yo_eligible": is_yo_eligible(classification),
        "predicate_exposure": has_predicate_exposure(classification),
    }


def _build_case_facts(req: ResolveRequest) -> CaseFacts:
    if req.predicate_vfos > req.predicate_felonies:
        raise ValueError("Violent predicates cannot exceed the number of predicate felonies")
    prior_kwargs: dict[str, Any] = {
        "prior_record": PriorRecord(
            predicate_felonies=req.predicate_felonies, predicate_vfos=req.predicate_vfos
        )
    }
    if req.prior_record_status and not (req.predicate_felonies or req.predicate_vfos):
        try:
            prior_kwargs = {"prior_record_status": PriorRecordStatus(req.prior_record_status)}
        except ValueError:
            pass  # unknown legacy value: keep the (empty) predicate record
    try:
        age = AgeCategory(req.defendant_age_category)
    except ValueError:
        age = AgeCategory.ADULT
    fields = req.model_dump(exclude={
        "predicate_felonies", "predicate_vfos", "prior_record_status", "defendant_age_category",
    })
    return CaseFacts(**fields, **prior_kwargs, defendant_age_category=age)


def _offense_or_raise(section: str) -> dict:
    off = get_all_offenses().get(section)
    if off is None:
        raise UnknownSection(f"Unknown section {section}")
    return off


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_offenses(q: str | None = None) -> list[dict]:
    items = [
        {
            "section": s,
            "name": o.get("name", ""),
            "classification": o.get("classification", "Violation"),
            "article": o.get("article", 0),
        }
        for s, o in get_all_offenses().items()
    ]
    items.sort(key=lambda t: (t["article"] or 0, t["section"]))
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["section"].lower() or ql in i["name"].lower()]
    return items


def offense_detail(section: str) -> dict:
    off = _offense_or_raise(section)
    classification = off.get("classification", "Violation")
    elig = _eligibility(section, classification)
    attempt_preview = None
    if off.get("isAttempt") and off.get("attemptOf"):
        target = get_all_offenses().get(off["attemptOf"])
        target_cls = target["classification"] if target else "Unknown"
        try:
            attempt_preview = {
                "target_section": off["attemptOf"],
                "target_classification": target_cls,
                "resolved": resolve_attempt_classification(off["attemptOf"], target_cls),
            }
        except Exception as e:
            attempt_preview = {"error": str(e)}
    return {
        "section": section,
        "name": off.get("name", ""),
        "classification": classification,
        "article": off.get("article", 0),
        "elements": off.get("elements"),
        "is_attempt": off.get("isAttempt", False),
        "attempt_of": off.get("attemptOf"),
        "is_conspiracy": off.get("isConspiracy", False),
        "conspiracy_of": off.get("conspiracyOf"),
        "conditional_classification": off.get("conditionalClassification"),
        "eligibility": elig,
        "attempt_preview": attempt_preview,
    }


def resolve(body: dict[str, Any]) -> dict:
    req = ResolveRequest.model_validate(body)
    _offense_or_raise(req.section)
    out = sentencing.resolve(req.section, _build_case_facts(req))
    data = out.model_dump(mode="json")
    data["report_markdown"] = render_report(out)
    return data


def default_report(section: str) -> str:
    """Resolve with default case facts and return just the markdown report."""
    _offense_or_raise(section)
    return render_report(sentencing.resolve(section, CaseFacts(section=section)))


# ---------------------------------------------------------------------------
# JSON-string entry point for Pyodide (avoids JsProxy <-> dict conversion).
# Offense lists/details are precomputed at build time by scripts/build_site.py.
# ---------------------------------------------------------------------------


def _call_json(fn, *args) -> str:
    try:
        return json.dumps({"ok": True, "data": fn(*args)})
    except UnknownSection as e:
        return json.dumps({"ok": False, "status": 404, "error": str(e.args[0])})
    except Exception as e:
        return json.dumps({"ok": False, "status": 400, "error": f"Engine error: {e}"})


def resolve_json(body_json: str) -> str:
    return _call_json(resolve, json.loads(body_json))
