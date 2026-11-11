"""Tests for the admin tool's checks (webapp/admin_bridge.py)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from crimetime import reference
from webapp import admin_bridge as ab
from webapp import bridge

DATA = Path(__file__).resolve().parent.parent / "data"
LISTS = json.loads((DATA / "lists.json").read_text())
TABLES = json.loads((DATA / "sentencing_tables.json").read_text())
DRUG_B_SECOND = ("drugFelony", "statuses", "second_felony_drug_offender", "rows", "ClassB", "termYears")


@pytest.fixture(autouse=True)
def fresh_state():
    ab.load_published(copy.deepcopy(LISTS), copy.deepcopy(TABLES))
    yield
    reference.reset_data()


def _draft():
    return copy.deepcopy(LISTS), copy.deepcopy(TABLES)


def _set(obj, path, value):
    for k in path[:-1]:
        obj = obj[k]
    obj[path[-1]] = value


def test_live_data_has_no_errors():
    errors = [i for i in ab.validate(LISTS, TABLES, TABLES) if i["level"] == "error"]
    assert errors == []


def test_inverted_range_is_an_error():
    lists, tables = _draft()
    _set(tables, DRUG_B_SECOND, [12, 4])
    issues = ab.validate_tables(tables, TABLES)
    assert any("greater than maximum" in i["message"] for i in issues)


def test_text_in_number_field_and_empty_citation_are_errors():
    lists, tables = _draft()
    _set(tables, ("drugFelony", "statuses", "first_offender", "rows", "ClassC", "termYears"), ["one", 5])
    _set(tables, ("drugFelony", "statuses", "first_offender", "statute"), "  ")
    msgs = [i["message"] for i in ab.validate_tables(tables, TABLES)]
    assert "Statute citation cannot be empty" in msgs


def test_offense_checks():
    lists, _ = _draft()
    lists["offenses"]["999.99"] = {"article": 1, "section": "999.99", "name": "", "classification": "ClassZ"}
    lists["offenses"]["120.05"]["attemptOf"] = "1.00"
    lists["lists"]["SMF_LIST"]["sections"].append("888.88")
    msgs = {(i["where"], i["message"]) for i in ab.validate_offenses(lists)}
    assert ("Offense §999.99", "Name is required") in msgs
    assert ("Offense §999.99", "Unknown classification 'ClassZ'") in msgs
    assert ("Offense §999.99", "Article should be 999 for this section") in msgs
    assert ("Offense §120.05", "attemptOf points to §1.00, which is not an offense") in msgs
    assert ("SMF_LIST › sections", "§888.88 is listed but is not in the offense list") in msgs


def test_check_draft_marks_only_new_issues():
    lists, tables = _draft()
    _set(tables, DRUG_B_SECOND, [12, 4])
    ab.set_draft(lists, tables)
    out = json.loads(ab.check_draft_json())["data"]
    new = [i for i in out["issues"] if i["new"]]
    assert len(new) == 1 and "greater than maximum" in new[0]["message"]
    assert out["changes"] == [{
        "file": "Sentencing tables", "path": list(DRUG_B_SECOND), "old": [2, 12], "new": [12, 4],
    }]


def test_list_membership_change_is_reported_as_added_removed():
    lists, tables = _draft()
    lists["lists"]["SMF_LIST"]["sections"].remove("120.06")
    ab.set_draft(lists, tables)
    [change] = ab.data_changes((LISTS, TABLES), (lists, tables))
    assert change["removed"] == ["120.06"] and change["added"] == []


def test_offense_edit_scopes_impact_to_that_offense_and_its_attempts():
    lists, tables = _draft()
    lists["offenses"]["120.05"]["name"] = "Assault 2"
    secs = ab.affected_sections((LISTS, TABLES), (lists, tables))
    assert "120.05" in secs and "220.39" not in secs
    _, tables2 = _draft()
    _set(tables2, DRUG_B_SECOND, [4, 12])
    assert ab.affected_sections((LISTS, TABLES), (LISTS, tables2)) is None


def test_impact_reports_the_changed_drug_range():
    lists, tables = _draft()
    _set(tables, DRUG_B_SECOND, [4, 12])
    ab.set_draft(lists, tables)
    r = ab.impact()
    assert r["severe"] == 0
    secs = {g["section"] for g in r["groups"]}
    assert "220.39" in secs
    g = next(g for g in r["groups"] if g["section"] == "220.39")
    assert {"field": "Sentence option", "old": "Determinate sentence of 2–12 years",
            "new": "Determinate sentence of 4–12 years"} in g["changes"]
    assert "1 prior felony, no special circumstances" in g["scenarios"]
    # Non-drug offenses are untouched.
    assert "120.05" not in secs


def test_impact_flags_scenarios_that_start_failing():
    lists, tables = _draft()
    del tables["drugFelony"]["statuses"]["second_felony_drug_offender"]["rows"]["ClassB"]
    ab.set_draft(lists, tables)
    r = ab.impact()
    assert r["severe"] > 0
    assert r["groups"][0]["changes"][0]["severe"]


def test_unchanged_draft_has_no_impact():
    r = ab.impact()
    assert r["scenarios_changed"] == 0


def test_try_case_compares_live_and_draft():
    lists, tables = _draft()
    _set(tables, DRUG_B_SECOND, [4, 12])
    ab.set_draft(lists, tables)
    r = ab.try_case({"section": "220.39", "predicate_felonies": 1})
    assert r["live"]["available_dispositions"][0]["term"]["min_value"] == 2
    assert r["draft"]["available_dispositions"][0]["term"]["min_value"] == 4


def test_bundle_round_trip_and_formatting():
    manifest = {"version": "2026-01-01.1", "changes": []}
    z = ab.bundle(manifest)
    back = ab.read_bundle(z)
    assert back["lists"] == LISTS and back["tables"] == TABLES and back["manifest"] == manifest
    # The repo files are already in the bundle's format, so re-publishing unchanged data is a no-op diff.
    assert ab.dump_lists(LISTS) == (DATA / "lists.json").read_text()
    assert ab.dump_tables(TABLES) == (DATA / "sentencing_tables.json").read_text()


def test_read_bundle_rejects_other_zips():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "hi")
    with pytest.raises(ValueError, match="Not a CrimeTime data bundle"):
        ab.read_bundle(buf.getvalue())


def test_repealed_offense_is_hidden_from_public_list():
    lists, tables = _draft()
    lists["offenses"]["120.05"]["repealed"] = {"date": "2026-11-01", "note": "test"}
    reference.set_data(lists, tables)
    sections = {o["section"] for o in bridge.list_offenses()}
    assert "120.05" not in sections
    assert "120.05" in {o["section"] for o in bridge.list_offenses(include_repealed=True)}


def test_engine_settings_cannot_be_changed():
    _, tables = _draft()
    _set(tables, ("drugFelony", "statuses", "first_offender", "sentenceType"), "indeterminate")
    msgs = [i["message"] for i in ab.validate_tables(tables, TABLES)]
    assert any("engine setting" in m for m in msgs)
