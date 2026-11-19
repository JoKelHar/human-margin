# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The three scenarios: their committed Positions regenerate byte-for-byte by running
decide/, reachability and stance are what the scenario files declare, and each Position
cites its Context and Goal."""

from __future__ import annotations

from brief.decide_link import break_even_of, maker_stance, run_decide
from brief.scenarios import (
    canonical_json,
    context_of,
    goal_of,
    load_position,
    load_scenario,
    position_path,
    slugs,
)
from brief.scenarios.generate import build_position


def test_three_scenarios_present():
    assert slugs() == ["aurora", "fjellbre", "verftet"]


def test_regeneration_reproduces_committed_positions():
    for slug in slugs():
        committed = position_path(slug).read_text(encoding="utf-8")
        regenerated = canonical_json(build_position(slug))
        assert regenerated == committed, \
            f"{slug}/position.json is stale -- run: uv run python -m brief.scenarios.generate"


def test_reachability_matches_the_scenario_files():
    seen = {}
    for slug in slugs():
        sc = load_scenario(slug)
        seen[slug] = run_decide(sc["decide_inputs"])["reachable"]
        assert seen[slug] == sc["expected"]["reachable"], slug
    assert seen == {"aurora": True, "fjellbre": True, "verftet": False}


def test_stance_matches_the_scenario_files():
    for slug in slugs():
        sc = load_scenario(slug)
        r = run_decide(sc["decide_inputs"])
        st = maker_stance(break_even_of(r), sc["decide_inputs"]["goal"])
        assert st.maker.value == sc["expected"]["stance"], slug
        assert not st.near_boundary, f"{slug} ratio {st.ratio:.1f}% is too close to a threshold"


def test_the_three_verdicts_are_distinct_and_one_is_unreachable():
    stances = sorted(load_scenario(s)["expected"]["stance"] for s in slugs())
    reach = [run_decide(load_scenario(s)["decide_inputs"])["reachable"] for s in slugs()]
    assert stances == ["ai", "human", "hybrid"]
    assert reach.count(False) == 1


def test_each_position_cites_its_context_and_goal():
    for slug in slugs():
        sc = load_scenario(slug)
        ctx, goal = context_of(sc), goal_of(sc)
        pos = load_position(slug)
        assert pos.envelope.id == f"{slug}-pos"
        assert pos.envelope.parent_ids == [ctx.envelope.id, goal.envelope.id]
        assert ctx.market == "NO"
