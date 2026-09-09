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
