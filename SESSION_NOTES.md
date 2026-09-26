# Session Notes

## Where You Left Off

### Last session (Sep 26, 2026)

**Major work completed:**
1. Built batch ingestion pipeline (`scripts/ingest_offenses.py`) — discover/review/merge subcommands
2. Merged 503 new offenses via pipeline (registry now has 605 offenses total)
3. Wired all 3 modifier bumps into the sentencing engine:
   - SMF (§130.91) — violent redesignation
   - Hate crime (§485.10) — tier shift + Class B floors + Class A-I 20yr min
   - Terrorism (§490.25) — tier shift + VFO designation + Class B→A-I + A-I life without parole
4. Added offense-specific A-I/A-II overrides (§125.27 murder 1st 20-25yr, §125.26 aggravated murder LWOP, §130.95/§130.96 predatory sexual assault 10-25yr)
5. Fixed prior-record-status routing for A-II felonies and VFOs with non-VFO prior statuses
6. Engine now resolves all 15,125 combos (605 offenses × 5 prior statuses × 5 modifier states) with zero errors

**Last commits:**
- `763a700` Fix VFO with non-VFO prior status and 70.08 Class E gaps
- `52a9f9b` Fix A-II and non-VFO prior-record-status routing errors
- `67357e1` Add terrorism A-I LWOP, offense-specific A-I overrides, document 70.05/70.08 gaps
- `648ebe8` Wire SMF, hate crime, and terrorism modifier bumps into sentencing engine
- `4ced1e1` Merge 503 offenses via ingestion pipeline (§140.40–§499.99)
- `5cb49ec` Add batch offense ingestion pipeline (discover/review/merge)
- `a301d34` Add Article 140 offenses §140.10–§140.40 via NYS API auto-resolve

### Uncommitted state
Working tree is clean. All changes committed.

---

## What Still Needs Doing

### High priority — data correctness
- [ ] Add §160.05 (robbery 3rd, Class D felony) to VFO_LIST.classD — it IS a VFO per PL 70.02(1)(c) but is missing from the curated list
- [ ] Verify §263.10, §263.15, §265.17 against VFO_LIST — flagged as potentially violent Class D felonies not in VFO_LIST
- [ ] Fill in `elements` for the 503 offenses added via ingestion pipeline (all have `elements: null`)
- [ ] Add §165.15 (theft of services) and §490.25 (crime of terrorism) manually — both are conditional offenses flagged for review in staging

### Medium priority — coverage gaps
- [ ] Backfill articles 100–140 gap (sections <140.40 that were skipped — run `ingest_offenses.py discover --from 100.00 --to 140.40`)
- [ ] Juvenile offender sentencing track (PL 70.05) — no JUVENILE age category exists yet; hate crime 70.05 floor blocked on this
- [ ] §125.25 subd 5 (murder 2nd cop-killer provision) needs subdivision-level override for life without parole
- [ ] SMF "violent redesignation" statutory basis needs legal verification (not explicit in §130.91 text)

### Low priority — testing & polish
- [ ] Expand sentencing test coverage beyond §120.02 (misdemeanors, violations, persistent offenders, post-2027 sunset logic)
- [ ] Add .env.example with required keys
- [ ] Write README.md (currently empty)
- [ ] Reconcile SQLite DB with JSON (JSON is canonical; DB is outdated)

---

## How to Continue

### Running the sentencing UI
```bash
streamlit run sentencing_ui.py
```

### Running the ingestion pipeline
```bash
# Discover new offenses (scan range, write to staging)
.venv/bin/python scripts/ingest_offenses.py discover --from 100.00 --to 140.40

# Review the staging file
.venv/bin/python scripts/ingest_offenses.py review

# Merge approved offenses (dry-run first, then apply)
.venv/bin/python scripts/ingest_offenses.py merge --dry-run
.venv/bin/python scripts/ingest_offenses.py merge --no-dry-run
```

### Running tests
```bash
.venv/bin/python -m pytest tests/ -q
# 129 passed, 6 skipped (skips are cache-dependent)
```

### Key architecture decisions
- **JSON is canonical** — `data/lists.json` + `data/sentencing_tables.json` are the source of truth. SQLite DB is outdated and ignored.
- **Modifiers applied in order**: SMF → hate crime → terrorism. Each sees the previous modifier's result.
- **Prior-record-status normalization**: VFOs with non-VFO statuses fall back to 70.02 first offender; non-VFOs with VFO statuses fall back to 70.06/70.10 (then 70.06→first offender for A-I/A-II per 70.06(6)).
- **Offense-specific overrides** in `sentencing_tables.json` `offenseOverrides` section handle §125.27, §125.26, §130.95, §130.96.

### Key files
| File | Purpose |
|---|---|
| `data/lists.json` | 605 offenses + VFO/SMF/HATECRIME lists |
| `data/sentencing_tables.json` | Sentencing ranges + hate crime floors + offense overrides |
| `crimetime/sentencing.py` | Main engine: `resolve(section, case_facts)` |
| `crimetime/legislation.py` | NYS API helpers (shared by app + ingestion pipeline) |
| `crimetime/resolvers.py` | A1-A17 axiom implementations |
| `sentencing_ui.py` | Streamlit sentencing UI |
| `app.py` | Streamlit data entry console |
| `scripts/ingest_offenses.py` | Batch ingestion pipeline CLI |
