"""Turn reviewers' answer files into one report.

    uv run python scripts/import_reviews.py                  # reviews/incoming/*.json -> reviews/report.md
    uv run python scripts/import_reviews.py a.json b.json    # specific files
    uv run python scripts/import_reviews.py --out other.md

Reviewers check crimes one by one on the site's /review/ page, download their
answers and email the file back. Put the files in reviews/incoming/
(gitignored: they contain reviewer names). The report lists every line a
reviewer marked wrong, with what they say it should be, grouped by crime.
Answers given before the calculator's output for that crime changed are
listed separately as out of date.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from webapp.review_bridge import build_sheets  # noqa: E402

INCOMING = ROOT / "reviews" / "incoming"
DEFAULT_OUT = ROOT / "reviews" / "report.md"


def load_reviews(paths: list[Path]) -> list[dict]:
    reviews = []
    for p in paths:
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"skip {p.name}: {e}", file=sys.stderr)
            continue
        if data.get("format") != "crimetime-legal-review" or not isinstance(data.get("answers"), dict):
            print(f"skip {p.name}: not a CrimeTime review file", file=sys.stderr)
            continue
        data["_file"] = p.name
        reviews.append(data)
    return reviews


def build_report(reviews: list[dict], sheets: dict) -> str:
    by_section = {s["section"]: s for s in sheets["sheets"]}
    who = lambda r: (r.get("reviewer") or {}).get("name") or r["_file"]  # noqa: E731

    checked: dict[str, list[str]] = {}
    problems: list[tuple[dict, str, dict]] = []  # (sheet, reviewer, answer)
    stale: list[tuple[str, str]] = []
    for r in reviews:
        for sec, a in r["answers"].items():
            sheet = by_section.get(sec)
            if sheet is None or not a.get("done"):
                continue
            if a.get("hash") != sheet["hash"]:
                stale.append((sec, who(r)))
                continue
            checked.setdefault(sec, []).append(who(r))
            if a.get("wrong") or a.get("comment"):
                problems.append((sheet, who(r), a))

    lines = [
        "# CrimeTime legal review — report",
        "",
        f"Data `{sheets['data_version']}`. {len(reviews)} reviewer file(s): "
        + ", ".join(f"{who(r)} ({sum(1 for a in r['answers'].values() if a.get('done'))} crimes)" for r in reviews) + ".",
        "",
        f"**{len(checked)} of {sheets['count']} crimes checked.** "
        f"{len({s['section'] for s, _, a in problems if a.get('wrong')})} have at least one line marked wrong.",
        "",
        "## Lines marked wrong",
    ]
    last = None
    for sheet, reviewer, a in sorted(problems, key=lambda t: list(by_section).index(t[0]["section"])):
        if sheet["section"] != last:
            lines += ["", f"### §{sheet['section']} {sheet['name']}"]
            last = sheet["section"]
        labels = {ln["key"]: ln for ln in sheet["lines"]}
        for key, fix in (a.get("wrong") or {}).items():
            ln = labels.get(key, {"label": key, "value": "?"})
            lines.append(f"- **{ln['label']}** — {reviewer}")
            lines.append(f"  - Calculator says: {ln['value']}")
            lines.append(f"  - Should be: {fix or '_(no detail given)_'}")
        if a.get("comment"):
            lines.append(f"- Comment from {reviewer}: {a['comment']}")
    if not problems:
        lines += ["", "_Nothing marked wrong yet._"]

    if stale:
        lines += ["", "## Out of date — the calculator changed after these were checked", ""]
        lines += [f"- §{sec} {by_section[sec]['name']} ({reviewer})" for sec, reviewer in stale]

    lines += ["", "## Crimes checked and found correct", ""]
    ok = [sec for sec in by_section if sec in checked
          and not any(s["section"] == sec and a.get("wrong") for s, _, a in problems)]
    lines += [f"- §{sec} {by_section[sec]['name']} ({', '.join(checked[sec])})" for sec in ok] or ["_None yet._"]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path, help=f"answer files (default: {INCOMING.relative_to(ROOT)}/*.json)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    paths = args.files or sorted(INCOMING.glob("*.json"))
    if not paths:
        sys.exit(f"No answer files. Put them in {INCOMING.relative_to(ROOT)}/ or pass paths.")
    reviews = load_reviews(paths)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_report(reviews, build_sheets()))
    print(f"Wrote {args.out} from {len(reviews)} file(s)")


if __name__ == "__main__":
    main()
