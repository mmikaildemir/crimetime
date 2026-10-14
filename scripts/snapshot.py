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

from crimetime import reference  # noqa: E402
from crimetime.models import CaseFacts  # noqa: E402
from crimetime.sentencing import resolve  # noqa: E402

GOLDEN_PATH = REPO_ROOT / "tests" / "golden" / "outputs.json.gz"

# (predicate_felonies, predicate_vfos) — every distinct pattern the engine can
# distinguish: none, one non-violent, one violent, two non-violent, two with
# one violent, two violent.
PRIOR_PATTERNS = [(0, 0), (1, 0), (1, 1), (2, 0), (2, 1), (2, 2)]

VARIANTS: dict[str, dict] = {
    "base": {},
    "smf": {"sexually_motivated": True},
    "hate": {"hate_crime_motivated": True},
    "terror": {"terrorism_motivated": True},
    "hate+terror": {"hate_crime_motivated": True, "terrorism_motivated": True},
    "forhire": {"victim_is_for_hire_operator": True},
    "jo": {"defendant_age_category": "juvenile_offender"},
    "yo": {"defendant_age_category": "youthful_offender_eligible"},
    "dwi": {"is_dwi": True},
    "exceptions": {
        "domestic_violence_by_victim": True,
        "victim_seeking_restitution": True,
        "plea_from_armed_felony_indictment": True,
        "armed_felony_mitigating_factor": True,
    },
    "conditional": {
        "intended_underlying_offense_class": "ClassA_I_Felony",
        "prior_conviction_same_section_within_years": 3,
    },
}


def _facts_kwargs(prior: tuple[int, int]) -> dict:
    """Prior-record kwargs for CaseFacts.

    Expressed via the legacy status enum until PriorRecord exists, so the
    snapshot can be generated against the pre-refactor engine. (2, 1) has no
    legacy equivalent; it maps to 70.04 (one violent predicate).
    """
    from crimetime import models

    if hasattr(models, "PriorRecord"):
        return {"prior_record": {"predicate_felonies": prior[0], "predicate_vfos": prior[1]}}
    legacy = {
        (0, 0): "first_offender",
        (1, 0): "second_felony_offender_70_06",
        (1, 1): "second_violent_felony_offender_70_04",
        (2, 0): "persistent_felony_offender_70_10",
        (2, 1): "second_violent_felony_offender_70_04",
        (2, 2): "persistent_violent_felony_offender_70_08",
    }
    return {"prior_record_status": legacy[prior]}


def scenarios():
    """Yield (key, section, CaseFacts kwargs)."""
    offenses = reference.get_all_offenses()
    overrides = reference.get_offense_overrides()
    for section in sorted(offenses):
        is_crime = offenses[section].get("classification") != "Violation"
        priors = PRIOR_PATTERNS if is_crime else [(0, 0)]
        subdivisions = [None] + sorted(
            set(overrides.get(section, {}).get("subdivisions", {}))
            | set(overrides.get(section, {}).get("subdivisionOverride", {}))
        )
        for prior in priors:
            for vname, extra in VARIANTS.items():
                for subd in subdivisions:
                    kw = {"section": section, "subdivision": subd, **_facts_kwargs(prior), **extra}
                    yield f"{section}|{subd or '-'}|{prior[0]}{prior[1]}|{vname}", section, kw
            if is_crime:
                kw = {"section": section, "is_attempt": True, "attempt_of_section": section,
                      **_facts_kwargs(prior)}
                yield f"{section}|-|{prior[0]}{prior[1]}|attempt", section, kw


def run_all() -> dict[str, dict]:
    results = {}
    for key, section, kw in scenarios():
        try:
            results[key] = resolve(section, CaseFacts(**kw)).model_dump(mode="json")
        except Exception as e:  # recorded so error behaviour is pinned too
            results[key] = {"error": f"{type(e).__name__}: {e}"}
    return results


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


def _flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def diff(old: dict[str, dict], new: dict[str, dict], ignore_new_keys: set[str] = frozenset()):
    """Return a list of human-readable difference lines.

    ignore_new_keys: top-level output fields that may be added without
    counting as a change (e.g. new trace fields).
    """
    lines = []
    for key in sorted(set(old) | set(new)):
        if key not in new:
            lines.append(f"- {key}: scenario removed")
            continue
        if key not in old:
            lines.append(f"+ {key}: scenario added")
            continue
        o = dict(_flatten(old[key]))
        n = {p: v for p, v in _flatten(new[key]) if p.split(".")[0].split("[")[0] not in ignore_new_keys}
        for path in sorted(set(o) | set(n)):
            if o.get(path, "<absent>") != n.get(path, "<absent>"):
                lines.append(f"~ {key} {path}: {o.get(path, '<absent>')!r} -> {n.get(path, '<absent>')!r}")
    return lines


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
