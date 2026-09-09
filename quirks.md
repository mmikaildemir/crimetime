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

## §120.40 — Definitions (stalking article)

- **Do not add.** This is a definitions section, not an offense. Defines terms used by §120.45, 120.50, 120.55, 120.60.
- Defines "specified predicate crime" (subd 5) — a stalking-specific list of prior crimes that elevate stalking charges. This is DIFFERENT from the PL 70.04/70.06 predicate felony concept.
- Includes: violent felony offenses; sex offenses (130.20, 130.25, 130.30, 130.55, 130.60, 130.70, 255.25, 255.26, 255.27, formerly 130.40/130.45); assault 3rd (120.00); menacing 1st-3rd (120.13/120.14/120.15); coercion 1st-3rd (135.65/135.61/135.60); aggravated harassment 2nd (240.30); harassment 1st (240.25); criminal mischief 1st-3rd (145.05/145.10/145.12); criminal tampering 1st (145.20); arson 3rd/4th (150.05/150.10); criminal contempt 1st (215.51); endangering welfare of a child (260.10); stalking 2nd-4th (120.45/120.50/120.55).
- Relevant when modeling §120.50 and §120.55 — their elements reference "specified predicate crime" as a triggering condition.
- Not modeled yet — would need a "specified predicate crime" list concept separate from VFO_LIST/SMF_LIST/HATECRIME_LIST.
