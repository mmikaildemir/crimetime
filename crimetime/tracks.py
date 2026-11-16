"""Sentencing tracks — which Article 70 scheme governs the current conviction.

Each track answers three questions:

  applies(ctx)            Does this scheme govern this conviction?
  derive_status(ctx)      Given the defendant's predicate facts
                          (CaseFacts.prior_record), which offender status
                          does this scheme assign?
  primary / alternatives  The primary disposition (+ PRS) and alternative
                          dispositions, read from the track's self-describing
                          table in data/sentencing_tables.json.

TRACKS is ordered and the first track that applies governs. Offender status
is a conclusion of (track x predicate facts): the same record — one violent
predicate — is 70.04 on the violent track, 70.06 on the non-violent track and
70.80(5)(c) on the sex-offense track.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from . import reference
from .models import (
    AgeCategory,
    CaseFacts,
    Disposition,
    DispositionType,
    OffenderStatus,
    PostReleaseSupervision,
    TermRange,
    TermUnit,
)
from .resolvers import is_felony, is_misdemeanor, is_violation

if TYPE_CHECKING:
    from .sentencing import SentencingContext


# ---------------------------------------------------------------------------
# Classification -> table class key
# ---------------------------------------------------------------------------

_CLASS_KEY_MAP = {
    "ClassA_I_Felony": "ClassA_I",
    "ClassA_II_Felony": "ClassA_II",
    "ClassB_Felony": "ClassB",
    "ClassC_Felony": "ClassC",
    "ClassD_Felony": "ClassD",
    "ClassE_Felony": "ClassE",
    # Violent variants map to same class letter
    "ClassB_Violent_Felony": "ClassB",
    "ClassC_Violent_Felony": "ClassC",
    "ClassD_Violent_Felony": "ClassD",
    "ClassE_Violent_Felony": "ClassE",
}



def class_key(classification: str) -> str:
    """Map a classification to its sentencing-table class key (e.g. 'ClassD')."""
    return _CLASS_KEY_MAP.get(classification, classification)


_A_CLASSES = ("ClassA_I_Felony", "ClassA_II_Felony")


# ---------------------------------------------------------------------------
# Offense-type predicates used by track applicability
# ---------------------------------------------------------------------------


def _is_drug_offense(offense: dict) -> bool:
    """Drug felony (Article 220 or 222) per PL 70.70/70.71."""
    return offense.get("article", 0) in (220, 222)


# Felony sex offense sections outside Article 130 (per PL 70.80(1)(a))
_SEX_OFFENSE_EXTRA_SECTIONS = {
    "230.05", "230.06", "230.11", "230.12", "230.13",
    "255.26", "255.27",
}


def _is_sex_offense(offense: dict, section: str) -> bool:
    """Felony sex offense per PL 70.80(1)(a): Article 130 felonies and
    specific 230/255 sections."""
    if offense.get("article", 0) == 130:
        return True
    return section in _SEX_OFFENSE_EXTRA_SECTIONS


# Class A-II sections explicitly named in PL 70.08(1)(a), so they reach the
# persistent violent felony offender table even though VFO_LIST (70.02(1))
# only covers B/C/D/E.
_SPECIAL_70_08_AII_SECTIONS = {"130.95", "130.96"}

# Sections with special Class A-I juvenile treatment (70.05(2)(a)/(b))
_JUVENILE_A_I_MURDER = "125.25"
_JUVENILE_A_I_ARSON_KIDNAP = {"150.20", "135.25"}


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------


def _status_block(table: str, status: OffenderStatus) -> dict:
    block = reference.get_status_table(table, status.value)
    if block is None:
        raise ValueError(f"No {table} table for offender status {status.value}")
    return block


def _row(block: dict, table: str, status: OffenderStatus, cls_key: str, section: str) -> dict:
    row = block["rows"].get(cls_key)
    if row is None:
        raise ValueError(
            f"No {table}/{status.value} table entry for {cls_key} (section {section})"
        )
    return row


def _determinate(
    block: dict, row: dict, term: Optional[list] = None, statute: Optional[str] = None
) -> tuple[Disposition, Optional[PostReleaseSupervision]]:
    """Determinate disposition + PRS from a self-describing table row."""
    term = term or row["termYears"]
    disp = Disposition(
        type=DispositionType.DETERMINATE,
        label=f"Determinate sentence of {term[0]}–{term[1]} years",
        statute_refs=[statute or row.get("statute", block["statute"])],
        term=TermRange(min_value=term[0], max_value=term[1]),
    )
    prs = None
    if "prsYears" in row:
        prs = PostReleaseSupervision(
            min_years=row["prsYears"][0],
            max_years=row["prsYears"][1],
            statute_refs=[block["prsRef"]],
        )
    return disp, prs


# ---------------------------------------------------------------------------
# Offense-specific overrides (PL 70.00(3)(a), 70.02(3))
# ---------------------------------------------------------------------------


def offense_override(ctx: SentencingContext) -> Optional[dict]:
    """The offense-specific override governing this conviction, if any.

    A completed offense uses the entry keyed by its section; an attempt uses
    only the "attempt_<section>" entry, because the statutes name attempts
    separately (e.g. 70.02(3)(b)(ii) attempted 120.11, 70.00(3)(a)(i)(C)
    attempted murder 1st). An entry with "subdivisionOverride" applies only
    to that subdivision; an entry with "subdivisions" may refine per
    subdivision.
    """
    facts = ctx.case_facts
    overrides = reference.get_offense_overrides()
    if facts.is_attempt and facts.attempt_of_section:
        override = overrides.get(f"attempt_{facts.attempt_of_section}")
    else:
        override = overrides.get(ctx.section)
    if not override:
        return None
    only_subd = override.get("subdivisionOverride")
    if only_subd is not None and facts.subdivision != only_subd:
        return None
    if facts.subdivision and "subdivisions" in override:
        return override["subdivisions"].get(facts.subdivision) or override
    return override


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------


class Track:
    """Base class. Subclasses set `name` and `table` and override the hooks."""

    name: str = ""
    table: Optional[str] = None  # key in sentencing_tables.json, if status-driven

    def applies(self, ctx: SentencingContext) -> bool:
        raise NotImplementedError

    def derive_status(self, ctx: SentencingContext) -> OffenderStatus:
        return OffenderStatus.NOT_APPLICABLE

    def primary(
        self, ctx: SentencingContext, status: OffenderStatus
    ) -> tuple[Disposition, Optional[PostReleaseSupervision]]:
        raise NotImplementedError

    def alternatives(self, ctx: SentencingContext) -> list[Disposition]:
        # A second or persistent offender must be sentenced to imprisonment
        # (PL 70.06(2), 70.04(2), 70.08(2), 70.10(2)); the PL 60.01
        # alternatives are only for offenders without a predicate.
        if ctx.status not in (OffenderStatus.FIRST_OFFENDER, OffenderStatus.NOT_APPLICABLE):
            return []
        return _first_offender_felony_alternatives(ctx)

    def status_label(self, status: OffenderStatus) -> str:
        if self.table:
            block = reference.get_status_table(self.table, status.value)
            if block and "label" in block:
                return block["label"]
        return status.value.replace("_", " ").capitalize()


class JuvenileOffenderTrack(Track):
    """PL 70.05 — juvenile offenders get reduced indeterminate sentences,
    regardless of VFO/drug/sex status. Covers Class A-I (murder/arson/kidnap),
    B, C, D felonies; Class E/A-II and non-felonies use the adult tracks."""

    name = "juvenile_offender"
    table = "juvenileOffender"

    def applies(self, ctx):
        return (
            is_felony(ctx.classification)
            and ctx.case_facts.defendant_age_category == AgeCategory.JUVENILE_OFFENDER
            and class_key(ctx.classification) in ("ClassA_I", "ClassB", "ClassC", "ClassD")
        )

    def alternatives(self, ctx):
        # PL 60.10: a juvenile offender is sentenced to imprisonment under
        # 70.05 (or as a youthful offender under 60.02), notwithstanding any
        # other law — no 60.01 alternatives.
        return []

    def primary(self, ctx, status):
        block = _status_block(self.table, status)
        cls_key = class_key(ctx.classification)
        if cls_key == "ClassA_I":
            if ctx.section == _JUVENILE_A_I_MURDER:
                cls_key = "ClassA_I_murder"
            else:
                # Arson/kidnapping 1st per 70.05(2)(b). Other A-I felonies are
                # not explicitly in 70.05; fall back to the same row.
                cls_key = "ClassA_I_arson_kidnap"
        row = _row(block, self.table, status, cls_key, ctx.section)
        statute = row.get("statute", block["statute"])

        max_term = row.get("maxTerm", row.get("maxTermYears"))
        min_years = row.get("minYears")
        min_rule = row.get("minTermRule")

        if max_term == "life":
            return Disposition(
                type=DispositionType.INDETERMINATE,
                label=f"Indeterminate sentence — {min_years[0]}–{min_years[1]} years to life",
                statute_refs=[statute],
                term=TermRange(min_value=min_years[0], max_value=999),
                conditions=min_rule,
            ), None
        if min_years:
            return Disposition(
                type=DispositionType.INDETERMINATE,
                label=f"Indeterminate sentence — {min_years[0]}–{min_years[1]} to {max_term[0]}–{max_term[1]} years max",
                statute_refs=[statute],
                term=TermRange(min_value=min_years[0], max_value=max_term[1]),
                conditions=min_rule,
            ), None
        return Disposition(
            type=DispositionType.INDETERMINATE,
            label=f"Indeterminate sentence — 1yr to 1/3 of max (max {max_term[1]} years)",
            statute_refs=[statute],
            term=TermRange(min_value=1, max_value=max_term[1]),
            conditions=min_rule,
        ), None


class DrugFelonyTrack(Track):
    """PL 70.70 (non-A) / 70.71 (A) — determinate sentences for Article
    220/222 felonies. VFO drug offenses stay on the violent track per 70.70(4)."""

    name = "drug_felony"
    table = "drugFelony"

    def applies(self, ctx):
        return is_felony(ctx.classification) and not ctx.vfo and _is_drug_offense(ctx.offense)

    def derive_status(self, ctx):
        # 70.70(4) / 70.71(4): the predicate was a violent felony.
        if ctx.prior.predicate_vfos >= 1:
            return OffenderStatus.SECOND_FELONY_DRUG_OFFENDER_PRIOR_VFO
        if ctx.prior.predicate_felonies >= 1:
            return OffenderStatus.SECOND_FELONY_DRUG_OFFENDER
        return OffenderStatus.FIRST_OFFENDER

    def primary(self, ctx, status):
        block = _status_block(self.table, status)
        row = _row(block, self.table, status, class_key(ctx.classification), ctx.section)
        return _determinate(block, row)

    def alternatives(self, ctx):
        """Drug felonies have their own alternatives, which survive a
        non-violent predicate (70.70(3)(c)-(e)) but not a violent one
        (70.70(4), 70.71(4): determinate sentence only)."""
        status = ctx.status
        cls = class_key(ctx.classification)
        second = status == OffenderStatus.SECOND_FELONY_DRUG_OFFENDER
        if status == OffenderStatus.SECOND_FELONY_DRUG_OFFENDER_PRIOR_VFO:
            return []
        if cls == "ClassA_I":
            return []
        if cls == "ClassA_II":
            return [_lifetime_probation("PL 70.71(3)(c), 65.00" if second else "PL 70.71(2)(c), 65.00")]

        if not second:
            # 70.70(2)(b)-(c): the usual alternatives, with the alternative
            # definite sentence extended to class B and C drug felonies.
            alts = [
                d for d in _generate_felony_alternatives(ctx.classification, ctx.case_facts)
                if d.type != DispositionType.DEFINITE
            ]
            return [_drug_definite_sentence("PL 70.70(2)(c)"), *alts]

        # 70.70(3): second felony drug offender, non-violent predicate.
        if cls == "ClassB":
            return [_lifetime_probation("PL 70.70(3)(c), 65.00")]
        alts = [_drug_definite_sentence("PL 70.70(3)(e)")]
        alts += [
            d for d in _generate_felony_alternatives(ctx.classification, ctx.case_facts)
            if d.type == DispositionType.SPLIT
        ]
        probation = _probation_from_table()
        probation.statute_refs = ["PL 70.70(3)(c), 65.00"]
        alts.append(probation)
        return alts


class SexOffenseFelonyTrack(Track):
    """PL 70.80 — determinate sentences with sex-offense PRS (70.45(2-a)) for
    non-Class-A felony sex offenses."""

    name = "sex_offense_felony"
    table = "sexOffenseFelony"

    def applies(self, ctx):
        return (
            is_felony(ctx.classification)
            and _is_sex_offense(ctx.offense, ctx.section)
            and ctx.classification not in _A_CLASSES
        )

    def derive_status(self, ctx):
        if ctx.prior.predicate_vfos >= 1:
            return OffenderStatus.SEX_OFFENDER_PREDICATE_VIOLENT_70_80_5C
        if ctx.prior.predicate_felonies >= 1:
            return OffenderStatus.SEX_OFFENDER_PREDICATE_NONVIOLENT_70_80_5B
        return OffenderStatus.FIRST_OFFENDER

    def primary(self, ctx, status):
        block = _status_block(self.table, status)
        row = _row(block, self.table, status, class_key(ctx.classification), ctx.section)
        return _determinate(block, row)

    def alternatives(self, ctx):
        # 70.80 sentences get no 60.01 alternatives.
        return []


class ViolentFelonyTrack(Track):
    """PL 70.02 / 70.06(6) / 70.04 / 70.08 — violent felony offenses."""

    name = "violent_felony"
    table = "violentFelony"

    def applies(self, ctx):
        if not is_felony(ctx.classification):
            return False
        if ctx.vfo:
            return True
        # 130.95/130.96 (A-II) are named in 70.08(1)(a) despite not being in VFO_LIST.
        return ctx.section in _SPECIAL_70_08_AII_SECTIONS and ctx.prior.predicate_vfos >= 2

    def derive_status(self, ctx):
        prior = ctx.prior
        if not ctx.vfo:  # 130.95/130.96 special case — only reached as 70.08
            return OffenderStatus.PERSISTENT_VIOLENT_FELONY_OFFENDER_70_08
        if prior.predicate_vfos >= 2:
            # PL 70.08(3) has no Class E provision. Two violent predicates
            # still satisfy 70.04(1) (one or more), so sentence as a second
            # violent felony offender under 70.04(3)(d).
            if ctx.classification in ("ClassE_Felony", "ClassE_Violent_Felony"):
                return OffenderStatus.SECOND_VIOLENT_FELONY_OFFENDER_70_04
            return OffenderStatus.PERSISTENT_VIOLENT_FELONY_OFFENDER_70_08
        if prior.predicate_vfos == 1:
            return OffenderStatus.SECOND_VIOLENT_FELONY_OFFENDER_70_04
        if prior.predicate_felonies >= 1:
            # PL 70.06(6): second felony offender (any non-violent predicate)
            # convicted of a VFO.
            return OffenderStatus.SECOND_FELONY_OFFENDER_VFO_70_06_6
        return OffenderStatus.FIRST_OFFENDER

    def primary(self, ctx, status):
        block = _status_block(self.table, status)
        cls_key = class_key(ctx.classification)

        if status == OffenderStatus.PERSISTENT_VIOLENT_FELONY_OFFENDER_70_08:
            row = block["versions"][block["activeVersion"]].get(cls_key)
            if row is None:
                raise ValueError(f"No 70.08 table entry for {cls_key} (section {ctx.section})")
            min_years = row.get("minYears")
            if isinstance(min_years, list):
                min_text = f"{min_years[0]}–{min_years[1]} years"
            else:  # 70.08(3)(a): a fixed minimum (25 years for 130.95/130.96)
                min_text = f"{row.get('minYearsFixed', 20)} years"
            return Disposition(
                type=DispositionType.INDETERMINATE,
                label=f"Indeterminate sentence — {min_text} to life",
                statute_refs=[block["statute"]],
                term=TermRange(
                    min_value=min_years[0] if isinstance(min_years, list) else row.get("minYearsFixed", 20),
                    max_value=999,
                ),
            ), None

        row = _row(block, self.table, status, cls_key, ctx.section)
        # 70.02(3) offense-specific elevated determinate ranges apply only to
        # the first violent felony offender.
        if status == OffenderStatus.FIRST_OFFENDER:
            override = offense_override(ctx) or {}
            if "determinateOverride" in override:
                return _determinate(
                    block, row,
                    term=override["determinateOverride"],
                    statute=override.get("_ref", row.get("statute", block["statute"])),
                )
            disp, prs = _determinate(block, row)
            disp.conditions = _subdivision_override_note(ctx)
            return disp, prs
        return _determinate(block, row)


class NonViolentFelonyTrack(Track):
    """PL 70.00 / 70.06 / 70.10 — indeterminate sentences for other felonies."""

    name = "nonviolent_felony"
    table = "nonViolentFelony"

    def applies(self, ctx):
        return is_felony(ctx.classification)

    def derive_status(self, ctx):
        prior = ctx.prior
        # PL 70.10: two or more predicate felonies, violent or not.
        if prior.predicate_felonies >= 2:
            return OffenderStatus.PERSISTENT_FELONY_OFFENDER_70_10
        if prior.predicate_felonies >= 1:
            # PL 70.06 does not apply to Class A-I/A-II.
            if ctx.classification in _A_CLASSES:
                return OffenderStatus.FIRST_OFFENDER
            return OffenderStatus.SECOND_FELONY_OFFENDER_70_06
        return OffenderStatus.FIRST_OFFENDER

    def primary(self, ctx, status):
        block = _status_block(self.table, status)

        if status == OffenderStatus.PERSISTENT_FELONY_OFFENDER_70_10:
            all_classes = block["rows"]["allClasses"]
            return Disposition(
                type=DispositionType.INDETERMINATE,
                label="Indeterminate sentence — court MAY sentence as Class A-I (discretionary)",
                statute_refs=[block["statute"]],
                term=TermRange(min_value=all_classes.get("possibleMinYears", [15, 25])[0], max_value=999),
                conditions="Discretionary — requires separate judicial finding, not automatic from 2 priors alone",
            ), None

        row = _row(block, self.table, status, class_key(ctx.classification), ctx.section)
        max_years = row["maxTermYears"]
        statute = block["statute"]
        min_period_str = _format_min_period_rule(row)
        if max_years == "life":
            min_period = row.get("minYears", [15, 25])
            return Disposition(
                type=DispositionType.INDETERMINATE,
                label=f"Indeterminate sentence — {min_period[0]}–{min_period[1]} years to life",
                statute_refs=[statute],
                term=TermRange(min_value=min_period[0], max_value=999),
                conditions=min_period_str,
            ), None
        label = f"Indeterminate sentence — max {max_years[0]}–{max_years[1]} years"
        if min_period_str:
            label += f", min {_format_min_period_short(row)}"
        return Disposition(
            type=DispositionType.INDETERMINATE,
            label=label,
            statute_refs=[statute],
            term=TermRange(min_value=max_years[0], max_value=max_years[1]),
            conditions=min_period_str,
        ), None


class MisdemeanorTrack(Track):
    """PL 70.15(1)-(3) — definite sentences; prior felonies don't change the range."""

    name = "misdemeanor"

    def applies(self, ctx):
        return is_misdemeanor(ctx.classification)

    def primary(self, ctx, status):
        return _resolve_primary_misdemeanor_disposition(ctx.classification), None

    def alternatives(self, ctx):
        return _generate_misdemeanor_alternatives(ctx.classification, ctx.case_facts)

    def status_label(self, status):
        return "Not applicable — prior felonies do not change misdemeanor sentencing (PL 70.15)"


