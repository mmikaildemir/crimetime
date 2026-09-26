"""Test the full sentencing engine against the PL 120.02 reference example.

The reference output (from CrimeTime) lists 21 distinct outputs for:
  RECKLESS ASSAULT OF A CHILD, PL 120.02, Class D violent Felony, Adult

These tests verify the engine produces all of them.
"""

import pytest

from crimetime.models import AgeCategory, CaseFacts, PriorRecordStatus
from crimetime.sentencing import resolve


class TestPL12002BasicCase:
    """120.02 — Class D VFO, adult, first offender — basic case (no exception triggers)."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="120.02",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
        )
        return resolve("120.02", facts)

    def test_offense_name(self, output):
        assert output.offense_name == "Reckless assault of a child"

    def test_classification(self, output):
        assert output.classification == "ClassD_Felony"

    def test_is_vfo(self, output):
        assert output.is_vfo is True

    def test_determinate_sentence(self, output):
        """#1: Determinate 2–7 years."""
        det = [d for d in output.available_dispositions if d.type.value == "determinate"]
        assert len(det) == 1
        assert det[0].term.min_value == 2
        assert det[0].term.max_value == 7

    def test_prs(self, output):
        """#2: Post-release supervision 1.5–3 years."""
        det = [d for d in output.available_dispositions if d.type.value == "determinate"][0]
        assert det.prs is not None
        assert det.prs.min_years == 1.5
        assert det.prs.max_years == 3

    def test_definite_sentence(self, output):
        """#6: Definite sentence up to 1 year."""
        definite = [d for d in output.available_dispositions if d.type.value == "definite"]
        assert len(definite) == 1
        assert definite[0].term.max_value == 12  # months

    def test_intermittent(self, output):
        """#7: Intermittent imprisonment available."""
        intermittent = [d for d in output.available_dispositions if d.type.value == "intermittent"]
        assert len(intermittent) == 1

    def test_split_sentence(self, output):
        """#8: Split sentence with imprisonment + probation/CD."""
        split = [d for d in output.available_dispositions if d.type.value == "split"]
        assert len(split) == 1
        assert split[0].split_imprisonment_max_months == 6

    def test_probation(self, output):
        """#10: Probation 3/4/5 years."""
        probation = [d for d in output.available_dispositions if d.type.value == "probation"]
        assert len(probation) == 1
        assert probation[0].probation_years == [3, 4, 5]

    def test_conditional_discharge(self, output):
        """#11: Conditional discharge 3 years, record statement required for felony."""
        cd = [d for d in output.available_dispositions if d.type.value == "conditional_discharge"]
        assert len(cd) == 1
        assert cd[0].conditional_discharge_years == 3
        assert cd[0].record_statement_required is True

    def test_unconditional_discharge(self, output):
        """#12: Unconditional discharge, record statement required for felony."""
        ud = [d for d in output.available_dispositions if d.type.value == "unconditional_discharge"]
        assert len(ud) == 1
        assert ud[0].record_statement_required is True

    def test_fine(self, output):
        """#13: Fine up to $5,000 or double gain."""
        fines = [f for f in output.financial_obligations if f.type.value == "fine"]
        assert len(fines) == 1
        assert fines[0].amount == 5000

    def test_mandatory_surcharge(self, output):
        """#14: Mandatory surcharge $300."""
        surcharges = [f for f in output.financial_obligations if f.type.value == "mandatory_surcharge"]
        assert len(surcharges) == 1
        assert surcharges[0].amount == 300

    def test_crime_victim_assistance_fee(self, output):
        """#15: Crime victim assistance fee $25."""
        cvafs = [f for f in output.financial_obligations if f.type.value == "crime_victim_assistance_fee"]
        assert len(cvafs) == 1
        assert cvafs[0].amount == 25

    def test_dna_databank_fee(self, output):
        """#20: DNA databank fee $50."""
        dna_fees = [f for f in output.financial_obligations if f.type.value == "dna_databank_fee"]
        assert len(dna_fees) == 1
        assert dna_fees[0].amount == 50

    def test_dna_sample(self, output):
        """#21: DNA sample required."""
        dna_samples = [c for c in output.collateral_requirements if c.type.value == "dna_sample"]
        assert len(dna_samples) == 1


