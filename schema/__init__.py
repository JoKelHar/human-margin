# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Shared artefact contracts (v0.1): Figure, Envelope, Context, Goal, Position.

See :mod:`schema.models`. JSON Schema for each model is generated into
``schema/json/`` by :mod:`schema.generate`.
"""

from __future__ import annotations

from .briefs import (
    Acknowledgement,
    Brief,
    CopyLine,
    Decision,
    DecisionMode,
    Deliverable,
    Maker,
    Mandatory,
    MakerRecommendation,
    Outcome,
)
from .models import (
    MODELS,
    SCHEMA_VERSION,
    Confidence,
    Context,
    Envelope,
    Figure,
    Goal,
    MadeBy,
    Position,
    Source,
    Status,
)

__all__ = [
    # v0.1
    "SCHEMA_VERSION", "Source", "Confidence", "MadeBy", "Status",
    "Figure", "Envelope", "Context", "Goal", "Position", "MODELS",
    # v0.2
    "Maker", "Outcome", "DecisionMode", "MakerRecommendation", "Deliverable",
    "Mandatory", "CopyLine", "Acknowledgement", "Brief", "Decision",
]