class ViolationTrack(Track):
    """PL 70.15(4) — violations."""

    name = "violation"

    def applies(self, ctx):
        return is_violation(ctx.classification)

    def primary(self, ctx, status):
        return _resolve_primary_violation_disposition(), None

    def alternatives(self, ctx):
        return _generate_violation_alternatives()

    def status_label(self, status):
        return "Not applicable — violation (PL 70.15(4))"


# Ordered: the first track that applies governs.
TRACKS: list[Track] = [
    JuvenileOffenderTrack(),
    DrugFelonyTrack(),
    SexOffenseFelonyTrack(),
    ViolentFelonyTrack(),
    NonViolentFelonyTrack(),
    MisdemeanorTrack(),
    ViolationTrack(),
]


def select_track(ctx: SentencingContext) -> Track:
    for track in TRACKS:
        if track.applies(ctx):
            return track
    raise ValueError(f"Unknown classification: {ctx.classification}")


# ---------------------------------------------------------------------------
# Disposition builders shared by tracks
# ---------------------------------------------------------------------------


def _format_min_period_rule(row: dict) -> str | None:
    """Format a human-readable minimum-period rule from structured data fields.

    Handles both the new structured schema (minPeriodFloor / minPeriodCeiling)
    and the legacy free-text minTermRule for backward compatibility.
    """
    floor = row.get("minPeriodFloor")
    ceiling = row.get("minPeriodCeiling")
    ref = row.get("minPeriodRef", "")

    if floor is not None or ceiling is not None:
        parts = []
        if floor is not None:
            if isinstance(floor, str):
                parts.append(f"not less than {floor}")
            else:
                parts.append(f"not less than {floor} year{'s' if floor != 1 else ''}")
        if ceiling is not None:
            parts.append(f"not more than {ceiling}")
        rule = ", and ".join(parts) if len(parts) > 1 else parts[0]
        if ref:
            rule += f" ({ref})"
        return f"Minimum period: {rule}"

    legacy = row.get("minTermRule")
    if legacy:
        return f"Minimum period: {legacy}"

    return None


