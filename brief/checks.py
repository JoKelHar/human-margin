# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Maker-neutral checks on a Brief.

The same rules apply whichever maker the brief commits to:
  - schema: the Brief validates.
  - no_naked_numbers: every number in a text field is backed by a Figure (inputs or
    assumptions), by value and unit. Legal mandatories are not scanned (citations/years).
  - maker_match: the maker recommendation equals Decide's stance, or the brief explains
    the divergence in open_questions; a near-boundary stance requires an open question.
  - native_review: Norwegian copy lines must be flagged needs_native_review.
  - ai_labelling: a brief with any AI or hybrid maker must carry an AI-content labelling
    mandatory (ai_disclosure or ai_act). Where the risk is lopsided, the safe option is
    the default: labelling is a default mandatory, never an open question. Dropping it is
    an explicit human opt-out recorded at the gate, not something the brief omits.
"""

from __future__ import annotations

from dataclasses import dataclass

from brief.decide_link import maker_stance
from brief.numbers import UNIT_ALIASES, _fold, unmatched
from schema import Brief, Context, Figure, Goal, Maker, Position

# Text fields checked for naked numbers. Legal mandatories are excluded by design.
_TEXT_FIELDS = ("objective", "audience", "insight", "proposition", "hypothesis", "tone")

# Mandatory ids that satisfy the AI-content labelling duty.
_LABELLING_IDS = frozenset({"ai_disclosure", "ai_act"})
# Makers whose output can pass as real and so triggers the labelling duty.
_AI_MAKERS = frozenset({Maker.ai, Maker.hybrid})


@dataclass(frozen=True)
class Finding:
    check: str
    ok: bool
    detail: str


@dataclass
class CheckReport:
    findings: list[Finding]

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings)

    def to_dict(self) -> dict:
        return {"ok": self.ok,
                "findings": [{"check": f.check, "ok": f.ok, "detail": f.detail}
                             for f in self.findings]}


def _canon_unit(unit: str) -> str:
    return UNIT_ALIASES.get(_fold(unit), unit)


def figure_pool(brief: Brief, goal: Goal, position: Position) -> list[tuple[float, str]]:
    """Every (value, canonical-unit) a brief's text may legitimately cite."""
    figs: list[Figure] = [goal.target, goal.budget, brief.budget, brief.success_measure]
    figs += list(position.figures) + list(brief.assumptions)
    return [(f.value, _canon_unit(f.unit)) for f in figs]


def _fig_by_ref(position: Position, needle: str) -> Figure | None:
    return next((f for f in position.figures if f.ref and needle in f.ref), None)


def stance_of(position: Position):
    be = _fig_by_ref(position, "break-even")
    goal = _fig_by_ref(position, "goal: target")
    return maker_stance(be.value, goal.value)


def _text_blobs(brief: Brief) -> list[tuple[str, str]]:
    blobs = [(f, getattr(brief, f)) for f in _TEXT_FIELDS]
    blobs.append(("maker_recommendation.rationale", brief.maker_recommendation.rationale))
    blobs += [(f"copy_lines[{i}]", c.text) for i, c in enumerate(brief.copy_lines)]
    blobs += [(f"open_questions[{i}]", q) for i, q in enumerate(brief.open_questions)]
    return blobs


def _check_numbers(brief: Brief, pool: list[tuple[float, str]]) -> Finding:
    offenders = []
    for field, text in _text_blobs(brief):
        for bad in unmatched(text, pool):
            offenders.append(f"{field}: {bad}")
    ok = not offenders
    detail = "every number is backed by a Figure" if ok else \
        "naked numbers (no matching Figure value+unit): " + "; ".join(offenders)
    return Finding("no_naked_numbers", ok, detail)


def _check_maker(brief: Brief, position: Position) -> Finding:
    st = stance_of(position)
    rec = brief.maker_recommendation.maker
    explained = any(k in _fold(q) for q in brief.open_questions
                    for k in ("decide", "stance", st.maker.value, "disagree", "differs"))
    if st.near_boundary and not brief.open_questions:
        return Finding("maker_match", False,
                       f"stance {st.maker.value} is within the boundary margin "
                       f"(ratio {st.ratio:.1f}%); an open question is required")
    if rec == st.maker:
        return Finding("maker_match", True, f"maker {rec.value} matches Decide's stance")
    if explained:
        return Finding("maker_match", True,
                       f"maker {rec.value} differs from Decide's {st.maker.value}, "
                       "explained in open_questions")
    return Finding("maker_match", False,
                   f"maker {rec.value} differs from Decide's stance {st.maker.value} "
                   "with no explanation in open_questions")


def _check_native_review(brief: Brief) -> Finding:
    offenders = [f"copy_lines[{i}] ({c.language})"
                 for i, c in enumerate(brief.copy_lines)
                 if _fold(c.language)[:2] in ("nb", "nn", "no") and not c.needs_native_review]
    ok = not offenders
    return Finding("native_review", ok,
                   "Norwegian copy flagged for native review" if ok else
                   "Norwegian copy not flagged needs_native_review: " + ", ".join(offenders))


def _uses_ai(brief: Brief) -> bool:
    makers = {brief.maker_recommendation.maker} | {d.maker for d in brief.deliverables}
    return bool(makers & _AI_MAKERS)


def _check_labelling(brief: Brief) -> Finding:
    if not _uses_ai(brief):
        return Finding("ai_labelling", True,
                       "no AI or hybrid maker; AI-content labelling not required")
    has = any(m.id in _LABELLING_IDS for m in brief.mandatories)
    return Finding("ai_labelling", has,
                   "AI-content labelling mandatory present" if has else
                   "brief uses AI/hybrid makers but carries no AI-content labelling "
                   "mandatory (ai_disclosure or ai_act); labelling is a default mandatory, "
                   "not an open question")


def check_brief(brief: Brief, context: Context, goal: Goal, position: Position) -> CheckReport:
    findings = [Finding("schema", True, "Brief validates against schema v0.2")]
    findings.append(_check_numbers(brief, figure_pool(brief, goal, position)))
    findings.append(_check_maker(brief, position))
    findings.append(_check_native_review(brief))
    findings.append(_check_labelling(brief))
    return CheckReport(findings)


__all__ = ["Finding", "CheckReport", "check_brief", "figure_pool", "stance_of"]
