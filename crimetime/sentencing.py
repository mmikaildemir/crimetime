"""The sentencing decision engine.

resolve(section, case_facts) -> SentencingOutput

The engine is a fixed pipeline of named stages over a SentencingContext:

  1. classify                 offense classification, attempt (PL 110.05) and
                              offense-intrinsic conditional classification
  2. classification modifiers SMF (130.91) -> hate crime (485.10) ->
                              terrorism (490.25), driven by the
                              classificationModifiers table
  3. track + offender status  which Article 70 scheme governs, and the status
                              it assigns from the predicate facts
                              (crimetime/tracks.py)
  4. dispositions             primary (+ PRS) and alternatives from the track
  5. adjustments              post-disposition changes, in ADJUSTMENTS order
  6. exceptions, financial obligations, collateral requirements

Every stage appends TraceStep records, so the output explains itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from . import reference
from .exceptions import generate_all_exceptions
from .financial import generate_all_financial, generate_collateral_requirements
from .models import (
    CaseFacts,
    Disposition,
    DispositionType,
    ModifierApplied,
    OffenderStatus,
    PriorRecord,
    SentencingOutput,
    TermRange,
    TermUnit,
    TraceStep,
)
from .resolvers import (
    is_felony,
    is_for_hire_eligible,
    is_vfo,
    resolve_attempt_classification,
    resolve_vfo_of_attempt,
)
from .tracks import Track, select_track


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class SentencingContext:
    """Mutable state threaded through the pipeline stages."""

    section: str
    offense: dict
    case_facts: CaseFacts
    classification: str = ""
    vfo: bool = False
    modifiers_applied: list[ModifierApplied] = field(default_factory=list)
    track: Optional[Track] = None
    status: Optional[OffenderStatus] = None
    dispositions: list[Disposition] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)

    @property
    def prior(self) -> PriorRecord:
        return self.case_facts.prior_record

    def note(self, stage: str, detail: str, *statute_refs: str) -> None:
        self.trace.append(TraceStep(stage=stage, detail=detail, statute_refs=list(statute_refs)))

    def modifier(self, modifier_type: str) -> Optional[ModifierApplied]:
        return next((m for m in self.modifiers_applied if m.modifier_type == modifier_type), None)


# ---------------------------------------------------------------------------
# Stage 1: classify
# ---------------------------------------------------------------------------


def _resolve_conditional_classification(
    conditional: dict, case_facts: CaseFacts
) -> str:
    """Resolve conditional classification rules from an offense's conditionalClassification block.

    Supports conditions: "in" (field value in list), "true" (field is truthy), "gt" (field > value)
    Falls back to conditional["fallback"] if no rule matches.
    """
    for rule in conditional.get("rules", []):
        field_name = rule["field"]
        condition = rule.get("condition", "in")
        field_value = getattr(case_facts, field_name, None)

        if condition == "in":
            if field_value in rule.get("values", []):
                return rule["resulting_classification"]
        elif condition == "true":
            if field_value:
                return rule["resulting_classification"]
        elif condition == "gt":
            threshold = rule.get("values", [0])[0]
            if field_value is not None and field_value > threshold:
                return rule["resulting_classification"]

    return conditional.get("fallback", "Violation")


def _classify(ctx: SentencingContext) -> None:
    facts = ctx.case_facts
    ctx.classification = ctx.offense["classification"]
    ctx.vfo = is_vfo(ctx.section, ctx.classification)
    ctx.note("classify", f"Offense classification {ctx.classification}")

    if facts.is_attempt and facts.attempt_of_section:
        target = reference.get_offense(facts.attempt_of_section)
        target_classification = target["classification"] if target else "Unknown"
        ctx.classification = resolve_attempt_classification(
            facts.attempt_of_section, target_classification, facts.subdivision
        )
        ctx.vfo, _ = resolve_vfo_of_attempt(facts.attempt_of_section, target_classification)
        ctx.note("classify", f"Attempt of §{facts.attempt_of_section} → {ctx.classification}", "PL 110.05")

    # Offense-intrinsic escalation, e.g. §130.86 luring a child: E→C/D by
    # intended offense class; §225.90: A misdemeanor→E felony with a prior.
    conditional = ctx.offense.get("conditionalClassification")
    if conditional:
        ctx.classification = _resolve_conditional_classification(conditional, facts)
        ctx.vfo = is_vfo(ctx.section, ctx.classification)
        ctx.note("classify", f"Conditional classification → {ctx.classification}")


# ---------------------------------------------------------------------------
# Stage 2: classification modifiers (data-driven)
# ---------------------------------------------------------------------------


def _apply_classification_modifiers(ctx: SentencingContext) -> None:
    """Apply the classificationModifiers ladders in their declared order.

    Each modifier sees the classification produced by the previous one. A
    modifier fires when its case fact is set, the section is on its
    eligibility list (and the offense is a felony, if felonyOnly), and one of
    its branches maps the current classification.
    """
    config = reference.get_classification_modifiers()
    for modifier_type in config["order"]:
        mod = config[modifier_type]
        if not getattr(ctx.case_facts, mod["factField"]):
            continue
        if not reference.is_listed(mod["eligibilityList"], ctx.section):
            continue
        if mod.get("felonyOnly") and not is_felony(ctx.classification):
            continue
        branch = next((b for b in mod["branches"] if ctx.classification in b["map"]), None)
        if branch is None:
            continue

        before = ctx.classification
        ctx.classification = branch["map"][before]
        effect = branch["vfo"]
        if effect == "deem":
            ctx.vfo = True
        elif effect == "undeem":
            ctx.vfo = False
        elif effect == "derive":
            ctx.vfo = is_vfo(ctx.section, ctx.classification)

        ctx.modifiers_applied.append(ModifierApplied(
            modifier_type=modifier_type,
            branch=branch["name"],
            base_classification=before,
            resulting_classification=ctx.classification,
        ))
        ctx.note("modifier", f"{modifier_type} ({branch['name']}): {before} → {ctx.classification}", mod["statute"])


# ---------------------------------------------------------------------------
# Stages 3-4: track, offender status, dispositions
# ---------------------------------------------------------------------------


def _sentence_on_track(ctx: SentencingContext) -> None:
    ctx.track = select_track(ctx)
    ctx.note("track", f"Sentencing track: {ctx.track.name}")

    ctx.status = ctx.track.derive_status(ctx)
    ctx.note(
        "offender_status",
        f"{ctx.track.status_label(ctx.status)} (predicate felonies: "
        f"{ctx.prior.predicate_felonies}, of which violent: {ctx.prior.predicate_vfos})",
    )

    primary, prs = ctx.track.primary(ctx, ctx.status)
    if prs:
        primary.prs = prs
    ctx.dispositions = [primary, *ctx.track.alternatives(ctx)]


# ---------------------------------------------------------------------------
# Stage 5: post-disposition adjustments
# ---------------------------------------------------------------------------
# Each adjuster edits ctx.dispositions in place and returns a trace detail if
# it changed anything. They run in ADJUSTMENTS order.


def _hate_floor_statute(ctx: SentencingContext) -> Optional[str]:
    """Which 485.10(3) floor applies, keyed by the governing Article 70 section.

    LEGACY-PARITY: keyed on the offense's VFO flag and the raw predicate
    counts, as the old status selector did, not on the derived status.
    """
    prior = ctx.prior
    if ctx.vfo and prior.predicate_felonies == 0:
        return "70.02"
    if ctx.vfo and prior.predicate_vfos == 1:
        return "70.04"
    if not ctx.vfo and prior.predicate_felonies == 0:
        return "70.00"
    if not ctx.vfo and prior.predicate_felonies == 1 and prior.predicate_vfos == 0:
        return "70.06"
    # 70.05 (juvenile offender): §485.10(3)(d) sets a 4-year max floor — not yet applied.
    # 70.08: §485.10(3) lists no floor; the 70.08 minimums already exceed them.
    return None


def _raise_primary_min(ctx: SentencingContext, floor: float) -> None:
    primary = ctx.dispositions[0]
    if primary.term:
        primary.term = TermRange(
            min_value=max(primary.term.min_value, floor),
            max_value=primary.term.max_value,
            unit=primary.term.unit,
        )


def _adjust_hate_crime_floors(ctx: SentencingContext) -> Optional[str]:
    """§485.10(3)/(4) minimum floors for the ClassB and ClassA_I hate-crime branches."""
    hate = ctx.modifier("hate_crime")
    if not hate or hate.branch not in ("ClassB", "ClassA_I") or not ctx.dispositions:
        return None
    bump_table = reference.get_hatecrime_bump_table()

    if hate.branch == "ClassB":
        statute = _hate_floor_statute(ctx)
        floor = bump_table.get("ClassB", {}).get("floors", {}).get(statute or "", {})
        value = floor.get("termMin", floor.get("maxTermMin"))
        if value is None:
            return None
        _raise_primary_min(ctx, value)
        return f"Hate crime Class B floor ({statute}): at least {value} years"

    min_period = bump_table.get("ClassA_I", {}).get("minPeriod", 20)
    _raise_primary_min(ctx, min_period)
    return f"Hate crime Class A-I minimum period: at least {min_period} years"


def _adjust_terrorism_lwop(ctx: SentencingContext) -> Optional[str]:
    """§490.25(2)(d): terrorism with a Class A-I specified offense → life
    without parole, replacing every other disposition."""
    terrorism = ctx.modifier("terrorism")
    if not terrorism or terrorism.branch != "life_without_parole":
        return None
    ctx.dispositions = [Disposition(
        type=DispositionType.LIFE_WITHOUT_PAROLE,
        label="Life imprisonment without parole",
        statute_refs=["PL 490.25(2)(d)"],
        conditions="Terrorism with Class A-I specified offense — sentence shall be life without parole",
    )]
    return "Terrorism Class A-I: life without parole"


def _adjust_offense_overrides(ctx: SentencingContext) -> Optional[str]:
    """Offense-specific overrides (PL 70.00(3)(a)), e.g. §125.27 20-25yr
    minimum, §125.26 life without parole; attempt-specific overrides
    (70.00(3)(a)(i)(C)) are keyed "attempt_<section>". Terrorism LWOP wins."""
    terrorism = ctx.modifier("terrorism")
    if terrorism and terrorism.branch == "life_without_parole":
        return None
    facts = ctx.case_facts
    overrides = reference.get_offense_overrides()
    override = overrides.get(ctx.section)
    if not override and facts.is_attempt and facts.attempt_of_section:
        override = overrides.get(f"attempt_{facts.attempt_of_section}")
    if not override:
        return None

    subd_override = None
    if facts.subdivision and "subdivisions" in override:
        subd_override = override["subdivisions"].get(facts.subdivision)
    effective = subd_override or override

    if effective.get("lifeWithoutParole"):
        ctx.dispositions = [Disposition(
            type=DispositionType.LIFE_WITHOUT_PAROLE,
            label="Life imprisonment without parole",
            statute_refs=[effective.get("_ref", "PL 70.00(3)(a)")],
            conditions=f"Offense-specific override for §{ctx.section}" + (f" subd {facts.subdivision}" if facts.subdivision else ""),
        )]
        return f"Offense-specific override for §{ctx.section}: life without parole"
    if "minYears" in effective and ctx.dispositions:
        min_override = effective["minYears"]
        primary = ctx.dispositions[0]
        if primary.term:
            primary.term = TermRange(
                min_value=max(primary.term.min_value, min_override[0]),
                max_value=max(primary.term.max_value, min_override[1]),
                unit=primary.term.unit,
            )
        return f"Offense-specific override for §{ctx.section}: minimum {min_override[0]}–{min_override[1]} years"
    return None


def _adjust_for_hire(ctx: SentencingContext) -> Optional[str]:
    """PL 60.07(1): victim operating a for-hire vehicle and a 60.07(2)(a)
    specified offense → the minimum term is 3-5 years greater; max unchanged.

    A minimum-term adjustment, not a classification modifier, so it stacks
    with the hate-crime/terrorism outcomes. We represent the enhanced floor
    (old min + 3). The court's discretion to decline is an ExceptionPath.
    """
    facts = ctx.case_facts
    if not facts.victim_is_for_hire_operator:
        return None
    if not is_for_hire_eligible(
        ctx.section, is_attempt=facts.is_attempt, attempt_of_section=facts.attempt_of_section
    ):
        return None
    if not ctx.dispositions:
        return None
    primary = ctx.dispositions[0]
    if not primary.term or primary.term.unit != TermUnit.YEARS:
        return None

    primary.term = TermRange(
        min_value=primary.term.min_value + 3,
        max_value=primary.term.max_value,
        unit=primary.term.unit,
    )
    primary.label = f"{primary.label} (for-hire enhancement applied: min +3-5 yr per PL 60.07)"
    primary.statute_refs = list(primary.statute_refs) + ["PL 60.07"]
    return "For-hire vehicle enhancement: minimum +3 years"


# Order matters: floors before LWOP replacement, overrides after both, and
# for-hire last because it adds to the final minimum.
ADJUSTMENTS: list[tuple[Callable[[SentencingContext], Optional[str]], str]] = [
    (_adjust_hate_crime_floors, "PL 485.10(3)-(4)"),
    (_adjust_terrorism_lwop, "PL 490.25(2)(d)"),
    (_adjust_offense_overrides, "PL 70.00(3)(a)"),
    (_adjust_for_hire, "PL 60.07"),
]


def _apply_adjustments(ctx: SentencingContext) -> None:
    for adjust, statute in ADJUSTMENTS:
        detail = adjust(ctx)
        if detail:
            ctx.note("adjustment", detail, statute)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _estimated_jail_term_days(dispositions: list[Disposition]) -> Optional[float]:
    """Jail term used for the surcharge-summons collateral (last term wins)."""
    jail_term_days = None
    for d in dispositions:
        if d.term and d.term.unit == TermUnit.DAYS:
            jail_term_days = d.term.max_value
        elif d.term and d.term.unit == TermUnit.MONTHS:
            jail_term_days = d.term.max_value * 30
        elif d.term and d.term.unit == TermUnit.YEARS:
            jail_term_days = d.term.max_value * 365
    return jail_term_days


def resolve(section: str, case_facts: CaseFacts) -> SentencingOutput:
    """Resolve the full sentencing output for an offense given case facts.

    Args:
        section: NYS Penal Law section number (e.g. '120.02')
        case_facts: CaseFacts instance with the case-specific parameters

    Returns:
        SentencingOutput with all available dispositions, exceptions,
        financial obligations, collateral requirements, and a decision trace.
    """
    offense = reference.get_offense(section)
    if offense is None:
        raise ValueError(f"Unknown offense section: {section}")

    ctx = SentencingContext(section=section, offense=offense, case_facts=case_facts)
    _classify(ctx)
    base_classification = ctx.classification
    _apply_classification_modifiers(ctx)
    _sentence_on_track(ctx)
    _apply_adjustments(ctx)

    return SentencingOutput(
        section=section,
        offense_name=offense.get("name", section),
        classification=ctx.classification,
        is_vfo=ctx.vfo,
        available_dispositions=ctx.dispositions,
        exception_paths=generate_all_exceptions(ctx.classification, ctx.vfo, case_facts),
        financial_obligations=generate_all_financial(
            ctx.classification,
            victim_seeking_restitution=case_facts.victim_seeking_restitution,
            section=section,
        ),
        collateral_requirements=generate_collateral_requirements(
            ctx.classification, jail_term_days=_estimated_jail_term_days(ctx.dispositions)
        ),
        base_classification=base_classification if ctx.modifiers_applied else None,
        modifiers_applied=ctx.modifiers_applied,
        sentencing_track=ctx.track.name,
        offender_status=ctx.status,
        offender_status_label=ctx.track.status_label(ctx.status),
        trace=ctx.trace,
    )
