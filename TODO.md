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
