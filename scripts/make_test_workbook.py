"""Build docs/testing/CrimeTime_test_cases.xlsx: user test cases for the
sentencing calculator and the admin tool.

Every "The screen should show" cell is checked against the real engine
(crimetime.sentencing.resolve) and the admin bridge (webapp/admin_bridge.py)
before the file is written; if the engine and the workbook disagree, this
script stops with an error. Re-run after engine or data changes:

    uv run python scripts/make_test_workbook.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crimetime.models import CaseFacts, PriorRecord  # noqa: E402
from crimetime.sentencing import resolve  # noqa: E402
from webapp import admin_bridge as ab  # noqa: E402

OUT = ROOT / "docs" / "testing" / "CrimeTime_test_cases.xlsx"
SITE = "https://mmikaildemir.github.io/crimetime/"
ADMIN = SITE + "admin/"

START = "Open the site. If an earlier case is still showing, click Clear page (bottom of Case Facts)."
CALC = "Click Calculate Sentence."


def search(section: str, name: str) -> str:
    return f'In "Find an offense", type {section} and click "{name}".'


def priors(felonies: int, vfos: int) -> str:
    return (f'Under "Defendant prior record", set "Prior predicate felonies" to {felonies} '
            f'and "…of which violent (VFO)" to {vfos}.')


# ---------------------------------------------------------------------------
# Sentencing cases
# ---------------------------------------------------------------------------
# facts: CaseFacts kwargs. must: strings that must appear in the engine output
# (classification, status, dispositions, PRS, exceptions). count: exact number
# of authorized dispositions, when the case is about what is NOT offered.

SENTENCING = [
    dict(
        title="Baseline: non-violent felony, first offender",
        section="155.40", facts={},
        steps=[START, search("155.40", "Grand larceny in the second degree"),
               "Leave the prior record at 0 and 0.", CALC],
        show=("Final classification: Class C Felony · Violent felony: No\n"
              "Offender status: First felony offender — PL 70.00\n"
              "Authorized dispositions (5):\n"
              "• Indeterminate sentence — max 3–15 years, min 1 yr to max/3\n"
              "• Split sentence (up to 6 months + probation/CD)\n"
              "• Probation for 3, 4, 5 years\n"
              "• Conditional discharge for 3 years\n"
              "• Unconditional discharge\n"
              "Financial obligations include a fine up to $5,000 and a $300 surcharge."),
        legal=("PL 70.00(2)(c), (3)(b): class C max 3–15 years, minimum 1 year to 1/3 of max.\n"
               "PL 60.01, 65.00(3)(a)(i), 65.05, 65.20: probation 3–5 years, CD, UD available to a first offender.\n"
               "PL 80.00(1), 60.35(1)(a)(i): fine and surcharge amounts."),
        must=["First felony offender — PL 70.00", "max 3–15 years", "Probation for 3, 4, 5 years",
              "Conditional discharge for 3 years", "Unconditional discharge", "Mandatory surcharge of $300"],
        count=5,
    ),
    dict(
        title="Second felony offender: prison only",
        section="155.40", facts={"prior_record": PriorRecord(predicate_felonies=1)},
        steps=[START, search("155.40", "Grand larceny in the second degree"), priors(1, 0), CALC],
        show=("Offender status: Second felony offender — PL 70.06\n"
              "Authorized dispositions (1): Indeterminate sentence — max 6–15 years, min max/2\n"
              "No probation, conditional discharge, unconditional discharge or split sentence."),
        legal=("PL 70.06(2): a second felony offender MUST receive an indeterminate sentence.\n"
               "PL 70.06(3)(c): class C max 6–15 years. PL 70.06(4)(b): minimum is 1/2 of the max.\n"
               "Confirm nothing other than imprisonment is offered."),
        must=["Second felony offender — PL 70.06", "max 6–15 years, min max/2"],
        count=1,
    ),
    dict(
        title="Violent felony, first offender (determinate + PRS)",
        section="120.10", facts={},
        steps=[START, search("120.10", "Assault in the first degree"), "Leave the prior record at 0 and 0.", CALC],
        show=("Final classification: Class B Felony · Violent felony: Yes\n"
              "Offender status: First violent felony offender — PL 70.02\n"
              "Authorized dispositions (1): Determinate sentence of 5–25 years\n"
              "Post-release supervision: 2.5–5 years."),
        legal=("PL 70.02(1)(a): 120.10 is a class B violent felony.\n"
               "PL 70.02(2)(a), (3)(a): determinate sentence of 5–25 years; no probation/CD.\n"
               "PL 70.45(2): post-release supervision of 2.5–5 years for a class B/C violent felony."),
        must=["First violent felony offender — PL 70.02", "Determinate sentence of 5–25 years", "PRS 2.5–5"],
        count=1,
    ),
    dict(
        title="Second violent felony offender",
        section="120.05", facts={"prior_record": PriorRecord(predicate_felonies=1, predicate_vfos=1)},
        steps=[START, search("120.05", "Assault in the second degree"), priors(1, 1), CALC],
        show=("Offender status: Second violent felony offender — PL 70.04\n"
              "Authorized dispositions (1): Determinate sentence of 5–7 years\n"
              "Post-release supervision: 1.5–3 years."),
        legal=("PL 70.04(1): one predicate violent felony conviction (10-year lookback, 70.04(1)(b)(iv)-(v)).\n"
               "PL 70.04(3)(c): class D, determinate 5–7 years.\n"
               "PL 70.45(2): post-release supervision for a class D/E violent felony."),
        must=["Second violent felony offender — PL 70.04", "Determinate sentence of 5–7 years", "PRS 1.5–3"],
        count=1,
    ),
    dict(
        title="Persistent violent felony offender (life maximum)",
        section="160.10", facts={"prior_record": PriorRecord(predicate_felonies=2, predicate_vfos=2)},
        steps=[START, search("160.10", "Robbery in the second degree"), priors(2, 2), CALC],
        show=("Offender status: Persistent violent felony offender — PL 70.08\n"
              "Authorized dispositions (1): Indeterminate sentence — 16–25 years to life"),
        legal=("PL 70.08(1)(a): two or more predicate violent felony convictions.\n"
               "PL 70.08(2): indeterminate sentence, maximum life.\n"
               "PL 70.08(3)(b): class C, minimum 16–25 years (check which version is in effect: the minimums change on 9/1/2027)."),
        must=["Persistent violent felony offender — PL 70.08", "Indeterminate sentence — 16–25 years to life"],
        count=1,
    ),
    dict(
        title="Second felony drug offender (non-violent prior)",
        section="220.39", facts={"prior_record": PriorRecord(predicate_felonies=1)},
        steps=[START, search("220.39", "Criminal sale of a controlled substance in the third degree"),
               priors(1, 0), CALC],
        show=("Offender status: Second felony drug offender — PL 70.70(3) / 70.71(3)\n"
              "Authorized dispositions (2):\n"
              "• Determinate sentence of 2–12 years (PRS 1.5–3 years)\n"
              "• Lifetime probation\n"
              "Then change \"…of which violent\" to 1 and calculate again: only a Determinate sentence of 6–15 years."),
        legal=("PL 70.70(3)(a)-(b)(i): non-violent prior, class B drug felony: determinate 2–12 years.\n"
               "PL 70.70(3)(c): lifetime probation is allowed for a class B second felony drug offender.\n"
               "PL 70.70(4)(b)(i): if the prior was violent, determinate 6–15 years and no probation."),
        must=["Second felony drug offender", "Determinate sentence of 2–12 years", "Lifetime probation"],
        count=2,
    ),
    dict(
        title="Hate crime raises the class and keeps violent status",
        section="120.05", facts={"hate_crime_motivated": True},
        steps=[START, search("120.05", "Assault in the second degree"),
               'Open "Enhancements" and tick "Hate crime motivated".', CALC],
        show=("Final classification: Class C Felony · Base classification: Class D Felony · Violent felony: Yes\n"
              "Modifiers applied: hate crime, D → C\n"
              "Authorized dispositions (1): Determinate sentence of 3.5–15 years (PRS 2.5–5 years). No probation."),
        legal=("PL 485.05(3): 120.05 is a specified offense.\n"
               "PL 485.10(2): one category higher (D → C). PL 485.10(1): because 120.05 is a violent felony, the hate crime is deemed a violent felony.\n"
               "PL 70.02(3)(b): class C violent felony, determinate 3.5–15 years."),
        must=["ClassC_Felony", "VFO=True", "Determinate sentence of 3.5–15 years"],
        count=1,
    ),
    dict(
        title="Attempt with its own statutory range",
        section="120.11", facts={"is_attempt": True, "attempt_of_section": "120.11"},
        steps=[START, search("120.11", "Aggravated assault upon a police officer or a peace officer"),
               'Open "Offense shape" and tick "Attempt" (Target section stays 120.11).', CALC],
        show=("Final classification: Class C Felony · Violent felony: Yes\n"
              "Authorized dispositions (1): Determinate sentence of 7–20 years, citing PL 70.02(3)(b)(ii)\n"
              "(not the 10–30 years for the completed crime)."),
        legal=("PL 110.05(4): an attempt of a class B felony is a class C felony.\n"
               "PL 70.02(1)(b): attempted class B violent felony is a class C violent felony.\n"
               "PL 70.02(3)(b)(ii): attempted 120.11 is 7–20 years."),
        must=["ClassC_Felony", "Determinate sentence of 7–20 years", "70.02(3)(b)(ii)"],
        count=1,
    ),
    dict(
        title="Misdemeanor: prior felonies don't matter",
        section="120.00", facts={"prior_record": PriorRecord(predicate_felonies=2)},
        steps=[START, search("120.00", "Assault in the third degree"), priors(2, 0), CALC],
        show=("Final classification: Class A Misdemeanor\n"
              "Offender status: Not applicable — prior felonies do not change misdemeanor sentencing (PL 70.15)\n"
              "Authorized dispositions (6): Definite sentence up to 364 days · Intermittent imprisonment · "
              "Split sentence (up to 60 days) · Probation for 2, 3 years · Conditional discharge for 1 year · Unconditional discharge\n"
              "Surcharge $175."),
        legal=("PL 70.15(1): class A misdemeanor, definite sentence up to 364 days.\n"
               "PL 65.00(3)(b): is a 2- or 3-year probation term right under the current statute?\n"
               "PL 65.05(3)(b): 1-year CD for a misdemeanor. PL 60.35(1)(a)(ii): $175 surcharge."),
        must=["ClassA_Misdemeanor", "Definite sentence up to 364 days", "Probation for 2, 3 years",
              "Conditional discharge for 1 year", "Mandatory surcharge of $175"],
        count=6,
    ),
    dict(
        title="Domestic violence exception (PL 60.12)",
        section="120.05", facts={"domestic_violence_by_victim": True},
        steps=[START, search("120.05", "Assault in the second degree"),
               'Open "Exception triggers" and tick "Domestic violence by victim".', CALC],
        show=("Authorized dispositions (1): Determinate sentence of 2–7 years\n"
              "Exception paths (3): Domestic violence exception — alternative determinate sentence; "
              "— alternative definite sentence; — alternative probation (each citing PL 60.12)."),
        legal=("PL 60.12(1): applies when the defendant was a victim of domestic violence by the victim of this offense "
               "and the abuse was a significant contributing factor; the court must make findings on the record.\n"
               "PL 60.12(2)-(4): check the alternative ranges shown for a class D violent felony."),
        must=["Determinate sentence of 2–7 years", "Domestic violence exception — alternative determinate sentence",
              "Domestic violence exception — alternative definite sentence",
              "Domestic violence exception — alternative probation"],
        count=1,
    ),
]


def engine_text(section: str, facts: dict) -> tuple[str, int]:
    out = resolve(section, CaseFacts(section=section, **facts))
    parts = [out.classification, f"VFO={out.is_vfo}", out.offender_status_label or ""]
    for d in out.available_dispositions:
        parts += [d.label, *d.statute_refs]
        if d.prs:
            parts.append(f"PRS {d.prs.min_years:g}–{d.prs.max_years:g}")
    parts += [e.label for e in out.exception_paths]
    parts += [f.label for f in out.financial_obligations]
    return "\n".join(parts), len(out.available_dispositions)


def check_sentencing() -> None:
    for i, c in enumerate(SENTENCING, 1):
        text, count = engine_text(c["section"], c["facts"])
        missing = [m for m in c["must"] if m not in text]
        if missing or count != c["count"]:
            sys.exit(f"Sentencing case {i} ({c['title']}) no longer matches the engine.\n"
                     f"Missing: {missing}; dispositions: {count} (expected {c['count']})\n---\n{text}")
    # Case 6's second half: violent prior.
    text, count = engine_text("220.39", {"prior_record": PriorRecord(predicate_felonies=1, predicate_vfos=1)})
    assert count == 1 and "Determinate sentence of 6–15 years" in text, text


# ---------------------------------------------------------------------------
# Admin cases (simulated with the admin bridge on a copy of the data)
# ---------------------------------------------------------------------------

ADMIN_START = [
    f"Open the admin tool: {ADMIN}",
    'If it says "You have unpublished changes from an earlier session", click "Start fresh".',
]
REVIEW = 'Click "Review & publish" (top right).'
TRY = 'In step 4 "Try a case", enter the case and click "Calculate with my changes". Compare the "Live data" and "With your changes" columns.'
RECORD = ('In step 5 "Record why", fill in your name, Source: "Practice exercise — not a real law change", '
          'and a short reason. Step 6 should turn all green. Do NOT deploy anything; downloading the bundle is optional.')
CLEANUP = 'Click "Discard draft" in the bar at the top, then click it again to confirm. The bar should say "No changes yet".'


def _edit_range(lists, tables):
    tables["violentFelony"]["statuses"]["first_offender"]["rows"]["ClassD"]["termYears"] = [3, 7]


def _edit_vfo(lists, tables):
    lists["lists"]["VFO_LIST"]["classC"]["sections"].append("155.40")


def _edit_hate(lists, tables):
    lists["lists"]["HATECRIME_LIST"]["sections"].append("215.51")


ADMINS = [
    dict(
        title="Change a sentencing range (pretend the legislature raised the class D violent floor)",
        edit=_edit_range,
        steps=[*ADMIN_START,
               'Go to the "Sentencing tables" tab and choose "Violent felonies".',
               'Open "First violent felony offender — PL 70.02". In the Class D row, change "Term (years)" from 2 to 7 → 3 to 7. '
               "The cell is highlighted and the table name gets a gold dot.",
               REVIEW,
               'Step 3 "Effect on sentences": click "Check effect" (takes up to a minute).',
               TRY + " Try: 120.05 with 0 prior felonies; then 120.05 with 1 prior felony, 1 violent; then 120.18.",
               RECORD],
        show=("Step 1 lists your one change. Step 2: no new problems (12 existing notes in the live data are listed separately, \"not caused by you\").\n"
              "Step 3: about {changed} results changed, in {sections} offenses.\n"
              "Try a case:\n• 120.05, no priors: Live 2–7 years → With your changes 3–7 years\n"
              "• 120.05, 1 violent prior: 5–7 years in both (70.04 is a different table)\n"
              "• 120.18: 2–8 years in both (its own range)"),
        legal=("Only first-offender class D violent felony results (PL 70.02(3)(c)) should change. That includes offenses that become class D violent "
               "through an attempt or a hate-crime/terrorism bump. Second and persistent offenders (70.04, 70.06(6), 70.08) and offenses with their "
               "own 70.02(3)(c) range (120.18, 265.02 subd 10) should not. Skim the step 3 list for anything that shouldn't be there."),
        cases=[({"section": "120.05"}, "Determinate sentence of 2–7 years", "Determinate sentence of 3–7 years"),
               ({"section": "120.05", "predicate_felonies": 1, "predicate_vfos": 1},
                "Determinate sentence of 5–7 years", "Determinate sentence of 5–7 years"),
               ({"section": "120.18"}, "Determinate sentence of 2–8 years", "Determinate sentence of 2–8 years")],
    ),
    dict(
        title="Make an offense a violent felony (pretend 155.40 was added to PL 70.02(1)(b))",
        edit=_edit_vfo,
        steps=[*ADMIN_START,
               'Go to the "Offenses" tab, search 155.40 and click "Grand larceny in the second degree".',
               'Under "Statutory lists", change "Violent felony offense" to "Violent felony, Class C".',
               REVIEW,
               'Step 3: click "Check effect".',
               TRY + " Try: 155.40 with 0 prior felonies; then 155.40 with 1 prior felony (0 violent).",
               RECORD],
        show=("Step 3: about {changed} results changed, all in 155.40.\n"
              "Try a case:\n• 155.40, no priors: Live = indeterminate max 3–15 years plus split, probation, CD, UD → "
              "With your changes = First violent felony offender, determinate 3.5–15 years only\n"
              "• 155.40, 1 prior: Live = indeterminate max 6–15 years → With your changes = 70.06(6), determinate 5–15 years"),
        legal=("Violent-felony status alone should move the case to PL 70.02: determinate 3.5–15 years (70.02(3)(b)) and no probation/CD/UD "
               "(70.02(2)(a)). A second felony offender convicted of a violent felony goes to 70.06(6)(b): 5–15 years. "
               "No other offense should change."),
        cases=[({"section": "155.40"}, "Indeterminate sentence — max 3–15 years", "Determinate sentence of 3.5–15 years"),
               ({"section": "155.40", "predicate_felonies": 1},
                "Indeterminate sentence — max 6–15 years", "Determinate sentence of 5–15 years")],
    ),
    dict(
        title="Add an offense to the hate-crime list (pretend 215.51 was added to PL 485.05(3))",
        edit=_edit_hate,
        steps=[*ADMIN_START,
               'Go to the "Offenses" tab, search 215.51 and click "Criminal contempt in the first degree".',
               'Under "Statutory lists", tick "Hate crime".',
               REVIEW,
               'Step 3: click "Check effect".',
               TRY + ' Try: 215.51 with "Hate crime" ticked; then 215.51 without it.',
               RECORD],
        show=("Step 3: about {changed} results changed, all in 215.51 and all with the hate-crime box ticked.\n"
              "Try a case:\n• 215.51 + Hate crime: Live = Class E felony, max 3–4 years (the box had no effect) → "
              "With your changes = Class D felony, max 3–7 years\n"
              "• 215.51 without Hate crime: the same in both columns"),
        legal=("PL 485.10(2): a class E specified offense becomes class D. 215.51 is not a violent felony, so it stays non-violent "
               "(PL 70.00(2)(d): class D max 3–7 years). Cases without the hate-crime finding must not change."),
        cases=[({"section": "215.51", "hate_crime_motivated": True},
                "Indeterminate sentence — max 3–4 years", "Indeterminate sentence — max 3–7 years"),
               ({"section": "215.51"}, "Indeterminate sentence — max 3–4 years", "Indeterminate sentence — max 3–4 years")],
    ),
]


def check_admin() -> None:
    lists = json.loads((ROOT / "data" / "lists.json").read_text())
    tables = json.loads((ROOT / "data" / "sentencing_tables.json").read_text())
    for i, c in enumerate(ADMINS, 1):
        ab.load_published(lists, tables)
        dl, dt = copy.deepcopy(lists), copy.deepcopy(tables)
        c["edit"](dl, dt)
        ab.set_draft(dl, dt)
        imp = ab.impact()
        c["show"] = c["show"].format(changed=imp["scenarios_changed"], sections=imp["sections_changed"])
        if i > 1 and imp["sections_changed"] != 1:
            sys.exit(f"Admin case {i}: expected changes in one offense, got {imp['sections_changed']}")
        for body, live, draft in c["cases"]:
            r = ab.try_case(body)
            got = ([d["label"] for d in r["live"]["available_dispositions"]][0],
                   [d["label"] for d in r["draft"]["available_dispositions"]][0])
            if not (got[0].startswith(live) and got[1].startswith(draft)):
                sys.exit(f"Admin case {i} {body}: expected {live!r} → {draft!r}, got {got}")


# ---------------------------------------------------------------------------
# Workbook
# ---------------------------------------------------------------------------

FONT = "Arial"
NAVY = "1F3A5F"
HEAD = Font(name=FONT, bold=True, color="FFFFFF", size=10)
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
TITLE = Font(name=FONT, size=16, bold=True, color=NAVY)
H2 = Font(name=FONT, size=12, bold=True, color=NAVY)
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
INPUT_FILL = PatternFill("solid", fgColor="FFF4C2")
BAND_FILL = PatternFill("solid", fgColor="F3F6FA")
THIN = Side(style="thin", color="C9D1DC")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")


def numbered(steps: list[str]) -> str:
    return "\n".join(f"{n}. {s}" for n, s in enumerate(steps, 1))


def case_sheet(wb: Workbook, name: str, headers: list[tuple[str, int]], rows: list[list[str]]) -> None:
    ws = wb.create_sheet(name)
    for col, (h, width) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font, cell.fill, cell.alignment, cell.border = HEAD, HEAD_FILL, WRAP, BOX
        ws.column_dimensions[cell.column_letter].width = width
    result_col = [h for h, _ in headers].index("Result") + 1
    for r, values in enumerate(rows, 2):
        for col, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=col, value=v)
            cell.font, cell.alignment, cell.border = BODY, WRAP, BOX
            if col <= 2:
                cell.font = BOLD
            if col >= result_col:
                cell.fill = INPUT_FILL
            elif r % 2 == 1:
                cell.fill = BAND_FILL
        lines = max(str(v).count("\n") + 1 + len(str(v)) // 55 for v in values)
        ws.row_dimensions[r].height = min(409, 14 * lines)
    last = len(rows) + 1
    letter = ws.cell(row=1, column=result_col).column_letter
    dv = DataValidation(type="list", formula1='"Pass,Fail,Not sure"', allow_blank=True)
    dv.prompt, dv.promptTitle = "Choose Pass, Fail or Not sure", "Result"
    ws.add_data_validation(dv)
    dv.add(f"{letter}2:{letter}{last}")
    rng = f"{letter}2:{letter}{last}"
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"Pass"'], fill=PatternFill("solid", fgColor="C6EFCE")))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"Fail"'], fill=PatternFill("solid", fgColor="FFC7CE")))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"Not sure"'], fill=PatternFill("solid", fgColor="FFEB9C")))
    ws.freeze_panes = "C2"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:1"


def how_to_use(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "How to use"
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 100
    rows: list[tuple[str, str, Font | None]] = [
        ("CrimeTime 2.0 — user test cases", "", TITLE),
        ("", "", None),
        ("Calculator (public site)", SITE, None),
        ("Admin tool", ADMIN, None),
        ("Tester name", "", "input"),
        ("Date", "", "input"),
        ("", "", None),
        ("How to test", "", H2),
        ("1", "Do the cases in order, one at a time. Each row says what to click and what the screen should show.", None),
        ("2", 'Sentencing cases: click "Clear page" before each new case so nothing carries over.', None),
        ("3", 'Admin cases: your changes are a DRAFT. Nothing you do there changes the public site. Finish each case with "Discard draft".', None),
        ("4", 'Compare the screen with "The screen should show", then check the law in "Check legally". '
              "A case can fail because the screen differs OR because the expected answer itself is legally wrong. Both are worth reporting.", None),
        ("5", 'Fill in only the yellow cells: pick Pass, Fail or Not sure in "Result" and explain anything odd in "Notes".', None),
        ("6", 'You can also click the "Feedback" button on the site to report a problem with the case details filled in.', None),
        ("7", "Save this file and send it back when you're done.", None),
        ("", "", None),
        ("Example of a filled-in result", "", H2),
        ("Result", "Fail", "input"),
        ("Notes", "(Example only) The screen matched, but the probation term looks wrong to me under PL 65.00(3) — please double-check.", "input"),
        ("", "", None),
        ("Terms used", "", H2),
        ("VFO", "Violent felony offense, listed in PL 70.02(1).", None),
        ("Predicate felony", "A prior felony conviction that counts for sentencing (PL 70.06(1)(b): sentenced within 10 years, plus time incarcerated).", None),
        ("Determinate / indeterminate", "A fixed term (e.g. 5 years) vs. a minimum and maximum (e.g. 2 to 6 years).", None),
        ("PRS", "Post-release supervision after a determinate sentence (PL 70.45).", None),
        ("CD / UD", "Conditional discharge (PL 65.05) / unconditional discharge (PL 65.20).", None),
    ]
    for r, (a, b, style) in enumerate(rows, 1):
        ca, cb = ws.cell(row=r, column=1, value=a), ws.cell(row=r, column=2, value=b)
        ca.font, cb.font = BOLD, BODY
        ca.alignment = cb.alignment = WRAP
        if isinstance(style, Font):
            ca.font = style
        elif style == "input":
            cb.fill, cb.border = INPUT_FILL, BOX
    for r in (3, 4):
        cell = ws.cell(row=r, column=2)
        cell.hyperlink = cell.value
        cell.font = Font(name=FONT, size=10, color="0563C1", underline="single")
    ws.row_dimensions[1].height = 26


def build() -> None:
    check_sentencing()
    check_admin()
    wb = Workbook()
    how_to_use(wb)
    case_sheet(
        wb, "Sentencing",
        [("#", 5), ("What this tests", 24), ("Steps", 52), ("The screen should show", 52),
         ("Check legally", 52), ("Result", 11), ("Notes", 34)],
        [[f"S{i}", c["title"], numbered(c["steps"]), c["show"], c["legal"], "", ""]
         for i, c in enumerate(SENTENCING, 1)],
    )
    case_sheet(
        wb, "Admin",
        [("#", 5), ("What this tests", 24), ("Steps", 58), ("The screen should show", 50),
         ("Check legally", 46), ("Clean up", 26), ("Result", 11), ("Notes", 34)],
        [[f"A{i}", c["title"], numbered(c["steps"]), c["show"], c["legal"], CLEANUP, "", ""]
         for i, c in enumerate(ADMINS, 1)],
    )
    # "Clean up" is an instruction, not an input.
    ws = wb["Admin"]
    for r in range(2, len(ADMINS) + 2):
        ws.cell(row=r, column=6).fill = PatternFill(fill_type=None) if r % 2 == 0 else BAND_FILL
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(SENTENCING)} sentencing + {len(ADMINS)} admin cases")


if __name__ == "__main__":
    build()
