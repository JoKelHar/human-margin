# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Content formats + production-cost matrix: loading, validation, expert slots."""

from __future__ import annotations

import pytest

from mediekjop.planner.formats import (
    APPROACHES,
    FormatError,
    Tri,
    baseline_format,
    load_costs,
    load_formats,
    unfilled_cost_slots,
)


def test_formats_load_and_baseline_is_defined():
    fmts = load_formats()
    assert fmts, "expected at least one format"
    base = baseline_format()
    assert base in fmts
    # the baseline's multipliers are 1.0 by construction
    b = fmts[base]
    assert (b.ctr_mult.point, b.cvr_mult.point) == (1.0, 1.0)
    for f in fmts.values():
        assert all(a in APPROACHES for a in f.approaches)


def test_cost_matrix_is_keyed_by_format_and_approach():
    costs = load_costs()
    assert ("ugc_talking_head", "human_led") in costs
    for (fmt, approach), cell in costs.items():
        assert cell.nok.low <= cell.nok.point <= cell.nok.high


def test_unfilled_expert_slots_are_flagged():
    slots = unfilled_cost_slots()
    assert slots, "the owner's commercial day-rate cells are expert slots to fill"
    assert all(c.tier == "expert_estimate" and not c.filled for c in slots)


def test_tri_rejects_unordered_range():
    with pytest.raises(FormatError):
        Tri(low=5.0, point=1.0, high=10.0)
