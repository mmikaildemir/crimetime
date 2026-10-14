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

## Conditional classification (offense-intrinsic escalation)

Some offenses have a base classification that escalates based on a case fact. Modeled via `conditionalClassification` block on the offense entry in `data/lists.json`.

### §120.70 — Luring a child
- Base: Class E felony. If intended offense was Class A → Class C. If Class B → Class D. Fallback: Class E.
- Field: `intended_underlying_offense_class`
- Note: §120.70 (not §130.86 — confirmed via NYS Open Legislation API)

### §225.90, §225.95 — Gaming manipulation / manufacture
- Base: Class A misdemeanor. If prior conviction of same offense within 5 years → Class E felony. Fallback: Class A misdemeanor.
- Field: `prior_conviction_same_section_within_years`

### §260.35 — Misrepresentation by caregiver
- Classification stays Class A misdemeanor, but if imprisonment imposed, max 6 months (not 12). This is a sentence cap, not a classification change — not yet modeled as conditionalClassification. Flag for later.

- VFO, SMF, Hate Crime, Predicate Exposure, YO Eligible, 70.04-reachable, 70.06-reachable — all computed at runtime from `(section, classification)` against the already-populated lists in `data/lists.json`.
- The Lists tab is only for when the legislature amends a source statute (PL 70.02, 130.91, or 485.05).

## §120.40 — Definitions (stalking article)

- **Do not add.** This is a definitions section, not an offense. Defines terms used by §120.45, 120.50, 120.55, 120.60.
- Defines "specified predicate crime" (subd 5) — a stalking-specific list of prior crimes that elevate stalking charges. This is DIFFERENT from the PL 70.04/70.06 predicate felony concept.
- Includes: violent felony offenses; sex offenses (130.20, 130.25, 130.30, 130.55, 130.60, 130.70, 255.25, 255.26, 255.27, formerly 130.40/130.45); assault 3rd (120.00); menacing 1st-3rd (120.13/120.14/120.15); coercion 1st-3rd (135.65/135.61/135.60); aggravated harassment 2nd (240.30); harassment 1st (240.25); criminal mischief 1st-3rd (145.05/145.10/145.12); criminal tampering 1st (145.20); arson 3rd/4th (150.05/150.10); criminal contempt 1st (215.51); endangering welfare of a child (260.10); stalking 2nd-4th (120.45/120.50/120.55).
- Relevant when modeling §120.50 and §120.55 — their elements reference "specified predicate crime" as a triggering condition.
- Not modeled yet — would need a "specified predicate crime" list concept separate from VFO_LIST/SMF_LIST/HATECRIME_LIST.

## Terrorism eligibility (PL 490.25) — list intentionally identical to HATECRIME_LIST

- PL 490.25(3) defines "specified offense" by cross-reference to PL 485.05(3) — the same list used for hate-crime eligibility.
- As a result, `TERRORISM_LIST.sections` in `data/lists.json` is **intentionally identical** to `HATECRIME_LIST.sections` while those two statutory provisions remain coupled.
- The engine models them as **separate lists** (`TERRORISM_LIST` + `is_terrorism_eligible` in `resolvers.py`) so that if the legislature decouples 490.25(3) from 485.05(3), the terrorism bump (`_apply_terrorism_bump` in `sentencing.py`) will read from the independently-editable `TERRORISM_LIST` rather than silently following `HATECRIME_LIST`.
- Do not "simplify" by collapsing the two lists or by routing the terrorism bump through `is_hatecrime_eligible` — the previous design did exactly that and was a latent single-point-of-failure bug.

## For-hire vehicle enhancement (PL 60.07) — structured eligibility list

- PL 60.07(1) adds 3–5 years to the minimum term (indeterminate or determinate) when the victim was operating a for-hire vehicle (taxicab, livery, or black car per 60.07(2)(b)–(g)) and the offense is a "specified offense" per 60.07(2)(a).
- **Unlike HATECRIME_LIST and TERRORISM_LIST, the FOR_HIRE_LIST is NOT a flat section list.** 60.07(2)(a) selectively lists completed offenses and attempts of *specific* offenses. The two lists differ:
  - `completedSections`: 120.07, 120.06, 120.10, 125.20, 125.15, 160.15, 160.10
  - `attemptOfSections`: 125.25, 120.07, 120.10, 125.20, 160.15
  - E.g., 120.06 completed IS eligible but attempt of 120.06 is NOT. 125.25 completed is NOT eligible but attempt of 125.25 IS.
- The enhancement is a **post-disposition minimum-term adjustment**, NOT a classification modifier. It stacks on top of SMF/hate-crime/terrorism classification bumps because it operates on the final post-modifier minimum.
- The judicial escape hatch (court may decline the enhancement if it finds on the record that it would be unduly harsh, not imposing it is consistent with public safety, and not imposing it would not deprecate the seriousness of the crime) is modeled as an `ExceptionPath` of type `FOR_HIRE_ENHANCEMENT`.
- Procedural gate: CPL 200.61 requires a special information filed by the DA with the indictment; this is a pre-conviction procedural requirement, not modeled by the engine.
