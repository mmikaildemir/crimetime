"""CrimeTime — Batch offense ingestion pipeline.

Triage all NYS Penal Law sections, auto-add the straightforward ones to a
staging file, flag the hard cases (attempt / conspiracy / conditional
classification) for manual review, then merge approved entries into
data/lists.json. No autonomous writes to the source of truth.

Subcommands:
  discover   Fetch + triage all PEN sections, write staging file
  review     Print a human review report from the staging file
  merge      Merge approved staging entries into data/lists.json

Usage:
  python scripts/ingest_offenses.py discover
  python scripts/ingest_offenses.py review
  python scripts/ingest_offenses.py merge --dry-run
  python scripts/ingest_offenses.py merge --only 140.10,140.15
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

# Make the crimetime package importable when running the script directly
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from crimetime.legislation import (
    fetch_section,
    find_all_classifications,
    list_sections,
    parse_article,
    parse_classification,
)

DATA_DIR = _REPO_ROOT / "data"
LISTS_PATH = DATA_DIR / "lists.json"
STAGING_DIR = DATA_DIR / "staging"
STAGING_PATH = STAGING_DIR / "new_offenses.json"
CACHE_DIR = STAGING_DIR / "cache"

# Default scan window: articles 100-499 are the substantive offenses.
# Skips Art 1-40 (general provisions/defenses), 70 (sentencing), 80 (sealing),
# 85 (registration). Overridable via --from / --to (numeric section comparison).
DEFAULT_FROM = 100.00
DEFAULT_TO = 499.99

# Politeness delay between uncached API calls (seconds)
FETCH_DELAY = 0.15

# Regexes for detecting hard cases that should NOT be auto-added.
#
# NOTE: attempt/conspiracy detection via statute text was removed — it produced
# false positives because completed offenses routinely mention "attempt to
# commit" / "conspiracy to commit" in their definitional language (e.g.
# "with intent to commit or attempt to commit any felony"). The isAttempt /
# isConspiracy flags in data/lists.json are only set on charging variants tied
# to a named target, which are not separate statute sections. Article 105
# (conspiracy) and Article 110 (attempt) sections are themselves completed
# degree offenses and are added as regular offenses (matching the existing
# convention where 105.05 etc. are marked isConspiracy: false).
#
# The only remaining hard-case signal is CONDITIONAL classification: text that
# mentions >1 distinct classification, indicating subdivision-dependent class.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _section_key(section: str) -> float:
    """Convert a section string to a float for numeric range comparison.

    '140.10' -> 140.10, '130.65-a' -> 130.65. Sections with letter suffixes
    lose the suffix for comparison purposes (the suffix is a subdivision
    marker, not part of the article ordering).
    """
    base = section.split("-")[0]
    try:
        return float(base)
    except ValueError:
        return 0.0


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _cache_path(section: str) -> Path:
    # Sanitize section for filename (replace any non-alnum/dot/dash)
    safe = re.sub(r"[^0-9A-Za-z.\-]", "_", section)
    return CACHE_DIR / f"{safe}.json"


def _load_cache(section: str) -> dict | None:
    p = _cache_path(section)
    if p.exists():
        try:
            return _load_json(p)
        except Exception:
            return None
    return None


def _save_cache(section: str, result: dict) -> None:
    _save_json(_cache_path(section), result)


def _fetch_with_cache(section: str, force: bool = False) -> dict | None:
    """Fetch a section, using disk cache unless --force. Returns the API
    'result' object (with text, title, etc.) or None."""
    if not force:
        cached = _load_cache(section)
        if cached is not None:
            return cached
    result = fetch_section(section)
    if result is not None:
        _save_cache(section, result)
    return result


def _detect_hard_case(text: str, all_classes: list[str]) -> str | None:
    """Return a review flag string if this offense should NOT be auto-added.

    Reasons:
      'conditional'   — text mentions >1 distinct classification (likely
                         subdivision-dependent class; base class alone is
                         incomplete)
    Returns None for straight crimes that are safe to auto-add.
    """
    if len(all_classes) > 1:
        return "conditional"
    return None


def _build_staging_entry(
    section: str, name: str, classification: str, text: str, needs_review: str | None
) -> dict:
    """Build a staging entry in the same shape as data/lists.json offenses,
    plus two staging-only fields (stripped at merge): needsReview + raw_text_snippet.
    """
    snippet = text.replace("\\n", " ").strip()
    if len(snippet) > 240:
        snippet = snippet[:237] + "..."
    return {
        "article": parse_article(section),
        "section": section,
        "name": name,
        "classification": classification,
        "elements": None,
        "isAttempt": False,
        "attemptOf": None,
        "isConspiracy": False,
        "conspiracyOf": None,
        "needsReview": needs_review,
        "raw_text_snippet": snippet,
    }


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


def cmd_discover(args: argparse.Namespace) -> int:
    """Fetch + triage all PEN sections in the configured range, write staging."""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    existing = _load_json(LISTS_PATH)
    existing_offenses = existing.get("offenses", {})
    existing_sections = set(existing_offenses.keys())

    from_val = args.from_sec
    to_val = args.to_sec

    print(f"Listing all PEN sections from API...", file=sys.stderr)
    all_sections = list_sections("PEN")
    print(f"  API returned {len(all_sections)} sections", file=sys.stderr)

    # The search API does not return sections with letter suffixes (e.g.
    # '130.65-a'). Cross-reference existing offenses so any suffixed sections
    # we already track are still deduped — but we cannot discover new suffixed
    # sections this way. Documented as a known API limitation.
    all_known = set(all_sections) | existing_sections

    in_range = [
        s for s in all_known
        if from_val <= _section_key(s) <= to_val
    ]
    in_range = sorted(set(in_range), key=_section_key)
    print(
        f"  In range [{from_val}, {to_val}]: {len(in_range)} sections",
        file=sys.stderr,
    )

    new_offenses: dict[str, dict] = {}
    counts = Counter()
    fetches = 0

    for section in in_range:
        if section in existing_sections:
            counts["already_present"] += 1
            continue

        was_cached = (not args.force) and _load_cache(section) is not None
        result = _fetch_with_cache(section, force=args.force)
        if result is None:
            counts["fetch_failed"] += 1
            continue
        # Politeness delay only on uncached fetches
        if not was_cached:
            time.sleep(FETCH_DELAY)
        fetches += 1
        if fetches % 25 == 0:
            print(
                f"  ...processed {fetches} sections "
                f"({counts['crime']} crimes, {counts['non_crime']} non-crimes, "
                f"{counts['needs_review']} flagged)",
                file=sys.stderr,
            )

        # Skip repealed sections
        if result.get("repealedDate"):
            counts["repealed"] += 1
            continue

        text = result.get("text", "") or ""
        name = result.get("title", "") or ""
        classification = parse_classification(text)

        if classification is None:
            counts["non_crime"] += 1
            continue

        all_classes = find_all_classifications(text)
        needs_review = _detect_hard_case(text, all_classes)

        entry = _build_staging_entry(
            section, name, classification, text, needs_review
        )
        new_offenses[section] = entry
        if needs_review:
            counts["needs_review"] += 1
        else:
            counts["crime"] += 1

    # Write staging file with a summary header
    staging = {
        "schema": {"version": "0.1", "type": "staging"},
        "summary": {
            "from": from_val,
            "to": to_val,
            "total_scanned": len(in_range),
            "already_present": counts["already_present"],
            "non_crime_skipped": counts["non_crime"],
            "fetch_failed": counts["fetch_failed"],
            "repealed": counts["repealed"],
            "new_crimes": counts["crime"],
            "needs_review": counts["needs_review"],
            "total_new": counts["crime"] + counts["needs_review"],
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "offenses": new_offenses,
    }
    _save_json(STAGING_PATH, staging)

    print(file=sys.stderr)
    print("=== Discover summary ===")
    for k, v in staging["summary"].items():
        print(f"  {k:>20}: {v}")
    print(f"\nStaging written to {STAGING_PATH}")
    cache_count = len(list(CACHE_DIR.glob("*.json")))
    print(f"Cache: {CACHE_DIR} ({cache_count} files)")
    return 0


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------


def cmd_review(args: argparse.Namespace) -> int:
    """Print a human review report from the staging file."""
    if not STAGING_PATH.exists():
        print(f"No staging file at {STAGING_PATH}. Run `discover` first.")
        return 1

    staging = _load_json(STAGING_PATH)
    offenses = staging.get("offenses", {})
    summary = staging.get("summary", {})

    print("=== Staging summary ===")
    for k, v in summary.items():
        print(f"  {k:>20}: {v}")

    if not offenses:
        print("\nNo offenses in staging.")
        return 0

    class_counts = Counter(
        o["classification"] for o in offenses.values()
    )
    print("\n=== New offenses by classification ===")
    for cls, n in sorted(class_counts.items()):
        print(f"  {cls:>25}: {n}")

    flagged = {
        s: o for s, o in offenses.items() if o.get("needsReview")
    }
    print(f"\n=== Flagged for manual review ({len(flagged)}) ===")
    if not flagged:
        print("  (none — all new offenses are straight crimes)")
    for section in sorted(flagged, key=_section_key):
        o = flagged[section]
        print(
            f"  §{section}  {o['name']}  [{o['classification']}]  "
            f"-> {o['needsReview']}"
        )

    if args.report:
        report_path = STAGING_DIR / "review_report.md"
        with open(report_path, "w") as f:
            f.write("# Staging review report\n\n")
            f.write("## Summary\n\n")
            for k, v in summary.items():
                f.write(f"- **{k}**: {v}\n")
            f.write("\n## Offenses by classification\n\n")
            for cls, n in sorted(class_counts.items()):
                f.write(f"- {cls}: {n}\n")
            f.write(f"\n## Flagged for manual review ({len(flagged)})\n\n")
            if not flagged:
                f.write("_(none)_\n")
            for section in sorted(flagged, key=_section_key):
                o = flagged[section]
                f.write(
                    f"- §{section} {o['name']} [{o['classification']}] "
                    f"— {o['needsReview']}\n"
                )
        print(f"\nReport written to {report_path}")
    return 0


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------


def cmd_merge(args: argparse.Namespace) -> int:
    """Merge approved staging entries into data/lists.json.

    Default is --dry-run (no writes). Without --only, merges every entry
    where needsReview is None (the auto-approvable straight crimes).
    """
    if not STAGING_PATH.exists():
        print(f"No staging file at {STAGING_PATH}. Run `discover` first.")
        return 1

    staging = _load_json(STAGING_PATH)
    staging_offenses = staging.get("offenses", {})

    if args.only:
        allow = {s.strip() for s in args.only.split(",") if s.strip()}
        candidates = {
            s: o for s, o in staging_offenses.items() if s in allow
        }
        missing = allow - set(candidates)
        if missing:
            print(f"WARNING: not in staging: {sorted(missing)}")
    else:
        candidates = {
            s: o for s, o in staging_offenses.items()
            if not o.get("needsReview")
        }

    if not candidates:
        print("No candidates to merge.")
        return 0

    lists_data = _load_json(LISTS_PATH)
    offenses = lists_data.setdefault("offenses", {})
    before = len(offenses)

    already = sorted(
        s for s in candidates if s in offenses
    )
    if already:
        print(f"WARNING: already in lists.json (will skip): {already}")

    to_merge = {
        s: o for s, o in candidates.items() if s not in offenses
    }

    # Show what would merge
    print(f"=== Merge ({'DRY RUN' if args.dry_run else 'LIVE'}) ===")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Already present (skip): {len(already)}")
    print(f"  To merge: {len(to_merge)}")
    print(f"  Offenses before: {before}")
    print(f"  Offenses after:  {before + len(to_merge)}")

    for section in sorted(to_merge, key=_section_key):
        o = to_merge[section]
        print(f"  + §{section}  {o['name']}  [{o['classification']}]")

    # Sanity check: derived flags for each entry
    try:
        from crimetime.resolvers import (
            is_vfo, is_smf_eligible, is_hatecrime_eligible,
            has_predicate_exposure, is_yo_eligible,
        )
        print("\n  Sanity check (derived flags):")
        for section in sorted(to_merge, key=_section_key):
            o = to_merge[section]
            c = o["classification"]
            flags = {
                "VFO": is_vfo(section, c),
                "SMF": is_smf_eligible(section, c),
                "HC": is_hatecrime_eligible(section),
                "Pred": has_predicate_exposure(c),
                "YO": is_yo_eligible(c),
            }
            # Heuristic: a ClassD felony not in VFO_LIST may be surprising
            # (most Art 120-140 D-felonies are VFOs). Flag for eyeball.
            warning = ""
            if c == "ClassD_Felony" and not flags["VFO"]:
                warning = "  <- ClassD felony NOT in VFO_LIST (verify)"
            flag_str = " ".join(f"{k}={v}" for k, v in flags.items())
            print(f"    §{section}: {flag_str}{warning}")
    except Exception as e:
        print(f"  (sanity check skipped: {e})")

    if args.dry_run:
        print("\nDry run — no changes written. Re-run without --dry-run to apply.")
        return 0

    # Apply: strip staging-only fields, insert into lists.json offenses
    for section, o in to_merge.items():
        entry = {k: v for k, v in o.items() if k not in ("needsReview", "raw_text_snippet")}
        offenses[section] = entry

    _save_json(LISTS_PATH, lists_data)
    print(f"\nMerged {len(to_merge)} offenses into {LISTS_PATH}")
    print("Commit when satisfied:")
    print(f"  git add {LISTS_PATH.relative_to(_REPO_ROOT)} && git commit -m \"Add ... offenses via ingestion pipeline\"")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ingest_offenses",
        description="Batch offense ingestion pipeline for CrimeTime.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pd = sub.add_parser("discover", help="Fetch + triage PEN sections, write staging")
    pd.add_argument(
        "--from", dest="from_sec", type=float, default=DEFAULT_FROM,
        metavar="SECTION",
        help=f"Lower section bound (numeric, default {DEFAULT_FROM})",
    )
    pd.add_argument(
        "--to", dest="to_sec", type=float, default=DEFAULT_TO,
        metavar="SECTION",
        help=f"Upper section bound (numeric, default {DEFAULT_TO})",
    )
    pd.add_argument(
        "--force", action="store_true",
        help="Re-fetch even if a cached response exists",
    )
    pd.set_defaults(func=cmd_discover)

    pr = sub.add_parser("review", help="Print a review report from staging")
    pr.add_argument(
        "--report", action="store_true",
        help="Also write data/staging/review_report.md",
    )
    pr.set_defaults(func=cmd_review)

    pm = sub.add_parser("merge", help="Merge approved staging entries into lists.json")
    pm.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Show what would be merged without writing (default)",
    )
    pm.add_argument(
        "--no-dry-run", dest="dry_run", action="store_false",
        help="Actually write the merge to lists.json",
    )
    pm.add_argument(
        "--only", metavar="SECTIONS",
        help="Comma-separated allowlist of sections to merge (e.g. 140.10,140.15)",
    )
    pm.set_defaults(func=cmd_merge)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
