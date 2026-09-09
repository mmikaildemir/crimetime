# Legal Review: CrimeTime Sentencing Logic

**Purpose:** This document contains legal rules that our system applies when determining offense classification and sentencing eligibility under New York Penal Law. Please review each statement and indicate whether it is correct, incorrect, or needs clarification. Add notes where you disagree or have additional context.

**Instructions:**
- Mark each rule as **Correct**, **Incorrect**, or **Unsure**
- Use the **Notes** field to explain any disagreement or add nuance
- Section references like `[Ref: A2]` are internal tracking tags — you can ignore them
- If a list of statutes is provided, please confirm it matches current law or note any additions/removals

---

## Part 1: Classification & Basic Eligibility

### Rule 1 — What counts as a "crime" `[Ref: A1]`

Under NY Penal Law, only misdemeanors and felonies are classified as "crimes." Violations (e.g., disorderly conduct) are NOT crimes.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 2 — Youthful Offender eligibility `[Ref: A2]`

A defendant is eligible for Youthful Offender (YO) treatment if the offense is a crime (misdemeanor or felony) AND the offense is NOT a Class A-I or Class A-II felony. Class A-I and A-II felonies are explicitly excluded from YO eligibility under CPL §720.10(2)(a).

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 3 — Predicate exposure (repeat offender eligibility) `[Ref: A6]`

An offense has "predicate exposure" — meaning it can trigger sentencing enhancements for repeat felony offenders under PL §70.06 — if it is a felony AND is NOT a Class A-I felony.

**Important distinction:** Class A-I felonies are excluded from predicate exposure (PL §70.06(1)(a)). However, Class A-II felonies ARE included — PL §70.06(3)(a) and §70.06(4)(a) have live sentencing table entries for Class A-II as a second felony offender.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

---

## Part 2: Violent Felony, SMF, and Hate Crime Eligibility

### Rule 4 — Violent Felony Offender (VFO) status `[Ref: A3]`

An offense is a "violent felony" if:
- It is a Class B, C, D, or E felony, AND
- Its section number appears in the VFO_LIST enumerated in PL §70.02(1)

Class A-I and Class A-II felonies are NOT in the VFO framework — they are sentenced directly under PL §70.00(3)(a), outside Article 70.02 entirely.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 5 — Sexually Motivated Felony (SMF) eligibility `[Ref: A4]`

An offense is eligible for Sexually Motivated Felony treatment if:
- It is a felony, AND
- Its section number appears in the SMF_LIST enumerated in PL §130.91(2)

Misdemeanors are NOT eligible for SMF treatment (felony-gated).

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 6 — Hate Crime eligibility `[Ref: A5]`

An offense is eligible for Hate Crime enhancement if its section number appears in the HATECRIME_LIST enumerated in PL §485.05(3).

This is NOT felony-gated — both misdemeanors and felonies can be hate crime-eligible.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 7 — PRI 2nd Degree (70.04) reachability `[Ref: A7]`

An offense can trigger the PRI 2nd Degree violent felony enhancement (PL §70.04) if:
- It is itself a VFO (violent felony), AND
- It has predicate exposure (i.e., it is a felony that is not Class A-I)

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 8 — Second Felony Offender (70.06) reachability `[Ref: A8]`

An offense can trigger the Second Felony Offender enhancement (PL §70.06) if:
- It has predicate exposure (felony, not Class A-I), AND
- It is NOT a VFO

In other words: non-violent felonies (Class B through E) that are not Class A-I can trigger §70.06. Violent felonies go through §70.04 instead.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

---

## Part 3: Attempt & Conspiracy Rules

### Rule 9 — Attempt classification downgrade `[Ref: A9]`

When a defendant is charged with attempt to commit an offense, the attempt is classified one class lower than the completed offense, per PL §110.05. However, there are important exceptions:

1. **Sections that stay Class A-I on attempt:** The following offenses, when attempted, remain Class A-I felonies (no downgrade):
   - §125.27 (Aggravated Murder)
   - §220.21 (Criminal Possession of Controlled Substance in the First Degree)
   - §220.43 (Criminal Sale of Controlled Substance in the First Degree)
   - §490.45 (Crime of Terrorism in the Second Degree)
   - §490.55 (Crime of Terrorism in the Third Degree)

2. **Class A-II felonies stay Class A-II** on attempt (no downgrade).

3. **Class A-I felonies (not in the list above) downgrade to Class B** felony on attempt.

