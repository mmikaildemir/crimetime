"""CrimeTime admin tool — checks behind the static admin page (site/admin/).

The admin page keeps two copies of the reference data: the *published*
version it loaded and the admin's *draft*. This module, loaded into Pyodide
next to bridge.py, answers four questions about the draft:

    validate   is the draft well-formed? (ranges, citations, cross-references)
    changes    which data fields did the admin change?
    impact     which sentencing outputs change, and how?
    try_case   what does one case resolve to under the draft?

It also regenerates offenses.json for the data bundle the admin publishes.
Pure functions over dicts; the *_json wrappers are the Pyodide entry points.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Iterator

from crimetime import reference
from crimetime.scenarios import PRIOR_PATTERNS, VARIANTS, changed_paths, run_all

# Classifications an offense record may carry (data/lists.json "classification").
OFFENSE_CLASSES = [
    "ClassA_I_Felony", "ClassA_II_Felony",
    "ClassB_Felony", "ClassC_Felony", "ClassD_Felony", "ClassE_Felony",
    "ClassA_Misdemeanor", "ClassB_Misdemeanor", "Unclassified_Misdemeanor",
    "Violation",
]

SECTION_RE = re.compile(r"^\d{1,3}\.\d{2}(-[A-Za-z])?$")

# Engine settings (codes read by the pipeline's logic). The admin page shows
# them read-only; a draft that changes one is rejected.
LOCKED_KEYS = {
    "type", "sentenceType", "vfo", "eligibilityList", "factField", "order", "triggeringFactor",
    "triggeringFactors", "activeVersion", "name", "minTermRule", "effect",
}

# Number-valued fields whose name ends like this are amounts of time or money
# and must not be negative; two-number lists under them are [min, max] ranges.
_RANGE_SUFFIXES = ("Years", "Months", "Days", "Amount", "Max", "Min", "Floor", "Ceiling")

PRIOR_LABELS = {
    (0, 0): "no prior felonies",
    (1, 0): "1 prior felony",
    (1, 1): "1 prior violent felony",
    (2, 0): "2 prior felonies",
    (2, 1): "2 prior felonies (1 violent)",
    (2, 2): "2 prior violent felonies",
}
VARIANT_LABELS = {
    "base": "no special circumstances",
    "smf": "sexually motivated",
    "hate": "hate crime",
    "terror": "crime of terrorism",
    "hate+terror": "hate crime + terrorism",
    "forhire": "victim was a for-hire driver",
    "jo": "juvenile offender",
    "yo": "youthful-offender eligible",
    "dwi": "DWI",
    "exceptions": "domestic violence, restitution and armed-felony plea",
    "conditional": "conditional-classification facts",
    "attempt": "attempt",
}
assert set(VARIANT_LABELS) == set(VARIANTS) | {"attempt"}
assert set(PRIOR_LABELS) == set(PRIOR_PATTERNS)


# ---------------------------------------------------------------------------
# Session state: the published data and the admin's draft
# ---------------------------------------------------------------------------

_published: tuple[dict, dict] | None = None
_draft: tuple[dict, dict] | None = None
_published_results: dict[str, dict] = {}  # scenario key -> output, filled lazily per section
_published_sections_run: set[str] = set()


def load_published(lists: dict, tables: dict) -> None:
    """Set the data the draft is compared against (the live data bundle)."""
    global _published, _draft
    _published = (lists, tables)
    _draft = (copy.deepcopy(lists), copy.deepcopy(tables))
    _published_results.clear()
    _published_sections_run.clear()


def set_draft(lists: dict, tables: dict) -> None:
    global _draft
    _draft = (lists, tables)


def _require_state() -> tuple[tuple[dict, dict], tuple[dict, dict]]:
    if _published is None or _draft is None:
        raise RuntimeError("load_published() must be called first")
    return _published, _draft


def _use(data: tuple[dict, dict]) -> None:
    reference.set_data(*data)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _issue(level: str, where: str, message: str) -> dict:
    return {"level": level, "where": where, "message": message}


def _walk(obj: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    """Yield (path, value) for every node, depth first. Path items are keys/indexes."""
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, path + (i,))


def _list_sections(lists: dict) -> Iterator[tuple[str, str]]:
    """(where, section) for every section number named in the statutory lists."""
    for list_name, body in lists.get("lists", {}).items():
        for path, value in _walk(body):
            if not isinstance(value, list) or not path:
                continue
            key = str(path[-1])
            if key.startswith("former") or key.endswith("_note") or key.startswith("attemptOfClass"):
                continue  # former sections are historical; attemptOfClass holds classes
            for s in value:
                if isinstance(s, str) and SECTION_RE.match(s):
                    yield f"{list_name} › {' › '.join(map(str, path))}", s


def validate_offenses(lists: dict) -> list[dict]:
    issues = []
    offenses = lists.get("offenses", {})
    for key, off in offenses.items():
        where = f"Offense §{key}"
        if not SECTION_RE.match(key):
            issues.append(_issue("error", where, "Section number must look like 120.05"))
        if off.get("section") != key:
            issues.append(_issue("error", where, f"Section field ({off.get('section')!r}) does not match the key"))
        if not (off.get("name") or "").strip():
            issues.append(_issue("error", where, "Name is required"))
        if off.get("classification") not in OFFENSE_CLASSES:
            issues.append(_issue("error", where, f"Unknown classification {off.get('classification')!r}"))
        art = off.get("article")
        if not isinstance(art, int) or (SECTION_RE.match(key) and art != int(key.split(".")[0])):
            issues.append(_issue("error", where, f"Article should be {key.split('.')[0]} for this section"))
        for flag, ref in (("isAttempt", "attemptOf"), ("isConspiracy", "conspiracyOf")):
            target = off.get(ref)
            if off.get(flag) and not target:
                issues.append(_issue("error", where, f"{ref} is required when {flag} is set"))
            if target and target not in offenses:
                issues.append(_issue("error", where, f"{ref} points to §{target}, which is not an offense"))
        cond = off.get("conditionalClassification")
        if cond:
            for c in [cond.get("fallback")] + [r.get("resulting_classification") for r in cond.get("rules", [])]:
                if c not in OFFENSE_CLASSES:
                    issues.append(_issue("error", where, f"Conditional classification uses unknown class {c!r}"))
        rep = off.get("repealed")
        if rep is not None and not (isinstance(rep, dict) and rep.get("date")):
            issues.append(_issue("error", where, "A repealed offense needs a repeal date"))
    for where, s in _list_sections(lists):
        if s not in offenses:
            issues.append(_issue("warning", where, f"§{s} is listed but is not in the offense list"))
        elif offenses[s].get("repealed"):
            issues.append(_issue("warning", where, f"§{s} is repealed but still on this list"))
    return issues


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_tables(tables: dict, published_tables: dict | None = None) -> list[dict]:
    issues = []
    published_leaves = dict(_walk(published_tables)) if published_tables is not None else {}
    for path, value in _walk(tables):
        if not path or any(str(p).startswith("_") for p in path):
            continue  # notes are free text
        where = " › ".join(map(str, path))
        key = next((p for p in reversed(path) if isinstance(p, str)), "")
        if path in published_leaves:
            old = published_leaves[path]
            if _is_number(old) and not _is_number(value) and value is not None:
                issues.append(_issue("error", where, "Must be a number"))
            if isinstance(old, str) and not isinstance(value, str):
                issues.append(_issue("error", where, "Must be text"))
        if (key in LOCKED_KEYS and path in published_leaves and not _is_number(value)
                and not isinstance(value, bool) and value != published_leaves[path]):
            issues.append(_issue("error", where, "This is an engine setting; ask the developers to change it"))
        if _is_number(value) and value < 0:
            issues.append(_issue("error", where, "Cannot be negative"))
        if (isinstance(value, list) and len(value) == 2 and all(_is_number(v) for v in value)
                and key.endswith(_RANGE_SUFFIXES) and value[0] > value[1]):
            issues.append(_issue("error", where, f"Minimum ({value[0]}) is greater than maximum ({value[1]})"))
        if (key == "statute" or key.endswith("Ref")) and isinstance(value, str) and not value.strip():
            issues.append(_issue("error", where, "Statute citation cannot be empty"))
    return issues


def validate(lists: dict, tables: dict, published_tables: dict | None = None) -> list[dict]:
    issues = validate_offenses(lists) + validate_tables(tables, published_tables)
    return sorted(issues, key=lambda i: (i["level"] != "error", i["where"]))


# ---------------------------------------------------------------------------
# What changed in the data
# ---------------------------------------------------------------------------


def _leaves(obj: Any) -> dict[tuple, Any]:
    """Leaf values by path; [min, max] number pairs count as one leaf."""
    out = {}
    for path, value in _walk(obj):
        if isinstance(value, dict):
            continue
        if isinstance(value, list) and not (len(value) == 2 and all(_is_number(v) for v in value)):
            if all(not isinstance(v, (dict, list)) for v in value):
                out[path] = value  # a flat list (e.g. section numbers) is one value
            continue
        if path[:-1] and path[:-1] in out:
            continue  # element of a pair or flat list already recorded
        out[path] = value
    return out


def data_changes(old: tuple[dict, dict], new: tuple[dict, dict]) -> list[dict]:
    """Human-readable list of fields that differ between two data versions."""
    changes = []
    for file, o, n in (("Offenses & lists", old[0], new[0]), ("Sentencing tables", old[1], new[1])):
        lo, ln = _leaves(o), _leaves(n)
        for path in sorted(set(lo) | set(ln), key=lambda p: tuple(map(str, p))):
            a, b = lo.get(path, None), ln.get(path, None)
            if path in lo and path in ln and a == b:
                continue
            entry = {"file": file, "path": [str(p) for p in path], "old": a, "new": b}
            if isinstance(a, list) and isinstance(b, list) and not (len(a) == 2 and all(_is_number(v) for v in a)):
                entry["added"] = [v for v in b if v not in a]
                entry["removed"] = [v for v in a if v not in b]
            changes.append(entry)
    return changes


# ---------------------------------------------------------------------------
# Impact on sentencing outputs
# ---------------------------------------------------------------------------


def affected_sections(old: tuple[dict, dict], new: tuple[dict, dict]) -> set[str] | None:
    """Sections whose outputs can change, or None when every section can."""
    if old[1] != new[1] or old[0].get("schema") != new[0].get("schema"):
        return None
    oo, no = old[0].get("offenses", {}), new[0].get("offenses", {})
    touched = {s for s in set(oo) | set(no) if oo.get(s) != no.get(s)}
    old_listed = set(_list_sections(old[0]))
    new_listed = set(_list_sections(new[0]))
    touched |= {s for _, s in old_listed ^ new_listed}
    for list_name in set(old[0].get("lists", {})) | set(new[0].get("lists", {})):
        a = old[0]["lists"].get(list_name, {})
        b = new[0]["lists"].get(list_name, {})
        if a != b:  # e.g. sectionSubdivisions edits: re-run every section in the list
            touched |= {s for _, s in _list_sections({"lists": {list_name: a}})}
            touched |= {s for _, s in _list_sections({"lists": {list_name: b}})}
    # Attempts and conspiracies take their target's classification and lists.
    for s, off in no.items():
        if off.get("attemptOf") in touched or off.get("conspiracyOf") in touched:
            touched.add(s)
    return touched


def _scenario_label(key: str) -> dict:
    section, subd, prior, variant = key.split("|")
    p = (int(prior[0]), int(prior[1]))
    parts = [PRIOR_LABELS.get(p, prior), VARIANT_LABELS.get(variant, variant)]
    if subd != "-":
        parts.insert(0, f"subdivision {subd}")
    return {"section": section, "text": ", ".join(parts)}


_FIELD_LABELS = {
    "offense_name": "Offense name",
    "classification": "Classification",
    "is_vfo": "Violent felony offense",
    "offender_status": "Offender status",
    "sentencing_track": "Sentencing track",
}


def _summarize(old: dict, new: dict) -> list[dict]:
    """Readable before/after lines for one scenario's output."""
    if "error" in new and "error" not in old:
        return [{"field": "Result", "old": "calculates normally", "new": f"FAILS: {new['error']}", "severe": True}]
    if "error" in old and "error" not in new:
        return [{"field": "Result", "old": f"failed: {old['error']}", "new": "calculates normally"}]
    if "error" in old:
        return [{"field": "Error", "old": old["error"], "new": new["error"]}] if old != new else []
    lines = []
    for f, label in _FIELD_LABELS.items():
        if old.get(f) != new.get(f):
            lines.append({"field": label, "old": old.get(f), "new": new.get(f)})
    old_d = [d.get("label") for d in old.get("available_dispositions", [])]
    new_d = [d.get("label") for d in new.get("available_dispositions", [])]
    if old_d != new_d and len(old_d) == len(new_d):
        for a, b in zip(old_d, new_d):
            if a != b:
                lines.append({"field": "Sentence option", "old": a, "new": b})
    elif old_d != new_d:
        for lbl in new_d:
            if lbl not in old_d:
                lines.append({"field": "Sentence option", "old": None, "new": lbl})
        for lbl in old_d:
            if lbl not in new_d:
                lines.append({"field": "Sentence option", "old": lbl, "new": None})
    old_f = {f.get("label"): f.get("amount") for f in old.get("financial_obligations", [])}
    new_f = {f.get("label"): f.get("amount") for f in new.get("financial_obligations", [])}
    for lbl in sorted(set(old_f) | set(new_f), key=str):
        if old_f.get(lbl) != new_f.get(lbl):
            lines.append({"field": f"Financial: {lbl}", "old": old_f.get(lbl), "new": new_f.get(lbl)})
    if not lines:
        # Something below the headline fields changed (PRS, notes, statute refs...).
        for path, a, b in changed_paths(old, new)[:5]:
            lines.append({"field": path, "old": a, "new": b})
    return lines


