"""Golden-output regression test.

Every (offense x prior record x case-fact variant) output must match the
stored snapshot. After an intentional behaviour change, review the diff with
`uv run python scripts/snapshot.py --diff` and then regenerate with
`uv run python scripts/snapshot.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from snapshot import diff, load_golden, run_all  # noqa: E402

# Output fields added after the snapshot was taken; their presence alone is
# not a behaviour change.
ADDITIVE_FIELDS: set[str] = set()


def test_engine_matches_golden_snapshot():
    lines = diff(load_golden(), run_all(), ignore_new_keys=ADDITIVE_FIELDS)
    assert not lines, f"{len(lines)} differences, first 40:\n" + "\n".join(lines[:40])
