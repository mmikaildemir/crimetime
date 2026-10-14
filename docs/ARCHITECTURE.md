# Engine architecture

`crimetime.sentencing.resolve(section, case_facts)` turns **facts** into a
sentencing output. It runs a fixed pipeline, reads its rules from data tables,
and records every decision in `SentencingOutput.trace`.

## Facts in, conclusions out

The inputs (`CaseFacts`) are facts about the case. Legal conclusions are
derived by the engine and appear only in the output.

| Input fact | Derived conclusion (output) |
|---|---|
| `prior_record.predicate_felonies`, `prior_record.predicate_vfos` | `offender_status` and `offender_status_label` (e.g. "Second felony drug offender, prior violent felony — PL 70.70(4)") |
| `hate_crime_motivated`, `terrorism_motivated`, `sexually_motivated` | `modifiers_applied`, final `classification`, `is_vfo` |
| `defendant_age_category`, offense article and class | `sentencing_track` |

An offender status is a conclusion of **(sentencing track × predicate facts)**.
For example, one violent predicate gives a different status on each track:

| Track | Status |
|---|---|
| Violent felony | second violent felony offender, PL 70.04 |
| Non-violent felony | second felony offender, PL 70.06 |
| Drug felony | second felony drug offender with prior VFO, PL 70.70(4) |
| Sex offense felony | predicate sex offender, violent predicate, PL 70.80(5)(c) |

That's why the old single `PriorRecordStatus` selector couldn't express these
statuses. It is still accepted as an input and translated into predicate
counts (`LEGACY_STATUS_TO_PRIORS` in `models.py`).

## Pipeline (`crimetime/sentencing.py`)

1. **classify**: offense classification, attempt (PL 110.05, `resolvers.py`), and conditional classification.
2. **classification modifiers**: SMF → hate crime → terrorism, applied in the order set by the `classificationModifiers` table. Each branch maps a classification to a new one and says how VFO status changes (`keep` / `derive` / `deem` / `undeem`).
3. **track + offender status**: `tracks.select_track` picks the first track in `TRACKS` that applies. That track's `derive_status` reads `PriorRecord`.
4. **dispositions**: the track reads the primary disposition and PRS from its table, and generates the alternatives.
5. **adjustments**: run in `ADJUSTMENTS` order: hate-crime floors → terrorism LWOP → offense-specific overrides → for-hire +3.
6. **exceptions, financial obligations, collateral requirements** (`exceptions.py`, `financial.py`).

## Tracks (`crimetime/tracks.py`)

| Order | Track | Applies when | Table |
|---|---|---|---|
| 1 | `juvenile_offender` (70.05) | juvenile offender, felony class A-I/B/C/D | `juvenileOffender` |
| 2 | `drug_felony` (70.70/70.71) | Art. 220/222 felony, not a VFO | `drugFelony` |
| 3 | `sex_offense_felony` (70.80) | felony sex offense, not class A | `sexOffenseFelony` |
| 4 | `violent_felony` (70.02/70.06(6)/70.04/70.08) | VFO, or 130.95/130.96 with 2+ violent predicates | `violentFelony` |
| 5 | `nonviolent_felony` (70.00/70.06/70.10) | any other felony | `nonViolentFelony` |
| 6 | `misdemeanor`, `violation` (70.15) | — | `misdemeanor`, `violation` |

To add a sentencing scheme:
1. Add an `OffenderStatus` value for each new status.
2. Add a table keyed by those values.
3. Add a `Track` subclass and put it in `TRACKS` at the right precedence.

## Track table schema (`data/sentencing_tables.json`)

```json
"drugFelony": {
  "statuses": {
    "<OffenderStatus value>": {
      "label": "shown to users",
      "statute": "PL 70.70(4)",
      "sentenceType": "determinate",
      "prsRef": "PL 70.45(2)",
      "rows": { "ClassB": {"termYears": [6, 15], "prsYears": [1.5, 3]}, "ClassA_I": {"...": "...", "statute": "PL 70.71(4)"} }
    }
  }
}
```

A row's `statute` overrides the block's statute (used for class-A drug rows under
70.71). Two more tables drive the pipeline:
- `hateCrimeBump.ClassB.floorByStatus` maps (track, status) to a 485.10(3) floor.
- `classificationModifiers` holds the modifier ladders.

## Golden snapshot

`tests/test_golden.py` compares `resolve()` across 42,665 scenarios against
`tests/golden/outputs.json.gz`. The scenarios cover every offense × 6 predicate
patterns × case-fact variants. When you change behaviour on purpose:

```sh
uv run python scripts/snapshot.py --diff   # review exactly what changed
uv run python scripts/snapshot.py          # accept it
```
