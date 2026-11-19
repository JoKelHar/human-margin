# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Shared artefact contracts (v0.1).

Five Pydantic models the agents pass between each other. Two are value objects --
:class:`Figure` (a single number with its provenance) and :class:`Envelope` (the
version/lineage/status wrapper). Three are artefacts -- :class:`Context`,
:class:`Goal` and :class:`Position` -- and every artefact carries an ``envelope``.

No bare numbers: on an artefact, every numeric quantity is a :class:`Figure`, so the
only raw number in the whole tree is ``Figure.value``. That keeps each number tied to
its unit, source and as-of date wherever it travels.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "0.1"


class Source(str, Enum):
    """Where a figure came from, best (own) to weakest (assumption)."""

    own = "own"
    pooled = "pooled"
    public = "public"
    assumption = "assumption"


class Confidence(str, Enum):
    low = "low"
    med = "med"
    high = "high"


class MadeBy(str, Enum):
    agent = "agent"
    human = "human"


class Status(str, Enum):
    draft = "draft"
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"


class _Model(BaseModel):
    # Reject unknown fields: a stray key is a contract mismatch, not silent data.
    model_config = ConfigDict(extra="forbid")


class Figure(_Model):
    """A single number with its provenance. The one place a raw number may live."""

    value: float
    unit: str
    source: Source
    ref: str | None = None
    confidence: Confidence
    as_of: dt.date


class Envelope(_Model):
    """Version, lineage and review status carried by every artefact."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    schema_version: str = SCHEMA_VERSION
    parent_ids: list[str] = Field(default_factory=list)
    made_by: MadeBy
    status: Status = Status.draft


class Context(_Model):
    """The brief's setting: who it is for and the ground rules."""

    brand: str                     # synthetic until a real brand is linked
    market: str = "NO"
    language: str
    category: str
    legal_flags: list[str] = Field(default_factory=list)
    envelope: Envelope


class Goal(_Model):
    """What the work is trying to move, and the room it has to do it."""

    objective: str
    kpi: str
    target: Figure
    budget: Figure
    horizon: str
    envelope: Envelope


class Position(_Model):
    """A claim backed by figures, with the one thing that would change it."""

    claim: str
    figures: list[Figure] = Field(default_factory=list)
    confidence: Confidence
    what_would_change_it: str
    envelope: Envelope


# The artefacts whose JSON Schema ships in schema/json/ (in dependency order).
MODELS: tuple[type[BaseModel], ...] = (Figure, Envelope, Context, Goal, Position)

__all__ = [
    "SCHEMA_VERSION", "Source", "Confidence", "MadeBy", "Status",
    "Figure", "Envelope", "Context", "Goal", "Position", "MODELS",
]