4. **Specific bribery overrides:**
   - Attempt of §200.00 (Bribe Receiving, 3rd degree) → Class D felony
   - Attempt of §200.03 (Bribe Receiving, 2nd degree) → Class C felony
   - Attempt of §200.04 subdivision 2 (Bribe Receiving, 1st degree, subd. 2) → Class B felony

5. **All other offenses:** Standard one-class downgrade:
   - Class B felony → Class C felony
   - Class C felony → Class D felony
   - Class D felony → Class E felony
   - Class E felony → Class A misdemeanor
   - Class A misdemeanor → Class B misdemeanor

**Note:** §125.26 (Aggravated Murder) is deliberately excluded from the "stays Class A-I" list above because that treatment applies only to subdivision 1, not the whole section. This is handled separately in the subdivision-sensitive rules.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 10 — What counts as an "attempt" `[Ref: A10a]`

An offense is charged as an attempt when the defendant intended to commit a completed offense and took a substantial step toward its commission. The system tracks which completed offense the attempt targets (e.g., "attempt of 125.25" means attempted murder in the second degree).

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 11 — What counts as a "conspiracy" `[Ref: A10b]`

An offense is charged as a conspiracy when the defendant agreed with one or more persons to engage in conduct constituting a crime. The Article 105 conspiracy degree sections (105.00 through 105.17) are generic — they are defined by the severity of the target crime, not tied to a specific named offense. The system only links a conspiracy to a specific target offense when the charge is tied to a particular completed offense.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 12 — VFO status for attempts `[Ref: A11]`

VFO status for attempted offenses is determined by checking the VFO_LIST (PL §70.02(1)) in three ways:

1. **Named carve-outs:** If the target offense is explicitly listed in a VFO class's "attemptOfSection" array (e.g., attempt of 125.25, 135.25, or 150.20 is independently enumerated as a Class B VFO).

2. **Class-level downgrade rule:** If the target offense's VFO class has an "attemptOfClass" rule (e.g., attempt of any Class B VFO is a Class C VFO; attempt of any Class C VFO is a Class D VFO).

3. **Lesser-included carve-out:** If the target offense appears in the Class E "lesser included" list (e.g., attempt of §265.02 subdivisions 5/6/7/8 as a lesser included offense under CPL §220.20 is a Class E VFO).

This requires checking the statute text — it is not a simple "inherits automatically" rule.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 13 — SMF eligibility for attempts and conspiracies `[Ref: A12]`

An attempt or conspiracy of an SMF-eligible offense is itself SMF-eligible. This is because PL §130.91(2) includes a blanket catch-all clause: "any felony attempt or conspiracy to commit any of the foregoing offenses." So if the completed offense is on the SMF list, the attempt or conspiracy inherits eligibility automatically.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 14 — Hate Crime eligibility for attempts and conspiracies `[Ref: A13]`

An attempt or conspiracy of a hate-crime-eligible offense is itself hate-crime-eligible. This is because PL §485.05(3) includes a blanket catch-all clause: "any felony attempt or conspiracy to commit any of the foregoing offenses." So if the completed offense is on the Hate Crime list, the attempt or conspiracy inherits eligibility automatically.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

---

## Part 4: Subdivision-Sensitive Rules

### Rule 15 — Offenses with subdivision-dependent eligibility `[Ref: A14]`

Some offenses have multiple subdivisions (numbered clauses in the statute), and enhancement eligibility can vary depending on which subdivision applies:

**Example — §125.15 (Manslaughter in the Second Degree):**
- Subdivision 1 (recklessly causes death): SMF-eligible AND Hate Crime-eligible
- Subdivision 3 (intentionally causes or aids suicide): NOT SMF-eligible, NOT Hate Crime-eligible

When an offense has subdivision-dependent eligibility, the system asks which subdivision applies before determining enhancement eligibility.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 16 — Subdivision-sensitive attempt targets `[Ref: A14]`

Some offenses are treated differently as attempt targets depending on the subdivision:

**Example — §125.26 (Aggravated Murder):**
- Attempt of subdivision 1: stays Class A-I (per PL §110.05(1))
- Attempt of subdivision 2: does NOT stay Class A-I (standard downgrade applies)

Because of this, §125.26 is NOT included in the flat "stays Class A-I" list — the system checks the subdivision before applying the rule.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 17 — Sections whose attempt stays Class A-I `[Ref: A15]`

The following sections, when attempted, remain Class A-I felonies (no downgrade), per PL §110.05(1):

