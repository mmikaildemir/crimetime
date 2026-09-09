"""
CrimeTime Statutory Data Console (Streamlit)

Local admin tool for building the new normalized data model:
Statute → Classification → Modifier → Offense → SentencingRule.

Page map (§ citations used throughout):
  §1  Statutes
  §2  Classifications
  §3  Modifiers
  §4  Offenses
  §5  Offense–Modifier Eligibility
  §6  Classification Resolution
  §7  Provision Types
  §8  Sentencing Rules
  §9  Export

Data is stored in a local SQLite file (crimetime_data.db) in the same
directory as this script, so it persists across restarts.

Setup:
    pip install streamlit pandas requests python-dotenv

Run:
    streamlit run app.py
"""

import json
import os
import sqlite3
from contextlib import closing

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # picks up .env in the working directory

# ---- Open Legislation API -----------------------------------------------
_RAW_KEY = os.getenv("OPEN_LEGISLATION_API_KEY", "")
OPEN_LEG_API_KEY = _RAW_KEY.strip().strip("'").strip('"')
OPEN_LEG_BASE = "https://legislation.nysenate.gov/api/3/laws"

# Common NYS law IDs the user is likely to work with
LAW_ID_OPTIONS = [
    "PL",   # Penal Law
    "VTL",  # Vehicle & Traffic
    "CPL",  # Criminal Procedure
    "COR",  # Correction
    "TAX",  # Tax
    "EDN",  # Education
    "GML",  # General Municipal
    "MHY",  # Mental Hygiene
    "NAV",  # Navigation
]

DB_PATH = "crimetime_data.db"

