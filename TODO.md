# TODO

## Data Model Foundation
- [ ] Populate all 14 NY classification tiers with accurate PL citations
- [ ] Seed complete modifier catalog (Hate Crime, Terrorism, Sexually Motivated, PRI, Juvenile, etc.)
- [ ] Build offense database — map real NYS Penal Law sections to offenses
- [ ] Complete classification resolution rules for all enhancement statutes
- [ ] Finalize sentencing rules for every (classification, provision_type) pair

## Legal Review & Verification
- [ ] Verify all classification_resolution rows with attorney sign-off
- [ ] Resolve all TODO flags in SEED_RESOLUTION_RULES
- [ ] Add verified_by / verified_date tracking to all enhancement rules

## Enhance Rule Subtypes
- [ ] Add DeterminatePrisonRange subtype (currently hack uses MandatoryRangeEscalating)
- [ ] Add ParoleEligibility, Restitution, Registration, Diversionary subtypes

## Application Features
- [ ] Build search/filter across offenses, statutes, and rules
- [ ] Add bulk import from Excel/CSV (bridge extract_crimes.py output into app)
- [ ] Add scenario builder — compose hypothetical fact patterns and auto-resolve sentencing
- [ ] Add diff/audit log for schema and data changes

## Infrastructure
- [ ] Add proper pyproject.toml dependencies (streamlit, pandas, requests, python-dotenv)
- [ ] Add .env.example with required keys
- [ ] Write README.md with setup + architecture docs
- [ ] Add database migration/versioning strategy

## Sentencing engine — gaps found during the track/pipeline restructure
- [ ] PL 70.71(5): §220.77 (operating as a major trafficker, A-I) takes an indeterminate 70.00 sentence, but the drug track gives it the 70.71 determinate range
- [ ] PL 110.05(9): attempting a class B misdemeanor is a violation; `resolve_attempt_classification` currently raises for these
- [ ] Hate crime of a VFO: 485.10(1) deems it a VFO, but the `derive` effect re-checks VFO_LIST for the bumped class, so e.g. 120.05 (D VFO) + hate → C non-VFO. Legal review needed
- [ ] Hate-crime 70.05 juvenile floor (485.10(3)(d)) is not applied: the juvenile disposition's term holds the minimum period, not the max-term range
- [ ] Hate-crime floors on the sex-offense track (70.80) are UNVERIFIED (`floorByStatus._sexTrackNote`)
- [ ] Juvenile offenders get the adult 60.01 alternatives (probation, CD, ...) for non-VFO felonies; check PL 60.10
- [ ] 70.08 rows with `minYearsFixed` render the label "Indeterminate sentence — life to life"
- [ ] Predicate facts are user-attested; computing the 70.06(1)(b) 10-year lookback (with incarceration tolling) from conviction dates is not modeled
