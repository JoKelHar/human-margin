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


def test_production_cost_surfaces_when_the_cost_is_uncertain():
    # Sensitivity surfaces production cost when it is uncertain (the wide library
    # draft band). A firm supplied quote is near-certain (a narrow +/-15% band), so it
    # legitimately drops out of "what this hinges on" - that is honest, not a bug.
    r = plan(_scn(), benchmarks=_bench(), weights=WEIGHTS, draws=1500)   # no supplied cost
    assert any("production cost" in s.driver for s in r.sensitivity)


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


def test_costs_format_drives_the_headline_format():
    # Item 1 (root fix): the headline runs on the format the advertiser priced, so
    # every section uses the same format and the supplied human cost is placed.
    want = {"club_night": "ugc_talking_head", "local_gym": "short_video",
            "oslo_dinner": "static_image", "skincare_brand": "studio_shoot"}
    for stem, fmt in want.items():
        r = plan(load_scenario(EXAMPLES / f"{stem}.yaml"), draws=600)
        assert r.headline_format == fmt
        assert r.breakeven_cost.fmt == fmt or not r.breakeven_cost.feasible


def test_explicit_content_format_still_overrides_costs_format():
    scn = load_scenario(EXAMPLES / "club_night.yaml")
    scn.content_format = "static_image"
    assert plan(scn, draws=600).headline_format == "static_image"


def test_scenario_human_cost_is_placed_against_the_breakeven():
    # club_night prices a UGC talking-head at 3000 + 1200 = 4200; that cost is placed.
    r = plan(load_scenario(EXAMPLES / "club_night.yaml"), draws=1500)
    assert r.breakeven_cost.own_cost_nok == 4200
    assert r.breakeven_cost.own_placement in ("above_both", "between", "below_both")


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


def _bench_point(response=1.0, memory=1.25):
    """A near-deterministic benchmark set (point-only funnel) so the brand identity
    is checkable: only the format multipliers and cost bands still vary."""
    def row(metric, value, unit, **extra):
        return {"metric": metric, "industry": "any", "price_band": "any", "channel": "any",
                "geography": "NO", "value": value, "unit": unit, "source_name": "test",
                "source_url": "https://example.test", "published": dt.date(2026, 1, 1),
                "quality": "A", **extra}
    pt = lambda v: {"low": v, "point": v, "high": v}  # noqa: E731
    return [
        row("cpm", pt(100), "nok"), row("ctr", pt(1.2), "percent"),
        row("cvr", pt(3.0), "percent"), row("roas", pt(3.0), "ratio"),
        row("perf_multiplier", pt(response), "multiplier", effect="response"),
        row("perf_multiplier", pt(memory), "multiplier", effect="memory_brand"),
    ]


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.yaml")), ids=lambda p: p.stem)
def test_breakeven_and_brand_verdicts_cannot_disagree(path):
    # One shared AI comparator everywhere, so the two verdicts for the same scenario
    # always agree: "human+brand matches AI" (own cost <= brand-inclusive break-even)
    # iff "the brand effect closes the gap" (brand value >= what's needed to close it).
    r = plan(load_scenario(path), draws=3000)
    bc, br = r.breakeven_cost, r.brand
    own = bc.own_cost_nok or 0.0
    assert (own <= bc.with_brand[1]) == (br.brand_value >= br.worth_to_close)
    # The comparator is named and shared between the two sections.
    assert bc.ai_label and bc.ai_label == br.ai_label


def test_ai_comparator_prefers_the_human_format_then_falls_back():
    # Like-for-like where possible: local_gym (short_video) is compared with AI at
    # short_video; skincare (studio, no AI cell) falls back to AI's strongest overall.
    gym = plan(load_scenario(EXAMPLES / "local_gym.yaml"), draws=800).breakeven_cost
    assert "Short video" in gym.ai_label
    skin = plan(load_scenario(EXAMPLES / "skincare_brand.yaml"), draws=800).breakeven_cost
    assert "UGC talking-head" in skin.ai_label and skin.feasible  # studio is human-capable


def test_brand_breakeven_agrees_with_the_brand_line_worth():
    # The brand-inclusive break-even and the brand line describe the same effect:
    # including the brand edge raises the break-even by exactly the modelled brand
    # value (per draw with_brand - funnel == R * brand_value), so the two numbers agree.
    scn = _scn(content_format="short_video",
               costs={"format": "short_video", "human_led": {"photographer": 9000}})
    r = plan(scn, benchmarks=_bench_point(memory=1.25), weights=WEIGHTS, draws=6000)
    bc = r.breakeven_cost
    R = r.scenario.reuse_campaigns
    assert bc.with_brand[1] - bc.funnel[1] == pytest.approx(R * r.brand.brand_value, rel=0.03)
    # Direction also agrees: the human cost needs the brand edge (worth_to_close > 0)
    # exactly when it sits above the funnel-only break-even.
    assert (r.brand.worth_to_close > 0) == (bc.own_cost_nok > bc.funnel[1])


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
    assert any("lowest cost" in n.lower() for n in r.notes)


def test_breakeven_is_none_safe_when_only_one_approach_makes_the_format():
    # studio_shoot is human_led only; the engine still returns a plan.
    r = plan(_scn(content_format="studio_shoot"), benchmarks=_bench(), weights=WEIGHTS, draws=1000)
    assert r.headline_format  # a shared format was chosen for the comparison