class TestPL12002WithExceptions:
    """120.02 with all exception triggers active."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="120.02",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            plea_from_armed_felony_indictment=True,
            armed_felony_mitigating_factor=True,
            domestic_violence_by_victim=True,
            is_dwi=True,
            victim_seeking_restitution=True,
        )
        return resolve("120.02", facts)

    def test_armed_felony_exception(self, output):
        """#3: Armed felony exception appears."""
        armed = [e for e in output.exception_paths if e.type.value == "armed_felony_override"]
        assert len(armed) == 1

    def test_record_statement(self, output):
        """#4: Record statement required appears."""
        record = [e for e in output.exception_paths if e.type.value == "record_statement_required"]
        assert len(record) == 1

    def test_domestic_violence_exception(self, output):
        """#5: DV indeterminate exception with 3–7 year range."""
        dv = [e for e in output.exception_paths if e.type.value == "domestic_violence_indeterminate"]
        assert len(dv) == 1
        assert dv[0].resulting_disposition is not None
        assert dv[0].resulting_disposition.term.min_value == 3
        assert dv[0].resulting_disposition.term.max_value == 7

    def test_dwi_exception(self, output):
        """#9: DWI split sentence variant appears."""
        dwi = [e for e in output.exception_paths if e.type.value == "dwi_split_sentence_variant"]
        assert len(dwi) == 1

    def test_restitution(self, output):
        """#17–19: Restitution obligations appear when victim seeking restitution."""
        restitution = [f for f in output.financial_obligations if "restitution" in f.type.value]
        assert len(restitution) == 3


# ---------------------------------------------------------------------------
# Modifier bump tests
# ---------------------------------------------------------------------------

def _hc_modifier(output):
    """Extract the hate crime modifier from the output, or None."""
    for m in output.modifiers_applied:
        if m.modifier_type == "hate_crime":
            return m
    return None


class TestHateCrimeBumpMisdemeanor:
    """§120.00 (assault 3rd, Class A misdemeanor, HC-eligible) bumped to Class E felony
    when hate_crime_motivated=True. Exercises the misdemeanorOrClassCDE simple branch."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="120.00",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            hate_crime_motivated=True,
        )
        return resolve("120.00", facts)

    def test_base_classification_recorded(self, output):
        assert output.base_classification == "ClassA_Misdemeanor"

    def test_bumped_classification(self, output):
        assert output.classification == "ClassE_Felony"

    def test_modifier_recorded(self, output):
        mod = _hc_modifier(output)
        assert mod is not None
        assert mod.branch == "misdemeanorOrClassCDE"
        assert mod.base_classification == "ClassA_Misdemeanor"
        assert mod.resulting_classification == "ClassE_Felony"

    def test_dispositions_reflect_bumped_class(self, output):
        indeterminate = [
            d for d in output.available_dispositions
            if d.type.value == "indeterminate"
        ]
        assert len(indeterminate) >= 1
        assert output.available_dispositions[0].type.value == "indeterminate"


class TestHateCrimeBumpClassE:
    """§155.30 (grand larceny 4th, Class E felony, HC-eligible) bumped to Class D felony."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="155.30",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            hate_crime_motivated=True,
        )
        return resolve("155.30", facts)

    def test_base_classification_recorded(self, output):
        assert output.base_classification == "ClassE_Felony"

    def test_bumped_classification(self, output):
        assert output.classification == "ClassD_Felony"

    def test_modifier_recorded(self, output):
        mod = _hc_modifier(output)
        assert mod is not None
        assert mod.branch == "misdemeanorOrClassCDE"

    def test_vfo_not_set(self, output):
        assert output.is_vfo is False


class TestHateCrimeBumpNotTriggered:
    """§120.00 with hate_crime_motivated=False — no bump. Negative control."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="120.00",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            hate_crime_motivated=False,
        )
        return resolve("120.00", facts)

    def test_no_modifiers(self, output):
        assert output.modifiers_applied == []

    def test_no_base_classification_recorded(self, output):
        assert output.base_classification is None

    def test_classification_unchanged(self, output):
        assert output.classification == "ClassA_Misdemeanor"

    def test_dispositions_are_misdemeanor_level(self, output):
        definite = [
            d for d in output.available_dispositions
            if d.type.value == "definite"
        ]
        assert len(definite) >= 1


class TestHateCrimeBumpClassBFloors:
    """§120.10 (assault 1st, Class B VFO, HC-eligible) — ClassB branch applies
    minimum floors (§485.10(3)) without reclassifying. First VFO offender
    (70.02) gets floor of 8 years minimum."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="120.10",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            hate_crime_motivated=True,
        )
        return resolve("120.10", facts)

    def test_modifier_recorded(self, output):
        mod = _hc_modifier(output)
        assert mod is not None
        assert mod.branch == "ClassB"

    def test_classification_unchanged(self, output):
        assert output.classification == "ClassB_Felony"

    def test_base_classification_recorded(self, output):
        assert output.base_classification == "ClassB_Felony"

    def test_vfo_unchanged(self, output):
        assert output.is_vfo is True

    def test_floor_applied_to_determinate_min(self, output):
        """§485.10(3)(b): 70.02 determinate term must be at least 8 years.
        The table gives 5-25 for Class B VFO first offender; the floor
        raises the min from 5 to 8."""
        det = [d for d in output.available_dispositions if d.type.value == "determinate"]
        assert len(det) == 1
        assert det[0].term.min_value == 8
        assert det[0].term.max_value == 25