def _format_min_period_short(row: dict) -> str:
    """Compact min-period summary for the disposition label (no statute ref)."""
    floor = row.get("minPeriodFloor")
    ceiling = row.get("minPeriodCeiling")

    if floor is not None or ceiling is not None:
        parts = []
        if floor is not None:
            if isinstance(floor, str):
                parts.append(f"{floor}")
            else:
                parts.append(f"{floor} yr" if floor == 1 else f"{floor} yrs")
        if ceiling is not None:
            parts.append(f"to {ceiling}")
        return " ".join(parts) if parts else ""

    legacy = row.get("minTermRule")
    if legacy:
        return legacy

    return ""


def _resolve_primary_misdemeanor_disposition(
    classification: str,
) -> Disposition:
    """Resolve the primary disposition for a misdemeanor."""
    tables = reference.get_misdemeanor_table()
    if classification == "ClassA_Misdemeanor":
        row = tables.get("ClassA", {})
        first = row.get("firstOffender", {})
        max_days = first.get("maxTermDays", 364)
        return Disposition(
            type=DispositionType.DEFINITE,
            label=f"Definite sentence up to {max_days} days",
            statute_refs=["PL 70.15(1)"],
            term=TermRange(
                min_value=0,
                max_value=max_days,
                unit=TermUnit.DAYS,
            ),
        )
    elif classification == "ClassB_Misdemeanor":
        row = tables.get("ClassB", {})
        return Disposition(
            type=DispositionType.DEFINITE,
            label=f"Definite sentence up to {row.get('firstOffender', {}).get('maxTermMonths', 3)} months",
            statute_refs=["PL 70.15(2)"],
            term=TermRange(
                min_value=0,
                max_value=row.get("firstOffender", {}).get("maxTermMonths", 3),
                unit=TermUnit.MONTHS,
            ),
        )
    else:
        return Disposition(
            type=DispositionType.DEFINITE,
            label="Definite sentence as provided in the law creating the offense (max 364 days)",
            statute_refs=["PL 70.15(3)"],
            term=TermRange(min_value=0, max_value=364, unit=TermUnit.DAYS),
        )


