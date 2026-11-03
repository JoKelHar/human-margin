# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Config loading and channel priorities."""

from __future__ import annotations

from mediekjop.config import enabled_channels, reporting_currency


def test_reporting_currency_is_nok(cfg):
    assert reporting_currency(cfg) == "NOK"


def test_channel_priority_order(cfg):
    # Brief's priority order; pinterest is behind a flag (disabled), linkedin/x excluded.
    assert enabled_channels(cfg) == ["meta", "snapchat", "tiktok", "youtube"]
    assert cfg["channels"]["pinterest"]["enabled"] is False
    assert "linkedin" not in cfg["channels"]
    assert "x" not in cfg["channels"]


def test_placements_are_present_and_video_flagged(cfg):
    names = {(p["channel"], p["publisher"], p["name"]) for p in cfg["placements"]}
    assert ("snapchat", "snapchat", "spotlight") in names
    assert ("youtube", "youtube", "shorts") in names
    assert ("meta", "instagram", "reels") in names


def test_callout_terms_include_norwegian_ai_language(cfg):
    terms = {t.lower() for t in cfg["callout_terms"]}
    assert "ki-generert" in terms
    assert "ai-generert" in terms