| Section | Offense |
|---------|---------|
| 125.27 | Aggravated Murder |
| 220.21 | Criminal Possession of Controlled Substance, 1st Degree |
| 220.43 | Criminal Sale of Controlled Substance, 1st Degree |
| 490.45 | Crime of Terrorism, 2nd Degree |
| 490.55 | Crime of Terrorism, 3rd Degree |

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Rule 18 — Hate Crime classification bump `[Ref: A17]`

When an offense is hate-crime-eligible AND the crime was motivated by bias (per PL §485.05), the classification is enhanced per PL §485.10:

- **Misdemeanors and Class C/D/E felonies:** Bumped one category higher (e.g., Class A misdemeanor → Class E felony; Class E felony → Class D felony)
- **Class B felonies:** NOT a simple bump — fixed minimum floors apply depending on predicate-offender status (see §485.10(3))
- **Class A-I felonies:** NOT a bump — flat minimum 20 years indeterminate sentence (see §485.10(4))

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

---

## Part 5: Statutory Lists — VFO List (PL §70.02(1))

Please confirm the following sections are correctly listed as Violent Felony Offenses under PL §70.02(1). If any section is missing or incorrectly included, please note it.

### Class B Violent Felonies (22 sections)

| Section | |
|---------|---|
| 125.20 | 125.22 | 130.35 | 130.70 | 130.75 | 120.10 | 135.20 | 140.30 | 150.15 | 160.15 | 230.34 | 230.34-a | 255.27 | 265.04 | 265.09 | 265.13 | 120.11 | 120.07 | 215.17 | 490.35 | 490.40 | 490.47 |

**Note:** Attempt of §125.25 (Murder 2nd), §135.25 (Kidnapping 1st), and §150.20 (Arson 1st) is independently enumerated as a Class B VFO.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Class C Violent Felonies (18 sections)

| Section | |
|---------|---|
| 125.11 | 125.21 | 130.67 | 120.08 | 120.09 | 120.06 | 121.13 | 121.13-a | 140.25 | 160.10 | 265.03 | 265.08 | 265.12 | 265.14 | 265.19 | 490.15 | 490.30 | 490.37 |

**Note:** Attempt of any Class B VFO is a Class C VFO (per §70.02(1) class-level rule).

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Class D Violent Felonies (21 sections)

| Section | |
|---------|---|
| 120.02 | 120.05 | 120.18 | 120.60 | 121.12 | 130.30 | 130.65 | 130.80 | 130.66 | 130.90 | 135.35 | 265.02 | 265.11 | 215.16 | 490.10 | 490.20 | 240.60 | 240.62 | 240.63 | 405.18 | 265.50 |

**Subdivision restrictions apply to:**
- §120.60: only subdivision 1
- §135.35: only subdivisions 3a and 3b
- §265.02: only subdivisions 5, 6, 7, 8, 9, 10

**Note:** Attempt of any Class C VFO is a Class D VFO.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Class E Violent Felonies (4 sections)

| Section | |
|---------|---|
| 130.53 | 130.65-a | 240.55 | 240.61 |

**Note:** Attempt of §265.02 subdivisions 5/6/7/8 as a lesser included offense (CPL §220.20) is a Class E VFO.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

---

## Part 6: Statutory Lists — SMF List (PL §130.91(2))

Please confirm the following 30 sections are correctly listed as eligible for Sexually Motivated Felony treatment under PL §130.91(2).

| Section | Section | Section | Section | Section |
|---------|---------|---------|---------|---------|
| 120.05 | 120.06 | 120.07 | 120.10 | 120.60 |
| 121.12 | 121.13 | 125.15 | 125.20 | 125.25 |
| 125.26 | 125.27 | 135.20 | 135.25 | 140.20 |
| 140.25 | 140.30 | 150.15 | 150.20 | 160.05 |
| 160.10 | 160.15 | 230.30 | 230.32 | 230.33 |
| 230.34-a | 235.22 | 263.05 | 263.10 | 263.15 |

**Subdivision restriction applies to:**
- §125.15: only subdivision 1 is SMF-eligible

**Note:** PL §130.91(2) includes a blanket catch-all for "any felony attempt or conspiracy to commit any of the foregoing offenses."

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

---

## Part 7: Statutory Lists — Hate Crime List (PL §485.05(3))

Please confirm the following sections are correctly listed as eligible for Hate Crime enhancement under PL §485.05(3).

**Full list (86 sections):**