def _resolve_primary_violation_disposition() -> Disposition:
    """Resolve the primary disposition for a violation."""
    row = reference.get_violation_table().get("allOffenders", {})
    return Disposition(
        type=DispositionType.DEFINITE,
        label=f"Definite sentence up to {row.get('maxImprisonmentDays', 15)} days",
        statute_refs=["PL 70.15(4)"],
        term=TermRange(
            min_value=0,
            max_value=row.get("maxImprisonmentDays", 15),
            unit=TermUnit.DAYS,
        ),
    )



def _subdivision_override_note(ctx: SentencingContext) -> Optional[str]:
    """When an elevated range applies to only one subdivision and the user
    didn't give a subdivision, say so instead of guessing."""
    facts = ctx.case_facts
    if facts.subdivision or facts.is_attempt:
        return None
    override = reference.get_offense_overrides().get(ctx.section, {})
    subd = override.get("subdivisionOverride")
    if subd is None or "determinateOverride" not in override:
        return None
    lo, hi = override["determinateOverride"]
    return f"If convicted under subdivision {subd}, the term is {lo}–{hi} years ({override.get('_ref', '')})"


def _years_text(n) -> str:
    return f"{n} year" if n == 1 else f"{n} years"


def _years_list_text(years: list) -> str:
    """[3, 4, 5] -> "3, 4, 5 years"; [1] -> "1 year"."""
    return f"{', '.join(str(y) for y in years)} {'year' if years == [1] else 'years'}"


