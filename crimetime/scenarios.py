"""Scenario sweep over the sentencing engine.

Runs resolve() over every offense x prior-record pattern x case-fact variant.
Used by the golden snapshot (scripts/snapshot.py, tests/test_golden.py) and by
the admin tool's impact preview (webapp/admin_bridge.py) to show exactly which
outputs a data edit changes.
"""

from __future__ import annotations

from typing import Iterable, Iterator

from . import reference
from .models import CaseFacts
from .sentencing import resolve

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


def _prior_kwargs(prior: tuple[int, int]) -> dict:
    return {"prior_record": {"predicate_felonies": prior[0], "predicate_vfos": prior[1]}}


def scenarios(sections: Iterable[str] | None = None) -> Iterator[tuple[str, str, dict]]:
    """Yield (key, section, CaseFacts kwargs), optionally only for `sections`."""
    offenses = reference.get_all_offenses()
    overrides = reference.get_offense_overrides()
    wanted = sorted(offenses) if sections is None else sorted(s for s in set(sections) if s in offenses)
    for section in wanted:
        is_crime = offenses[section].get("classification") != "Violation"
        priors = PRIOR_PATTERNS if is_crime else [(0, 0)]
        subdivisions = [None] + sorted(
            set(overrides.get(section, {}).get("subdivisions", {}))
            | set(overrides.get(section, {}).get("subdivisionOverride", {}))
        )
        for prior in priors:
            for vname, extra in VARIANTS.items():
                for subd in subdivisions:
                    kw = {"section": section, "subdivision": subd, **_prior_kwargs(prior), **extra}
                    yield f"{section}|{subd or '-'}|{prior[0]}{prior[1]}|{vname}", section, kw
            if is_crime:
                kw = {"section": section, "is_attempt": True, "attempt_of_section": section,
                      **_prior_kwargs(prior)}
                yield f"{section}|-|{prior[0]}{prior[1]}|attempt", section, kw


def run_all(sections: Iterable[str] | None = None) -> dict[str, dict]:
    results = {}
    for key, section, kw in scenarios(sections):
        try:
            results[key] = resolve(section, CaseFacts(**kw)).model_dump(mode="json")
        except Exception as e:  # recorded so error behaviour is pinned too
            results[key] = {"error": f"{type(e).__name__}: {e}"}
    return results


def flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flatten(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def changed_paths(old: dict, new: dict, ignore_new_keys: set[str] = frozenset()) -> list[tuple[str, object, object]]:
    """(path, old value, new value) for every leaf that differs between two outputs."""
    keep = lambda path: path.split(".")[0].split("[")[0] not in ignore_new_keys  # noqa: E731
    o = {p: v for p, v in flatten(old) if keep(p)}
    n = {p: v for p, v in flatten(new) if keep(p)}
    return [
        (path, o.get(path, "<absent>"), n.get(path, "<absent>"))
        for path in sorted(set(o) | set(n))
        if o.get(path, "<absent>") != n.get(path, "<absent>")
    ]


def diff(old: dict[str, dict], new: dict[str, dict], ignore_new_keys: set[str] = frozenset()) -> list[str]:
    """Return a list of human-readable difference lines.

    ignore_new_keys: top-level output fields left out of the comparison
    (e.g. fields added since the snapshot was taken).
    """
    lines = []
    for key in sorted(set(old) | set(new)):
        if key not in new:
            lines.append(f"- {key}: scenario removed")
            continue
        if key not in old:
            lines.append(f"+ {key}: scenario added")
            continue
        for path, o, n in changed_paths(old[key], new[key], ignore_new_keys):
            lines.append(f"~ {key} {path}: {o!r} -> {n!r}")
    return lines
