"""Markdown sentencing-options memorandum renderer.

Takes a SentencingOutput and emits a public-facing report that reads as
declarative prosecutorial work product — state what the engine routed to,
not what the doctrine is. Every number carries its statutory cite so the
reader can verify against the statute book in one pass.

Run indirectly via sentencing_ui.py (or call render_report directly).
"""

from __future__ import annotations

from crimetime.models import (
    Disposition,
    DispositionType,
    ExceptionPath,
    ModifierApplied,
    SentencingOutput,
    TermUnit,
)
from crimetime.reference import get_all_offenses


# ---------------------------------------------------------------------------
# Term / amount formatting
# ---------------------------------------------------------------------------


def _format_term(term) -> str:
    if term is None:
        return "—"
    unit = term.unit.value if hasattr(term.unit, "value") else str(term.unit)
    if term.max_value >= 999:
        return f"{term.min_value} {unit} to life"
    if term.min_value == term.max_value:
        return f"{term.min_value} {unit}"
    return f"{term.min_value}–{term.max_value} {unit}"


def _format_amount(amount: float | None) -> str:
    if amount is None:
        return "—"
    return f"${amount:,.0f}"


def _join_refs(refs: list[str]) -> str:
    return ", ".join(refs) if refs else "—"


# ---------------------------------------------------------------------------
# Per-type prose scaffolding (deterministic, not educational)
# ---------------------------------------------------------------------------


_DISPOSITION_TYPE_LABEL = {
    DispositionType.DETERMINATE: "Determinate sentence",
    DispositionType.INDETERMINATE: "Indeterminate sentence",
    DispositionType.DEFINITE: "Definite sentence",
    DispositionType.INTERMITTENT: "Intermittent imprisonment",
    DispositionType.SPLIT: "Split sentence",
    DispositionType.PROBATION: "Probation",
    DispositionType.CONDITIONAL_DISCHARGE: "Conditional discharge",
    DispositionType.UNCONDITIONAL_DISCHARGE: "Unconditional discharge",
    DispositionType.FINE: "Fine",
    DispositionType.LIFE_WITHOUT_PAROLE: "Life without parole",
}


_MODIFIER_LABEL = {
    "hate_crime": "Hate crime modifier",
    "terrorism": "Terrorism modifier",
    "sexually_motivated_felony": "Sexually motivated felony redesignation",
}


_EXCEPTION_LABEL = {
    "armed_felony_override": "Armed felony override",
    "domestic_violence_indeterminate": "Domestic violence alternative",
    "dwi_split_sentence_variant": "DWI sentence variant",
    "record_statement_required": "Record statement required",
    "for_hire_enhancement": "For-hire vehicle enhancement",
}


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_offense(out: SentencingOutput, article: int | str) -> str:
    lines = [f"## 1. Offense", ""]
    lines.append(
        f"**§{out.section} — {out.offense_name}**  \n"
        f"Article {article} · {out.classification}"
    )
    return "\n".join(lines) + "\n\n"


def _render_modifier_line(m: ModifierApplied) -> str:
    label = _MODIFIER_LABEL.get(m.modifier_type, m.modifier_type.replace("_", " ").title())
    branch = f" ({m.branch})" if m.branch else ""
    return (
        f"- {label}{branch}: "
        f"`{m.base_classification}` → `{m.resulting_classification}`"
    )


def _render_exception_line(e: ExceptionPath) -> str:
    label = _EXCEPTION_LABEL.get(e.type.value, e.label)
    refs = f" ({_join_refs(e.statute_refs)})" if e.statute_refs else ""
    triggers = ""
    if e.triggering_factors:
        triggers = f" — triggers: {', '.join(e.triggering_factors)}"
    parts = [f"- {label}{refs}{triggers}"]
    if e.resulting_disposition:
        parts.append(f"  - Resulting: {e.resulting_disposition.label}")
    return "\n".join(parts)


def _render_classification_route(out: SentencingOutput) -> str:
    lines = ["## 2. Classification & Sentencing Route", ""]

    has_modifiers = bool(out.modifiers_applied)
    has_exceptions = bool(out.exception_paths)

    if not has_modifiers and not has_exceptions:
        lines.append(
            f"Classified as `{out.classification}`. "
            f"No modifiers or exceptions applied."
        )
        lines.append("")
    else:
        if has_modifiers:
            lines.append("**Modifiers applied:**")
            for m in out.modifiers_applied:
                lines.append(_render_modifier_line(m))
            lines.append("")
        if has_exceptions:
            lines.append("**Exception paths triggered:**")
            for e in out.exception_paths:
                lines.append(_render_exception_line(e))
            lines.append("")

    lines.append(
        f"**Final classification:** `{out.classification}`  \n"
        f"**Violent felony offense:** {'Yes' if out.is_vfo else 'No'}"
    )
    return "\n".join(lines) + "\n\n"


