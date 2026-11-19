# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The one bridge from Decide's figures to a maker stance and a Position.

Decide is positions-not-advice: it outputs figures (break-even extra sales, the usual
band), never a human/ai/hybrid verdict. :func:`maker_stance` derives that verdict here,
in brief/, from the break-even as a share of the goal and the thresholds in
:mod:`brief.config` -- so decide/ stays non-prescriptive. :func:`position_from` maps a
Decide run onto a :class:`schema.Position` with a deterministic envelope, so the
committed scenario Positions regenerate byte-for-byte.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from brief.config import AI_MIN, BOUNDARY_MARGIN, HUMAN_MAX
from decide.compute import Inputs, compute, formats
from schema import (
    Confidence,
    Envelope,
    Figure,
    Maker,
    MadeBy,
    Position,
    Source,
    Status,
)

AS_OF = dt.date(2026, 11, 19)


@dataclass(frozen=True)
class Stance:
    maker: Maker
    ratio: float            # break_even / goal, as a percent
    confidence: Confidence  # low when the ratio is too close to a threshold to call
    near_boundary: bool     # within BOUNDARY_MARGIN points of a threshold


def maker_stance(break_even: float, goal: float) -> Stance:
    """Decide's figures -> a maker verdict, by the thresholds in brief.config."""
    human_max, ai_min, margin = HUMAN_MAX.value, AI_MIN.value, BOUNDARY_MARGIN.value
    ratio = break_even / goal * 100
    if ratio <= human_max:
        maker = Maker.human
    elif ratio >= ai_min:
        maker = Maker.ai
    else:
        maker = Maker.hybrid
    near = min(abs(ratio - human_max), abs(ratio - ai_min)) <= margin
    return Stance(maker=maker, ratio=ratio,
                  confidence=Confidence.low if near else Confidence.high, near_boundary=near)


def run_decide(decide_inputs: dict) -> dict:
    """Run Decide on a scenario's inputs. Pure Decide; no maths added here."""
    return compute(Inputs(**decide_inputs))


def break_even_of(decide_output: dict) -> int:
    return int(str(decide_output["a2"]["big"]).replace(" ", "").replace(" ", ""))


def _fig(value: float, unit: str, ref: str) -> Figure:
    # Decide's scenario figures are synthetic placeholders: assumptions, low confidence.
    return Figure(value=float(value), unit=unit, source=Source.assumption,
                  confidence=Confidence.low, as_of=AS_OF, ref=ref)


def position_from(slug: str, decide_inputs: dict, parent_ids: list[str]) -> Position:
    """Map a Decide run onto a Position with a deterministic envelope id ``{slug}-pos``.

    Every number Decide produced for the scenario becomes a Figure, so the Position
    carries no bare numbers and the brief's no-naked-numbers check can trace each one.
    """
    r = run_decide(decide_inputs)
    one, many = r["unit_one"], r["unit_many"]
    goal = decide_inputs["goal"]
    be = break_even_of(r)
    stance = maker_stance(be, goal)
    band = {f["key"]: f for f in formats()}[decide_inputs["fmt"]]["human"]

    figures = [
        _fig(r["human_eff"], "NOK", "decide: human production quote"),
        _fig(r["ai_eff"], "NOK", "decide: ai version cost"),
        _fig(r["value_per"], "NOK", f"decide: value per {one}"),
        _fig(be, many, "decide: human-margin break-even (a2)"),
        _fig(goal, many, "goal: target sales"),
        _fig(band["low"], "NOK", "decide: usual band low (a3)"),
        _fig(band["high"], "NOK", "decide: usual band high (a3)"),
        _fig(round(stance.ratio, 1), "percent", "break-even as a share of the goal"),
    ]
    return Position(
        claim=r["a2"]["text"],
        figures=figures,
        confidence=Confidence.low,
        what_would_change_it=("real campaign data for this brand -- the account's own "
                              "conversion rate, CPM and client prices -- replacing the "
                              "assumed ranges"),
        envelope=Envelope(id=f"{slug}-pos", schema_version="0.1",
                          parent_ids=list(parent_ids), made_by=MadeBy.agent,
                          status=Status.draft),
    )


__all__ = ["Stance", "maker_stance", "run_decide", "break_even_of", "position_from", "AS_OF"]
