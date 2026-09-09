# Quirks

## §120.35 — Promoting a suicide attempt; when punishable as attempt to commit murder

- Not a standalone offense — it's a conditional/limiting rule layered on top of attempt to commit murder (§125.25).
- Only applies when the conduct also constitutes promoting a suicide attempt (§120.30) AND the defendant used duress or deception.
- Entered as: `isAttempt=True`, `attemptOf=125.25` → classification auto-resolves to `ClassB_Felony` (A9 branch 3: attempt of Class A-I → Class B).
- The §120.30 linkage and duress/deception requirement live in `elements` but aren't formally modeled. Needs a "conditional applicability" concept the ontology doesn't have yet.

## General: attempted classification auto-resolution

- When `isAttempt=True` and `attemptOf` has a valid target section, classification is auto-resolved via A9 (PL 110.05 ordered branching) — no manual entry.
- Target offense must already exist in the data. Add the base offense first, then add the attempt.
- VFO status for the attempt is resolved via A11 (three-way check against VFO_LIST: named carve-out, class-level downgrade, or lesser-included).

## General: derived flags need only (section, classification)

- VFO, SMF, Hate Crime, Predicate Exposure, YO Eligible, 70.04-reachable, 70.06-reachable — all computed at runtime from `(section, classification)` against the already-populated lists in `data/lists.json`.
- The Lists tab is only for when the legislature amends a source statute (PL 70.02, 130.91, or 485.05).
