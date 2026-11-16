"""Per-crime review sheets (webapp/review_bridge.py) and the answers report."""

import copy
import sys
from pathlib import Path

import pytest

from crimetime import reference
from webapp import review_bridge as rb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import import_reviews  # noqa: E402


@pytest.fixture(scope="module")
def sheets():
    reference.reset_data()
    return rb.build_sheets()


@pytest.fixture(autouse=True)
def _reset():
    yield
    reference.reset_data()


def by_section(sheets):
    return {s["section"]: s for s in sheets["sheets"]}


def lines(sheet):
    return {ln["key"]: ln["value"] for ln in sheet["lines"]}


def test_one_sheet_per_current_offense(sheets):
    current = [s for s, o in reference.get_all_offenses().items() if not o.get("repealed") and not o.get("isAttempt")]
    assert sheets["count"] == len(current) == len(sheets["sheets"])
    assert len({s["section"] for s in sheets["sheets"]}) == sheets["count"]


def test_felony_sheet_covers_the_questions_reviewers_check(sheets):
    ln = lines(by_section(sheets)["120.05"])
    for key in ("class", "vfo", "hate", "attempt", "juvenile", "sentence_0", "sentence_1v", "sentence_2v"):
        assert key in ln
    assert ln["vfo"] == "Yes"
    assert ln["attempt"].startswith("Allowed")


def test_misdemeanor_sheet_shows_attempt_failure(sheets):
    ln = lines(by_section(sheets)["120.15"])
    assert "juvenile" not in ln and "sentence_1" not in ln
    assert "no result" in ln["attempt"]


def test_partial_subdivision_listing_is_spelled_out(sheets):
    ln = lines(by_section(sheets)["125.15"])
    assert ln["hate"] == "Yes, but only subdivision 1"
    assert "hate crime: no" in ln["subdivision_3"]


def test_hash_changes_only_for_affected_crimes(sheets):
    before = by_section(sheets)
    tables = copy.deepcopy(reference._load_sentencing())
    tables["violentFelony"]["statuses"]["first_offender"]["rows"]["ClassD"]["termYears"] = [2, 8]
    reference.set_data(tables=tables)
    after = {s["section"]: s for s in (rb.sheet(sec, reference.get_offense(sec)) for sec in ("120.05", "155.30"))}
    assert after["120.05"]["hash"] != before["120.05"]["hash"]
    assert after["155.30"]["hash"] == before["155.30"]["hash"]


def test_report_lists_wrong_lines_and_stale_answers(sheets):
    d = by_section(sheets)
    review = {
        "format": "crimetime-legal-review", "_file": "a.json", "reviewer": {"name": "Reviewer A"},
        "answers": {
            "125.15": {"done": True, "hash": d["125.15"]["hash"],
                       "wrong": {"attempt": "Not cognizable: reckless (People v. Campbell)"}},
            "120.05": {"done": True, "hash": d["120.05"]["hash"], "wrong": {}},
            "155.30": {"done": True, "hash": "oldhash", "wrong": {}},
        },
    }
    report = import_reviews.build_report([review], sheets)
    assert "**2 of" in report
    assert "### §125.15 Manslaughter in the second degree" in report
    assert "Should be: Not cognizable" in report
    assert "§155.30" in report.split("## Out of date")[1]
    assert "§120.05" in report.split("## Crimes checked and found correct")[1]
