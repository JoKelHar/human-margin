# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The "If you go AI" card: format->tools mapping, fits-budget, stale banner, rules."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from mediekjop.planner.budget_check import ai_options, load_ai_tools
from mediekjop.planner.report import PRESCRIPTIVE

ROOT = Path(__file__).resolve().parents[1]
FRESH = dt.date(2026, 11, 18)       # on/before review_by
STALE = dt.date(2027, 3, 1)         # after review_by 2027-02-18


def _names(card) -> list[str]:
    return [t["name"] for t in card["tools"]]


# --- format -> tools mapping -------------------------------------------------

def test_each_format_maps_to_its_use_case():
    assert ai_options("static", today=FRESH)["use_case_label"].startswith("Static images")
    assert ai_options("studio", today=FRESH)["use_case_label"].startswith("Studio-style")
    assert "Runway Pro" in _names(ai_options("video", today=FRESH))
    assert "HeyGen Creator" in _names(ai_options("ugc", today=FRESH))
    # Studio maps to the product tools (not a studio-named use case).
    assert _names(ai_options("studio", today=FRESH)) == ["Photoroom Pro", "Photoroom Max", "Adobe Firefly Pro Plus"]


def test_tools_are_in_price_order():
    for fmt in ("static", "video", "ugc", "studio"):
        prices = [t["price_nok"] for t in ai_options(fmt, today=FRESH)["tools"]]
        assert prices == sorted(prices), f"{fmt} tools not in price order: {prices}"


def test_voice_row_only_for_video_and_ugc():
    assert ai_options("video", today=FRESH)["voice"] is not None
    assert ai_options("ugc", today=FRESH)["voice"] is not None
    assert ai_options("static", today=FRESH)["voice"] is None
    assert ai_options("studio", today=FRESH)["voice"] is None
    voice = ai_options("ugc", today=FRESH)["voice"]
    assert voice["label"] == "Norwegian voice-over" and len(voice["tools"]) == 3


def test_ugc_card_note_and_video_alternative():
    assert "misleading marketing" in ai_options("ugc", today=FRESH)["card_note"]
    assert ai_options("studio", today=FRESH)["card_note"] == ""
    alts = ai_options("video", today=FRESH)["alternatives"]
    assert alts and "Google Flow" in alts[0]["name"] and alts[0]["price_text"].startswith("about ")


# --- "fits your AI budget" ---------------------------------------------------

def test_fits_your_ai_budget_logic():
    card = ai_options("static", ai_cost=300, today=FRESH)   # Firefly 110, Canva 190, Midjourney 650
    fits = {t["name"]: t["fits"] for t in card["tools"]}
    assert fits["Adobe Firefly Standard"] and fits["Canva Pro"] and not fits["Midjourney Pro"]
    # A tool exactly at the budget fits; zero budget fits nothing.
    assert ai_options("ugc", ai_cost=310, today=FRESH)["tools"][0]["fits"]      # HeyGen = 310
    assert not any(t["fits"] for t in ai_options("static", ai_cost=0, today=FRESH)["tools"])


# --- stale banner ------------------------------------------------------------

def test_stale_flag_tracks_review_by():
    assert not ai_options("ugc", today=FRESH)["stale"]
    assert ai_options("ugc", today=STALE)["stale"]
    assert ai_options("ugc", today=FRESH)["checked_display"] == "18 Nov 2026"


# --- rule lines --------------------------------------------------------------

def test_rule_lines_reference_the_norway_rules():
    ugc = ai_options("ugc", today=FRESH)
    assert [r["id"] for r in ugc["tools"][0]["rules"]] == ["misleading", "ai_act"]
    assert [r["id"] for r in ugc["rules"]] == ["misleading", "ai_act"]
    for r in ugc["rules"]:                       # the linked text is present
        assert r["text"] and r["label"]
    # studio -> retouch_label; static -> no rules.
    assert [r["id"] for r in ai_options("studio", today=FRESH)["rules"]] == ["retouch_label"]
    assert ai_options("static", today=FRESH)["rules"] == []


# --- copy guard (our labels; owner data excluded) ----------------------------

def test_card_labels_are_positions_not_recommendations():
    # The labels WE add - headings, badges, the fits chip text, footer - must never
    # say best/recommended/choose. (Vendor includes/pros/cons are owner data.)
    card = ai_options("ugc", ai_cost=300, today=FRESH)
    ours = [card["use_case_label"], card["format_label"], "fits your AI budget",
            "No affiliate links or paid placement", card["checked_display"]]
    ours += [t["price_text"] for t in card["tools"]]
    ours += [t["badge"] or "" for t in card["tools"]]
    ours += [r["label"] for r in card["rules"]]
    low = " ".join(ours).lower()
    assert not [w for w in PRESCRIPTIVE if w in low]


def test_ai_options_golden_matches_python():
    golden = json.loads((ROOT / "tests" / "golden" / "ai_options.json").read_text(encoding="utf-8"))
    for case in golden:
        got = ai_options(case["input"]["fmt"], case["input"]["ai_cost"],
                         today=dt.date.fromisoformat(case["input"]["today"]))
        assert got == case["output"]


def test_no_tracking_params_in_sources():
    data = load_ai_tools()
    urls = [data["free_baseline"]["source"]]
    urls += [r["source"] for r in data["norway_rules"]]
    for uc in data["use_cases"]:
        urls += [t["source"] for t in uc.get("tools", [])]
    for u in urls:
        assert "utm_" not in u and "?ref=" not in u and "fbclid" not in u, f"tracking param in {u}"
