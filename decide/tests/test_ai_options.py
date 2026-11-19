# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The "If you go AI" card: format->tools mapping, fits-budget, stale banner, rules."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from decide.compute import ai_options, load_ai_tools
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


def _ai_act_rule() -> dict:
    rules = {r["id"]: r for r in load_ai_tools()["norway_rules"]}
    return rules["ai_act"]


def test_ai_act_rule_cites_primary_sources_and_current_wording():
    rule = _ai_act_rule()
    # Primary government sources replace the earlier secondary explainer.
    assert rule["sources"] == [
        "https://www.regjeringen.no/no/aktuelt/regjeringen-sender-forenklinger-i-ki-forordningen-pa-horing/id3187283/",
        "https://www.regjeringen.no/no/aktuelt/id3169693/",
    ]
    assert "legal247" not in (rule["source"] + " ".join(rule["sources"]))
    assert "could pass as real must be visibly labelled as AI" in rule["text"]
    assert "closes 11 December 2026" in rule["text"]


def test_ai_act_rule_fails_once_review_by_has_passed():
    # A real-time staleness tripwire: once review_by is in the past, this test fails,
    # forcing a re-check of the AI Act's Norwegian status rather than silent staleness.
    rule = _ai_act_rule()
    assert rule["as_of"] == "2026-11-19"
    review_by = dt.date.fromisoformat(rule["review_by"])
    assert review_by == dt.date(2027, 3, 1)
    assert dt.date.today() <= review_by, (
        f"ai_act rule is past review_by {review_by}: re-verify the AI Act's Norwegian "
        "status and the consultation outcome, then bump as_of/review_by")


# --- rule lines --------------------------------------------------------------

def test_rule_lines_are_per_tool_and_expand_to_the_text():
    # De-duplicated: no card-level rules block; each tool carries its own line plus the
    # full rule text (for the inline expand).
    ugc = ai_options("ugc", today=FRESH)
    assert "rules" not in ugc                     # no block at the top of the card
    hey = ugc["tools"][0]
    assert [r["id"] for r in hey["rules"]] == ["misleading", "ai_act"]
    for r in hey["rules"]:
        assert r["label"] and r["text"] and r["source"]
    # studio -> retouch_label on the Photoroom tools; static -> no tool rules.
    studio = ai_options("studio", today=FRESH)
    assert [r["id"] for r in studio["tools"][0]["rules"]] == ["retouch_label"]
    assert all(not t["rules"] for t in ai_options("static", today=FRESH)["tools"])


# --- copy guard (our labels; owner data excluded) ----------------------------

def test_card_labels_are_positions_not_recommendations():
    # The labels WE add - headings, badges, the fits chip text, footer - must never
    # say best/recommended/choose. (Vendor includes/pros/cons are owner data.)
    card = ai_options("ugc", ai_cost=300, today=FRESH)
    ours = [card["use_case_label"], card["format_label"], "fits your AI budget",
            "No affiliate links or paid placement", card["checked_display"]]
    ours += [t["price_text"] for t in card["tools"]]
    ours += [t["badge"] or "" for t in card["tools"]]
    ours += [r["label"] for t in card["tools"] for r in t["rules"]]
    low = " ".join(ours).lower()
    assert not [w for w in PRESCRIPTIVE if w in low]


def test_ai_options_golden_matches_python():
    golden = json.loads((ROOT / "tests" / "golden" / "ai_options.json").read_text(encoding="utf-8"))
    for case in golden:
        got = ai_options(case["input"]["fmt"], case["input"]["ai_cost"],
                         today=dt.date.fromisoformat(case["input"]["today"]))
        assert got == case["output"]


def test_schema_every_pros_con_is_a_string_and_tools_are_complete():
    # The bug this guards: a bare ": " makes PyYAML parse a list item as a mapping,
    # which rendered as "[object Object]". load_ai_tools() must reject that.
    data = load_ai_tools()
    required = ("name", "tier", "price_usd", "price_nok", "norwegian", "source")
    for uc in data["use_cases"]:
        for t in uc.get("tools", []):
            assert all(k in t for k in required), f"{t.get('name')} missing a required field"
            for field in ("pros", "cons"):
                for item in t.get(field, []):
                    assert isinstance(item, str), f"{t['name']} {field} not a string: {item!r}"


def test_malformed_ai_tools_fails_the_build(tmp_path):
    import pytest as _pytest
    from decide.compute import _validate_ai_tools
    with _pytest.raises(ValueError):
        _validate_ai_tools({"use_cases": [{"tools": [{"name": "X", "tier": "entry",
            "price_usd": 1, "price_nok": 10, "norwegian": "n/a", "source": "s",
            "cons": [{"a": "b"}]}]}]})                 # a mapping, not a string
    with _pytest.raises(ValueError):
        _validate_ai_tools({"use_cases": [{"tools": [{"name": "X"}]}]})   # missing fields


def test_no_tracking_params_in_sources():
    data = load_ai_tools()
    urls = [data["free_baseline"]["source"]]
    urls += [r["source"] for r in data["norway_rules"]]
    for uc in data["use_cases"]:
        urls += [t["source"] for t in uc.get("tools", [])]
    for u in urls:
        assert "utm_" not in u and "?ref=" not in u and "fbclid" not in u, f"tracking param in {u}"
