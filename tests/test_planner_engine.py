# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Decision engine: funnel, format/cost effects, break-even, memory-brand, seed.

These use controlled in-memory benchmarks so the arithmetic is checkable, plus
the real formats.yaml / weights.yaml (the engine loads those from disk).
"""

from __future__ import annotations

import datetime as dt

import pytest

from mediekjop.planner import load_weights, scenario_from_dict
from mediekjop.planner.currency import FxRates
from mediekjop.planner.engine import plan

FX = FxRates(rates={"NOK": 1.0, "EUR": 11.7, "USD": 10.8, "GBP": 13.6},
             as_of=dt.date(2026, 1, 1), is_fallback=True)
WEIGHTS = load_weights()


def _bench(response=1.0, memory=1.18):
    """Minimal NO benchmark set so relevance is high and nothing is widened."""
    def row(metric, value, unit, **extra):
        return {"metric": metric, "industry": "any", "price_band": "any", "channel": "any",
                "geography": "NO", "value": value, "unit": unit, "source_name": "test",
                "source_url": "https://example.test", "published": dt.date(2026, 1, 1),
                "quality": "A", **extra}
    return [
        row("cpm", {"low": 90, "point": 100, "high": 110}, "nok"),
        row("ctr", {"low": 1.0, "point": 1.2, "high": 1.4}, "percent"),
        row("cvr", {"low": 2.0, "point": 3.0, "high": 4.0}, "percent"),
        row("roas", {"low": 2.0, "point": 3.0, "high": 4.0}, "ratio"),
        row("perf_multiplier", {"low": response, "point": response, "high": response},
            "multiplier", effect="response"),
        row("perf_multiplier", {"low": memory, "point": memory, "high": memory},
            "multiplier", effect="memory_brand"),
    ]


def _scn(**over):
    d = {"name": "t", "industry": "beauty_skincare", "objective": "online_sales",
         "brand_positioning": "premium", "currency": "NOK", "price": 900, "budget": 40000,
         "margin": 0.6, "reuse_campaigns": 1}
    d.update(over)
    return scenario_from_dict(d, FX)


def test_plan_runs_and_every_cell_is_finite():
    r = plan(_scn(), benchmarks=_bench(), weights=WEIGHTS, draws=2000)
    assert r.cells, "expected approach x format cells"
    for c in r.cells:
        assert all(x == x for x in c.conv)          # not NaN
        assert c.conv_per_1000 > 0 and c.cost_per_conv > 0
    assert r.leader in ("human_led", "ai_assisted", "ai_generated")


def test_format_changes_the_result():
    r = plan(_scn(), benchmarks=_bench(), weights=WEIGHTS, draws=3000)
    by_fmt = {}
    for c in r.cells:
        if c.approach == "ai_generated":
            by_fmt[c.fmt] = c.conv_per_1000
    # UGC and static priors differ, so the same approach must score differently.
    assert by_fmt["ugc_talking_head"] != pytest.approx(by_fmt["static_image"], rel=1e-3)


def test_production_cost_changes_the_result():
    # Higher human-led production -> higher break-even lift (needs more response to pay off).
    cheap = plan(_scn(costs={"human_led": {"designer": 2000}, "ai_driven": {"tool_subscriptions": 1500}}),
                 benchmarks=_bench(), weights=WEIGHTS, draws=3000)
    dear = plan(_scn(costs={"human_led": {"photographer": 60000}, "ai_driven": {"tool_subscriptions": 1500}}),
                benchmarks=_bench(), weights=WEIGHTS, draws=3000)
    assert dear.breakeven.lift[1] > cheap.breakeven.lift[1]


def test_scenario_supplied_cost_is_not_marked_a_draft():
    # The advertiser's own production cost is their real figure (own_scenario),
    # never flagged as a library draft.
    r = plan(_scn(costs={"human_led": {"photographer": 9000},
                         "ai_driven": {"tool_subscriptions": 1200}}),
             benchmarks=_bench(), weights=WEIGHTS, draws=1500)
    human = [c for c in r.cells if c.approach == "human_led"]
    assert human and all(c.prod_filled and c.prod_tier == "own_scenario" for c in human)


def test_library_draft_costs_bite_when_no_cost_is_supplied():
    # With no supplied costs, human cells fall back to the drafted library band
    # and are flagged provisional.
    r = plan(_scn(), benchmarks=_bench(), weights=WEIGHTS, draws=1500)
    human = [c for c in r.cells if c.approach == "human_led"]
    assert any(not c.prod_filled for c in human)


def test_memory_brand_never_enters_conversions():
    # response forced to parity; memory_brand large. Human and AI conversions (same
    # format) must be identical -> the brand prior does NOT touch the funnel.
    r = plan(_scn(), benchmarks=_bench(response=1.0, memory=2.0), weights=WEIGHTS, draws=2000)
    cells = {(c.approach, c.fmt): c for c in r.cells}
    h = cells[("human_led", "short_video")]
    a = cells[("ai_generated", "short_video")]
    assert h.conv == pytest.approx(a.conv, rel=1e-9)
    # ...but the brand line DID pick up the large edge.
    assert r.brand.brand_value > 0


def test_sampling_is_stable_under_a_fixed_seed():
    a = plan(_scn(), benchmarks=_bench(), weights=WEIGHTS, draws=2000, seed=42)
    b = plan(_scn(), benchmarks=_bench(), weights=WEIGHTS, draws=2000, seed=42)
    assert a.breakeven.lift == b.breakeven.lift
    assert [c.conv_per_1000 for c in a.cells] == [c.conv_per_1000 for c in b.cells]


def test_sensitivity_names_real_inputs():
    r = plan(_scn(), benchmarks=_bench(), weights=WEIGHTS, draws=2000)
    known = {"production cost (human-led)", "production cost (AI)", "CPM",
             "click-through rate", "conversion rate", "AI-vs-human response"}
    assert r.sensitivity and len(r.sensitivity) <= 3
    assert all(s.driver in known for s in r.sensitivity)
    swings = [s.swing for s in r.sensitivity]
    assert swings == sorted(swings, reverse=True)


def test_capacity_caps_conversions_and_sets_objective():
    r = plan(_scn(capacity=50), benchmarks=_bench(), weights=WEIGHTS, draws=2000)
    assert r.capacity_capped
    for c in r.cells:
        assert c.conv[2] <= 50 + 1e-6                 # p90 conversions capped at capacity
    assert any("sell out" in n.lower() for n in r.notes)


def test_breakeven_is_none_safe_when_only_one_approach_makes_the_format():
    # studio_shoot is human_led only; the engine still returns a plan.
    r = plan(_scn(content_format="studio_shoot"), benchmarks=_bench(), weights=WEIGHTS, draws=1000)
    assert r.headline_format  # a shared format was chosen for the comparison
