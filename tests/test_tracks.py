"""Offender-status derivation: the same predicate facts mean different
statuses on different sentencing tracks."""

import pytest
from pydantic import ValidationError

from crimetime.models import CaseFacts, OffenderStatus as S, PriorRecord, PriorRecordStatus
from crimetime.sentencing import resolve


def _status(section, felonies, vfos, **facts):
    out = resolve(section, CaseFacts(
        section=section,
        prior_record=PriorRecord(predicate_felonies=felonies, predicate_vfos=vfos),
        **facts,
    ))
    return out.sentencing_track, out.offender_status


# (section, felonies, vfos, expected track, expected status)
CASES = [
    # Non-violent felony: 155.40 grand larceny 2nd (C), 125.25 murder 2nd (A-I)
    ("155.40", 0, 0, "nonviolent_felony", S.FIRST_OFFENDER),
    ("155.40", 1, 0, "nonviolent_felony", S.SECOND_FELONY_OFFENDER_70_06),
    ("155.40", 1, 1, "nonviolent_felony", S.SECOND_FELONY_OFFENDER_70_06),
    ("155.40", 2, 0, "nonviolent_felony", S.PERSISTENT_FELONY_OFFENDER_70_10),
    ("155.40", 2, 1, "nonviolent_felony", S.PERSISTENT_FELONY_OFFENDER_70_10),
    ("125.25", 1, 0, "nonviolent_felony", S.FIRST_OFFENDER),  # 70.06 excludes class A
    # Violent felony: 120.10 assault 1st (B VFO)
    ("120.10", 0, 0, "violent_felony", S.FIRST_OFFENDER),
    ("120.10", 1, 0, "violent_felony", S.SECOND_FELONY_OFFENDER_VFO_70_06_6),
    ("120.10", 2, 0, "violent_felony", S.SECOND_FELONY_OFFENDER_VFO_70_06_6),
    ("120.10", 1, 1, "violent_felony", S.SECOND_VIOLENT_FELONY_OFFENDER_70_04),
    ("120.10", 2, 1, "violent_felony", S.SECOND_VIOLENT_FELONY_OFFENDER_70_04),
    ("120.10", 2, 2, "violent_felony", S.PERSISTENT_VIOLENT_FELONY_OFFENDER_70_08),
    # Drug felony: 220.39 criminal sale 3rd (B)
    ("220.39", 0, 0, "drug_felony", S.FIRST_OFFENDER),
    ("220.39", 1, 0, "drug_felony", S.SECOND_FELONY_DRUG_OFFENDER),
    ("220.39", 1, 1, "drug_felony", S.SECOND_FELONY_DRUG_OFFENDER_PRIOR_VFO),
    # Sex offense: 130.35 rape 1st (B)
    ("130.35", 0, 0, "sex_offense_felony", S.FIRST_OFFENDER),
    ("130.35", 1, 0, "sex_offense_felony", S.SEX_OFFENDER_PREDICATE_NONVIOLENT_70_80_5B),
    ("130.35", 1, 1, "sex_offense_felony", S.SEX_OFFENDER_PREDICATE_VIOLENT_70_80_5C),
    # Prior felonies don't change misdemeanor sentencing
    ("120.00", 2, 2, "misdemeanor", S.NOT_APPLICABLE),
]


@pytest.mark.parametrize("section,felonies,vfos,track,status", CASES)
def test_derived_status(section, felonies, vfos, track, status):
    assert _status(section, felonies, vfos) == (track, status)


def test_class_e_vfo_has_no_70_08_range():
    # 240.55 is a class E VFO; PL 70.08(3) has no class E provision, so 70.02 applies.
    assert _status("240.55", 2, 2) == ("violent_felony", S.FIRST_OFFENDER)


def test_juvenile_offender_track_ignores_priors():
    assert _status("120.10", 2, 2, defendant_age_category="juvenile_offender") == (
        "juvenile_offender", S.NOT_APPLICABLE)


def test_drug_prior_vfo_uses_70_70_4_range():
    out = resolve("220.39", CaseFacts(section="220.39", prior_record=PriorRecord(predicate_felonies=1, predicate_vfos=1)))
    primary = out.available_dispositions[0]
    assert primary.statute_refs == ["PL 70.70(4)"]
    assert (primary.term.min_value, primary.term.max_value) == (6, 15)
    assert out.offender_status_label.startswith("Second felony drug offender, prior violent felony")


def test_prior_record_rejects_more_vfos_than_felonies():
    with pytest.raises(ValidationError):
        PriorRecord(predicate_felonies=1, predicate_vfos=2)


@pytest.mark.parametrize("legacy", list(PriorRecordStatus))
def test_legacy_status_input_still_accepted(legacy):
    out = resolve("120.10", CaseFacts(section="120.10", prior_record_status=legacy))
    assert out.sentencing_track == "violent_felony"


def test_trace_records_each_stage():
    out = resolve("120.05", CaseFacts(section="120.05", hate_crime_motivated=True))
    stages = [t.stage for t in out.trace]
    assert stages[0] == "classify"
    assert "modifier" in stages and "track" in stages and "offender_status" in stages
