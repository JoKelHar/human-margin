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
    drafted_cost_slots,
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


def test_drafted_cost_slots_are_flagged_separately_from_empty_ones():
    drafts = drafted_cost_slots()
    # The commercial human/hybrid cells carry an owner-adjusted drafted band, still
    # tier assumption and awaiting promotion to expert_estimate.
    keys = {(c.fmt, c.approach) for c in drafts}
    assert keys == {
        ("static_image", "human_led"), ("short_video", "human_led"),
        ("short_video", "ai_assisted"), ("ugc_talking_head", "human_led"),
        ("studio_shoot", "human_led"),
    }
    for c in drafts:
        assert c.tier == "assumption" and not c.filled          # never dressed up as sourced
        assert "draft" in c.source.lower()
    # No bare expert slot is left empty once drafted.
    assert unfilled_cost_slots() == []


def test_drafted_bands_match_the_owner_adjusted_values():
    by_key = {(c.fmt, c.approach): c for c in drafted_cost_slots()}
    assert (lambda c: (c.nok.low, c.nok.point, c.nok.high))(
        by_key[("studio_shoot", "human_led")]) == (20000, 60000, 150000)
    assert (lambda c: (c.nok.low, c.nok.point, c.nok.high))(
        by_key[("ugc_talking_head", "human_led")]) == (2000, 3600, 8000)
    # Every owner-adjusted draft carries the owner's source marker.
    for c in drafted_cost_slots():
        assert c.source == "Owner-adjusted Claude draft, 2026-11"


def test_tri_rejects_unordered_range():
    with pytest.raises(FormatError):
        Tri(low=5.0, point=1.0, high=10.0)