def _published_results_for(sections: set[str] | None, published: tuple[dict, dict]) -> dict[str, dict]:
    """Published-data outputs, run once per section and cached for the session."""
    _use(published)
    all_secs = set(published[0].get("offenses", {}))
    wanted = all_secs if sections is None else sections & all_secs
    todo = wanted - _published_sections_run
    if todo:
        _published_results.update(run_all(todo))
        _published_sections_run.update(todo)
    return {k: v for k, v in _published_results.items() if k.split("|")[0] in wanted}


def impact(max_groups: int = 200) -> dict:
    """Compare sentencing outputs under the published data and the draft."""
    published, draft = _require_state()
    sections = affected_sections(published, draft)
    try:
        old = _published_results_for(sections, published)
        _use(draft)
        new = run_all(sections)
    finally:
        _use(draft)
    names = {s: o.get("name", "") for s, o in {**published[0].get("offenses", {}), **draft[0].get("offenses", {})}.items()}

    # Group scenarios that changed in exactly the same way (e.g. one range edit
    # shows up identically for six case-fact variants).
    groups: dict[str, dict] = {}
    severe = 0
    changed = 0
    for key in sorted(set(old) | set(new)):
        if key not in new:
            lines = [{"field": "Scenario", "old": "exists", "new": "removed (offense deleted)"}]
        elif key not in old:
            lines = [{"field": "Scenario", "old": None, "new": "new offense"}]
        elif old[key] == new[key]:
            continue
        else:
            lines = _summarize(old[key], new[key])
        changed += 1
        severe += any(line.get("severe") for line in lines)
        label = _scenario_label(key)
        sig = json.dumps([label["section"], lines], sort_keys=True, default=str)
        g = groups.setdefault(sig, {
            "section": label["section"],
            "name": names.get(label["section"], ""),
            "changes": lines,
            "scenarios": [],
        })
        g["scenarios"].append(label["text"])
    ordered = sorted(groups.values(), key=lambda g: (not any(c.get("severe") for c in g["changes"]), g["section"]))
    return {
        "scope": "all offenses" if sections is None else f"{len(sections)} affected offense(s)",
        "scenarios_checked": len(new),
        "scenarios_changed": changed,
        "severe": severe,
        "sections_changed": len({g["section"] for g in groups.values()}),
        "groups": ordered[:max_groups],
        "truncated": max(0, len(ordered) - max_groups),
    }


