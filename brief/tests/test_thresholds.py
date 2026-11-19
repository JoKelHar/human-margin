# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The maker-stance thresholds are Figures (so the gate can show their provenance),
held as low-confidence assumptions, and ordered human_max < ai_min."""

from __future__ import annotations

from brief import config
from schema import Confidence, Figure, Source


def test_thresholds_are_assumption_figures_at_low_confidence():
    for name, fig in config.THRESHOLDS:
        assert isinstance(fig, Figure), name
        assert fig.unit == "percent", name
        assert fig.source is Source.assumption, name
        assert fig.confidence is Confidence.low, name
        assert fig.ref and "threshold" in fig.ref, name


def test_threshold_values_and_order():
    assert config.HUMAN_MAX.value == 10
    assert config.AI_MIN.value == 35
    assert config.BOUNDARY_MARGIN.value == 3
    assert config.HUMAN_MAX.value < config.AI_MIN.value
    # the boundary band never swallows a whole stance
    assert config.BOUNDARY_MARGIN.value * 2 < config.AI_MIN.value - config.HUMAN_MAX.value


def test_thresholds_list_covers_each_named_bound():
    names = {n for n, _ in config.THRESHOLDS}
    assert names == {"human_max", "ai_min", "boundary_margin"}
