# CrimeTime — Vision & Requirements

## Problem

NYS criminal sentencing is a multi-layered system of statutes, classifications, enhancements, and sentencing rules that interact in complex ways. A single offense can trigger multiple sentencing pathways depending on modifiers (prior convictions, hate crime, terrorism, sexual motivation, juvenile status, etc.), and each modifier changes the classification tier and applicable sentencing range.

There is no single structured, queryable, auditable system that models this data with legal traceability.

## Goal

Build a **normalized legal data model** and **admin console** that:

1. Represents the full hierarchy: **Statute → Classification → Modifier → Offense → SentencingRule**
2. Resolves the resulting classification when a modifier applies to an offense
3. Returns the correct sentencing range (imprisonment, fine, probation, etc.) for any (offense, modifier) combination
4. Tracks legal verification per row — every enhancement rule has a `verified_by` / `verified_date`
5. Exports cleanly for use by downstream tools (scenario builder, CLI, web app, etc.)

## Architecture

```
Statutes (NYS Penal Law, VTL, CPL, COR, etc.)
  └── Offenses (specific sections, elements, subsections)
        ├── base_classification (e.g. Class E Felony)
        └── eligible modifiers (PL 130.91, PL 485.10, etc.)
              └── classification_resolution (modifier × base_class → resulting_class)
                    └── sentencing_rules (classification × provision_type → rule)
```

### Core Entities

| Entity | Purpose |
|---|---|
| `statutes` | NYS law sections with title, section, text, effective/repeal dates |
| `classifications` | 14 NY tiers (A-I Felony, B Violent, C, D, E, A/B Misdemeanor, Violation, etc.) |
| `modifiers` | Enhancement types (Hate Crime, Crime of Terrorism, Sexually Motivated Felony, PRI, Juvenile) |
| `offenses` | Specific criminal acts linked to a statute and base classification |
| `offense_modifier_eligibility` | Which offenses can legally carry which modifiers |
| `classification_resolution` | Lookup: given a modifier + base classification, what is the resulting tier? |
| `provision_types` | Types of sentencing (Imprisonment, Fine, Probation, Conditional Discharge) |
| `rules` | Structured sentencing parameters per (provision_type, classification) |

### Rule Subtypes

| Subtype | Use Case |
|---|---|
| `IndeterminateFelonyRange` | PL 70.00 felonies (min set by court, max fixed) |
| `MandatoryRangeEscalating` | PL 70.02 violent felonies (determinate, mandatory min, PRI escalation) |
| `DefiniteSentenceSimple` | Misdemeanors & violations (fixed max term) |
| `SimpleCap` | Fines with max amounts |
| `CorporateCap` | Corporate fine limits |

## What This Is

- A **data model** for NY criminal sentencing
- An **admin console** (Streamlit) for building and maintaining that data
- A **seed system** with verified defaults for enhancement statutes
- An **export format** (JSON) for downstream consumption

## What This Is Not

- A legal advice tool — all data must be verified by counsel
- A production sentencing calculator — it's the data layer, not the decision engine
- A replacement for official NYS legislation sources

## Iterative Approach

Phase 1 — **Foundation**: Populate classifications, modifiers, seed resolution rules, add real offenses
Phase 2 — **Sentencing**: Complete rules for every (classification, provision_type) pair, add DeterminatePrisonRange subtype
Phase 3 — **Legal Review**: Attorney sign-off on all enhancement rows, resolve TODO flags
Phase 4 — **Features**: Search, scenario builder, bulk import from extract_crimes.py output
Phase 5 — **Hardening**: Audit logging, migration strategy, documentation

## Key Decisions Already Made

- SQLite for local persistence (simple, portable, no server)
- Streamlit for admin UI (fast iteration, Python-native)
- `classification_resolution` separated from `offense_modifier_eligibility` (cleaner concerns: eligibility vs. tier shift)
- `verified_by` / `verified_date` columns on classification_resolution for audit trail
- Seed data idempotent — safe to run repeatedly