RULE_SUBTYPE_FIELDS = {
    "SimpleCap": [
        ("max_amount", "Max amount ($)", "number"),
        ("can_stand_alone", "Can stand alone as sole sentence", "checkbox"),
    ],
    "CorporateCap": [
        ("max_amount", "Max amount ($)", "number"),
    ],
    "MandatoryRangeEscalating": [
        ("min_amount", "Min amount ($)", "number"),
        ("max_amount", "Max amount ($)", "number"),
        ("mandatory", "Mandatory", "checkbox"),
        ("escalates_on_prior_within", "Escalates on prior within", "text"),
        ("escalated_min", "Escalated min ($)", "number"),
        ("escalated_max", "Escalated max ($)", "number"),
        ("requires_pairing", "Requires pairing with", "text"),
    ],
    "IndeterminateFelonyRange": [
        ("max_term_min_years", "Max term \u2014 min years", "number"),
        ("max_term_max_years", "Max term \u2014 max years", "number"),
        ("has_alt_definite_option", "Has alternative definite option", "checkbox"),
        ("alt_definite_max_days", "Alt. definite max (days)", "number"),
    ],
    "DefiniteSentenceSimple": [
        ("max_months", "Max months", "number"),
    ],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS statutes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    section TEXT NOT NULL,
    section_text TEXT,
    effective_date TEXT,
    repeal_date TEXT
);
CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier TEXT NOT NULL,
    is_felony INTEGER DEFAULT 0,
    is_violent INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS modifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    class_shift_rule TEXT,
    citation_base TEXT
);
CREATE TABLE IF NOT EXISTS offenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statute_id INTEGER REFERENCES statutes(id),
    subsection TEXT,
    name TEXT NOT NULL,
    elements_text TEXT,
    base_classification_id INTEGER REFERENCES classifications(id)
);
CREATE TABLE IF NOT EXISTS offense_modifiers (
    -- LEGACY TABLE: kept for migration warning only.
    -- Do not add new rows here. Use offense_modifier_eligibility instead.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offense_id INTEGER REFERENCES offenses(id),
    modifier_id INTEGER REFERENCES modifiers(id),
    resulting_classification_id INTEGER REFERENCES classifications(id)
);
CREATE TABLE IF NOT EXISTS provision_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provision_type_id INTEGER REFERENCES provision_types(id),
    rule_subtype TEXT NOT NULL,
    classification_id INTEGER REFERENCES classifications(id),
    statute_basis_id INTEGER REFERENCES statutes(id),
    template_text TEXT,
    citation_base TEXT,
    parameters TEXT
);
-- Shared lookup: (modifier x base_classification) -> resulting_classification.
-- Covers ~30-40 rows total for all three NY enhancement statutes:
--   PL 485.10 (Hate Crime), PL 490.25 (Crime of Terrorism),
--   PL 130.91 (Sexually Motivated Felony).
-- Populated once from verified statute text via the "Run seed data" button in §6.
--
-- IMPORTANT CAVEATS:
--   1. Rows where resolution_note contains "TODO: add SentencingRule" represent
--      minimum-term or life-sentence enhancements that are NOT pure classification
--      shifts. A companion entry in the `rules` table is required to fully model
--      those cases. This table alone is insufficient for those rows.
--   2. This table was populated from statute text verified as of mid-2026.
--      It is NOT a substitute for legal review before production use.
--      Use verified_by / verified_date columns to record legal sign-off per row.
CREATE TABLE IF NOT EXISTS classification_resolution (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    modifier_id                 INTEGER REFERENCES modifiers(id),
    base_classification_id      INTEGER REFERENCES classifications(id),
    resulting_classification_id INTEGER REFERENCES classifications(id),
    resolution_note             TEXT,
    citation                    TEXT,
    verified_by                 TEXT,   -- nullable; legal reviewer name/initials
    verified_date               TEXT    -- nullable; ISO date of legal sign-off
);
-- Which offenses are legally eligible to carry a given modifier.
-- Eligibility is offense-specific: each enhancement statute enumerates a
-- closed list of "specified offenses" (e.g. PL 130.91(2) lists ~29 offenses).
-- Classification resolution is NOT stored here -- it is computed on-the-fly
-- from classification_resolution via resolve_classification().
CREATE TABLE IF NOT EXISTS offense_modifier_eligibility (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    offense_id  INTEGER REFERENCES offenses(id),
    modifier_id INTEGER REFERENCES modifiers(id)
);
"""

ENTITIES = {
    "statutes":                     {"label": "Statutes",                     "cite": "\u00a71", "singular": "Statute"},
    "classifications":              {"label": "Classifications",              "cite": "\u00a72", "singular": "Classification"},
    "modifiers":                    {"label": "Modifiers",                    "cite": "\u00a73", "singular": "Modifier"},
    "offenses":                     {"label": "Offenses",                     "cite": "\u00a74", "singular": "Offense"},
    "offense_modifier_eligibility": {"label": "Offense\u2013Modifier Eligibility", "cite": "\u00a75", "singular": "Eligibility link"},
    "classification_resolution":    {"label": "Classification Resolution",    "cite": "\u00a76", "singular": "Resolution rule"},
    "provision_types":              {"label": "Provision Types",              "cite": "\u00a77", "singular": "Provision type"},
    "rules":                        {"label": "Sentencing Rules",             "cite": "\u00a78", "singular": "Sentencing rule"},
}

# ---- Seed data for classification_resolution ----------------------------
# Source: PL 485.10 (Hate Crime), PL 490.25 (Crime of Terrorism),
#         PL 130.91 (Sexually Motivated Felony).
# Each tuple: (modifier_name, base_tier, result_tier, citation, note)
# Names must exactly match what is entered in the modifiers / classifications tables.
SEED_RESOLUTION_RULES = [
    # ---- Hate Crime (PL 485.10) ----------------------------------------
    # Already violent felonies: stay in the same tier (PL 485.10(1))
    ("Hate Crime", "Class B Violent Felony", "Class B Violent Felony",
     "PL 485.10(1)", "Already a violent felony \u2014 no tier shift per PL 485.10(1)."),
    ("Hate Crime", "Class C Violent Felony", "Class C Violent Felony",
     "PL 485.10(1)", "Already a violent felony \u2014 no tier shift per PL 485.10(1)."),
    ("Hate Crime", "Class D Violent Felony", "Class D Violent Felony",
     "PL 485.10(1)", "Already a violent felony \u2014 no tier shift per PL 485.10(1)."),
    ("Hate Crime", "Class E Violent Felony", "Class E Violent Felony",
     "PL 485.10(1)", "Already a violent felony \u2014 no tier shift per PL 485.10(1)."),
    # Non-violent felonies: one tier higher + violent (PL 485.10(2))
    ("Hate Crime", "Class E Felony", "Class D Violent Felony",
     "PL 485.10(2)", "One tier higher; becomes violent felony."),
    ("Hate Crime", "Class D Felony", "Class C Violent Felony",
     "PL 485.10(2)", "One tier higher; becomes violent felony."),
    ("Hate Crime", "Class C Felony", "Class B Violent Felony",
     "PL 485.10(2)", "One tier higher; becomes violent felony."),
    # Misdemeanors (PL 485.10(2))
    ("Hate Crime", "Class B Misdemeanor", "Class A Misdemeanor",
     "PL 485.10(2)", "One category higher."),
    ("Hate Crime", "Class A Misdemeanor", "Class E Felony",
     "PL 485.10(2)",
     "NEEDS REVIEW: 'one category higher than a misdemeanor' \u2014 confirm exact "
     "statutory wording with legal reviewer before finalizing."),
    # Class B Felony: no tier shift; minimum term enhanced only (PL 485.10(3))
    ("Hate Crime", "Class B Felony", "Class B Felony",
     "PL 485.10(3)",
     "No tier shift. Minimum term enhanced only. "
     "TODO: add SentencingRule entry for the enhanced minimum term \u2014 "
     "this row alone does not capture the full enhancement."),
    # Class A-I Felony: no tier shift; minimum term \u226520 yrs (PL 485.10(4))
    ("Hate Crime", "Class A-I Felony", "Class A-I Felony",
     "PL 485.10(4)",
     "No tier shift. Minimum term enhanced to not less than 20 years. "
     "TODO: add SentencingRule entry for the enhanced minimum term \u2014 "
     "this row alone does not capture the full enhancement."),

    # ---- Crime of Terrorism (PL 490.25) ---------------------------------
    # Non-violent felonies: one tier higher + violent (PL 490.25(2)(a)+(b))
    ("Crime of Terrorism", "Class E Felony", "Class D Violent Felony",
     "PL 490.25(2)(a)+(b)", "Becomes violent AND shifts one category higher."),
    ("Crime of Terrorism", "Class D Felony", "Class C Violent Felony",
     "PL 490.25(2)(a)+(b)", "Becomes violent AND shifts one category higher."),
    ("Crime of Terrorism", "Class C Felony", "Class B Violent Felony",
     "PL 490.25(2)(a)+(b)", "Becomes violent AND shifts one category higher."),
    # Class B Felony \u2192 Class A-I: DISTINCT rule, not a simple +1 tier (PL 490.25(2)(c))
    ("Crime of Terrorism", "Class B Felony", "Class A-I Felony",
     "PL 490.25(2)(c)",
     "EXCEPTION: this is a distinct statutory rule, NOT a standard +1 tier shift. "
     "Flag clearly for legal review."),
    # Class A-I: classification unchanged; sentence = life without parole (PL 490.25(2)(d))
    ("Crime of Terrorism", "Class A-I Felony", "Class A-I Felony",
     "PL 490.25(2)(d)",
     "No tier shift. Sentence becomes life without parole. "
     "TODO: add SentencingRule entry for life without parole \u2014 "
     "this row alone does not capture the full enhancement."),

    # ---- Sexually Motivated Felony (PL 130.91) --------------------------
    # Same letter class, violent redesignation only \u2014 no tier shift.
    # NOTE: applies ONLY to the ~29 specified offenses in PL 130.91(2).
    # Eligibility must be set per offense in offense_modifier_eligibility.
    ("Sexually Motivated Felony", "Class E Felony", "Class E Violent Felony",
     "PL 130.91",
     "Violent redesignation only; no tier shift. Only for specified offenses in PL 130.91(2)."),
    ("Sexually Motivated Felony", "Class D Felony", "Class D Violent Felony",
     "PL 130.91",
     "Violent redesignation only; no tier shift. Only for specified offenses in PL 130.91(2)."),
    ("Sexually Motivated Felony", "Class C Felony", "Class C Violent Felony",
     "PL 130.91",
     "Violent redesignation only; no tier shift. Only for specified offenses in PL 130.91(2)."),
    ("Sexually Motivated Felony", "Class B Felony", "Class B Violent Felony",
     "PL 130.91",
     "Violent redesignation only; no tier shift. Only for specified offenses in PL 130.91(2)."),

    # ---- PRI 2nd Degree (PL 70.04(1)) ------------------------------------
    # Prior: Class A-I, A-II, B Violent, C Violent, D Violent, or B Felony
    # Within 10 years. Result: current offense class shifts +1 tier.
    ("PRI 2nd Degree", "Class E Felony", "Class D Violent Felony",
     "PL 70.04(1)", "One tier higher; becomes violent felony."),
    ("PRI 2nd Degree", "Class D Felony", "Class C Violent Felony",
     "PL 70.04(1)", "One tier higher; becomes violent felony."),
    ("PRI 2nd Degree", "Class C Felony", "Class B Violent Felony",
     "PL 70.04(1)", "One tier higher; becomes violent felony."),
    ("PRI 2nd Degree", "Class B Felony", "Class A-I Felony",
     "PL 70.04(1)", "Two tiers higher (capped at A-I)."),
    ("PRI 2nd Degree", "Class B Misdemeanor", "Class A Misdemeanor",
     "PL 70.04(1)", "One category higher."),
    ("PRI 2nd Degree", "Class A Misdemeanor", "Class E Felony",
     "PL 70.04(1)", "One category higher."),

    # ---- PRI 2nd Degree — Already 2nd (PL 70.04(2)) ---------------------
    # Prior: Class A-I, A-II, B Violent, C Violent, D Violent, or B Felony
    # Within 10 years. Already a PRI 2nd. Result: current offense class shifts +2 tiers.
    ("PRI 2nd Degree (Already 2nd)", "Class E Felony", "Class C Violent Felony",
     "PL 70.04(2)", "Two tiers higher; becomes violent felony."),
    ("PRI 2nd Degree (Already 2nd)", "Class D Felony", "Class B Violent Felony",
     "PL 70.04(2)", "Two tiers higher; becomes violent felony."),
    ("PRI 2nd Degree (Already 2nd)", "Class C Felony", "Class A-I Felony",
     "PL 70.04(2)", "Three tiers higher (capped at A-I)."),
    ("PRI 2nd Degree (Already 2nd)", "Class B Felony", "Class A-I Felony",
     "PL 70.04(2)", "Capped at A-I Felony."),
    ("PRI 2nd Degree (Already 2nd)", "Class B Misdemeanor", "Class A-I Felony",
     "PL 70.04(2)", "Capped at A-I Felony."),
    ("PRI 2nd Degree (Already 2nd)", "Class A Misdemeanor", "Class A-I Felony",
     "PL 70.04(2)", "Capped at A-I Felony."),

    # ---- PRI 3rd Degree (PL 70.03) --------------------------------------
    # Prior: Class C Violent, D Violent, B Felony, or C Felony
    # Within 10 years. Result: violent redesignation only, no tier shift.
    ("PRI 3rd Degree", "Class E Felony", "Class E Violent Felony",
     "PL 70.03", "Violent redesignation only; no tier shift."),
    ("PRI 3rd Degree", "Class D Felony", "Class D Violent Felony",
     "PL 70.03", "Violent redesignation only; no tier shift."),
    ("PRI 3rd Degree", "Class C Felony", "Class C Violent Felony",
     "PL 70.03", "Violent redesignation only; no tier shift."),
    ("PRI 3rd Degree", "Class B Felony", "Class B Violent Felony",
     "PL 70.03", "Violent redesignation only; no tier shift."),

    # ---- Juvenile PRI (PL 40.12) ----------------------------------------
    # Juvenile adjudication (16+) that would be a class A–D felony if committed by an adult.
    # Treated as a prior conviction for PRI purposes.
    # Same resolution as adult priors of equivalent degree.
    ("Juvenile PRI", "Class E Felony", "Class D Violent Felony",
     "PL 40.12, PL 70.04(1)", "Juvenile adjudication counts as PRI 2nd Degree. One tier higher; becomes violent felony."),
    ("Juvenile PRI", "Class D Felony", "Class C Violent Felony",
     "PL 40.12, PL 70.04(1)", "Juvenile adjudication counts as PRI 2nd Degree. One tier higher; becomes violent felony."),
    ("Juvenile PRI", "Class C Felony", "Class B Violent Felony",
     "PL 40.12, PL 70.04(1)", "Juvenile adjudication counts as PRI 2nd Degree. One tier higher; becomes violent felony."),
    ("Juvenile PRI", "Class B Felony", "Class A-I Felony",
     "PL 40.12, PL 70.04(1)", "Juvenile adjudication counts as PRI 2nd Degree. Capped at A-I."),
    ("Juvenile PRI", "Class B Misdemeanor", "Class A Misdemeanor",
     "PL 40.12, PL 70.04(1)", "Juvenile adjudication counts as PRI 2nd Degree. One category higher."),
    ("Juvenile PRI", "Class A Misdemeanor", "Class E Felony",
     "PL 40.12, PL 70.04(1)", "Juvenile adjudication counts as PRI 2nd Degree. One category higher."),
]


# ---- Open Legislation lookup widget ------------------------------------

def render_open_legislation_lookup(page_key: str):
    """Collapsible panel that fetches a law sub-document by lawId + locationId."""
    with st.expander("\U0001f50d Open Legislation lookup", expanded=False):
        col1, col2 = st.columns([1, 2])
        law_id = col1.selectbox(
            "Law",
            LAW_ID_OPTIONS,
            key=f"ol_law_{page_key}",
            help="Three-letter NYS law code, e.g. PL for Penal Law",
        )
        location_id = col2.text_input(
            "Section / Article / Location ID",
            placeholder="e.g. 120.05  or  A70  or  T1",
            key=f"ol_loc_{page_key}",
        )
        if st.button("Fetch", key=f"ol_btn_{page_key}"):
            if not location_id.strip():
                st.warning("Enter a section or article number.")
            else:
                url = f"{OPEN_LEG_BASE}/{law_id.strip()}/{location_id.strip()}"
                try:
                    resp = requests.get(url, params={"key": OPEN_LEG_API_KEY}, timeout=10)
                    data = resp.json()
                except Exception as exc:
                    st.error(f"Request failed: {exc}")
                    return
                if not data.get("success"):
                    st.error(
                        f"API error: {data.get('message', 'Unknown error')} "
                        f"(code {data.get('errorCode', '?')})"
                    )
                    return
                result = data.get("result", {})
                title = result.get("title", "\u2014")
                doc_type = result.get("docType", "\u2014")
                active_date = result.get("activeDate", "\u2014")
                text = result.get("text") or ""
                st.markdown(
                    f"**{law_id} {location_id}** \u00b7 {doc_type} \u00b7 *{title}*  "
                    f"(active {active_date})"
                )
                if text:
                    st.text_area(
                        "Statutory text",
                        value=text,
                        height=300,
                        key=f"ol_text_{page_key}",
                        disabled=True,
                    )
                else:
                    st.info("No text returned for this location (it may be a structural node).")


@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema():
    """Apply all CREATE TABLE IF NOT EXISTS statements. Called on every app start
    so new tables are always created even when the connection is already cached."""
    conn = get_conn()
    with closing(conn.cursor()) as cur:
        cur.executescript(SCHEMA)
    conn.commit()


def fetch_df(table, extra_select="*"):
    conn = get_conn()
    return pd.read_sql_query(f"SELECT {extra_select} FROM {table} ORDER BY id DESC", conn)


def fetch_options(table, label_fn):
    df = fetch_df(table)
    if df.empty:
        return {}
    return {row["id"]: label_fn(row) for _, row in df.iterrows()}


def statute_label(row):
    return f"{row['title']} {row['section']}"


def classification_label(row):
    return row["tier"]


def modifier_label(row):
    return row["name"]


def offense_label(row):
    return row["name"]


def provision_type_label(row):
    return row["name"]


def insert_row(table, fields: dict):
    conn = get_conn()
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["?"] * len(fields))
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(fields.values()))
    conn.commit()


def delete_row(table, row_id):
    conn = get_conn()
    try:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def render_delete_control(table, df):
    if df.empty:
        return
    st.caption("Delete a record")
    options = {int(row["id"]): f"#{int(row['id'])}" for _, row in df.iterrows()}
    col1, col2 = st.columns([3, 1])
    with col1:
        target = st.selectbox(
            "Record ID", list(options.keys()),
            format_func=lambda x: options[x],
            key=f"del_{table}",
            label_visibility="collapsed",
        )
    with col2:
        if st.button("Delete", key=f"delbtn_{table}"):
            ok = delete_row(table, target)
            if ok:
                st.rerun()
            else:
                st.error(
                    "Can\u2019t delete \u2014 this record is still referenced by another table. "
                    "Delete the dependent records first."
                )


def _parse_date(s):
    import datetime
    try:
        return datetime.date.fromisoformat(s) if s else None
    except ValueError:
        return None


# ---- Classification resolution helper ----------------------------------

def resolve_classification(offense_id: int, modifier_id: int) -> dict:
    """
    Derives the resulting classification for an (offense, modifier) pair:
      1. Looks up the offense's base_classification_id.
      2. Joins into classification_resolution on (modifier_id, base_classification_id).
    Returns a dict with keys:
      found (bool), base_tier, resulting_tier, resulting_classification_id,
      citation, resolution_note   -- or --
      found=False, message (str)
    """
    conn = get_conn()
    offense_row = conn.execute(
        "SELECT base_classification_id FROM offenses WHERE id = ?", (offense_id,)
    ).fetchone()
    if not offense_row:
        return {"found": False, "message": "Offense not found."}
    base_class_id = offense_row[0]
    if base_class_id is None:
        return {"found": False, "message": "Offense has no base classification assigned."}

    row = conn.execute(
        """
        SELECT cr.resulting_classification_id,
               cr.citation,
               cr.resolution_note,
               c_base.tier  AS base_tier,
               c_res.tier   AS resulting_tier
        FROM   classification_resolution cr
        JOIN   classifications c_base ON c_base.id = cr.base_classification_id
        JOIN   classifications c_res  ON c_res.id  = cr.resulting_classification_id
        WHERE  cr.modifier_id            = ?
        AND    cr.base_classification_id = ?
        """,
        (modifier_id, base_class_id),
    ).fetchone()

    if not row:
        base_tier_row = conn.execute(
            "SELECT tier FROM classifications WHERE id = ?", (base_class_id,)
        ).fetchone()
        base_tier = base_tier_row[0] if base_tier_row else f"id={base_class_id}"
        return {
            "found": False,
            "message": (
                f"No resolution rule defined for base classification \u2018{base_tier}\u2019 "
                "with this modifier. Add it in \u00a76 Classification Resolution."
            ),
        }

    return {
        "found": True,
        "base_tier": row[3],
        "resulting_tier": row[4],
        "resulting_classification_id": row[0],
        "citation": row[1],
        "resolution_note": row[2],
    }


# ---- Migration warning --------------------------------------------------

def check_migration_warning() -> list:
    """
    Returns rows from the legacy offense_modifiers table (if any).
    The table is NOT dropped -- rows are listed so the user can manually
    re-enter them as offense_modifier_eligibility rows in §5.
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT om.id,
                   COALESCE(o.name, '?')  AS offense_name,
                   COALESCE(m.name, '?')  AS modifier_name,
                   COALESCE(c.tier, '?')  AS old_resulting_tier
            FROM   offense_modifiers om
            LEFT JOIN offenses        o ON o.id = om.offense_id
            LEFT JOIN modifiers       m ON m.id = om.modifier_id
            LEFT JOIN classifications c ON c.id = om.resulting_classification_id
            """
        ).fetchall()
        return [
            {"id": r[0], "offense": r[1], "modifier": r[2], "old_class": r[3]}
            for r in rows
        ]
    except Exception:
        return []


PRI_2ND_PRIOR_DEGREES = [
    "Class A-I Felony",
    "Class A-II Felony",
    "Class B Violent Felony",
    "Class C Violent Felony",
    "Class D Violent Felony",
    "Class B Felony",
]

PRI_3RD_PRIOR_DEGREES = [
    "Class C Violent Felony",
    "Class D Violent Felony",
    "Class B Felony",
    "Class C Felony",
]


def resolve_prior_modifier(modifier_options: dict, prior_degree: str, within_10_years: bool, already_2nd: bool, is_juvenile: bool = False) -> dict:
    """
    Maps PRI user inputs to the correct modifier and resolution.
    Returns dict with keys:
      modifier_id, modifier_name, citation, explanation
    Or {"error": "..."} if inputs don't qualify for any PRI.
    """
    if not within_10_years:
        return {"error": "PRI does not apply — prior must be within 10 years of current offense (PL §70.03/70.04 sunset)."}

    if prior_degree in PRI_2ND_PRIOR_DEGREES:
        modifier_name = "PRI 2nd Degree (Already 2nd)" if already_2nd else "PRI 2nd Degree"
        citation = "PL 70.04(2)" if already_2nd else "PL 70.04(1)"
        if is_juvenile:
            citation = "PL 40.12, " + citation
        prior_type = "already a PRI 2nd" if already_2nd else "qualifying prior"
        modifier_id = None
        for mid, mname in modifier_options.items():
            if mname == modifier_name:
                modifier_id = mid
                break
        if modifier_id is None:
            return {"error": f"Modifier '{modifier_name}' not found. Add it in §3 Modifiers first."}
        explanation = (
            f"Prior: {prior_degree} + {prior_type} + within 10 years "
            f"→ {modifier_name} ({citation})"
        )
        return {"modifier_id": modifier_id, "modifier_name": modifier_name, "citation": citation, "explanation": explanation}

    if prior_degree in PRI_3RD_PRIOR_DEGREES:
        modifier_name = "PRI 3rd Degree"
        citation = "PL 70.03"
        if is_juvenile:
            citation = "PL 40.12, " + citation
        modifier_id = None
        for mid, mname in modifier_options.items():
            if mname == modifier_name:
                modifier_id = mid
                break
        if modifier_id is None:
            return {"error": f"Modifier '{modifier_name}' not found. Add it in §3 Modifiers first."}
        explanation = (
            f"Prior: {prior_degree} + within 10 years "
            f"→ {modifier_name} ({citation}) — violent redesignation only, no tier shift."
        )
        return {"modifier_id": modifier_id, "modifier_name": modifier_name, "citation": citation, "explanation": explanation}

    return {"error": f"Prior degree '{prior_degree}' does not qualify for PRI under PL §70.03/70.04."}


# ---- Seed data loader --------------------------------------------------

def seed_classification_resolution() -> str:
    """
    Populates classification_resolution with the verified seed rows defined in
    SEED_RESOLUTION_RULES. Matches modifiers by name and classifications by tier
    string -- both must already exist in the database.
    Idempotent: skips entirely if the table already has rows.
    Returns a human-readable status string.
    """
    conn = get_conn()
    existing = conn.execute("SELECT COUNT(*) FROM classification_resolution").fetchone()[0]
    if existing > 0:
        return f"Seed skipped \u2014 table already has {existing} rows."

    inserted = 0
    skipped = []
    for modifier_name, base_tier, result_tier, citation, note in SEED_RESOLUTION_RULES:
        mod_row  = conn.execute("SELECT id FROM modifiers       WHERE name = ?", (modifier_name,)).fetchone()
        base_row = conn.execute("SELECT id FROM classifications WHERE tier = ?", (base_tier,)).fetchone()
        res_row  = conn.execute("SELECT id FROM classifications WHERE tier = ?", (result_tier,)).fetchone()
        if mod_row and base_row and res_row:
            conn.execute(
                """INSERT INTO classification_resolution
                   (modifier_id, base_classification_id, resulting_classification_id,
                    resolution_note, citation)
                   VALUES (?, ?, ?, ?, ?)""",
                (mod_row[0], base_row[0], res_row[0], note, citation),
            )
            inserted += 1
        else:
            missing = []
            if not mod_row:  missing.append(f"modifier \u2018{modifier_name}\u2019")
            if not base_row: missing.append(f"classification \u2018{base_tier}\u2019")
            if not res_row:  missing.append(f"classification \u2018{result_tier}\u2019")
            skipped.append(f"{modifier_name} / {base_tier}: missing {', '.join(missing)}")
    conn.commit()

    if not skipped:
        return f"\u2705 Seeded {inserted} rows successfully."
    return (
        f"Seeded {inserted} rows. {len(skipped)} skipped (missing prereqs):\n"
        + "\n".join(f"  \u2022 {s}" for s in skipped)
    )


# ---- NY Classification Tier Seed Data ----------------------------------
# All 14 NY felony/misdemeanor/violation tiers with is_felony and is_violent flags.
# Sources: PL 5.05, PL 70.00, PL 70.02, PL 70.15.
NY_CLASSIFICATIONS = [
    # Felonies (10 tiers)
    ("Class A-I Felony", 1, 0, "PL 70.00(3)(a)"),
    ("Class A-II Felony", 1, 0, "PL 70.00(3)(b)"),
    ("Class B Felony", 1, 0, "PL 70.00(3)(c)"),
    ("Class C Felony", 1, 0, "PL 70.00(3)(c)"),
    ("Class D Felony", 1, 0, "PL 70.00(3)(c)"),
    ("Class E Felony", 1, 0, "PL 70.00(3)(c)"),
    ("Class B Violent Felony", 1, 1, "PL 70.02(3)(a)"),
    ("Class C Violent Felony", 1, 1, "PL 70.02(3)(b)"),
    ("Class D Violent Felony", 1, 1, "PL 70.02(3)(c)"),
    ("Class E Violent Felony", 1, 1, "PL 70.02(3)(d)"),
    # Misdemeanors (3 tiers)
    ("Class A Misdemeanor", 0, 0, "PL 70.15(1)"),
    ("Class B Misdemeanor", 0, 0, "PL 70.15(2)"),
    ("Unclassified Misdemeanor", 0, 0, "PL 70.15(3)"),
    # Violations (1 tier)
    ("Violation", 0, 0, "PL 70.15(4)"),
]


def seed_classifications() -> str:
    """
    Populates classifications with all 14 NY tiers.
    Idempotent: skips tiers that already exist.
    Returns a human-readable status string.
    """
    conn = get_conn()
    existing_tiers = {
        row[0]
        for row in conn.execute("SELECT tier FROM classifications").fetchall()
    }
    inserted = 0
    skipped = []
    for tier, is_felony, is_violent, citation in NY_CLASSIFICATIONS:
        if tier in existing_tiers:
            skipped.append(f"  \u2022 {tier} (already exists)")
            continue
        conn.execute(
            """INSERT INTO classifications (tier, is_felony, is_violent)
               VALUES (?, ?, ?)""",
            (tier, is_felony, is_violent),
        )
        inserted += 1
        existing_tiers.add(tier)
    conn.commit()
    if inserted == 0:
        return f"\u2705 All {len(NY_CLASSIFICATIONS)} tiers already exist."
    return f"\u2705 Seeded {inserted} classification tier(s). {len(skipped)} skipped."


# ========================================================================
# PAGE FUNCTIONS
# ========================================================================

def statutes_page():
    st.subheader("\u00a71 Statutes")

    # ---- Step 1: API lookup (outside the form so it can update session state) ----
    st.markdown("##### \U0001f50d Look up a statute via Open Legislation")
    col1, col2, col3 = st.columns([1, 2, 1])
    law_sel = col1.selectbox("Law", LAW_ID_OPTIONS, key="stat_law_sel")
    loc_inp = col2.text_input(
        "Section / Location ID",
        placeholder="e.g. 168-T  or  120.05",
        key="stat_loc_inp",
    )
    col3.markdown("<br>", unsafe_allow_html=True)
    fetch_clicked = col3.button("Fetch \u2197", key="stat_fetch_btn", use_container_width=True)

    if fetch_clicked:
        loc = loc_inp.strip()
        if not loc:
            st.warning("Enter a section or location ID.")
        else:
            url = f"{OPEN_LEG_BASE}/{law_sel}/{loc}"
            try:
                data = requests.get(url, params={"key": OPEN_LEG_API_KEY}, timeout=10).json()
            except Exception as exc:
                st.error(f"Request failed: {exc}")
                data = {}
            if data.get("success"):
                res = data["result"]
                st.session_state["stat_pf"] = {
                    "law_id":        res.get("lawId", law_sel),
                    "law_name":      res.get("lawName", ""),
                    "location_id":   res.get("locationId", loc),
                    "api_title":     res.get("title", ""),
                    "doc_type":      res.get("docType", ""),
                    "section_text":  (res.get("text") or "").strip(),
                    "active_date":   res.get("activeDate") or "",
                    "repealed_date": res.get("repealedDate") or "",
                }
            else:
                st.error(data.get("message", "Document not found."))
                st.session_state.pop("stat_pf", None)

    pf = st.session_state.get("stat_pf", {})

    if pf:
        st.success(
            f"\U0001f4c4 **{pf['law_name']} ({pf['law_id']}) \u00a7\u00a0{pf['location_id']}** "
            f"\u2014 {pf['api_title']} ({pf['doc_type']})"
        )

    st.markdown("---")
    st.markdown("##### Confirm and save")

    default_law_idx = LAW_ID_OPTIONS.index(pf["law_id"]) if pf.get("law_id") in LAW_ID_OPTIONS else 0
    with st.form("add_statute", clear_on_submit=True):
        c1, c2 = st.columns(2)
        title   = c1.selectbox("Law", LAW_ID_OPTIONS, index=default_law_idx)
        section = c2.text_input("Section", value=pf.get("location_id", ""), placeholder="120.05")
        section_text = st.text_area(
            "Section text",
            value=pf.get("section_text", ""),
            placeholder="Full statutory language \u2014 auto-filled after Fetch",
            height=200,
        )
        c3, c4 = st.columns(2)
        effective_date = c3.date_input("Effective date", value=_parse_date(pf.get("active_date", "")))
        repeal_date    = c4.date_input("Repeal date",    value=_parse_date(pf.get("repealed_date", "")))

        if st.form_submit_button("Add statute"):
            if section:
                insert_row("statutes", {
                    "title": title,
                    "section": section,
                    "section_text": section_text,
                    "effective_date": str(effective_date) if effective_date else None,
                    "repeal_date":    str(repeal_date)    if repeal_date    else None,
                })
                st.session_state.pop("stat_pf", None)
                st.success("Statute added.")
                st.rerun()
            else:
                st.error("Section is required.")

    df = fetch_df("statutes")
    st.dataframe(df, use_container_width=True, hide_index=True)
    render_delete_control("statutes", df)


def classifications_page():
    st.subheader("\u00a72 Classifications")
    st.caption(
        "NY Penal Law \u00a75.05 classification tiers. "
        "\u26a0\ufe0f Verify all tiers against current statute text \u2014 "
        "NOT a substitute for legal review."
    )
    render_open_legislation_lookup("classifications")

    col_seed, _ = st.columns([1, 3])
    if col_seed.button(
        "\U0001f331 Seed all 14 NY tiers", key="seed_classifications_btn",
        help="Populates all 14 NY classification tiers (PL 5.05, 70.00, 70.02, 70.15). Idempotent.",
    ):
        msg = seed_classifications()
        if msg.startswith("\u2705"):
            st.success(msg)
            st.rerun()
        else:
            st.warning(msg)

    with st.form("add_classification", clear_on_submit=True):
        tier = st.text_input("Tier", placeholder="Class E Felony")
        c1, c2 = st.columns(2)
        is_felony  = c1.checkbox("Is felony")
        is_violent = c2.checkbox("Is violent")
        if st.form_submit_button("Add classification"):
            if tier:
                insert_row("classifications", {
                    "tier": tier,
                    "is_felony": int(is_felony),
                    "is_violent": int(is_violent),
                })
                st.success("Classification added.")
                st.rerun()
            else:
                st.error("Tier is required.")

    df = fetch_df("classifications")
    st.dataframe(df, use_container_width=True, hide_index=True)
    render_delete_control("classifications", df)


def modifiers_page():
    st.subheader("\u00a73 Modifiers")
    render_open_legislation_lookup("modifiers")
    with st.form("add_modifier", clear_on_submit=True):
        name = st.text_input("Name", placeholder="Hate Crime")
        c1, c2 = st.columns(2)
        class_shift_rule = c1.text_input("Class shift rule", placeholder="+1 tier")
        citation_base    = c2.text_input("Citation base",    placeholder="PL 485.10")
        if st.form_submit_button("Add modifier"):
            if name:
                insert_row("modifiers", {
                    "name": name,
                    "class_shift_rule": class_shift_rule,
                    "citation_base": citation_base,
                })
                st.success("Modifier added.")
                st.rerun()
            else:
                st.error("Name is required.")

    df = fetch_df("modifiers")
    st.dataframe(df, use_container_width=True, hide_index=True)
    render_delete_control("modifiers", df)


def offenses_page():
    st.subheader("\u00a74 Offenses")
    render_open_legislation_lookup("offenses")

    statute_options = fetch_options("statutes", statute_label)
    class_options   = fetch_options("classifications", classification_label)

    if not statute_options or not class_options:
        st.warning("Add at least one Statute (\u00a71) and one Classification (\u00a72) first.")
        return

    with st.form("add_offense", clear_on_submit=True):
        statute_id = st.selectbox(
            "Statute", list(statute_options.keys()),
            format_func=lambda x: statute_options[x],
        )
        c1, c2 = st.columns(2)
        subsection = c1.text_input("Subsection", placeholder="01")
        name       = c2.text_input("Name", placeholder="Grand Larceny in the Fourth Degree")
        elements_text = st.text_area("Elements text")
        base_classification_id = st.selectbox(
            "Base classification", list(class_options.keys()),
            format_func=lambda x: class_options[x],
        )
        if st.form_submit_button("Add offense"):
            if name:
                insert_row("offenses", {
                    "statute_id": statute_id,
                    "subsection": subsection,
                    "name": name,
                    "elements_text": elements_text,
                    "base_classification_id": base_classification_id,
                })
                st.success("Offense added.")
                st.rerun()
            else:
                st.error("Name is required.")

    df = fetch_df("offenses")
    if not df.empty:
        df["statute"]            = df["statute_id"].map(statute_options)
        df["base_classification"] = df["base_classification_id"].map(class_options)
    st.dataframe(df, use_container_width=True, hide_index=True)
    render_delete_control("offenses", df)

    # ---- PRI / Juvenile PRI resolver -----------------------------------
    modifier_options = fetch_options("modifiers", modifier_label)
    pri_qualifying = [d for d in PRI_2ND_PRIOR_DEGREES + PRI_3RD_PRIOR_DEGREES]

    if modifier_options:
        with st.expander("\U0001f4c6 PRI / Juvenile PRI Resolution", expanded=False):
            st.caption(
                "Maps prior conviction details to the correct PRI modifier and resolves the "
                "classification shift. PL §70.03 (3rd Degree), §70.04 (2nd Degree), §40.12 (Juvenile)."
            )

            c1, c2 = st.columns(2)
            pri_type = c1.selectbox(
                "Prior type",
                ["Adult prior conviction", "Juvenile adjudication (PL 40.12)"],
                key="pri_type_sel",
            )
            within_10 = c2.selectbox(
                "Prior committed within last 10 years?",
                ["Yes", "No"],
                key="pri_within_10_sel",
            )

            if within_10 == "Yes":
                c3, c4 = st.columns(2)
                prior_degree = c3.selectbox(
                    "Degree of most serious prior",
                    pri_qualifying,
                    key="pri_degree_sel",
                )
                already_2nd = c4.selectbox(
                    "Already a PRI 2nd Degree?",
                    ["No", "Yes"],
                    key="pri_already_2nd_sel",
                )

                if st.button("Resolve PRI", key="pri_resolve_btn"):
                    is_juvenile = pri_type == "Juvenile adjudication (PL 40.12)"
                    result = resolve_prior_modifier(
                        modifier_options, prior_degree, True, already_2nd == "Yes", is_juvenile
                    )
                    if "error" in result:
                        st.warning(result["error"])
                    else:
                        st.success(
                            f"**{result['explanation']}**\n\n"
                            f"→ Modifier: `{result['modifier_name']}`\n"
                            f"→ Citation: `{result['citation']}`"
                        )
            else:
                st.info("PRI does not apply — prior is outside the 10-year sunset window.")

    # ---- Enhancement resolver panel ------------------------------------
    modifier_options = fetch_options("modifiers", modifier_label)
    elig_df = fetch_df("offense_modifier_eligibility")
    if not df.empty and not elig_df.empty and modifier_options:
        with st.expander("\U0001f517 Resolve enhancement classifications", expanded=False):
            offense_ids = {
                int(row["id"]): row.get("name", f"#{int(row['id'])}")
                for _, row in df.iterrows()
            }
            sel_offense = st.selectbox(
                "Select offense", list(offense_ids.keys()),
                format_func=lambda x: offense_ids[x],
                key="resolver_offense_sel",
            )
            eligible = elig_df[elig_df["offense_id"] == sel_offense]["modifier_id"].tolist()
            if not eligible:
                st.info(
                    "No modifier eligibility rows for this offense. "
                    "Add them in \u00a75 Offense\u2013Modifier Eligibility."
                )
            else:
                rows = []
                for mod_id in eligible:
                    r = resolve_classification(sel_offense, int(mod_id))
                    rows.append({
                        "Modifier":         modifier_options.get(int(mod_id), f"#{mod_id}"),
                        "Base tier":        r.get("base_tier", "\u2014"),
                        "\u2192 Resulting": r.get("resulting_tier", "\u26a0 " + r.get("message", "")) if r["found"] else ("\u26a0 " + r.get("message", "")),
                        "Citation":         r.get("citation", "") if r["found"] else "",
                        "Note":             r.get("resolution_note", "") if r["found"] else "",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def offense_modifier_eligibility_page():
    st.subheader("\u00a75 Offense\u2013Modifier Eligibility")
    st.caption(
        "Records which offenses are legally eligible to carry a given modifier "
        "(i.e. the offense appears in that statute\u2019s \u2018specified offenses\u2019 list). "
        "Classification resolution is computed automatically from \u00a76."
    )
    render_open_legislation_lookup("offense_modifier_eligibility")

    offense_options  = fetch_options("offenses",  offense_label)
    modifier_options = fetch_options("modifiers", modifier_label)

    if not offense_options or not modifier_options:
        st.warning(
            "Add at least one Offense (\u00a74) and one Modifier (\u00a73) first."
        )
        return

    with st.form("add_elig", clear_on_submit=True):
        offense_id  = st.selectbox(
            "Offense",  list(offense_options.keys()),
            format_func=lambda x: offense_options[x],
        )
        modifier_id = st.selectbox(
            "Modifier", list(modifier_options.keys()),
            format_func=lambda x: modifier_options[x],
        )
        if st.form_submit_button("Add eligibility link"):
            insert_row("offense_modifier_eligibility", {
                "offense_id": offense_id,
                "modifier_id": modifier_id,
            })
            st.success("Eligibility link added.")
            st.rerun()

    df = fetch_df("offense_modifier_eligibility")
    if not df.empty:
        df["offense"]  = df["offense_id"].map(offense_options)
        df["modifier"] = df["modifier_id"].map(modifier_options)
    st.dataframe(df, use_container_width=True, hide_index=True)
    render_delete_control("offense_modifier_eligibility", df)


def classification_resolution_page():
    st.subheader("\u00a76 Classification Resolution")
    st.caption(
        "Shared lookup: (modifier \u00d7 base classification) \u2192 resulting classification. "
        "~30\u201340 rows total; covers PL\u00a0485.10, PL\u00a0490.25, PL\u00a0130.91. "
        "\u26a0\ufe0f Verified against statute text current as of mid-2026 \u2014 "
        "NOT a substitute for legal review before production use. "
        "Use the Verified\u00a0by / Verified\u00a0date fields to record legal sign-off per row."
    )
    render_open_legislation_lookup("classification_resolution")

    # ---- Seed button ----
    col_seed, _ = st.columns([1, 3])
    if col_seed.button(
        "\U0001f331 Run seed data", key="seed_btn",
        help=(
            "Inserts the ~23 verified resolution rules. "
            "Requires modifiers and classifications to be populated first with "
            "exact names: \u2018Hate Crime\u2019, \u2018Crime of Terrorism\u2019, "
            "\u2018Sexually Motivated Felony\u2019 and matching tier strings."
        ),
    ):
        msg = seed_classification_resolution()
        if msg.startswith("\u2705"):
            st.success(msg)
            st.rerun()
        else:
            st.warning(msg)

    st.markdown("---")

    modifier_options = fetch_options("modifiers", modifier_label)
    class_options    = fetch_options("classifications", classification_label)

    if not modifier_options or not class_options:
        st.info(
            "Add Modifiers (\u00a73) and Classifications (\u00a72) first, "
            "then use \u2018Run seed data\u2019 to auto-populate, "
            "or add rows manually below."
        )
    else:
        with st.form("add_resolution", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            modifier_id = c1.selectbox(
                "Modifier", list(modifier_options.keys()),
                format_func=lambda x: modifier_options[x],
            )
            base_classification_id = c2.selectbox(
                "Base classification", list(class_options.keys()),
                format_func=lambda x: class_options[x],
            )
            resulting_classification_id = c3.selectbox(
                "Resulting classification", list(class_options.keys()),
                format_func=lambda x: class_options[x],
            )
            resolution_note = st.text_area(
                "Resolution note",
                placeholder="e.g. No tier shift; min-term enhanced only. TODO: add SentencingRule.",
            )
            c4, c5, c6 = st.columns(3)
            citation      = c4.text_input("Citation",      placeholder="PL 485.10(2)")
            verified_by   = c5.text_input("Verified by",   placeholder="Attorney name / initials")
            verified_date = c6.date_input("Verified date", value=None)

            if st.form_submit_button("Add resolution rule"):
                insert_row("classification_resolution", {
                    "modifier_id":                  modifier_id,
                    "base_classification_id":       base_classification_id,
                    "resulting_classification_id":  resulting_classification_id,
                    "resolution_note":              resolution_note,
                    "citation":                     citation,
                    "verified_by":                  verified_by or None,
                    "verified_date":                str(verified_date) if verified_date else None,
                })
                st.success("Resolution rule added.")
                st.rerun()

    df = fetch_df("classification_resolution")
    if not df.empty:
        df["modifier"]                = df["modifier_id"].map(modifier_options)
        df["base_classification"]     = df["base_classification_id"].map(class_options)
        df["resulting_classification"] = df["resulting_classification_id"].map(class_options)
    st.dataframe(df, use_container_width=True, hide_index=True)
    render_delete_control("classification_resolution", df)

    # ---- Quick resolver ------------------------------------------------
    st.markdown("---")
    st.markdown("##### \U0001f50e Quick resolve")
    offense_options = fetch_options("offenses", offense_label)
    if offense_options and modifier_options:
        r1, r2 = st.columns(2)
        q_offense  = r1.selectbox(
            "Offense",  list(offense_options.keys()),
            format_func=lambda x: offense_options[x], key="qr_offense",
        )
        q_modifier = r2.selectbox(
            "Modifier", list(modifier_options.keys()),
            format_func=lambda x: modifier_options[x], key="qr_modifier",
        )
        if st.button("Resolve", key="qr_btn"):
            result = resolve_classification(int(q_offense), int(q_modifier))
            if result["found"]:
                st.success(
                    f"**{result['base_tier']}** \u2192 **{result['resulting_tier']}**  \n"
                    f"Citation: {result['citation']}  \n"
                    f"Note: {result['resolution_note']}"
                )
            else:
                st.warning(result["message"])
    else:
        st.info("Add Offenses (\u00a74) and Modifiers (\u00a73) to use the quick resolver.")


def provision_types_page():
    st.subheader("\u00a77 Provision Types")
    render_open_legislation_lookup("provision_types")
    with st.form("add_provision_type", clear_on_submit=True):
        name = st.text_input("Name", placeholder="DefiniteSentence")
        if st.form_submit_button("Add provision type"):
            if name:
                insert_row("provision_types", {"name": name})
                st.success("Provision type added.")
                st.rerun()
            else:
                st.error("Name is required.")

    df = fetch_df("provision_types")
    st.dataframe(df, use_container_width=True, hide_index=True)
    render_delete_control("provision_types", df)


def rules_page():
    st.subheader("\u00a78 Sentencing Rules")
    render_open_legislation_lookup("rules")

    provision_options = fetch_options("provision_types", provision_type_label)
    class_options     = fetch_options("classifications", classification_label)
    statute_options   = fetch_options("statutes", statute_label)

    if not provision_options or not class_options:
        st.warning(
            "Add at least one Provision type (\u00a77) and one Classification (\u00a72) first."
        )
        return

    subtype = st.selectbox(
        "Rule subtype", list(RULE_SUBTYPE_FIELDS.keys()), key="rule_subtype_select"
    )

    with st.form("add_rule", clear_on_submit=True):
        provision_type_id = st.selectbox(
            "Provision type", list(provision_options.keys()),
            format_func=lambda x: provision_options[x],
        )
        classification_id = st.selectbox(
            "Classification", list(class_options.keys()),
            format_func=lambda x: class_options[x],
        )
        statute_basis_id = st.selectbox(
            "Statute basis (optional)",
            [None] + list(statute_options.keys()),
            format_func=lambda x: "\u2014 none \u2014" if x is None else statute_options[x],
        )
        template_text = st.text_area(
            "Template text",
            placeholder="A fine of up to {max_amount} dollars\u2026",
        )
        citation_base = st.text_input(
            "Citation", placeholder="Penal Law 60.05(7) and 80.00"
        )

        st.markdown(f"**Parameters for `{subtype}`**")
        params = {}
        for key, label, ftype in RULE_SUBTYPE_FIELDS[subtype]:
            if ftype == "number":
                params[key] = st.number_input(label, value=0, step=1)
            elif ftype == "checkbox":
                params[key] = st.checkbox(label)
            else:
                params[key] = st.text_input(label)

        if st.form_submit_button("Add rule"):
            insert_row("rules", {
                "provision_type_id": provision_type_id,
                "rule_subtype":      subtype,
                "classification_id": classification_id,
                "statute_basis_id":  statute_basis_id,
                "template_text":     template_text,
                "citation_base":     citation_base,
                "parameters":        json.dumps(params),
            })
            st.success("Rule added.")
            st.rerun()

    df = fetch_df("rules")
    if not df.empty:
        df["provision_type"] = df["provision_type_id"].map(provision_options)
        df["classification"] = df["classification_id"].map(class_options)
    st.dataframe(df, use_container_width=True, hide_index=True)
    render_delete_control("rules", df)


def export_page():
    st.subheader("\u00a79 Export")
    st.write("Downloads every table as one JSON file, ready for a loader script.")

    payload = {}
    for table in ENTITIES:
        df = fetch_df(table)
        payload[table] = df.to_dict(orient="records")

    # Materialised resolved view: every (offense, modifier) eligibility pair
    # with the derived base and resulting classification tiers.
    conn = get_conn()
    resolved_rows = conn.execute(
        """
        SELECT o.id           AS offense_id,
               o.name         AS offense_name,
               m.id           AS modifier_id,
               m.name         AS modifier_name,
               c_base.tier    AS base_tier,
               c_res.tier     AS resulting_tier,
               cr.citation,
               cr.resolution_note
        FROM   offense_modifier_eligibility ome
        JOIN   offenses               o      ON o.id  = ome.offense_id
        JOIN   modifiers              m      ON m.id  = ome.modifier_id
        LEFT JOIN classification_resolution cr
               ON  cr.modifier_id            = ome.modifier_id
               AND cr.base_classification_id = o.base_classification_id
        LEFT JOIN classifications c_base ON c_base.id = o.base_classification_id
        LEFT JOIN classifications c_res  ON c_res.id  = cr.resulting_classification_id
        """
    ).fetchall()
    payload["resolved_view"] = [
        {
            "offense_id": r[0], "offense_name": r[1],
            "modifier_id": r[2], "modifier_name": r[3],
            "base_tier": r[4], "resulting_tier": r[5],
            "citation": r[6], "resolution_note": r[7],
        }
        for r in resolved_rows
    ]

    json_bytes = json.dumps(payload, indent=2, default=str).encode("utf-8")
    st.download_button(
        "Download JSON export",
        data=json_bytes,
        file_name="crimetime-data-model-export.json",
        mime="application/json",
    )
    st.json(payload)


PAGES = {
    "statutes":                     statutes_page,
    "classifications":              classifications_page,
    "modifiers":                    modifiers_page,
    "offenses":                     offenses_page,
    "offense_modifier_eligibility": offense_modifier_eligibility_page,
    "classification_resolution":    classification_resolution_page,
    "provision_types":              provision_types_page,
    "rules":                        rules_page,
}


def main():
    st.set_page_config(page_title="Statutory Data Console", layout="wide")
    st.title("Statutory Data Console")
    st.caption(f"Local database: {DB_PATH}")

    # Ensure all tables exist (runs every start; safe with IF NOT EXISTS)
    ensure_schema()

    # ---- Migration warning (legacy offense_modifiers rows) ----
    legacy_rows = check_migration_warning()

    with st.sidebar:
        if legacy_rows:
            st.warning(
                f"\u26a0\ufe0f **Legacy data** \u2014 {len(legacy_rows)} row(s) found in the old "
                "`offense_modifiers` table. Please review and re-enter as "
                "**\u00a75 Offense\u2013Modifier Eligibility** rows.\n\n"
                + "\n".join(
                    f"\u2022 #{r['id']}: {r['offense']} \u00d7 {r['modifier']} "
                    f"(was \u2192 {r['old_class']})"
                    for r in legacy_rows
                )
            )

        st.header("Docket")
        counts = {t: len(fetch_df(t)) for t in ENTITIES}
        choice = st.radio(
            "Section",
            list(ENTITIES.keys()) + ["export"],
            format_func=lambda k: (
                f"{ENTITIES[k]['cite']}  {ENTITIES[k]['label']}  ({counts[k]})"
                if k in ENTITIES
                else "\u00a79  Export"
            ),
            label_visibility="collapsed",
        )

    if choice == "export":
        export_page()
    else:
        PAGES[choice]()


if __name__ == "__main__":
    main()