# ---------------------------------------------------------------------------
# Try a case / export
# ---------------------------------------------------------------------------


def _bridge():
    try:
        import bridge  # Pyodide: bridge.py sits next to this module
    except ImportError:
        from webapp import bridge
    return bridge


def try_case(body: dict) -> dict:
    """Resolve one case under the live data and under the draft."""
    published, draft = _require_state()
    out = {}
    for name, data in (("live", published), ("draft", draft)):
        _use(data)
        try:
            out[name] = _bridge().resolve(body)
        except KeyError:
            out[name] = None  # offense not in this version
        except Exception as e:
            out[name] = {"error": str(e)}
    _use(draft)
    return out


def offenses_index() -> list[dict]:
    """offenses.json for the draft: details of every offense in list order."""
    _, draft = _require_state()
    _use(draft)
    b = _bridge()
    return [b.offense_detail(o["section"]) for o in b.list_offenses()]


# ---------------------------------------------------------------------------
# JSON entry points for Pyodide
# ---------------------------------------------------------------------------


def _call_json(fn, *args) -> str:
    try:
        return json.dumps({"ok": True, "data": fn(*args)}, default=str)
    except Exception as e:
        return json.dumps({"ok": False, "status": 400, "error": f"{type(e).__name__}: {e}"})


def load_published_json(lists_json: str, tables_json: str) -> str:
    return _call_json(lambda: load_published(json.loads(lists_json), json.loads(tables_json)) or True)