120.00, 120.05, 120.06, 120.07, 120.10, 120.12, 120.13, 120.14, 120.15, 120.20, 120.25, 121.11, 121.12, 121.13, 125.15, 125.20, 125.25, 125.26, 125.27, 120.45, 120.50, 120.55, 120.60, 130.20, 130.25, 130.30, 130.35, 130.52, 130.53, 130.55, 130.60, 130.65, 130.65-a, 130.66, 130.67, 130.70, 135.05, 135.10, 135.20, 135.25, 135.60, 135.61, 135.65, 140.10, 140.15, 140.17, 140.20, 140.25, 140.30, 145.00, 145.05, 145.10, 145.12, 150.05, 150.10, 150.15, 150.20, 155.25, 155.30, 155.35, 155.40, 155.42, 160.05, 160.10, 160.15, 230.34, 230.34-a, 240.25, 240.30, 240.50, 240.55, 240.60, 265.03, 265.04, 490.10, 490.15, 490.20, 490.25, 490.30, 490.35, 490.37, 490.40, 490.45, 490.47, 490.50, 490.55

**Subdivision restrictions apply to:**
- §125.15: only subdivision 1
- §125.20: only subdivisions 1, 2, and 4
- §240.30: only subdivisions 1, 2, and 4
- §265.03: only subdivision 1
- §265.04: only subdivision 1

**Note:** PL §485.05(3) includes a blanket catch-all for "any felony attempt or conspiracy to commit any of the foregoing offenses." This is NOT felony-gated — both misdemeanors and felonies can be hate-crime-eligible.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

---

## Part 8: Scenario Test Cases

The following scenarios test edge cases in the classification logic. For each, please confirm whether the system's determination is correct.

### Scenario 1 — Attempt of Murder 2nd Degree

**Fact pattern:** Defendant is charged with attempt to commit §125.25 (Murder in the Second Degree), a Class A-I felony.

**System says:** The attempt is classified as a Class B felony (not Class A-I), because §125.25 is not in the "stays Class A-I" list. It is also a Class B VFO because §125.25 is explicitly named in the VFO_LIST Class B attempt carve-out.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Scenario 2 — Manslaughter 2nd, Subdivision 3 (Aiding Suicide)

**Fact pattern:** Defendant is convicted of §125.15 subdivision 3 (intentionally causes or aids another person to commit suicide), a Class C felony.

**System says:** This subdivision is NOT eligible for SMF treatment and NOT eligible for Hate Crime enhancement. Only subdivision 1 of §125.15 is on those lists.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Scenario 3 — Murder 2nd Degree (Class A-I, no predicate exposure)

**Fact pattern:** Defendant is convicted of §125.25 (Murder in the Second Degree), a Class A-I felony. Defendant has one prior felony conviction.

**System says:** The defendant is NOT eligible for Youthful Offender treatment (Class A-I excluded per CPL §720.10(2)(a)). The offense does NOT have predicate exposure (Class A-I excluded per PL §70.06(1)(a)). The Second Felony Offender enhancement (§70.06) does NOT apply.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Scenario 4 — Class A-II Felony with Prior

**Fact pattern:** Defendant is convicted of a Class A-II felony. Defendant has one prior felony conviction within the lookback period.

**System says:** The offense DOES have predicate exposure (Class A-II is included — only Class A-I is excluded). The Second Felony Offender enhancement (§70.06) CAN apply. PL §70.06(3)(a)/(4)(a) has dedicated sentencing table entries for Class A-II.

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Scenario 5 — Conspiracy of a Hate Crime Offense

**Fact pattern:** Defendant is charged with conspiracy to commit §120.05 (Assault in the Second Degree), which is on the Hate Crime list. The crime was motivated by bias.

**System says:** The conspiracy is Hate Crime-eligible because PL §485.05(3) includes a blanket catch-all for "any felony attempt or conspiracy to commit any of the foregoing offenses."

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

### Scenario 6 — VFO with Prior Violent Felony

**Fact pattern:** Defendant is convicted of §120.10 (Aggravated Assault upon a Police Officer), a Class B VFO. Defendant has one prior violent felony conviction within 10 years.

**System says:** The offense is a VFO AND has predicate exposure. PRI 2nd Degree (§70.04) applies. Second Felony Offender (§70.06) does NOT apply because the offense is a VFO (70.04 takes precedence).

- [ ] Correct
- [ ] Incorrect
- [ ] Unsure

**Notes:** _______________________________________________

---

## Reviewer Information

**Reviewer name:** _______________________________________

**Date of review:** _______________________________________

**Overall assessment:**
- [ ] The rules as written are substantially correct
- [ ] There are errors that need correction (please note above)
- [ ] I need additional information to complete this review

**Additional comments:**

_______________________________________________________
_______________________________________________________
_______________________________________________________
_______________________________________________________
