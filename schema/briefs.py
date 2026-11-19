# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Brief and Decision artefacts (schema v0.2).

A Brief turns a scenario (Context + Goal) and Decide's Position into a creative brief
plus a test hypothesis. A Decision is the human gate's record. Both carry an Envelope;
a Brief's ``parent_ids`` are [Context, Goal, Decide Position].

The v0.1 value objects (:class:`Figure`, :class:`Envelope`) are reused unchanged. The
same no-bare-numbers rule holds: every quantity on an artefact is a Figure, so the only
raw numbers here are each Figure's ``value`` and the structural ``Deliverable.count``.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum

from pydantic import model_validator

from .models import Confidence, Envelope, Figure, MadeBy, _Model


class Maker(str, Enum):
    human = "human"
    ai = "ai"
    hybrid = "hybrid"


class Outcome(str, Enum):
    approve = "approve"
    edit = "edit"
    reject = "reject"


class DecisionMode(str, Enum):
    interactive = "interactive"   # a real human at a TTY went through the gate
    fixture = "fixture"           # a test fixture; never a human sign-off


class MakerRecommendation(_Model):
    """Which maker the brief commits to, citing the Decide Position it rests on."""

    maker: Maker
    position_id: str              # the cited Decide Position's envelope id
    rationale: str


class Deliverable(_Model):
    format: str
    count: int                    # a structural count, not a measured quantity
    maker: Maker


class Mandatory(_Model):
    """A must-carry item; ``id`` cites a decide/ norway_rules id or 'ai_disclosure'."""

    id: str
    text: str


class CopyLine(_Model):
    text: str
    language: str
    needs_native_review: bool


class Acknowledgement(_Model):
    """One reviewer sign-off at the gate, tied to the item's content hash."""

    item_type: str                # "assumption" | "open_question"
    item_ref: str                 # stable ref/hash of the acknowledged item
    acknowledged: bool
    note: str | None = None


class Brief(_Model):
    objective: str
    audience: str
    insight: str
    proposition: str
    maker_recommendation: MakerRecommendation
    deliverables: list[Deliverable]
    mandatories: list[Mandatory]
    tone: str
    budget: Figure
    success_measure: Figure
    hypothesis: str
    copy_lines: list[CopyLine]
    assumptions: list[Figure]
    open_questions: list[str]
    envelope: Envelope

    @model_validator(mode="after")
    def _assumptions_are_sourced_as_assumption(self) -> Brief:
        for i, fig in enumerate(self.assumptions):
            if fig.source.value != "assumption":
                raise ValueError(f"assumptions[{i}] has source={fig.source.value!r}, "
                                 "every Brief assumption must be source='assumption'")
        return self


class Decision(_Model):
    target_id: str                # the Brief's envelope id
    outcome: Outcome
    reason: str | None = None
    edits: str | None = None
    decided_by: str
    timestamp: dt.datetime
    mode: DecisionMode
    shown_hash: str               # hash of exactly what the reviewer was shown
    acknowledgements: list[Acknowledgement]
    envelope: Envelope

    @model_validator(mode="after")
    def _human_made_and_consistent(self) -> Decision:
        if self.envelope.made_by is not MadeBy.human:
            raise ValueError("a Decision must be made_by=human")
        if self.mode is DecisionMode.fixture and self.decided_by != "fixture":
            raise ValueError("a fixture-mode Decision must set decided_by='fixture'")
        if self.outcome in (Outcome.reject, Outcome.edit) and not (self.reason or "").strip():
            raise ValueError(f"outcome={self.outcome.value} requires a reason")
        return self


# Added to the generated JSON Schema set (schema/json/).
BRIEF_MODELS: tuple[type, ...] = (Brief, Decision)

__all__ = [
    "Maker", "Outcome", "DecisionMode", "MakerRecommendation", "Deliverable",
    "Mandatory", "CopyLine", "Acknowledgement", "Brief", "Decision", "BRIEF_MODELS",
]
