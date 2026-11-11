"""Golden-output snapshot of the sentencing engine.

Runs resolve() over every offense x prior-record fact pattern x case-fact
variant and records the full output. Used by tests/test_golden.py to prove a
refactor changes nothing, and to make intentional behaviour changes reviewable
as a diff.

    uv run python scripts/snapshot.py           # rewrite tests/golden/outputs.json.gz
    uv run python scripts/snapshot.py --diff    # show what changed vs the stored snapshot
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from crimetime.scenarios import diff, run_all  # noqa: E402,F401  (re-exported for tests)

GOLDEN_PATH = REPO_ROOT / "tests" / "golden" / "outputs.json.gz"


def load_golden() -> dict[str, dict]:
    with gzip.open(GOLDEN_PATH, "rt") as f:
        stored = json.load(f)
    return {key: stored["outputs"][i] for key, i in stored["index"].items()}


def write_golden(results: dict[str, dict]) -> None:
    # Most scenarios share an output (e.g. prior record is irrelevant to a
    # misdemeanor), so store each distinct output once plus a key -> index map.
    outputs: list[str] = []
    seen: dict[str, int] = {}
    index = {}
    for key in sorted(results):
        blob = json.dumps(results[key], sort_keys=True, separators=(",", ":"))
        if blob not in seen:
            seen[blob] = len(outputs)
            outputs.append(blob)
        index[key] = seen[blob]
    payload = '{"index":' + json.dumps(index, separators=(",", ":")) + ',"outputs":[' + ",".join(outputs) + "]}"
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the gzip bytes deterministic across regenerations
    with open(GOLDEN_PATH, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:
        f.write(payload.encode())


if __name__ == "__main__":
    results = run_all()
    if "--diff" in sys.argv:
        lines = diff(load_golden(), results)
        print("\n".join(lines) or "no differences")
        print(f"\n{len(lines)} differing paths", file=sys.stderr)
    else:
        write_golden(results)
        errors = sum(1 for r in results.values() if "error" in r)
        print(f"wrote {len(results)} scenarios ({errors} raise) to {GOLDEN_PATH.relative_to(REPO_ROOT)}")
