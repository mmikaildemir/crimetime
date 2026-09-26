"""NYS Open Legislation API helpers — shared by the Streamlit app and the
batch ingestion pipeline.

Extracted from app.py so that both the interactive console and the
`scripts/ingest_offenses.py` CLI import from a single source of truth.

Key functions:
  - load_api_key()           — read OPEN_LEGISLATION_API_KEY from env
  - fetch_section(section)   — fetch one statute's full metadata + text
  - parse_classification(text) — extract the base classification from text
  - parse_article(section)   — derive article number from a section string
  - list_sections(law_id)     — list all section locationIds for a law (NEW)
  - find_all_classifications(text) — all distinct class matches (NEW, used to
                                     detect conditional offenses)
"""

from __future__ import annotations

import os
import re
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

OPEN_LEG_BASE = "https://legislation.nysenate.gov/api/3/laws"

# All classification enum values used in data/lists.json, ordered by severity
# (A-I felony down through violation). Used for dropdowns and validation.
CLASSIFICATIONS = [
    "ClassA_I_Felony", "ClassA_II_Felony",
    "ClassB_Felony", "ClassC_Felony", "ClassD_Felony", "ClassE_Felony",
    "ClassB_Violent_Felony", "ClassC_Violent_Felony",
    "ClassD_Violent_Felony", "ClassE_Violent_Felony",
    "ClassA_Misdemeanor", "ClassB_Misdemeanor", "Unclassified_Misdemeanor",
    "Violation",
]

# Maps statute text patterns to our classification enum. These match the
# CLASSIFICATION DECLARATION LINE specifically — the sentence at the end of
# a statute that says "<Offense name> is a class X felony/misdemeanor" or
# "is a violation". This avoids false matches on class mentions that appear
# inside definitional language (e.g. "previously convicted of a class A
# misdemeanor", "convicted of a class A or class B felony"). The 'is a'
# prefix distinguishes the declaration from incidental mentions.
CLASS_TEXT_MAP = {
    r"is\s+a\s+class\s+a[-\s]?i\s+felony": "ClassA_I_Felony",
    r"is\s+a\s+class\s+a[-\s]?ii\s+felony": "ClassA_II_Felony",
    r"is\s+a\s+class\s+b\s+felony": "ClassB_Felony",
    r"is\s+a\s+class\s+c\s+felony": "ClassC_Felony",
    r"is\s+a\s+class\s+d\s+felony": "ClassD_Felony",
    r"is\s+a\s+class\s+e\s+felony": "ClassE_Felony",
    r"is\s+a\s+class\s+a\s+misdemeanor": "ClassA_Misdemeanor",
    r"is\s+a\s+class\s+b\s+misdemeanor": "ClassB_Misdemeanor",
    r"is\s+a\s+violation(?!\s+of)": "Violation",
}


def load_api_key() -> str:
    """Read the NYS Open Legislation API key from the environment.

    The .env file stores it as OPEN_LEGISLATION_API_KEY='...' (with literal
    quotes). Strip quotes and whitespace.
    """
    return os.getenv("OPEN_LEGISLATION_API_KEY", "").strip().strip("'").strip('"')


def fetch_section(section: str, law_id: str = "PEN", api_key: Optional[str] = None) -> Optional[dict]:
    """Fetch a single statute's full metadata + text from the NYS API.

    Returns the 'result' object on success, or None on failure (bad key,
    network error, section not found). The result includes fields:
      locationId, title, docType, activeDate, text, parents, repealedDate
    (repealedDate is only present when the section has been repealed.)
    """
    key = api_key or load_api_key()
    if not key:
        return None
    try:
        resp = requests.get(
            f"{OPEN_LEG_BASE}/{law_id}/{section}",
            params={"key": key, "full": "true"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success"):
            return data.get("result")
    except Exception:
        pass
    return None


def parse_classification(statute_text: str) -> Optional[str]:
    """Parse the base classification from statute text.

    Statutes end with patterns like 'is a class E felony' or 'is a class A
    misdemeanor'. Finds the EARLIEST classification mention in the text — the
    base classification always appears before any conditional escalation
    clauses (e.g. subdivision-dependent class bumps).
    """
    # Normalize: replace literal \n (backslash + n) with spaces, collapse whitespace
    text = statute_text.replace("\\n", " ")
    text_lower = re.sub(r"\s+", " ", text.lower())
    best_match = None
    best_pos = len(text_lower)
    for pattern, classification in CLASS_TEXT_MAP.items():
        m = re.search(pattern, text_lower)
        if m and m.start() < best_pos:
            best_pos = m.start()
            best_match = classification
    return best_match


def parse_article(section: str) -> int:
    """Derive article number from a section string (e.g. '120.70' -> 120).

    Sections with letter suffixes (e.g. '130.65-a') still resolve correctly
    since only the part before '.' is examined.
    """
    parts = section.split(".")
    return int(parts[0]) if parts[0].isdigit() else 0


def find_all_classifications(statute_text: str) -> list[str]:
    """Return ALL distinct classifications declared in the text, in order of
    first appearance of their declaration line.

    A 'declaration line' is a sentence like "<Offense> is a class X felony" —
    the pattern in CLASS_TEXT_MAP. Incidental class mentions inside
    definitional language (e.g. "previously convicted of a class A
    misdemeanor") do NOT count, since they lack the "is a class" prefix.

    Used to detect conditional offenses: a statute with more than one
    declaration (e.g. subdivision-dependent classification) is a signal that
    the base classification alone may not tell the whole story and the
    offense should be flagged for manual review.
    """
    text = statute_text.replace("\\n", " ")
    text_lower = re.sub(r"\s+", " ", text.lower())
    # Find every declaration match with its position, sort by position,
    # dedupe preserving first-appearance order.
    matches: list[tuple[int, str]] = []
    for pattern, classification in CLASS_TEXT_MAP.items():
        for m in re.finditer(pattern, text_lower):
            matches.append((m.start(), classification))
    matches.sort(key=lambda t: t[0])
    seen: list[str] = []
    seen_set: set[str] = set()
    for _, cls in matches:
        if cls not in seen_set:
            seen.append(cls)
            seen_set.add(cls)
    return seen


def list_sections(law_id: str = "PEN", api_key: Optional[str] = None) -> list[str]:
    """List all section locationIds for a given law via the search endpoint.

    Returns the 897 PEN section locationIds (e.g. '120.02', '1.00') in one
    call. NOTE: sections with letter suffixes (e.g. '130.65-a', '230.34-a')
    are NOT returned by the search API — callers that need those must
    cross-reference against the existing offenses in data/lists.json.
    """
    key = api_key or load_api_key()
    if not key:
        return []
    try:
        resp = requests.get(
            f"{OPEN_LEG_BASE}/search",
            params={
                "term": f"lawId:{law_id} AND docType:SECTION",
                "key": key,
                "limit": 1000,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return []
        items = data.get("result", {}).get("items", [])
        locs: list[str] = []
        for item in items:
            inner = item.get("result", item)
            loc = inner.get("locationId")
            if loc:
                locs.append(loc)
        return locs
    except Exception:
        return []