def _drug_definite_sentence(statute: str) -> Disposition:
    definite = reference.get_dispositions_table().get("felony", {}).get("definiteSentence", {})
    max_months = definite.get("maxMonths", 12)
    return Disposition(
        type=DispositionType.DEFINITE,
        label=f"Definite sentence up to {max_months} months",
        statute_refs=[statute],
        term=TermRange(min_value=0, max_value=max_months, unit=TermUnit.MONTHS),
        conditions=definite.get("conditions"),
    )


def _probation_from_table() -> Disposition:
    probation = reference.get_dispositions_table().get("felony", {}).get("probation", {})
    return Disposition(
        type=DispositionType.PROBATION,
        label=f"Probation for {_years_list_text(probation['years'])}",
        statute_refs=[probation["statuteRef"]],
        probation_years=probation["years"],
        conditions=probation.get("conditions"),
    )


def _lifetime_probation(statute: str) -> Disposition:
    return Disposition(
        type=DispositionType.PROBATION,
        label="Lifetime probation",
        statute_refs=[statute],
    )


# PL 60.05(4): these class C felonies "must be sentenced to imprisonment in
# accordance with section 70.00" — no 60.01 alternatives.
_PL_60_05_4_SECTIONS = frozenset({"190.42", "200.22", "200.27", "230.30", "150.10"})
_PL_60_05_4_ATTEMPTS = frozenset({"200.04", "200.12", "105.15", "145.12", "230.32"})

