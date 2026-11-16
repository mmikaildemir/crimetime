"""Which dispositions are authorized, given offender status, offense type
and offense-specific overrides."""

import pytest

from crimetime.models import CaseFacts, PriorRecord
from crimetime.report import render_report
from crimetime.sentencing import resolve


def _out(section, felonies=0, vfos=0, **facts):
    return resolve(section, CaseFacts(
        section=section,
        prior_record=PriorRecord(predicate_felonies=felonies, predicate_vfos=vfos),
        **facts,
    ))


def _types(out):
    return [d.type.value for d in out.available_dispositions]


# --- Offender status gates the PL 60.01 alternatives ------------------------

def test_first_offender_gets_alternatives():
    assert _types(_out("155.40")) == [
        "indeterminate", "split", "probation", "conditional_discharge", "unconditional_discharge",
    ]


@pytest.mark.parametrize("section,felonies,vfos", [
    ("155.40", 1, 0),  # 70.06(2) second felony offender
    ("200.22", 1, 1),  # violent predicate, non-violent current offense: still 70.06
    ("155.40", 2, 0),  # 70.10 persistent felony offender
    ("155.30", 1, 0),  # class E: no definite/intermittent either (70.00(4))
])
def test_predicate_felony_means_imprisonment_only(section, felonies, vfos):
    assert _types(_out(section, felonies, vfos)) == ["indeterminate"]


# --- Drug felonies: 70.70 / 70.71 -------------------------------------------

def test_first_drug_offender_class_b_may_get_definite_sentence():
    out = _out("220.39")
    assert _types(out)[:2] == ["determinate", "definite"]
    assert out.available_dispositions[1].statute_refs == ["PL 70.70(2)(c)"]


def test_second_drug_offender_class_b_lifetime_probation_only():
    out = _out("220.39", 1, 0)
    assert _types(out) == ["determinate", "probation"]
    assert out.available_dispositions[1].label == "Lifetime probation"
    assert out.available_dispositions[1].statute_refs == ["PL 70.70(3)(c), 65.00"]


def test_second_drug_offender_class_c_to_e_alternatives():
    # 220.06 criminal possession 5th (D)
    out = _out("220.06", 1, 0)
    assert _types(out) == ["determinate", "definite", "split", "probation"]
    assert out.available_dispositions[1].statute_refs == ["PL 70.70(3)(e)"]


def test_drug_offender_with_violent_predicate_imprisonment_only():
    assert _types(_out("220.39", 1, 1)) == ["determinate"]  # 70.70(4)


def test_class_a_ii_drug_lifetime_probation():
    for felonies, ref in [(0, "PL 70.71(2)(c), 65.00"), (1, "PL 70.71(3)(c), 65.00")]:
        out = _out("220.18", felonies, 0)
        assert _types(out) == ["determinate", "probation"]
        assert out.available_dispositions[1].statute_refs == [ref]


# --- Offense-specific overrides: attempts and subdivisions ------------------

def _primary(out):
    d = out.available_dispositions[0]
    return d.term.min_value, d.term.max_value


def test_265_02_elevated_range_only_for_subdivision_10():
    assert _primary(_out("265.02", subdivision="10")) == (3.5, 7)
    assert _primary(_out("265.02", subdivision="1")) == (2, 7)
    no_subd = _out("265.02")
    assert _primary(no_subd) == (2, 7)
    assert "subdivision 10" in no_subd.available_dispositions[0].conditions


@pytest.mark.parametrize("section,expected", [
    ("265.02", (1.5, 4)),   # attempt is class E; 70.02(3)(c)(ii) is for the completed crime
    ("125.21", (2, 7)),     # attempt is class D; (b)(i) is for the completed crime
    ("120.11", (7, 20)),    # 70.02(3)(b)(ii) names attempted 120.11
])
def test_attempts_use_their_own_range(section, expected):
    assert _primary(_out(section, is_attempt=True, attempt_of_section=section)) == expected


def test_attempted_murder_first_min_20_to_40():
    out = _out("125.27", is_attempt=True, attempt_of_section="125.27")
    d = out.available_dispositions[0]
    assert d.label == "Indeterminate sentence — 20–40 years to life"
    assert d.term.min_value == 20


def test_attempted_aggravated_murder_subd_1_is_a_i_not_lwop():
    out = _out("125.26", subdivision="1", is_attempt=True, attempt_of_section="125.26")
    assert out.classification == "ClassA_I_Felony"  # PL 110.05(1)
    assert out.available_dispositions[0].label == "Indeterminate sentence — 20–40 years to life"


def test_murder_first_label_shows_override_minimum():
    d = _out("125.27").available_dispositions[0]
    assert d.label == "Indeterminate sentence — 20–25 years to life"


def test_report_does_not_repeat_disposition_type():
    md = render_report(_out("200.22", 1, 1))
    assert "Indeterminate sentence — Indeterminate sentence" not in md
    assert "**Recommended** · Indeterminate sentence — max 6–15 years" in md
