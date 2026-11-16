"""CrimeTime legal review: one plain-language fact sheet per crime.

For each offense, build_sheets() asks the engine the questions a reviewer
would check and writes the answers as short lines:

    Classification, violent felony status, which enhancements it qualifies
    for, what an attempt becomes, the juvenile offender sentence, and the
    sentence for a first offender and with prior felonies.

The reviewer ticks any line that is wrong and says why. scripts/build_site.py
writes the sheets to _site/data/review_sheets.json for site/review/, and
scripts/import_reviews.py turns the returned review files into a report.

Every sheet has a content hash. When the engine or data changes a sheet,
earlier answers on it are reported as out of date.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crimetime import reference
from crimetime.models import CaseFacts
from crimetime.resolvers import is_hatecrime_eligible, is_smf_eligible
from crimetime.sentencing import resolve

ROOT = Path(__file__).resolve().parent.parent
STATUTE_TEXT = ROOT / "data" / "statute_text.json"

CLASS_NAMES = {
    "ClassA_I_Felony": "Class A-I felony", "ClassA_II_Felony": "Class A-II felony",
    "ClassB_Felony": "Class B felony", "ClassC_Felony": "Class C felony",
    "ClassD_Felony": "Class D felony", "ClassE_Felony": "Class E felony",
    "ClassB_Violent_Felony": "Class B violent felony", "ClassC_Violent_Felony": "Class C violent felony",
    "ClassD_Violent_Felony": "Class D violent felony", "ClassE_Violent_Felony": "Class E violent felony",
    "ClassA_Misdemeanor": "Class A misdemeanor", "ClassB_Misdemeanor": "Class B misdemeanor",
    "Unclassified_Misdemeanor": "Unclassified misdemeanor", "Violation": "Violation",
}

# (key, label, predicate felonies, of which violent)
PRIOR_ROWS = [
    ("sentence_0", "Sentence — no prior felonies", 0, 0),
    ("sentence_1", "Sentence — 1 prior felony (non-violent)", 1, 0),
    ("sentence_1v", "Sentence — 1 prior violent felony", 1, 1),
    ("sentence_2", "Sentence — 2 prior felonies (non-violent)", 2, 0),
    ("sentence_2v", "Sentence — 2 prior violent felonies", 2, 2),
]


def _cls(c: str | None) -> str:
    return CLASS_NAMES.get(c or "", c or "—")


def _run(section: str, **kw) -> dict | str:
    pf = kw.pop("predicate_felonies", 0)
    pv = kw.pop("predicate_vfos", 0)
    if kw.get("is_attempt"):
        kw["attempt_of_section"] = section
    try:
        return resolve(section, CaseFacts(
            section=section, prior_record={"predicate_felonies": pf, "predicate_vfos": pv}, **kw,
        )).model_dump(mode="json")
    except Exception as e:  # the failure is what the reviewer checks
        return f"The calculator gives no result ({e})"


def _sentence(out: dict | str) -> str:
    if isinstance(out, str):
        return out
    disp = out.get("available_dispositions") or []
    if not disp:
        return "No sentence produced"
    d = disp[0]
    text = d["label"]
    if d.get("prs"):
        text += f", plus {d['prs']['min_years']:g}–{d['prs']['max_years']:g} years post-release supervision"
    alts = [x["label"].split(" —")[0].split(" for ")[0] for x in disp[1:]]
    if alts:
        text += ". Alternatives: " + ", ".join(dict.fromkeys(alts)).lower()
    refs = ", ".join(d.get("statute_refs") or [])
    return text + (f" ({refs})" if refs else "")


def _yes_no(flag: bool) -> str:
    return "Yes" if flag else "No"


def _listed(flag: bool, list_name: str, section: str) -> str:
    """Yes/No, noting when the list names only some subdivisions."""
    subs = (reference._load_lists()["lists"].get(list_name, {}).get("sectionSubdivisions") or {}).get(section)
    if flag and subs:
        return f"Yes, but only subdivision{'s' if len(subs) > 1 else ''} {', '.join(subs)}"
    return _yes_no(flag)


def sheet(section: str, offense: dict) -> dict:
    cls = offense.get("classification", "Violation")
    is_felony = "Felony" in cls
    is_crime = cls != "Violation"
    base = _run(section)
    lines: list[dict] = []

    def add(key: str, label: str, value: str) -> None:
        lines.append({"key": key, "label": label, "value": value})

    add("class", "Classification", _cls(cls))
    if is_felony:
        vfo = isinstance(base, dict) and base.get("is_vfo")
        add("vfo", "Violent felony offense (PL 70.02)", _yes_no(bool(vfo)))
        add("smf", "Can be charged as sexually motivated (PL 130.91)", _listed(is_smf_eligible(section, cls), "SMF_LIST", section))
    if is_crime:
        add("hate", "Can be a hate crime (PL 485.05)", _listed(is_hatecrime_eligible(section), "HATECRIME_LIST", section))
    if is_felony:
        add("terror", "Can be a crime of terrorism (PL 490.25)", _yes_no(is_hatecrime_eligible(section)))

    if is_crime:
        att = _run(section, is_attempt=True)
        if isinstance(att, str):
            add("attempt", "If attempted (PL 110.05)", att)
        else:
            add("attempt", "If attempted (PL 110.05)",
                f"Allowed — becomes a {_cls(att['classification'])}" + (" (violent)" if att.get("is_vfo") else ""))

    if is_felony:
        jo = _run(section, defendant_age_category="juvenile_offender")
        if isinstance(jo, dict) and jo.get("sentencing_track") != "juvenile_offender":
            add("juvenile", "If the defendant is a juvenile offender (age 13–15)",
                "No juvenile rule — sentenced as an adult: " + _sentence(jo))
        else:
            add("juvenile", "If the defendant is a juvenile offender (age 13–15)", _sentence(jo))
        for key, label, pf, pv in PRIOR_ROWS:
            out = base if (pf, pv) == (0, 0) else _run(section, predicate_felonies=pf, predicate_vfos=pv)
            add(key, label, _sentence(out))
    else:
        add("sentence_0", "Sentence", _sentence(base))

    names = {"VFO": "violent felony", "SMF": "sexually motivated", "HateCrime": "hate crime"}
    for sub, info in sorted((offense.get("subdivisions") or {}).items()):
        member = info.get("memberOf") or {}
        value = "; ".join(f"{names.get(k, k)}: {_yes_no(v).lower()}" for k, v in member.items())
        add(f"subdivision_{sub}", f"Subdivision {sub}" + (f" — {info['elements']}" if info.get("elements") else ""),
            value or "No special treatment")

    digest = hashlib.sha256(json.dumps(lines, sort_keys=True).encode()).hexdigest()[:12]
    return {
        "section": section,
        "name": offense.get("name", ""),
        "article": offense.get("article") or 0,
        "classification": _cls(cls),
        "lines": lines,
        "hash": digest,
    }


def build_sheets() -> dict:
    offenses = reference.get_all_offenses()
    sheets = [
        sheet(s, o) for s, o in sorted(offenses.items(), key=lambda t: (t[1].get("article") or 0, t[0]))
        if not o.get("repealed") and not o.get("isAttempt")
    ]
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
    return {"data_version": manifest.get("version"), "count": len(sheets), "sheets": sheets}


def statutes_for_site(sheets: dict) -> dict:
    try:
        statutes = json.loads(STATUTE_TEXT.read_text())
    except FileNotFoundError:
        return {}
    return {s["section"]: statutes[s["section"]] for s in sheets["sheets"] if s["section"] in statutes}