# PL 60.05(5): these class D felonies "must be sentenced in accordance with
# section 70.00 or 85.00" — imprisonment (incl. a 70.00(4) definite sentence)
# or intermittent imprisonment, but no probation, split sentence or discharge.
_PL_60_05_5_SECTIONS = frozenset({"120.05", "121.12"})
_PL_60_05_5_ATTEMPTS = frozenset({"230.30"})

# PL 70.02(2)(b-1): menacing a police or peace officer — determinate only.
_PL_70_02_2_B1_SECTIONS = frozenset({"120.18"})

# PL 70.02(2)(c): determinate, or a definite sentence of no less than one year.
_PL_70_02_2_C_SECTIONS = frozenset({"265.11", "265.50"})
_PL_70_02_2_C_265_02_SUBDIVISIONS = frozenset({"5", "7", "8", "9"})


def _is_named(ctx: SentencingContext, sections: frozenset, attempts: frozenset = frozenset()) -> bool:
    """True if the conviction is one of `sections`, or an attempt of one of `attempts`."""
    facts = ctx.case_facts
    if facts.is_conspiracy:
        return False
    if facts.is_attempt:
        return facts.attempt_of_section in attempts
    return ctx.section in sections


def _is_70_02_2_c_offense(ctx: SentencingContext) -> bool:
    """PL 70.02(2)(c): 265.02(5)/(7)/(8)/(9) (completed, or attempted as a class
    E VFO), 265.11 and 265.50."""
    facts = ctx.case_facts
    target = facts.attempt_of_section if facts.is_attempt else ctx.section
    if facts.is_conspiracy:
        return False
    if target == "265.02":
        return facts.subdivision in _PL_70_02_2_C_265_02_SUBDIVISIONS
    return not facts.is_attempt and target in _PL_70_02_2_C_SECTIONS


def _first_offender_felony_alternatives(ctx: SentencingContext) -> list[Disposition]:
    """The 60.01 alternatives for a felony offender without a predicate,
    after the offense-specific limits of PL 60.05 and 70.02(2)."""
    cls = class_key(ctx.classification)
    alts = _generate_felony_alternatives(ctx.classification, ctx.case_facts)

    if ctx.vfo:
        # 70.02(2)(a): class B/C VFOs "must be a determinate sentence of
        # imprisonment" (routed there by 60.05(3)/(4)). The only carve-outs
        # are 60.05(6) (predicate offenders) and 70.02(4)(b) (armed-felony
        # plea mitigation), handled elsewhere / as ExceptionPaths.
        if cls in ("ClassB", "ClassC"):
            return []
        # 70.02(2)(b-1): menacing a police or peace officer — determinate only.
        if _is_named(ctx, _PL_70_02_2_B1_SECTIONS):
            return []
        # 70.02(2)(c): certain weapon offenses.
        if _is_70_02_2_c_offense(ctx):
            return _pl_70_02_2_c_alternatives(alts)
        # 70.02(2)(b): other class D VFOs follow the class D rules; only a
        # state-prison sentence must be determinate. Class E VFOs likewise
        # keep the class E alternatives. Fall through to 60.05(5).

    # 60.05(4): listed class C felonies — imprisonment under 70.00 only.
    if cls == "ClassC" and _is_named(ctx, _PL_60_05_4_SECTIONS, _PL_60_05_4_ATTEMPTS):
        return []

    # 60.05(5): listed class D felonies — 70.00 or 85.00 only.
    if cls == "ClassD" and _is_named(ctx, _PL_60_05_5_SECTIONS, _PL_60_05_5_ATTEMPTS):
        allowed = (DispositionType.DEFINITE, DispositionType.INTERMITTENT)
        return [d for d in alts if d.type in allowed]

    return alts