def set_draft_json(lists_json: str, tables_json: str) -> str:
    return _call_json(lambda: set_draft(json.loads(lists_json), json.loads(tables_json)) or True)


def check_draft_json() -> str:
    """Validation issues + data changes for the current draft (fast)."""
    def run():
        published, draft = _require_state()
        before = {json.dumps(i, sort_keys=True) for i in validate(published[0], published[1], published[1])}
        issues = validate(draft[0], draft[1], published[1])
        for i in issues:
            i["new"] = json.dumps(i, sort_keys=True) not in before
        return {
            "issues": issues,
            "changes": data_changes(published, draft),
        }
    return _call_json(run)


def impact_json() -> str:
    return _call_json(impact)


def try_case_json(body_json: str) -> str:
    return _call_json(try_case, json.loads(body_json))


# ---------------------------------------------------------------------------
# Data bundle (what the admin publishes; see docs/HOSTING.md)
# ---------------------------------------------------------------------------

BUNDLE_FILES = ("lists.json", "sentencing_tables.json", "manifest.json", "offenses.json")


def _compact(obj: Any, indent: int = 0, width: int = 130) -> str:
    """JSON with small objects/arrays kept on one line (the sentencing tables' style)."""
    one = json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))
    if not isinstance(obj, (dict, list)) or not obj or (indent > 0 and indent + len(one) <= width):
        return one
    pad = " " * (indent + 2)
    if isinstance(obj, dict):
        items = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {_compact(v, indent + 2, width)}" for k, v in obj.items()]
        return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
    return "[\n" + ",\n".join(pad + _compact(v, indent + 2, width) for v in obj) + "\n" + " " * indent + "]"