class TestHateCrimeBumpClassAIFloor:
    """§125.27 (murder 1st, Class A-I, HC-eligible) — ClassA_I branch applies
    20-year minimum period (§485.10(4)) without reclassifying."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="125.27",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            hate_crime_motivated=True,
        )
        return resolve("125.27", facts)

    def test_modifier_recorded(self, output):
        mod = _hc_modifier(output)
        assert mod is not None
        assert mod.branch == "ClassA_I"

    def test_classification_unchanged(self, output):
        assert output.classification == "ClassA_I_Felony"

    def test_min_period_raised_to_20(self, output):
        """§485.10(4): min period must be at least 20 years."""
        primary = output.available_dispositions[0]
        assert primary.term.min_value >= 20


# ---------------------------------------------------------------------------
# SMF bump tests (§130.91)
# ---------------------------------------------------------------------------


class TestSMFBumpViolentRedesignation:
    """§140.20 (burglary 3rd, Class D felony, SMF-eligible) — SMF redesignates
    to Class D Violent Felony, routing through VFO tables. No tier shift."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="140.20",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            sexually_motivated=True,
        )
        return resolve("140.20", facts)

    def test_modifier_recorded(self, output):
        smf_mods = [m for m in output.modifiers_applied if m.modifier_type == "sexually_motivated_felony"]
        assert len(smf_mods) == 1
        assert smf_mods[0].branch == "violent_redesignation"
        assert smf_mods[0].base_classification == "ClassD_Felony"
        assert smf_mods[0].resulting_classification == "ClassD_Violent_Felony"

    def test_classification_redesignated(self, output):
        assert output.classification == "ClassD_Violent_Felony"

    def test_vfo_set_true(self, output):
        """SMF makes the offense a VFO, routing through 70.02 tables."""
        assert output.is_vfo is True

    def test_determinate_disposition(self, output):
        """As a VFO, the primary disposition should be determinate (70.02),
        not indeterminate (70.00)."""
        det = [d for d in output.available_dispositions if d.type.value == "determinate"]
        assert len(det) >= 1


class TestSMFBumpNotTriggered:
    """§140.20 without sexually_motivated — no SMF redesignation."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="140.20",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            sexually_motivated=False,
        )
        return resolve("140.20", facts)

    def test_no_modifiers(self, output):
        assert output.modifiers_applied == []

    def test_classification_unchanged(self, output):
        assert output.classification == "ClassD_Felony"

    def test_vfo_stays_false(self, output):
        assert output.is_vfo is False


# ---------------------------------------------------------------------------
# Terrorism bump tests (§490.25)
# ---------------------------------------------------------------------------


class TestTerrorismBumpClassD:
    """§140.20 (burglary 3rd, Class D felony, HC-eligible=terrorism-eligible)
    with terrorism_motivated=True → bumped to Class C Violent Felony + vfo=True."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="140.20",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            terrorism_motivated=True,
        )
        return resolve("140.20", facts)

    def test_modifier_recorded(self, output):
        terror_mods = [m for m in output.modifiers_applied if m.modifier_type == "terrorism"]
        assert len(terror_mods) == 1
        assert terror_mods[0].branch == "ClassCDE"
        assert terror_mods[0].base_classification == "ClassD_Felony"
        assert terror_mods[0].resulting_classification == "ClassC_Violent_Felony"

    def test_bumped_classification(self, output):
        assert output.classification == "ClassC_Violent_Felony"

    def test_vfo_deemed_true(self, output):
        """§490.25(2)(a): terrorism deems the offense a VFO."""
        assert output.is_vfo is True

    def test_determinate_disposition(self, output):
        det = [d for d in output.available_dispositions if d.type.value == "determinate"]
        assert len(det) >= 1


class TestTerrorismBumpClassBToAI:
    """§120.10 (assault 1st, Class B felony, terrorism-eligible) → deemed
    Class A-I felony per §490.25(2)(c), sentenced per 70.00."""

    @pytest.fixture
    def output(self):
        facts = CaseFacts(
            section="120.10",
            prior_record_status=PriorRecordStatus.FIRST_OFFENDER,
            defendant_age_category=AgeCategory.ADULT,
            terrorism_motivated=True,
        )
        return resolve("120.10", facts)

    def test_modifier_recorded(self, output):
        terror_mods = [m for m in output.modifiers_applied if m.modifier_type == "terrorism"]
        assert len(terror_mods) == 1
        assert terror_mods[0].branch == "ClassB_to_A_I"

    def test_bumped_to_class_ai(self, output):
        assert output.classification == "ClassA_I_Felony"

    def test_indeterminate_disposition(self, output):
        """Class A-I is sentenced via indeterminate (70.00), not determinate."""
        primary = output.available_dispositions[0]
        assert primary.type.value == "indeterminate"