def _pl_70_02_2_c_alternatives(alts: list[Disposition]) -> list[Disposition]:
    """70.02(2)(c): a determinate sentence or a definite sentence of no less
    than one year. Under 70.02(2)(c)(i) the court may impose any other
    authorized sentence only on a defendant with no class A misdemeanor
    conviction in the five years before the offense, and only on a finding
    on the record."""
    finding = (
        "Only under PL 70.02(2)(c)(i): no class A misdemeanor conviction in the five "
        "years before the offense, and the court finds on the record that a determinate "
        "or one-year definite sentence would be unduly harsh and that this sentence is "
        "consistent with public safety and does not deprecate the seriousness of the crime"
    )
    result: list[Disposition] = []
    for d in alts:
        if d.type == DispositionType.DEFINITE:
            # A direct alternative under 70.02(2)(c), not a 70.00(4) sentence,
            # so the 70.00(4) finding does not apply.
            d.label = "Definite sentence of 1 year"
            d.statute_refs = ["PL 70.02(2)(c)"]
            d.term = TermRange(min_value=12, max_value=12, unit=TermUnit.MONTHS)
            d.conditions = None
        else:
            d.statute_refs = [*d.statute_refs, "PL 70.02(2)(c)(i)"]
            d.conditions = f"{d.conditions}; {finding}" if d.conditions else finding
        result.append(d)
    return result


def _generate_felony_alternatives(
    classification: str,
    case_facts: CaseFacts,
) -> list[Disposition]:
    """Generate alternative dispositions for a felony from the dispositions table.

    Gated by classification per statute:
      - Definite sentence (PL 70.00(4)): Class D/E felonies only. Callers
        only ask for alternatives for offenders without a predicate.
      - Intermittent (PL 85.00(2)): Class D/E felonies or non-felonies only.
      - Probation (PL 60.05(2)/65.00(1)(a)): NOT available for Class A felonies
        (60.05(2) requires imprisonment per 70.00 for Class A).

    Offense-specific limits (VFOs, PL 60.05(4)/(5)) are applied by
    _first_offender_felony_alternatives.
    """
    disp_table = reference.get_dispositions_table()
    fel = disp_table.get("felony", {})
    alternatives: list[Disposition] = []

    # Class letter for gating
    cls_letter = class_key(classification)
    is_class_de = cls_letter in ("ClassD", "ClassE")
    is_class_a = cls_letter in ("ClassA_I", "ClassA_II")

    # Definite sentence (PL 70.00(4)) — Class D/E only
    definite = fel.get("definiteSentence", {})
    if definite.get("eligible") and is_class_de:
        alternatives.append(
            Disposition(
                type=DispositionType.DEFINITE,
                label=f"Definite sentence up to {definite['maxMonths']} months",
                statute_refs=[definite["statuteRef"]],
                term=TermRange(
                    min_value=0, max_value=definite["maxMonths"], unit=TermUnit.MONTHS
                ),
                conditions=definite.get("conditions"),
            )
        )

    # Intermittent imprisonment (PL 85.00(2)) — Class D/E only
    intermittent = fel.get("intermittentImprisonment", {})
    if intermittent.get("eligible") and is_class_de:
        alternatives.append(
            Disposition(
                type=DispositionType.INTERMITTENT,
                label="Intermittent imprisonment for any term that could be imposed as a definite sentence",
                statute_refs=[intermittent["statuteRef"]],
                conditions=intermittent.get("conditions"),
            )
        )

    # Split sentence (PL 60.01(2)(d)) — NOT for Class A felonies per PL 60.01(2)
    split = fel.get("splitSentence", {})
    if split.get("eligible") and not is_class_a:
        imprisonment_months = split["imprisonmentMaxMonths"]
        if case_facts.is_dwi:
            imprisonment_months = split.get("dwiImprisonmentMaxMonths", 12)
        alternatives.append(
            Disposition(
                type=DispositionType.SPLIT,
                label=f"Split sentence — imprisonment up to {imprisonment_months} months + probation or conditional discharge",
                statute_refs=[split["statuteRef"]],
                split_imprisonment_max_months=imprisonment_months,
                split_intermittent_max_months=split.get("intermittentMaxMonths"),
                probation_years=split.get("probationYears", [3, 4, 5]),
                conditional_discharge_years=split.get("conditionalDischargeYears"),
            )
        )

    # Probation (PL 65.00) — NOT for Class A felonies per PL 60.05(2)
    probation = fel.get("probation", {})
    if probation.get("eligible") and not is_class_a:
        alternatives.append(_probation_from_table())

    # Conditional Discharge (PL 65.05) — NOT for Class A felonies per PL 60.01(2)
    cd = fel.get("conditionalDischarge", {})
    if cd.get("eligible") and not is_class_a:
        alternatives.append(
            Disposition(
                type=DispositionType.CONDITIONAL_DISCHARGE,
                label=f"Conditional discharge for {_years_text(cd['years'])}",
                statute_refs=[cd["statuteRef"]],
                conditional_discharge_years=cd["years"],
                record_statement_required=cd.get("recordStatementRequired", False),
                conditions=cd.get("conditions"),
            )
        )

    # Unconditional Discharge (PL 65.20) — NOT for Class A felonies per PL 60.01(3)
    ud = fel.get("unconditionalDischarge", {})
    if ud.get("eligible") and not is_class_a:
        alternatives.append(
            Disposition(
                type=DispositionType.UNCONDITIONAL_DISCHARGE,
                label="Unconditional discharge",
                statute_refs=[ud["statuteRef"]],
                record_statement_required=ud.get("recordStatementRequired", False),
                conditions=ud.get("conditions"),
            )
        )

    return alternatives