def dump_lists(lists: dict) -> str:
    return json.dumps(lists, indent=2, ensure_ascii=False) + "\n"


def dump_tables(tables: dict) -> str:
    return _compact(tables) + "\n"


def bundle(manifest: dict) -> bytes:
    """Zip of the draft data bundle; unzip into the site's data/ folder to publish."""
    import io
    import zipfile

    _, draft = _require_state()
    contents = {
        "lists.json": dump_lists(draft[0]),
        "sentencing_tables.json": dump_tables(draft[1]),
        "manifest.json": json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        "offenses.json": json.dumps(offenses_index(), separators=(",", ":")),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in BUNDLE_FILES:
            zf.writestr(zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)), contents[name])
    return buf.getvalue()


def read_bundle(data: bytes) -> dict:
    """Open a previously published bundle (to roll back or continue from it)."""
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = {n.rsplit("/", 1)[-1]: n for n in zf.namelist()}  # tolerate a top-level folder
        missing = [n for n in ("lists.json", "sentencing_tables.json") if n not in names]
        if missing:
            raise ValueError(f"Not a CrimeTime data bundle: missing {', '.join(missing)}")
        out = {
            "lists": json.loads(zf.read(names["lists.json"])),
            "tables": json.loads(zf.read(names["sentencing_tables.json"])),
        }
        out["manifest"] = json.loads(zf.read(names["manifest.json"])) if "manifest.json" in names else None
    return out


def bundle_json(manifest_json: str) -> str:
    import base64

    return _call_json(lambda: base64.b64encode(bundle(json.loads(manifest_json))).decode())


def read_bundle_json(b64: str) -> str:
    import base64

    return _call_json(read_bundle, base64.b64decode(b64))
