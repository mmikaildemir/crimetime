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
    values = [o["value"] for o in d["prior_status_options"]]
    assert "second_violent_felony_offender_70_04" in values


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
    assert facts.prior_record_status.value == "first_offender"
    assert facts.defendant_age_category.value == "adult"


def test_resolve_json_envelope():
    ok = json.loads(bridge.resolve_json(json.dumps({"section": "240.20"})))
    assert ok["ok"] and ok["data"]["section"] == "240.20"
    missing = json.loads(bridge.resolve_json(json.dumps({"section": "999.99"})))
    assert missing == {"ok": False, "status": 404, "error": "Unknown section 999.99"}
    bad = json.loads(bridge.resolve_json(json.dumps({"section": "120.05", "is_attempt": "maybe"})))
    assert not bad["ok"] and bad["status"] == 400