def _generate_misdemeanor_alternatives(
    classification: str,
    case_facts: CaseFacts,
) -> list[Disposition]:
    """Generate alternative dispositions for a misdemeanor."""
    disp_table = reference.get_dispositions_table()
    misd = disp_table.get("misdemeanor", {})

    # Pick the subclass
    if classification == "ClassA_Misdemeanor":
        sub = misd.get("classA", {})
    elif classification == "ClassB_Misdemeanor":
        sub = misd.get("classB", {})
    else:
        sub = misd.get("unclassified", {})

    alternatives: list[Disposition] = []

    # Intermittent
    intermittent = sub.get("intermittentImprisonment", {})
    if intermittent.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.INTERMITTENT,
                label="Intermittent imprisonment for any term that could be imposed as a definite sentence",
                statute_refs=[intermittent.get("statuteRef", "PL 85.00")],
                conditions=intermittent.get("conditions"),
            )
        )

    # Split sentence
    split = sub.get("splitSentence", {})
    if split.get("eligible"):
        imprisonment_days = split.get("imprisonmentMaxDays")
        imprisonment_months = split.get("imprisonmentMaxMonths")
        if case_facts.is_dwi:
            imprisonment_months = split.get("dwiImprisonmentMaxMonths", 12)
            imprisonment_days = None
        if imprisonment_days:
            alternatives.append(
                Disposition(
                    type=DispositionType.SPLIT,
                    label=f"Split sentence — imprisonment up to {imprisonment_days} days + probation or conditional discharge",
                    statute_refs=[split["statuteRef"]],
                    split_imprisonment_max_months=imprisonment_days / 30.0,
                    probation_years=split.get("probationYears", [3]),
                    conditional_discharge_years=split.get("conditionalDischargeYears"),
                )
            )
        else:
            alternatives.append(
                Disposition(
                    type=DispositionType.SPLIT,
                    label=f"Split sentence — imprisonment up to {imprisonment_months} months + probation or conditional discharge",
                    statute_refs=[split["statuteRef"]],
                    split_imprisonment_max_months=imprisonment_months,
                    probation_years=split.get("probationYears", [3]),
                    conditional_discharge_years=split.get("conditionalDischargeYears"),
                )
            )

    # Probation
    probation = sub.get("probation", {})
    if probation.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.PROBATION,
                label=f"Probation for {_years_list_text(probation['years'])}",
                statute_refs=[probation["statuteRef"]],
                probation_years=probation["years"],
                conditions=probation.get("conditions"),
            )
        )

    # Conditional Discharge
    cd = sub.get("conditionalDischarge", {})
    if cd.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.CONDITIONAL_DISCHARGE,
                label=f"Conditional discharge for {_years_text(cd['years'])}",
                statute_refs=[cd["statuteRef"]],
                conditional_discharge_years=cd["years"],
                record_statement_required=cd.get("recordStatementRequired", False),
                conditions=cd.get("conditions"),
            )
        )

    # Unconditional Discharge
    ud = sub.get("unconditionalDischarge", {})
    if ud.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.UNCONDITIONAL_DISCHARGE,
                label="Unconditional discharge",
                statute_refs=[ud.get("statuteRef", "PL 65.20(1)")],
                record_statement_required=ud.get("recordStatementRequired", False),
                conditions=ud.get("conditions"),
            )
        )

    return alternatives


def _generate_violation_alternatives() -> list[Disposition]:
    """Generate alternative dispositions for a violation."""
    disp_table = reference.get_dispositions_table()
    viol = disp_table.get("violation", {})
    alternatives: list[Disposition] = []

    cd = viol.get("conditionalDischarge", {})
    if cd.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.CONDITIONAL_DISCHARGE,
                label=f"Conditional discharge for {_years_text(cd['years'])}",
                statute_refs=[cd["statuteRef"]],
                conditional_discharge_years=cd["years"],
            )
        )

    ud = viol.get("unconditionalDischarge", {})
    if ud.get("eligible"):
        alternatives.append(
            Disposition(
                type=DispositionType.UNCONDITIONAL_DISCHARGE,
                label="Unconditional discharge",
                statute_refs=[ud.get("statuteRef", "PL 65.20(1)")],
            )
        )

    return alternatives
