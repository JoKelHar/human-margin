# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Planner Phase 1: scenario schema, validation and price banding."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from mediekjop.planner import ScenarioError, load_scenario, scenario_from_dict
from mediekjop.planner.currency import FxRates
from mediekjop.planner.schema import _industry_map, load_industries, price_band

EXAMPLES = Path(__file__).resolve().parents[1] / "scenarios" / "examples"
FX = FxRates(rates={"NOK": 1.0, "EUR": 11.7, "USD": 10.8, "GBP": 13.6},
             as_of=dt.date(2026, 1, 1), is_fallback=True)


def _base(**over):
    d = {"name": "t", "industry": "beauty_skincare", "objective": "online_sales",
         "brand_positioning": "premium", "currency": "NOK", "price": 900, "budget": 40000}
    d.update(over)
    return d


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.yaml")), ids=lambda p: p.stem)
def test_example_scenarios_load_and_resolve(path):
    scn = load_scenario(path, FX)
    assert scn.price_nok > 0 and scn.budget_nok > 0
    assert scn.band in ("low", "mid", "high")
    assert scn.value_per_conversion_nok > 0


def test_price_band_boundaries():
    row = _industry_map(load_industries())["beauty_skincare"]  # low_max 200, high_min 700
    assert price_band(200, row) == "low"
    assert price_band(201, row) == "mid"
    assert price_band(699, row) == "mid"
    assert price_band(700, row) == "high"


def test_value_per_conversion_from_margin():
    scn = scenario_from_dict(_base(margin=0.5), FX)
    assert scn.value_per_conversion_nok == 450
    assert not scn.value_is_assumed_from_price


def test_value_per_conversion_explicit_overrides():
    scn = scenario_from_dict(_base(margin=0.5, value_per_conversion=333), FX)
    assert scn.value_per_conversion_nok == 333


def test_value_assumed_from_price_when_nothing_given():
    scn = scenario_from_dict(_base(), FX)
    assert scn.value_per_conversion_nok == 900
    assert scn.value_is_assumed_from_price


def test_foreign_currency_converts_to_nok():
    scn = scenario_from_dict(_base(currency="EUR", price=100, budget=1000), FX)
    assert scn.price_nok == 1170
    assert scn.budget_nok == 11700


def test_capacity_cap_flag():
    assert scenario_from_dict(_base(capacity=40), FX).is_capacity_capped()
    assert not scenario_from_dict(_base(), FX).is_capacity_capped()


@pytest.mark.parametrize("bad", [
    {"industry": "spaceships"},
    {"currency": "JPY"},
    {"objective": "mind_control"},
    {"brand_positioning": "royal"},
    {"margin": 1.5},
])
def test_invalid_values_raise(bad):
    with pytest.raises(ScenarioError):
        scenario_from_dict(_base(**bad), FX)


def test_missing_required_field_raises():
    d = _base()
    del d["budget"]
    with pytest.raises(ScenarioError):
        scenario_from_dict(d, FX)
