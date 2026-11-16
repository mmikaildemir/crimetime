"""Offense-specific limits on first-offender felony alternatives:
PL 60.05(4), 60.05(5), 70.02(2)(a), (b), (b-1) and (c)."""

import pytest

from crimetime.models import AgeCategory, CaseFacts, PriorRecordStatus
from crimetime.sentencing import resolve


def _alt_types(section, **kw):
    facts = CaseFacts(
        section=section,
        prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
        defendant_age_category=AgeCategory.ADULT,
        **kw,
    )
    out = resolve(section, facts)
    return {d.type.value for d in out.available_dispositions[1:]}, out


ALL_D = {
    "definite", "intermittent", "split", "probation",
    "conditional_discharge", "unconditional_discharge",
}


@pytest.mark.parametrize("section", ["190.42", "200.22", "200.27", "230.30", "150.10"])
def test_60_05_4_listed_class_c_imprisonment_only(section):
    types, out = _alt_types(section)
    assert out.classification == "ClassC_Felony"
    assert types == set()


@pytest.mark.parametrize("target", ["200.04", "200.12", "105.15", "145.12", "230.32"])
def test_60_05_4_listed_attempts_imprisonment_only(target):
    types, out = _alt_types(target, is_attempt=True, attempt_of_section=target)
    assert out.classification == "ClassC_Felony"
    assert types == set()


@pytest.mark.parametrize("section", ["120.05", "121.12"])
def test_60_05_5_listed_class_d_70_00_or_85_00_only(section):
    types, _ = _alt_types(section)
    assert types == {"definite", "intermittent"}


def test_60_05_5_attempted_230_30():
    types, out = _alt_types("230.30", is_attempt=True, attempt_of_section="230.30")
    assert out.classification == "ClassD_Felony"
    assert types == {"definite", "intermittent"}


def test_class_c_vfo_determinate_only():
    types, _ = _alt_types("160.10")
    assert types == set()


def test_70_02_2_b1_menacing_police_officer_determinate_only():
    types, _ = _alt_types("120.18")
    assert types == set()


@pytest.mark.parametrize("section,subdivision", [("265.02", "7"), ("265.11", None), ("265.50", None)])
def test_70_02_2_c_weapon_offenses(section, subdivision):
    types, out = _alt_types(section, subdivision=subdivision)
    assert types == ALL_D
    definite = next(d for d in out.available_dispositions if d.type.value == "definite")
    assert definite.term.min_value == definite.term.max_value == 12
    assert definite.statute_refs == ["PL 70.02(2)(c)"]
    for d in out.available_dispositions[1:]:
        if d.type.value != "definite":
            assert "PL 70.02(2)(c)(i)" in d.statute_refs
            assert "70.02(2)(c)(i)" in d.conditions


def test_265_02_subdivision_10_not_in_70_02_2_c():
    types, out = _alt_types("265.02", subdivision="10")
    assert types == ALL_D
    assert all("PL 70.02(2)(c)(i)" not in d.statute_refs for d in out.available_dispositions)


def test_second_felony_offender_unaffected():
    facts = CaseFacts(
        section="200.22",
        prior_record_status=PriorRecordStatus.SECOND_FELONY_OFFENDER_70_06,
        defendant_age_category=AgeCategory.ADULT,
    )
    out = resolve("200.22", facts)
    assert out.available_dispositions[1:] == []
