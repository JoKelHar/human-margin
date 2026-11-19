# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Creator mode: the three answers, inclusions, margin, band position, AI alternative."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from decide.compute import (
    CREATOR_EXAMPLE,
    CreatorInputs,
    Inputs,
    compute,
    creator_compute,
)
from mediekjop.planner.report import PRESCRIPTIVE

ROOT = Path(__file__).resolve().parents[1]
# Positions, never price advice, in addition to the shared prescriptive guard.
_CREATOR_BANNED = ("charge more", "underpriced", "you should", "undercharge", "worth more")


def _strings(r: dict) -> str:
    out = []
    for a in (r["a"], r["b"], r["c"]):
        for v in a.values():
            if isinstance(v, str):
                out.append(v)
    return " ".join(out)


def test_example_matches_the_brief():
    r = creator_compute(CREATOR_EXAMPLE)   # ugc, your price 3500, nightlife 250
    assert r["a"]["big"] == "Inside usual range"
    assert r["a"]["text"].startswith("3 500 kr for a creator video sits inside the usual range")
    assert r["a"]["inclusions"] == "Includes 6 months usage, 2 revisions, no raw files."
    # AI cost = formats.yaml UGC band point (1 200), same as buying mode (not the tool sub).
    assert r["typical_ai"] == 1200
    assert r["b"]["big"] == "10"                 # ceil((3500 - 1200) / 250)
    assert "needs 10 more tickets from your creator video than from a typical AI version" in r["b"]["text"]
    assert r["c"]["text"] == "The closest AI option costs about 310 kr a month (HeyGen Creator)."


def test_both_modes_return_the_same_extra_sales_for_identical_inputs():
    # Creator mode and buying mode use the SAME AI cost (the band point), so a 3 500 kr
    # UGC video against a 250 kr ticket gives the same extra-sales number either way.
    creator = creator_compute(replace(CREATOR_EXAMPLE, fmt="ugc", price=3500,
                                      example_industry="nightlife", example_price=250))
    buying = compute(Inputs(industry="nightlife", goal_mode="max", price=250, human=3500,
                            ai=None, fmt="ugc", reuse=1, budget=5000))
    assert creator["b"]["big"] == buying["a2"]["big"] == "10"


def test_where_price_sits_tracks_the_band():
    assert creator_compute(replace(CREATOR_EXAMPLE, price=1000))["a"]["big"] == "Below usual"   # < 2000
    assert creator_compute(replace(CREATOR_EXAMPLE, price=5000))["a"]["big"] == "Inside usual range"
    assert creator_compute(replace(CREATOR_EXAMPLE, price=9000))["a"]["big"] == "Above usual"    # > 8000
    a = creator_compute(CREATOR_EXAMPLE)["a"]
    for k in ("pct_low", "pct_high", "pct_price"):
        assert 0.0 <= a[k] <= 100.0


def test_inclusions_line_reflects_the_inputs():
    r = creator_compute(replace(CREATOR_EXAMPLE, usage_months=12, revisions=3, raw_files=True))
    assert r["a"]["inclusions"] == "Includes 12 months usage, 3 revisions, raw files included."


def test_no_gap_when_price_under_the_typical_ai_cost():
    r = creator_compute(replace(CREATOR_EXAMPLE, price=1000))   # < typical AI band point 1200
    assert r["b"]["big"] == "0" and "costs no more than a typical AI version" in r["b"]["text"]


def test_singular_plural_for_months_and_revisions():
    r = creator_compute(replace(CREATOR_EXAMPLE, usage_months=1, revisions=1))
    assert r["a"]["inclusions"] == "Includes 1 month usage, 1 revision, no raw files."


def test_margin_replaces_the_example_price():
    pct = creator_compute(replace(CREATOR_EXAMPLE, margin=40, margin_unit="pct"))   # 250 * 40% = 100
    assert pct["b"]["big"] == "23"                 # ceil((3500 - 1200) / 100)
    assert "margin per ticket" in pct["b"]["how"]


def test_example_price_defaults_per_industry_and_can_be_overridden():
    assert creator_compute(replace(CREATOR_EXAMPLE, example_industry="fitness"))["example_price"] == 1800
    assert creator_compute(replace(CREATOR_EXAMPLE, example_price=500))["example_price"] == 500


def test_ai_alternative_is_the_entry_tier_tool_per_format():
    assert "HeyGen Creator" in creator_compute(replace(CREATOR_EXAMPLE, fmt="ugc"))["c"]["tool_name"]
    assert "Photoroom Pro" in creator_compute(replace(CREATOR_EXAMPLE, fmt="studio"))["c"]["tool_name"]
    assert "Kling" in creator_compute(replace(CREATOR_EXAMPLE, fmt="video"))["c"]["tool_name"]


def test_creator_copy_is_positions_not_price_advice():
    for over in ({}, {"price": 1000}, {"price": 200}, {"margin": 40, "margin_unit": "pct"}):
        text = _strings(creator_compute(replace(CREATOR_EXAMPLE, **over))).lower()
        assert not [w for w in PRESCRIPTIVE if w in text], f"prescriptive: {over}"
        assert not [w for w in _CREATOR_BANNED if w in text], f"price advice: {over}"
        assert "~" not in _strings(creator_compute(replace(CREATOR_EXAMPLE, **over)))


def test_creator_golden_matches_python():
    golden = json.loads((ROOT / "tests" / "golden" / "creator.json").read_text(encoding="utf-8"))
    for case in golden:
        d = case["input"]
        inp = CreatorInputs(fmt=d["fmt"], price=d["price"], usage_months=d["usageMonths"],
                            revisions=d["revisions"], raw_files=d["rawFiles"],
                            example_industry=d["exampleIndustry"], example_price=d["examplePrice"],
                            margin=d.get("margin"), margin_unit=d.get("marginUnit", "kr"))
        assert creator_compute(inp) == case["output"]
