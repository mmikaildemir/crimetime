"""Tests for crimetime.legislation — statute fetching and classification parsing.

These tests cover the extracted legislation helpers (formerly inline in
app.py) and the new list_sections / find_all_classifications functions.
Where possible we test against cached statute text from data/staging/cache/
to avoid hitting the live API.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crimetime.legislation import (
    CLASSIFICATIONS,
    CLASS_TEXT_MAP,
    find_all_classifications,
    parse_article,
    parse_classification,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "staging" / "cache"


# ---------------------------------------------------------------------------
# parse_classification — the core regex that extracts the base class
# ---------------------------------------------------------------------------


class TestParseClassification:
    """parse_classification must find the DECLARATION line, not incidental
    class mentions inside definitional language."""

    def test_class_d_felony_declaration(self):
        text = "§ 140.20 Burglary in the third degree. A person is guilty... Burglary in the third degree is a class D felony.\\n"
        assert parse_classification(text) == "ClassD_Felony"

    def test_class_b_misdemeanor_declaration(self):
        text = "Criminal trespass in the third degree is a class B misdemeanor.\\n"
        assert parse_classification(text) == "ClassB_Misdemeanor"

    def test_violation_declaration(self):
        # The negative lookahead (?!\s+of) prevents matching "violation of"
        text = "Trespass is a violation.\\n"
        assert parse_classification(text) == "Violation"

    def test_violation_of_not_matched(self):
        # "is a violation of" should NOT classify as Violation
        text = "This section is a violation of the public trust.\\n"
        assert parse_classification(text) is None

    def test_class_a_i_felony(self):
        text = "Murder in the second degree is a class A-I felony.\\n"
        assert parse_classification(text) == "ClassA_I_Felony"

    def test_class_a_ii_felony(self):
        text = "Some offense is a class A-II felony.\\n"
        assert parse_classification(text) == "ClassA_II_Felony"

    def test_non_crime_returns_none(self):
        # §1.00 "Short title" has no classification declaration line
        text = '§ 1.00 Short title. This chapter shall be known as the "Penal Law."\\n'
        assert parse_classification(text) is None

    def test_ignores_incidental_class_mention(self):
        # The prior-conviction language "convicted of a class A misdemeanor"
        # must NOT be picked up as the offense's own classification. The
        # declaration line "is a class D felony" at the end is the truth.
        text = (
            "Possesses a firearm and has been previously convicted of a felony "
            "or a class A misdemeanor defined in this chapter. "
            "Criminal possession of a weapon in the third degree is a class D felony.\\n"
        )
        assert parse_classification(text) == "ClassD_Felony"

    def test_ignores_class_mention_in_or_clause(self):
        # "convicted of a class A or class B felony" is not a declaration.
        text = (
            "Having been arrested for, charged with or convicted of a class A "
            "or class B felony, he escapes from custody. "
            "Escape in the first degree is a class D felony.\\n"
        )
        assert parse_classification(text) == "ClassD_Felony"

    def test_literal_newlines_normalized(self):
        # The API returns literal "\\n" (backslash + n); the parser must
        # normalize them to spaces before regex matching.
        text = "Burglary in the third degree is a class D felony.\\n"
        assert parse_classification(text) == "ClassD_Felony"


class TestParseClassificationCached:
    """Test parse_classification against real cached statute text."""

    @pytest.mark.parametrize("section,expected", [
        ("140.10", "ClassB_Misdemeanor"),  # Criminal trespass 3rd
        ("140.20", "ClassD_Felony"),       # Burglary 3rd
        ("140.25", "ClassC_Felony"),       # Burglary 2nd
        ("140.30", "ClassB_Felony"),       # Burglary 1st
        ("140.35", "ClassA_Misdemeanor"),  # Possession of burglar's tools
        ("140.40", "ClassB_Misdemeanor"),  # Unlawful possession of radio devices
        ("265.02", "ClassD_Felony"),       # Weapon possession 3rd (was misclassified before fix)
        ("205.15", "ClassD_Felony"),       # Escape 1st (was misclassified before fix)
    ])
    def test_cached_section(self, section, expected):
        cache_path = CACHE_DIR / f"{section}.json"
        if not cache_path.exists():
            pytest.skip(f"no cache for §{section} (run discover first)")
        data = json.loads(cache_path.read_text())
        assert parse_classification(data["text"]) == expected


# ---------------------------------------------------------------------------
# find_all_classifications — conditional offense detection
# ---------------------------------------------------------------------------


class TestFindAllClassifications:
    def test_single_declaration_returns_one(self):
        text = "Burglary in the third degree is a class D felony.\\n"
        result = find_all_classifications(text)
        assert result == ["ClassD_Felony"]

    def test_multiple_declarations_detected(self):
        # Conditional offense: base + subdivision-dependent escalation
        text = (
            "Theft of services is a class A misdemeanor. "
            "Subdivision two is a violation. "
            "Subdivision five is a class E felony.\\n"
        )
        result = find_all_classifications(text)
        assert len(result) == 3
        assert "ClassA_Misdemeanor" in result
        assert "Violation" in result
        assert "ClassE_Felony" in result

    def test_first_appearance_order(self):
        # The first declaration in the text should be first in the list
        text = (
            "Some offense is a class E felony. "
            "Subdivision two is a class B felony.\\n"
        )
        result = find_all_classifications(text)
        assert result[0] == "ClassE_Felony"
        assert result[1] == "ClassB_Felony"

    def test_incidental_mentions_not_counted(self):
        # "convicted of a class A misdemeanor" is not a declaration
        text = (
            "Previously convicted of a class A misdemeanor defined in this chapter. "
            "This offense is a class D felony.\\n"
        )
        result = find_all_classifications(text)
        assert result == ["ClassD_Felony"]

    def test_no_declaration_returns_empty(self):
        text = "§ 1.00 Short title. This chapter shall be known as the Penal Law.\\n"
        assert find_all_classifications(text) == []

    def test_conditional_cached(self):
        cache_path = CACHE_DIR / "165.15.json"
        if not cache_path.exists():
            pytest.skip("no cache for §165.15")
        data = json.loads(cache_path.read_text())
        result = find_all_classifications(data["text"])
        assert len(result) > 1, "§165.15 (theft of services) should be conditional"


# ---------------------------------------------------------------------------
# parse_article
# ---------------------------------------------------------------------------


class TestParseArticle:
    def test_simple_section(self):
        assert parse_article("120.02") == 120

    def test_section_with_suffix(self):
        assert parse_article("130.65-a") == 130

    def test_single_digit_article(self):
        assert parse_article("1.00") == 1

    def test_high_article(self):
        assert parse_article("490.25") == 490

    def test_non_numeric_returns_zero(self):
        assert parse_article("ABC") == 0


# ---------------------------------------------------------------------------
# CLASSIFICATIONS + CLASS_TEXT_MAP integrity
# ---------------------------------------------------------------------------


class TestClassificationConstants:
    def test_classifications_has_14_entries(self):
        # A-I, A-II, B/C/D/E felony, B/C/D/E violent felony, A/B misdemeanor,
        # unclassified misdemeanor, violation = 14
        assert len(CLASSIFICATIONS) == 14

    def test_violation_in_classifications(self):
        assert "Violation" in CLASSIFICATIONS

    def test_class_text_map_covers_all_felony_classes(self):
        felony_classes = {
            "ClassA_I_Felony", "ClassA_II_Felony",
            "ClassB_Felony", "ClassC_Felony", "ClassD_Felony", "ClassE_Felony",
        }
        mapped = set(CLASS_TEXT_MAP.values())
        assert felony_classes.issubset(mapped)

    def test_class_text_map_covers_misdemeanors_and_violation(self):
        assert CLASS_TEXT_MAP  # non-empty
        values = set(CLASS_TEXT_MAP.values())
        assert "ClassA_Misdemeanor" in values
        assert "ClassB_Misdemeanor" in values
        assert "Violation" in values
