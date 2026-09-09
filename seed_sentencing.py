"""
seed_sentencing.py

Seeds provision_types and base sentencing rules (imprisonment + fines)
into crimetime_data.db for all 14 NY classification tiers.

Idempotent: skips if rules table already has rows.
Run from the crimetime directory:
    python seed_sentencing.py
"""

import json
import sqlite3

DB_PATH = "crimetime_data.db"

PROVISION_TYPES = [
    "Imprisonment",
    "Fine",
    "Probation",
    "Conditional Discharge",
]

# (tier_name, provision_type_name, rule_subtype, params_dict, template_text, citation)
RULES = [
    # ---- Class A-I Felony (PL 70.00) ------------------------------------
    ("Class A-I Felony", "Imprisonment", "IndeterminateFelonyRange",
     {"max_term_min_years": 15, "max_term_max_years": 999,
      "has_alt_definite_option": False, "alt_definite_max_days": 0},
     "Indeterminate: minimum 15–25 years set by court; maximum = life imprisonment.",
     "PL 70.00(3)(a)"),
    ("Class A-I Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class A-II Felony (PL 70.00) -----------------------------------
    ("Class A-II Felony", "Imprisonment", "IndeterminateFelonyRange",
     {"max_term_min_years": 3, "max_term_max_years": 8,
      "has_alt_definite_option": False, "alt_definite_max_days": 0},
     "Indeterminate: minimum 3–8⅓ years set by court; maximum = life imprisonment.",
     "PL 70.00(3)(b)"),
    ("Class A-II Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class B Felony (non-violent, PL 70.00) -------------------------
    ("Class B Felony", "Imprisonment", "IndeterminateFelonyRange",
     {"max_term_min_years": 1, "max_term_max_years": 25,
      "has_alt_definite_option": False, "alt_definite_max_days": 0},
     "Indeterminate: minimum 1–3 years set by court; maximum up to 25 years.",
     "PL 70.00(3)(c)"),
    ("Class B Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class B Violent Felony (determinate, PL 70.02) ----------------
    # NOTE: MandatoryRangeEscalating used as workaround for determinate sentence.
    # min_amount/max_amount here represent years, not dollars.
    # TODO: add a dedicated DeterminatePrisonRange rule_subtype.
    ("Class B Violent Felony", "Imprisonment", "MandatoryRangeEscalating",
     {"min_amount": 5, "max_amount": 25, "mandatory": True,
      "escalates_on_prior_within": "", "escalated_min": 0,
      "escalated_max": 0, "requires_pairing": ""},
     "Determinate: 5–25 years. Mandatory minimum 5 years. "
     "(min_amount/max_amount fields represent years, not dollars.)",
     "PL 70.02(3)(a)"),
    ("Class B Violent Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class C Felony (non-violent, PL 70.00) -------------------------
    ("Class C Felony", "Imprisonment", "IndeterminateFelonyRange",
     {"max_term_min_years": 1, "max_term_max_years": 15,
      "has_alt_definite_option": False, "alt_definite_max_days": 0},
     "Indeterminate: minimum 1–3 years set by court; maximum up to 15 years.",
     "PL 70.00(3)(c)"),
    ("Class C Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class C Violent Felony (determinate, PL 70.02) ----------------
    ("Class C Violent Felony", "Imprisonment", "MandatoryRangeEscalating",
     {"min_amount": 3.5, "max_amount": 15, "mandatory": True,
      "escalates_on_prior_within": "", "escalated_min": 0,
      "escalated_max": 0, "requires_pairing": ""},
     "Determinate: 3½–15 years. Mandatory minimum 3½ years. "
     "(min_amount/max_amount fields represent years, not dollars.)",
     "PL 70.02(3)(b)"),
    ("Class C Violent Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class D Felony (non-violent, PL 70.00) -------------------------
    ("Class D Felony", "Imprisonment", "IndeterminateFelonyRange",
     {"max_term_min_years": 1, "max_term_max_years": 7,
      "has_alt_definite_option": False, "alt_definite_max_days": 0},
     "Indeterminate: minimum 1–3 years set by court; maximum up to 7 years.",
     "PL 70.00(3)(c)"),
    ("Class D Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class D Violent Felony (determinate, PL 70.02) ----------------
    ("Class D Violent Felony", "Imprisonment", "MandatoryRangeEscalating",
     {"min_amount": 2, "max_amount": 7, "mandatory": True,
      "escalates_on_prior_within": "", "escalated_min": 0,
      "escalated_max": 0, "requires_pairing": ""},
     "Determinate: 2–7 years. Mandatory minimum 2 years. "
     "(min_amount/max_amount fields represent years, not dollars.)",
     "PL 70.02(3)(c)"),
    ("Class D Violent Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class E Felony (non-violent, PL 70.00) -------------------------
    ("Class E Felony", "Imprisonment", "IndeterminateFelonyRange",
     {"max_term_min_years": 1, "max_term_max_years": 4,
      "has_alt_definite_option": True, "alt_definite_max_days": 365},
     "Indeterminate: minimum 1–1½ years set by court; maximum up to 4 years. "
     "Alternative definite sentence of up to 1 year available.",
     "PL 70.00(3)(c); PL 70.00(4)"),
    ("Class E Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class E Violent Felony (determinate, PL 70.02) ----------------
    ("Class E Violent Felony", "Imprisonment", "MandatoryRangeEscalating",
     {"min_amount": 1.5, "max_amount": 4, "mandatory": True,
      "escalates_on_prior_within": "", "escalated_min": 0,
      "escalated_max": 0, "requires_pairing": ""},
     "Determinate: 1½–4 years. Mandatory minimum 1½ years. "
     "(min_amount/max_amount fields represent years, not dollars.)",
     "PL 70.02(3)(d)"),
    ("Class E Violent Felony", "Fine", "SimpleCap",
     {"max_amount": 5000, "can_stand_alone": False},
     "Fine up to $5,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.00(1)"),

    # ---- Class A Misdemeanor (PL 70.15) ---------------------------------
    ("Class A Misdemeanor", "Imprisonment", "DefiniteSentenceSimple",
     {"max_months": 12},
     "Definite sentence: up to 1 year.",
     "PL 70.15(1)"),
    ("Class A Misdemeanor", "Fine", "SimpleCap",
     {"max_amount": 1000, "can_stand_alone": True},
     "Fine up to $1,000 or double defendant's gain from offense, whichever is greater.",
     "PL 80.05(1)"),

    # ---- Class B Misdemeanor (PL 70.15) ---------------------------------
    ("Class B Misdemeanor", "Imprisonment", "DefiniteSentenceSimple",
     {"max_months": 3},
     "Definite sentence: up to 3 months.",
     "PL 70.15(2)"),
    ("Class B Misdemeanor", "Fine", "SimpleCap",
     {"max_amount": 500, "can_stand_alone": True},
     "Fine up to $500 or double defendant's gain from offense, whichever is greater.",
     "PL 80.05(2)"),

    # ---- Unclassified Misdemeanor (PL 70.15) ----------------------------
    ("Unclassified Misdemeanor", "Imprisonment", "DefiniteSentenceSimple",
     {"max_months": 12},
     "Definite sentence: as provided in the law creating the offense; not to exceed 1 year.",
     "PL 70.15(3)"),
    ("Unclassified Misdemeanor", "Fine", "SimpleCap",
     {"max_amount": 1000, "can_stand_alone": True},
     "Fine as provided in the law creating the offense.",
     "PL 80.05(3)"),

    # ---- Violation (PL 70.15) -------------------------------------------
    # Note: actual maximum is 15 days; DefiniteSentenceSimple uses months,
    # so max_months=1 is stored as the closest integer. See template_text.
    ("Violation", "Imprisonment", "DefiniteSentenceSimple",
     {"max_months": 1},
     "Definite sentence: up to 15 days. "
     "(max_months stored as 1 month for schema compatibility; actual cap is 15 days.)",
     "PL 70.15(4)"),
    ("Violation", "Fine", "SimpleCap",
     {"max_amount": 250, "can_stand_alone": True},
     "Fine up to $250 or double defendant's gain from offense, whichever is greater.",
     "PL 80.05(4)"),
]


def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    # ---- Provision types ------------------------------------------------
    existing_pt = {
        row[0]
        for row in conn.execute("SELECT name FROM provision_types").fetchall()
    }
    pt_inserted = 0
    for name in PROVISION_TYPES:
        if name not in existing_pt:
            conn.execute("INSERT INTO provision_types (name) VALUES (?)", (name,))
            pt_inserted += 1
    conn.commit()
    print(f"Provision types: inserted {pt_inserted}, skipped {len(PROVISION_TYPES) - pt_inserted}.")

    # ---- Rules ----------------------------------------------------------
    existing_rules = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
    if existing_rules > 0:
        print(f"Rules table already has {existing_rules} rows — skipping rule seed.")
        conn.close()
        return

    # Build lookup maps
    class_map = {
        row[0]: row[1]
        for row in conn.execute("SELECT tier, id FROM classifications").fetchall()
    }
    pt_map = {
        row[0]: row[1]
        for row in conn.execute("SELECT name, id FROM provision_types").fetchall()
    }

    inserted = 0
    skipped = []
    for tier, pt_name, subtype, params, template, citation in RULES:
        class_id = class_map.get(tier)
        pt_id    = pt_map.get(pt_name)
        if not class_id:
            skipped.append(f"  MISSING classification: '{tier}'")
            continue
        if not pt_id:
            skipped.append(f"  MISSING provision type: '{pt_name}'")
            continue
        conn.execute(
            """INSERT INTO rules
               (provision_type_id, rule_subtype, classification_id,
                template_text, citation_base, parameters)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pt_id, subtype, class_id, template, citation, json.dumps(params)),
        )
        inserted += 1

    conn.commit()
    conn.close()

    print(f"Rules: inserted {inserted}.")
    if skipped:
        print(f"Skipped {len(skipped)} rows:")
        for s in skipped:
            print(s)
    else:
        print("All rules seeded successfully.")


if __name__ == "__main__":
    seed()
