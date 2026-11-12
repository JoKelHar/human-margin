# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Decision engine: funnel, format/cost effects, break-even, memory-brand, seed.

These use controlled in-memory benchmarks so the arithmetic is checkable, plus
the real formats.yaml / weights.yaml (the engine loads those from disk).
"""

from __future__ import annotations

import datetime as dt

import pytest

from pathlib import Path

from mediekjop.planner import load_scenario, load_weights, scenario_from_dict
from mediekjop.planner.currency import FxRates
from mediekjop.planner.engine import plan

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "scenarios" / "examples"

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


def test_scenario_supplied_cost_applies_to_the_headline_format_only():
    # The advertiser's own production cost is their real figure (own_scenario) for
    # the ONE format it is for (the headline, no `format` given). Every other format
    # for that approach falls back to the library band - one quote must not price a
    # studio shoot as cheaply as a UGC clip.
    r = plan(_scn(costs={"human_led": {"photographer": 9000},
                         "ai_driven": {"tool_subscriptions": 1200}}),
             benchmarks=_bench(), weights=WEIGHTS, draws=1500)
    hf = r.headline_format
    head = [c for c in r.cells if c.approach == "human_led" and c.fmt == hf]
    other = [c for c in r.cells if c.approach == "human_led" and c.fmt != hf]
    assert head and all(c.prod_filled and c.prod_tier == "own_scenario" for c in head)
    assert other and all(c.prod_tier != "own_scenario" for c in other)


def test_cost_override_can_target_a_named_format():
    # `costs.format` points the supplied figure at one specific format.
    r = plan(_scn(costs={"human_led": {"photographer": 9000},
                         "ai_driven": {"tool_subscriptions": 1200},
                         "format": "ugc_talking_head"}),
             benchmarks=_bench(), weights=WEIGHTS, draws=1500)
    own = [c for c in r.cells if c.prod_tier == "own_scenario"]
    assert own and all(c.fmt == "ugc_talking_head" for c in own)


def test_library_draft_costs_bite_when_no_cost_is_supplied():
    # With no supplied costs, human cells fall back to the drafted library band
    # and are flagged provisional.
    r = plan(_scn(), benchmarks=_bench(), weights=WEIGHTS, draws=1500)
    human = [c for c in r.cells if c.approach == "human_led"]
    assert any(not c.prod_filled for c in human)


def test_production_cost_can_be_named_in_hinges_on():
    # Sensitivity must be able to surface production cost as a driver (it is the
    # tool's core lever); at least one example scenario names it.
    named = set()
    for p in sorted(EXAMPLES.glob("*.yaml")):
        r = plan(load_scenario(p), draws=1500)
        named |= {s.driver for s in r.sensitivity}
    assert any("production cost" in d for d in named)


def test_budget_short_of_capacity_is_flagged():
    # club_night: a 5,000 NOK budget cannot reach 300 tickets.
    r = plan(load_scenario(EXAMPLES / "club_night.yaml"), draws=1500)
    assert r.capacity_capped and r.reach_p50 < r.scenario.capacity


def test_cost_above_value_is_flagged_for_every_affected_approach():
    # club_night: cost per sale sits above the 250 NOK ticket for every approach.
    r = plan(load_scenario(EXAMPLES / "club_night.yaml"), draws=1500)
    assert set(r.over_value) >= {c.approach for c in r.cells}


def test_skincare_reads_as_effectively_level():
    # The two leading approaches sit within ~5%, so no single leader is named.
    r = plan(load_scenario(EXAMPLES / "skincare_brand.yaml"), draws=2500)
    assert r.level and len(r.level_pair) == 2


def test_time_rule_makes_local_gym_read_ai_led():
    # The buyer's own AI-prompting time is not costed, so AI's per-krone cost drops
    # and AI-generated leads (the "slightly flatters AI" effect the time note warns of).
    r = plan(load_scenario(EXAMPLES / "local_gym.yaml"), draws=2500)
    assert not r.level and r.leader == "ai_generated"


def test_channel_defaults_to_meta_and_is_queried():
    r = plan(load_scenario(EXAMPLES / "club_night.yaml"), draws=800)
    assert r.channel == "meta"


def test_breakeven_cost_rises_when_the_brand_effect_is_included():
    # The human brand edge lets human-led bear a higher production cost, so the
    # brand-inclusive break-even is >= the funnel-only one (mb > 1).
    r = plan(_scn(), benchmarks=_bench(memory=1.3), weights=WEIGHTS, draws=3000)
    bc = r.breakeven_cost
    assert bc.with_brand[1] > bc.funnel[1]
    # p10<=p50<=p90 on both.
    assert bc.funnel[0] <= bc.funnel[1] <= bc.funnel[2]
    assert bc.with_brand[0] <= bc.with_brand[1] <= bc.with_brand[2]


def test_quote_placement_is_correct_at_the_boundaries():
    r = plan(_scn(), benchmarks=_bench(), weights=WEIGHTS, draws=2500)
    funnel, brand = r.breakeven_cost.funnel[1], r.breakeven_cost.with_brand[1]
    lo, hi = min(funnel, brand), max(funnel, brand)

    def place(q):
        return plan(_scn(human_quote=q), benchmarks=_bench(), weights=WEIGHTS,
                    draws=2500).breakeven_cost.placement

    assert place(lo * 0.5) == "below_both"
    assert place((lo + hi) / 2) == "between"
    assert place(hi * 2 + 1000) == "above_both"


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
