"""Tests for webapp/bridge.py — the engine entry points used by the static site (Pyodide)."""

import json

import pytest

from webapp import bridge


def test_list_offenses_sorted_and_filterable():
    items = bridge.list_offenses()
    assert len(items) > 500
    keys = [(i["article"] or 0, i["section"]) for i in items]
    assert keys == sorted(keys)
    assert all("assault" in i["name"].lower() or "assault" in i["section"] for i in bridge.list_offenses("assault"))


def test_offense_detail_eligibility():
    d = bridge.offense_detail("120.05")
    assert d["eligibility"]["is_felony"] and d["eligibility"]["vfo"]
    assert d["eligibility"]["predicate_exposure"]


def test_offense_detail_unknown_section():
    with pytest.raises(bridge.UnknownSection):
        bridge.offense_detail("999.99")


def test_resolve_includes_report():
    out = bridge.resolve({"section": "120.05"})
    assert out["classification"] == "ClassD_Felony"
    assert out["report_markdown"].startswith("# Sentencing Options Memorandum")


def test_resolve_passes_armed_felony_flags():
    facts = bridge._build_case_facts(bridge.ResolveRequest(
        section="265.03",
        plea_from_armed_felony_indictment=True,
        armed_felony_mitigating_factor=True,
    ))
    assert facts.plea_from_armed_felony_indictment and facts.armed_felony_mitigating_factor


def test_resolve_bad_enum_falls_back_to_defaults():
    facts = bridge._build_case_facts(bridge.ResolveRequest(
        section="120.05", prior_record_status="nope", defendant_age_category="nope"))
    assert facts.prior_record.predicate_felonies == 0
    assert facts.defendant_age_category.value == "adult"


def test_resolve_predicate_counts_derive_offender_status():
    out = bridge.resolve({"section": "220.39", "predicate_felonies": 1, "predicate_vfos": 1})
    assert out["offender_status"] == "second_felony_drug_offender_prior_vfo"
    assert out["available_dispositions"][0]["statute_refs"] == ["PL 70.70(4)"]
    assert out["available_dispositions"][0]["term"]["min_value"] == 6


def test_legacy_status_matches_predicate_counts():
    legacy = bridge.resolve({"section": "120.05", "prior_record_status": "second_violent_felony_offender_70_04"})
    facts = bridge.resolve({"section": "120.05", "predicate_felonies": 1, "predicate_vfos": 1})
    assert {k: v for k, v in legacy.items() if k != "report_markdown"} == \
        {k: v for k, v in facts.items() if k != "report_markdown"}


def test_resolve_rejects_more_vfos_than_felonies():
    out = json.loads(bridge.resolve_json(json.dumps(
        {"section": "120.05", "predicate_felonies": 1, "predicate_vfos": 2})))
    assert not out["ok"] and out["status"] == 400
    assert "cannot exceed" in out["error"]


def test_resolve_json_envelope():
    ok = json.loads(bridge.resolve_json(json.dumps({"section": "240.20"})))
    assert ok["ok"] and ok["data"]["section"] == "240.20"
    missing = json.loads(bridge.resolve_json(json.dumps({"section": "999.99"})))
    assert missing == {"ok": False, "status": 404, "error": "Unknown section 999.99"}
    bad = json.loads(bridge.resolve_json(json.dumps({"section": "120.05", "is_attempt": "maybe"})))
    assert not bad["ok"] and bad["status"] == 400
