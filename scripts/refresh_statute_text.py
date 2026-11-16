"""Refresh data/statute_text.json — the statute text shown to legal reviewers.

    uv run python scripts/refresh_statute_text.py

Collects the text of every offense section in data/lists.json plus the
sentencing statutes the review packs cite (Article 70, 110.05, 10.00, ...).
It reads the ingestion cache (data/staging/cache/) first and only calls the
NYS Open Legislation API (OPEN_LEGISLATION_API_KEY in .env) for sections not
yet cached. The output is committed, so the site build and CI need no API key.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

from ingest_offenses import _fetch_with_cache, _load_cache  # noqa: E402

OUT = ROOT / "data" / "statute_text.json"

# Sentencing and definitional statutes cited by the review packs.
EXTRA_SECTIONS = [
    "10.00", "30.00", "60.01", "60.07", "60.10", "60.12", "60.21", "60.35", "65.00", "65.05", "65.20",
    "70.00", "70.02", "70.04", "70.05", "70.06", "70.08", "70.10", "70.15", "70.45", "70.70",
    "70.71", "70.80", "80.00", "80.05", "110.00", "110.05", "130.91", "485.05", "485.10", "490.25",
]


def main() -> None:
    load_dotenv(ROOT / ".env")
    lists = json.loads((ROOT / "data" / "lists.json").read_text())
    sections = sorted(set(lists["offenses"]) | set(EXTRA_SECTIONS))
    out: dict[str, dict] = {}
    fetched = missing = 0
    for section in sections:
        cached = _load_cache(section) is not None
        result = _fetch_with_cache(section)
        if not cached:
            fetched += 1
            time.sleep(0.3)
        if not result or not result.get("text"):
            missing += 1
            continue
        out[section] = {
            "title": result.get("title", ""),
            "activeDate": result.get("activeDate", ""),
            "text": result["text"].replace("\\n", "\n").strip(),
        }
    OUT.write_text(json.dumps(out, indent=0, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(out)} sections "
          f"({fetched} fetched from the API, {missing} unavailable)")


if __name__ == "__main__":
    main()
