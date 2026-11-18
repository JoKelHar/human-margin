# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Budget check: the three answers, rounding, blank fallback, boundaries, copy guard."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mediekjop.planner.budget_check import EXAMPLE, SCENARIOS, Inputs, compute, formats
from mediekjop.planner.report import PRESCRIPTIVE

ROOT = Path(__file__).resolve().parents[1]


def _strings(r: dict) -> list[str]:
    out = []
    for a in (r["a1"], r["a2"], r["a3"]):
        for v in a.values():
            if isinstance(v, str):
                out.append(v)
    return out


# --- extra-sales maths and rounding -----------------------------------------

def test_example_human_margin_maths():
    r = compute(EXAMPLE)                       # human 4200, ai 300, price 250, reuse 2, goal 300
    assert r["a2"]["big"] == "16"              # ceil(3900/250)
    assert "about 8 per campaign" in r["a2"]["text"]   # ceil(3900/(250*2))
    assert r["a2"]["context"].startswith("That is 3%")  # round(16/2/300*100)


def test_rounding_rounds_up_like_js():
    # 3 901 / 250 = 15.604 -> 16; a cost gap of exactly a multiple stays exact.
    assert compute(replace(EXAMPLE, human=4201)) ["a2"]["big"] == "16"
    assert compute(replace(EXAMPLE, human=4050, ai=300))["a2"]["big"] == "15"   # 3750/250 = 15.0


def test_singular_unit_when_one_extra():
    # Singular reads only in the single-campaign branch (reuse > 1 always says "more <many>").
    r = compute(replace(EXAMPLE, human=400, ai=300, goal=1, budget=500, reuse=1))  # diff 100 -> 1
    assert r["a2"]["big"] == "1" and r["a2"]["unit"] == "more ticket"
    assert "more ticket than" in r["a2"]["text"]


# --- blank-quote fallback ----------------------------------------------------

def test_blank_human_uses_the_band_point_and_is_labelled():
    r = compute(replace(EXAMPLE, human=None))    # ugc human point = 3600
    assert r["human_blank"] and r["human_eff"] == 3600
    assert r["a2"]["big"] == "14"                # ceil((3600-300)/250)
    assert r["a2"]["note"] == ("Using the usual range: 2 000–8 000 kr. "
                               "Put in your quote for a sharper answer.")
    assert r["a3"]["blank"] and "No quote entered" in r["a3"]["text"]


def test_blank_ai_uses_the_band_point():
    r = compute(replace(EXAMPLE, ai=None))       # ugc ai point = 1200
    assert r["ai_blank"] and r["ai_eff"] == 1200
    assert "usual AI cost" in r["a2"]["note"]


def test_only_my_budget_both_blank_still_valid():
    r = compute(replace(EXAMPLE, human=None, ai=None))
    assert r["human_blank"] and r["ai_blank"]
    assert r["a1"]["big"] != "—"                 # the budget answer does not need the quotes
    assert "Using the usual ranges" in r["a2"]["note"]


# --- no-gap case -------------------------------------------------------------

def test_no_gap_when_human_costs_no_more():
    r = compute(replace(EXAMPLE, human=300, ai=4200))
    assert r["a2"]["big"] == "0"
    assert "costs no more" in r["a2"]["text"] and not r["a2"]["has_context"]


# --- budget boundaries -------------------------------------------------------

def test_no_price_and_no_budget_prompt_for_the_missing_number():
    assert compute(replace(EXAMPLE, price=0))["a2"]["text"] == "Add a price per ticket to see this."
    assert compute(replace(EXAMPLE, budget=0))["a1"]["text"] == "Add a media budget to see this."
    assert compute(replace(EXAMPLE, cpm=0))["a1"]["text"] == "Add a media budget to see this."


def test_max_mode_shows_a_likely_sales_range():
    r = compute(replace(EXAMPLE, goal_mode="max"))
    assert r["a1"]["big"].startswith("Usually ") and "tickets" in r["a1"]["big"]


# --- quote placement ---------------------------------------------------------

@pytest.mark.parametrize("fmt", ["static", "video", "ugc", "studio"])
def test_quote_placement_below_inside_above(fmt):
    f = next(x for x in formats() if x["key"] == fmt)
    lo, hi = f["human"]["low"], f["human"]["high"]
    assert compute(replace(EXAMPLE, fmt=fmt, human=lo - 1))["a3"]["big"] == "Below usual"
    assert compute(replace(EXAMPLE, fmt=fmt, human=(lo + hi) // 2))["a3"]["big"] == "Inside usual range"
    assert compute(replace(EXAMPLE, fmt=fmt, human=hi + 1, ai=500))["a3"]["big"] == "Above usual"


def test_band_bar_fractions_are_in_range():
    a3 = compute(EXAMPLE)["a3"]
    for k in ("pct_low", "pct_high", "pct_human"):
        assert 0.0 <= a3[k] <= 100.0
    assert a3["pct_low"] < a3["pct_high"]


# --- scenarios + copy guard --------------------------------------------------

@pytest.mark.parametrize("name", list(SCENARIOS))
def test_every_scenario_computes_and_is_a_position_not_advice(name):
    r = compute(SCENARIOS[name])
    low = " ".join(_strings(r)).lower()
    hits = [w for w in PRESCRIPTIVE if w in low]
    assert not hits, f"prescriptive wording in {name}: {hits}"
    assert "~" not in " ".join(_strings(r))      # no tilde on exact counts (copy uses ≈)


def test_golden_matches_current_python_output():
    # The committed golden (what the JS is tested against) still reflects Python.
    golden = json.loads((ROOT / "tests" / "golden" / "budget_check.json").read_text(encoding="utf-8"))
    for case in golden:
        inp = Inputs(industry=case["input"]["industry"], goal_mode=case["input"]["goalMode"],
                     goal=case["input"]["goal"], price=case["input"]["price"],
                     budget=case["input"]["budget"], fmt=case["input"]["fmt"],
                     human=case["input"]["human"], ai=case["input"]["ai"],
                     reuse=case["input"]["reuse"], cpm=case["input"]["cpm"])
        assert compute(inp) == case["output"]
