# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Agency quote check: fee positions and the stated-approach note."""

from __future__ import annotations

import datetime as dt

from mediekjop.planner import scenario_from_dict
from mediekjop.planner.agency import check_agency
from mediekjop.planner.currency import FxRates

FX = FxRates(rates={"NOK": 1.0, "EUR": 11.7, "USD": 10.8, "GBP": 13.6},
             as_of=dt.date(2026, 1, 1), is_fallback=True)


def _scn(mgmt_pct, approach="ai_generated", **over):
    d = {"name": "t", "industry": "beauty_skincare", "objective": "online_sales",
         "brand_positioning": "premium", "currency": "NOK", "price": 900, "budget": 40000,
         "agency": {"setup_fee": 15000, "monthly_management_fee": 12000,
                    "media_management_pct": mgmt_pct, "creative_production_fee": 25000,
                    "stated_approach": approach}}
    d.update(over)
    return scenario_from_dict(d, FX)


def test_no_agency_returns_absent():
    d = {"name": "t", "industry": "beauty_skincare", "objective": "online_sales",
         "brand_positioning": "premium", "currency": "NOK", "price": 900, "budget": 40000}
    assert not check_agency(scenario_from_dict(d, FX)).present


def test_management_fee_position_against_typical():
    within = check_agency(_scn(15))
    mgmt = next(l for l in within.lines if l.name.startswith("Management"))
    assert mgmt.position == "within typical"          # 15% inside 8-20
    above = check_agency(_scn(30))
    mgmt_hi = next(l for l in above.lines if l.name.startswith("Management"))
    assert mgmt_hi.position == "above typical"         # 30% over the 20 ceiling


def test_stated_approach_note_mentions_the_leader():
    ac = check_agency(_scn(15, approach="ai_generated"), leader="ai_generated")
    assert "matches" in ac.approach_note
    ac2 = check_agency(_scn(15, approach="human_shoot"), leader="ai_generated")
    assert "differs" in ac2.approach_note


def test_stated_approach_note_uses_level_logic():
    # When the headline is effectively level, the agency line names no single leader;
    # the quote's approach sits level with human-led on these inputs.
    ac = check_agency(_scn(15, approach="ai_generated"), leader="ai_generated",
                      level=True, level_pair=["ai_generated", "human_led"])
    assert "sits level with human-led" in ac.approach_note
    assert "matches" not in ac.approach_note and "differs" not in ac.approach_note


def test_loaded_cost_is_reported():
    ac = check_agency(_scn(15))
    assert ac.monthly_fee_nok > 0 and ac.loaded_total_nok >= ac.monthly_fee_nok
