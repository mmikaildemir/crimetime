# Quirks

## §120.35 — Promoting a suicide attempt; when punishable as attempt to commit murder

- **Do not add to the system.** This is not a standalone offense — it's a conditional/limiting rule.
- It says: when conduct constitutes both promoting a suicide attempt (§120.30) AND attempt to commit murder (§125.25), you can't convict of attempt to commit murder unless duress or deception was used.
- It's a merger/proviso rule, not an element-defining statute. The actual offense is either §120.30 (promoting a suicide attempt) or attempt of §125.25 (attempted murder) — both are separate entries.
- If we ever need to model the duress/deception limitation, it would be as a condition on the attempted murder conviction, not as an offense entry.

## General: attempted classification auto-resolution

- When `isAttempt=True` and `attemptOf` has a valid target section, classification is auto-resolved via A9 (PL 110.05 ordered branching) — no manual entry.
- Target offense must already exist in the data. Add the base offense first, then add the attempt.
- VFO status for the attempt is resolved via A11 (three-way check against VFO_LIST: named carve-out, class-level downgrade, or lesser-included).

## General: derived flags need only (section, classification)

- VFO, SMF, Hate Crime, Predicate Exposure, YO Eligible, 70.04-reachable, 70.06-reachable — all computed at runtime from `(section, classification)` against the already-populated lists in `data/lists.json`.
- The Lists tab is only for when the legislature amends a source statute (PL 70.02, 130.91, or 485.05).
