# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Maker-stance thresholds, stored as Figures so the gate can show their provenance.

The stance compares Decide's break-even extra sales to the campaign goal:

    ratio = break_even / goal

    ratio <= HUMAN_MAX            -> human   (<=10% of the target to break even: easy call)
    HUMAN_MAX < ratio < AI_MIN    -> hybrid
    ratio >= AI_MIN               -> ai      (>=35% of the target just to break even: not worth it)

These bounds are a judgement, not a measurement: below a tenth of the target the human
premium pays for itself easily; above a third it rarely does. They are assumptions, held
at low confidence, and reviewed at the gate. A ratio within BOUNDARY_MARGIN points of a
bound is too close to call, so the stance is held at low confidence and the brief must
raise an open question.
"""

from __future__ import annotations

import datetime as dt

from schema import Confidence, Figure, Source

AS_OF = dt.date(2026, 11, 19)


def _assumption(value: float) -> Figure:
    return Figure(value=value, unit="percent", source=Source.assumption,
                  confidence=Confidence.low, as_of=AS_OF,
                  ref="brief/config.py (owner-set stance threshold)")


# Break-even as a percent of the campaign goal.
HUMAN_MAX = _assumption(10)        # ratio <= 10%  -> human
AI_MIN = _assumption(35)           # ratio >= 35%  -> ai
BOUNDARY_MARGIN = _assumption(3)   # within 3 points of a bound -> too close to call

# Shown at the gate, in order, so the reviewer sees every threshold's provenance.
THRESHOLDS: tuple[tuple[str, Figure], ...] = (
    ("human_max", HUMAN_MAX),
    ("ai_min", AI_MIN),
    ("boundary_margin", BOUNDARY_MARGIN),
)

__all__ = ["AS_OF", "HUMAN_MAX", "AI_MIN", "BOUNDARY_MARGIN", "THRESHOLDS"]
