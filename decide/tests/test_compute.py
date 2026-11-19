# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Budget check: the three answers, rounding, blank fallback, boundaries, copy guard."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from decide.compute import (
    EXAMPLE,
    INDUSTRIES,
    SCENARIOS,
    Inputs,
    compute,
    formats,
)
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
    assert "the human version needs 16 more tickets" in r["a2"]["text"]   # pronoun, not "it"
    assert "about 8 per campaign" in r["a2"]["text"]
    assert "it needs" not in r["a2"]["text"]
    # 300 tickets is not reachable on this budget, so no share-of-target line (item 3).
    assert not r["a2"]["has_context"] and not r["reachable"]


def test_share_uses_the_displayed_per_campaign_figure():
    # The two numbers in one sentence must agree: 16 per campaign is 40% of a 40 target.
    r = compute(replace(EXAMPLE, goal=40, budget=600000, reuse=2, human=8000, ai=400))
    assert "about 16 per campaign" in r["a2"]["text"]
    assert r["a2"]["context"].startswith("That is 40% of your 40-ticket target")


def test_cpm_derived_estimates_round_to_two_sig_figs():
    r = compute(EXAMPLE)                       # views 43478 -> 43 000; one_in 145 -> 150
    assert "1 in 150 ad views" in r["a1"]["text"]
    assert "≈ 43 000" in r["a1"]["how"] and "43 478" not in r["a1"]["how"]
    # Exact maths stays exact: max cost per sale and extra sales are not rounded.
    assert "at most 17 kr" in r["a1"]["text"] and r["a2"]["big"] == "16"
    mx = compute(replace(EXAMPLE, goal_mode="max"))
    assert "covers about 43 000 views" in mx["a1"]["text"]      # views rounded
    assert "43 478" not in mx["a1"]["text"]


def test_target_share_only_when_reachable():
    # Reachable: a big budget on a tiny target shows the share; unreachable drops it.
    r = compute(replace(EXAMPLE, goal=5, budget=60000, reuse=1))
    assert r["reachable"] and r["a2"]["has_context"]
    assert "% of your 5-ticket target" in r["a2"]["context"]
    assert not compute(EXAMPLE)["a2"]["has_context"]        # example target unreachable


def test_views_not_people_wording():
    r = compute(EXAMPLE)
    assert "ad views would need to become a ticket" in r["a1"]["text"]
    assert "people who see the ad" not in r["a1"]["text"]


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

def test_blank_human_reads_as_typical_not_a_real_quote():
    r = compute(replace(EXAMPLE, human=None))    # ugc human point = 3600
    assert r["human_blank"] and r["human_eff"] == 3600
    assert r["a2"]["big"] == "14"                # ceil((3600-300)/250)
    assert r["a2"]["text"].startswith("A typical creator costs about 3 300 kr more than the AI version")
    assert r["a2"]["note"] == ("Typical range: 2 000–8 000 kr. Put in your quote for a sharper answer.")
    assert r["a3"]["blank"] and "usually runs" in r["a3"]["text"] and "No quote entered" in r["a3"]["text"]


def test_blank_ai_reads_as_typical():
    r = compute(replace(EXAMPLE, ai=None))       # ugc ai point = 1200
    assert r["ai_blank"] and r["ai_eff"] == 1200
    assert "a typical AI version" in r["a2"]["text"] and "costs about" in r["a2"]["text"]
    assert "Typical AI cost" in r["a2"]["note"]


def test_only_my_budget_both_blank_reads_as_typical():
    r = compute(replace(EXAMPLE, human=None, ai=None))
    assert r["human_blank"] and r["ai_blank"]
    assert r["a1"]["big"] != "—"                 # the budget answer does not need the quotes
    assert r["a2"]["text"].startswith("A typical creator costs about")
    assert "a typical AI version" in r["a2"]["text"]
    assert "Typical ranges" in r["a2"]["note"]


def test_margin_replaces_price_in_the_human_margin():
    # Margin in % of price, and in kr; both replace price and are named in "how".
    pct = compute(replace(EXAMPLE, margin=40, margin_unit="pct"))   # 250 * 40% = 100
    assert pct["value_per"] == 100.0 and pct["margin_used"]
    assert pct["a2"]["big"] == "39"                                  # ceil(3900/100)
    assert "margin per ticket" in pct["a2"]["how"]
    kr_margin = compute(replace(EXAMPLE, margin=200, margin_unit="kr"))
    assert kr_margin["value_per"] == 200.0 and kr_margin["a2"]["big"] == "20"   # ceil(3900/200)
    # Unset margin keeps the "use your margin instead" note.
    assert "use that instead" in compute(EXAMPLE)["a2"]["how"]


# --- no-gap case -------------------------------------------------------------

def test_no_gap_when_human_costs_no_more():
    r = compute(replace(EXAMPLE, human=300, ai=4200))
    assert r["a2"]["big"] == "0"
    assert "costs no more" in r["a2"]["text"] and not r["a2"]["has_context"]


# --- budget boundaries -------------------------------------------------------

def test_no_price_and_no_budget_prompt_for_the_missing_number():
    assert compute(replace(EXAMPLE, price=0))["a2"]["text"] == "Add a value per ticket to see this."
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
        d = case["input"]
        inp = Inputs(industry=d["industry"], goal_mode=d["goalMode"], goal=d["goal"],
                     price=d["price"], budget=d["budget"], fmt=d["fmt"], human=d["human"],
                     ai=d["ai"], reuse=d["reuse"], cpm=d["cpm"], margin=d.get("margin"),
                     margin_unit=d.get("marginUnit", "kr"), other_noun=d.get("otherNoun"))
        assert compute(inp) == case["output"]


# --- industry language: verb-neutral, noun isolated (item 6) -----------------

_BANNED = ("buy", "buys", "buying", "bought", "sell", "sells", "selling", "sold",
           "book", "books", "booked")


@pytest.mark.parametrize("ind", [i["key"] for i in INDUSTRIES])
@pytest.mark.parametrize("mode", ["target", "max"])
def test_industry_copy_is_verb_neutral_and_noun_isolated(ind, mode):
    other = "widget" if ind == "other" else None
    r = compute(replace(EXAMPLE, industry=ind, goal_mode=mode, other_noun=other))
    text = " ".join(_strings(r))
    words = set(re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower()))
    assert not (words & set(_BANNED)), f"{ind}/{mode}: banned verb in {words & set(_BANNED)}"
    # No other industry's noun leaks in (compare against this industry's own nouns).
    my = {r["unit_one"], r["unit_many"]}
    for other_ind in INDUSTRIES:
        if other_ind["key"] == ind:
            continue
        for noun in (other_ind["one"], other_ind["many"]):
            if noun in my:
                continue
            assert re.search(rf"\b{re.escape(noun)}\b", text) is None, f"{ind}: leaked '{noun}'"


def test_other_industry_uses_the_free_text_noun():
    r = compute(replace(EXAMPLE, industry="other", other_noun="signup", goal=5, budget=60000, reuse=1))
    assert r["unit_one"] == "signup" and r["unit_many"] == "signups"
    assert "more signups" in r["a2"]["text"]
    assert compute(replace(EXAMPLE, industry="other"))["unit_one"] == "sale"   # default
