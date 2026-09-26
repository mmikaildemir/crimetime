"""Tests for the ingestion pipeline — triage and merge logic.

Tests the helper functions in scripts/ingest_offenses.py without hitting
the live API (using cached statute text where needed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ingest_offenses import (
    _build_staging_entry,
    _detect_hard_case,
    _section_key,
)

from crimetime.legislation import find_all_classifications


# ---------------------------------------------------------------------------
# _section_key — numeric range comparison
# ---------------------------------------------------------------------------


class TestSectionKey:
    def test_simple(self):
        assert _section_key("140.10") == 140.10

    def test_with_suffix_strips(self):
        # '130.65-a' compares as 130.65
        assert _section_key("130.65-a") == 130.65

    def test_sort_order(self):
        sections = ["145.10", "140.05", "490.25", "265.02"]
        sorted_secs = sorted(sections, key=_section_key)
        assert sorted_secs == ["140.05", "145.10", "265.02", "490.25"]

    def test_range_filter(self):
        sections = ["100.00", "140.40", "140.41", "499.99", "500.00"]
        in_range = [s for s in sections if 140.40 < _section_key(s) <= 499.99]
        assert in_range == ["140.41", "499.99"]

    def test_non_numeric_returns_zero(self):
        assert _section_key("ABC") == 0.0


# ---------------------------------------------------------------------------
# _detect_hard_case — conditional offense flagging
# ---------------------------------------------------------------------------


class TestDetectHardCase:
    def test_straight_crime_no_flag(self):
        text = "Burglary in the third degree is a class D felony.\\n"
        classes = find_all_classifications(text)
        assert _detect_hard_case(text, classes) is None

    def test_conditional_offense_flagged(self):
        text = (
            "Theft of services is a class A misdemeanor. "
            "Subdivision two is a violation.\\n"
        )
        classes = find_all_classifications(text)
        assert _detect_hard_case(text, classes) == "conditional"

    def test_single_declaration_not_flagged(self):
        text = "Some offense is a class E felony.\\n"
        classes = find_all_classifications(text)
        assert _detect_hard_case(text, classes) is None

    def test_incidental_mention_not_flagged(self):
        # "convicted of a class A misdemeanor" is not a declaration,
        # so find_all_classifications returns only the real declaration,
        # so _detect_hard_case sees len == 1 and returns None.
        text = (
            "Previously convicted of a class A misdemeanor. "
            "This offense is a class D felony.\\n"
        )
        classes = find_all_classifications(text)
        assert _detect_hard_case(text, classes) is None


# ---------------------------------------------------------------------------
# _build_staging_entry — shape + staging-only fields
# ---------------------------------------------------------------------------


class TestBuildStagingEntry:
    def test_entry_has_required_fields(self):
        entry = _build_staging_entry(
            section="140.20",
            name="Burglary in the third degree",
            classification="ClassD_Felony",
            text="...is a class D felony.\\n",
            needs_review=None,
        )
        assert entry["section"] == "140.20"
        assert entry["article"] == 140
        assert entry["name"] == "Burglary in the third degree"
        assert entry["classification"] == "ClassD_Felony"
        assert entry["elements"] is None
        assert entry["isAttempt"] is False
        assert entry["attemptOf"] is None
        assert entry["isConspiracy"] is False
        assert entry["conspiracyOf"] is None

    def test_staging_only_fields_present(self):
        entry = _build_staging_entry(
            section="140.20",
            name="Burglary in the third degree",
            classification="ClassD_Felony",
            text="...is a class D felony.\\n",
            needs_review="conditional",
        )
        # These two fields are staging-only and must be stripped at merge
        assert entry["needsReview"] == "conditional"
        assert "raw_text_snippet" in entry

    def test_snippet_truncated(self):
        long_text = "x" * 500
        entry = _build_staging_entry(
            section="140.20",
            name="Test",
            classification="ClassD_Felony",
            text=long_text,
            needs_review=None,
        )
        assert len(entry["raw_text_snippet"]) <= 240
        assert entry["raw_text_snippet"].endswith("...")

    def test_snippet_normalizes_newlines(self):
        entry = _build_staging_entry(
            section="140.20",
            name="Test",
            classification="ClassD_Felony",
            text="line one\\nline two is a class D felony.",
            needs_review=None,
        )
        assert "\\n" not in entry["raw_text_snippet"]


# ---------------------------------------------------------------------------
# merge strips staging-only fields (integration)
# ---------------------------------------------------------------------------


class TestMergeStripsStagingFields:
    """Verify that the entry shape produced by _build_staging_entry, when
    stripped of staging-only fields, matches the offense shape in
    data/lists.json."""

    def test_stripped_entry_matches_lists_json_shape(self):
        entry = _build_staging_entry(
            section="140.20",
            name="Burglary in the third degree",
            classification="ClassD_Felony",
            text="...is a class D felony.\\n",
            needs_review=None,
        )
        # Simulate the merge strip
        merged = {
            k: v for k, v in entry.items()
            if k not in ("needsReview", "raw_text_snippet")
        }
        # Compare keys to an existing offense in lists.json
        lists = json.loads((REPO_ROOT / "data" / "lists.json").read_text())
        sample = list(lists["offenses"].values())[0]
        assert set(merged.keys()) == set(sample.keys()), (
            f"merged keys {set(merged.keys())} != "
            f"lists.json keys {set(sample.keys())}"
        )