def _render_disposition_block(d: Disposition, is_primary: bool) -> str:
    dtype_label = _DISPOSITION_TYPE_LABEL.get(d.type, d.type.value)
    prefix = "**Recommended**" if is_primary else "Alternative"
    lines = [f"{prefix} · {dtype_label} — {d.label}"]

    if d.term:
        lines.append(f"- Term: `{_format_term(d.term)}`")
    if d.prs:
        lines.append(f"- Post-release supervision: `{d.prs.min_years}–{d.prs.max_years} years`")
    if d.probation_years:
        lines.append(f"- Probation years: `{d.probation_years}`")
    if d.conditional_discharge_years is not None:
        lines.append(f"- Conditional discharge (years): `{d.conditional_discharge_years}`")
    if d.split_imprisonment_max_months is not None:
        lines.append(f"- Split imprisonment max (months): `{d.split_imprisonment_max_months}`")
    if d.fine_max_amount is not None:
        gain_note = " · alt double gain" if d.fine_alt_double_gain else ""
        lines.append(f"- Fine max: `{_format_amount(d.fine_max_amount)}`{gain_note}")
    if d.record_statement_required:
        lines.append("- Record statement required: `yes`")
    if d.conditions:
        lines.append(f"- Conditions: {d.conditions}")
    if d.statute_refs:
        lines.append(f"- Authority: {_join_refs(d.statute_refs)}")

    return "\n".join(lines)


def _render_dispositions(out: SentencingOutput) -> str:
    if not out.available_dispositions:
        return ""
    lines = ["## 3. Recommended Disposition", ""]
    primary = out.available_dispositions[0]
    lines.append(_render_disposition_block(primary, is_primary=True))
    lines.append("")

    alternatives = out.available_dispositions[1:]
    if alternatives:
        lines.append("## 4. Alternative Dispositions")
        lines.append("")
        for d in alternatives:
            lines.append(_render_disposition_block(d, is_primary=False))
            lines.append("")

    return "\n".join(lines)


def _render_financials(out: SentencingOutput) -> str:
    if not out.financial_obligations:
        return ""
    lines = ["## 5. Mandatory Financial Obligations", ""]
    lines.append("Upon conviction, the following financial obligations attach:")
    lines.append("")
    lines.append("| Type | Label | Amount | Authority | Conditions |")
    lines.append("|---|---|---|---|---|")
    for f in out.financial_obligations:
        lines.append(
            f"| {f.type.value} | {f.label} | {_format_amount(f.amount)} | "
            f"{_join_refs(f.statute_refs)} | {f.conditions or ''} |"
        )
    return "\n".join(lines) + "\n\n"


def _render_collateral(out: SentencingOutput) -> str:
    if not out.collateral_requirements:
        return ""
    lines = ["## 6. Collateral Requirements", ""]
    for c in out.collateral_requirements:
        refs = f" ({_join_refs(c.statute_refs)})" if c.statute_refs else ""
        lines.append(f"- **{c.label}**{refs}")
        lines.append(f"  - {c.description}")
    return "\n".join(lines) + "\n\n"


def _render_statutory_index(out: SentencingOutput) -> str:
    cites: set[str] = set()
    for d in out.available_dispositions:
        cites.update(d.statute_refs)
        if d.prs:
            cites.update(d.prs.statute_refs)
    for e in out.exception_paths:
        cites.update(e.statute_refs)
        if e.resulting_disposition:
            cites.update(e.resulting_disposition.statute_refs)
    for f in out.financial_obligations:
        cites.update(f.statute_refs)
    for c in out.collateral_requirements:
        cites.update(c.statute_refs)

    if not cites:
        return ""

    def _sort_key(ref: str) -> tuple:
        prefix = ref.replace("PL ", "").replace("CPL ", "").strip()
        parts = prefix.split("(")[0].split(".")
        try:
            return (0, int(parts[0]), int(parts[1]) if len(parts) > 1 else 0, ref)
        except ValueError:
            return (1, 0, 0, ref)

    sorted_cites = sorted(cites, key=_sort_key)
    lines = ["## 7. Statutory Index", ""]
    lines.append("Deduplicated statutory authority referenced above:")
    lines.append("")
    for ref in sorted_cites:
        lines.append(f"- {ref}")
    return "\n".join(lines) + "\n\n"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_report(out: SentencingOutput) -> str:
    """Render a SentencingOutput as a markdown sentencing-options memorandum."""
    offense = get_all_offenses().get(out.section, {})
    article = offense.get("article", "?")

    sections: list[str] = [
        "# Sentencing Options Memorandum",
        "",
        f"§{out.section} — {out.offense_name}",
        "",
        "---",
        "",
        _render_offense(out, article),
        _render_classification_route(out),
    ]

    dispositions_md = _render_dispositions(out)
    if dispositions_md:
        sections.append(dispositions_md)

    sections.append(_render_financials(out))
    sections.append(_render_collateral(out))
    sections.append(_render_statutory_index(out))

    # Renumber sections sequentially so gaps don't appear when a section
    # (e.g. "Alternative Dispositions") is absent.
    raw = "\n".join(sections)
    numbered: list[str] = []
    counter = 0
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and stripped[3].isdigit() and stripped[4] == ".":
            counter += 1
            title = stripped.split(".", 1)[1].strip()
            numbered.append(f"## {counter}. {title}")
        else:
            numbered.append(line)
    return "\n".join(numbered).rstrip() + "\n"
