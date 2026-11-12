# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Position, never a pick: the non-prescriptive guard over every rendered output.

Covers the CLI text, the JSON the web demo consumes, and - when built - the web
page's own files (the Pyodide page template and the committed example data).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mediekjop.planner import load_scenario
from mediekjop.planner.agency import check_agency
from mediekjop.planner.engine import plan
from mediekjop.planner.report import (
    PRESCRIPTIVE,
    TIME_NOTE,
    format_keys,
    render_text,
    to_dict,
)
from mediekjop.planner.snapshot import load_snapshots

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "scenarios" / "examples").glob("*.yaml"))


def _prescriptive_hits(text: str) -> list[str]:
    low = text.lower()
    return [w for w in PRESCRIPTIVE if w in low]


def _format_key_hits(text: str) -> list[str]:
    # Raw format keys must never surface in copy; labels only. Guard against the
    # multi-word keys (a single word like "other" is not a key here).
    return [k for k in format_keys() if "_" in k and k in text]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_cli_text_is_a_position_not_a_pick(path):
    scn = load_scenario(path)
    r = plan(scn, draws=1500)
    snaps = load_snapshots()
    text = render_text(r, check_agency(scn, r.leader), snaps.get(scn.industry))
    assert not _prescriptive_hits(text), f"prescriptive wording: {_prescriptive_hits(text)}"
    assert any(s in text for s in ("conversions per krone", "sell out", "cost per sale"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_rendered_copy_uses_format_labels_never_keys(path):
    # Copy rule: user-facing text uses formats.yaml labels, never the raw keys.
    scn = load_scenario(path)
    r = plan(scn, draws=1500)
    text = render_text(r, check_agency(scn, r.leader), load_snapshots().get(scn.industry))
    assert not _format_key_hits(text), f"raw format key in copy: {_format_key_hits(text)}"


def test_every_output_carries_the_time_rule_and_breakeven_cost():
    # Headline = costs.format (short_video); the scenario's own human cost is placed.
    scn = load_scenario(ROOT / "scenarios" / "examples" / "local_gym.yaml")
    r = plan(scn, draws=1500)
    text = render_text(r, check_agency(scn, r.leader), None)
    assert TIME_NOTE in text                                   # the fixed time-rule line
    assert "Break-even production cost (the headline)" in text
    assert r.headline_format == "short_video"                  # costs.format drives the headline
    assert "Your cost of" in text and "sits" in text           # own cost placed automatically
    d = to_dict(r, check_agency(scn, r.leader), None)
    assert d["time_note"] == TIME_NOTE
    assert d["breakeven_cost"]["own_placement"] in ("above_both", "between", "below_both")


def test_response_lift_moves_into_a_detail_section_under_the_headline():
    # Production-cost break-even stays the headline; response-lift becomes detail,
    # placed after the matrix (lower than the headline break-even).
    scn = load_scenario(ROOT / "scenarios" / "examples" / "skincare_brand.yaml")
    text = render_text(plan(scn, draws=1200), None, None)
    assert "Detail — break-even as a response gap" in text
    assert text.index("Break-even production cost (the headline)") < text.index(
        "Detail — break-even as a response gap")


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_dict_is_json_serialisable_and_non_prescriptive(path):
    scn = load_scenario(path)
    r = plan(scn, draws=1500)
    d = to_dict(r, check_agency(scn, r.leader), load_snapshots().get(scn.industry))
    blob = json.dumps(d)                       # must serialise
    assert not _prescriptive_hits(blob)
    assert d["cells"] and d["position"] and d["confidence"] in ("low", "medium", "high")


def test_club_night_leads_with_both_sanity_flags():
    # The product's core job: say plainly when the budget cannot reach capacity and
    # when cost per sale exceeds value - ahead of the approach comparison.
    scn = load_scenario(ROOT / "scenarios" / "examples" / "club_night.yaml")
    r = plan(scn, draws=1500)
    text = render_text(r, check_agency(scn, r.leader), None)
    assert "of 300 sales" in text
    assert "above the ticket price for every approach" in text
    # Capacity unreachable here, so the wording is "lowest cost per sale", never "sell out".
    assert "lowest cost per sale" in text and "least to sell out" not in text
    pos = text.index("POSITION")
    assert text.index("of 300 sales") < text.index("delivers the lowest cost per sale", pos)


def test_unreachable_capacity_never_says_sell_out():
    for stem in ("club_night", "oslo_dinner"):
        scn = load_scenario(ROOT / "scenarios" / "examples" / f"{stem}.yaml")
        text = render_text(plan(scn, draws=1200), None, None)
        assert "least to sell out" not in text and "lowest cost per sale" in text


def test_breakeven_zero_lower_bound_has_its_own_wording():
    # local_gym's funnel break-even has a 0 lower bound: say so explicitly rather
    # than printing a misleading "likely 0 NOK - X".
    scn = load_scenario(ROOT / "scenarios" / "examples" / "local_gym.yaml")
    text = render_text(plan(scn, draws=2000), None, None)
    assert "doesn't match even at zero production cost" in text
    assert "likely 0 NOK" not in text


def test_planner_runs_fully_offline_with_no_token_and_no_snapshot(monkeypatch):
    # Zero-integration first run: no Ad Library token, no snapshot file -> the
    # planner still produces a full position.
    monkeypatch.delenv("META_AD_LIBRARY_TOKEN", raising=False)
    scn = load_scenario(EXAMPLES[0])
    r = plan(scn, draws=800)
    text = render_text(r, check_agency(scn, r.leader), snapshot=None)
    assert "POSITION" in text
    assert not _prescriptive_hits(text)

    # With an unpopulated snapshot, the market line is one quiet line, nothing else.
    from mediekjop.planner.snapshot import Snapshot
    empty = Snapshot(industry=scn.industry, market="Oslo nightlife", as_of=None,
                     n=0, status="awaiting_fetch", source="")
    assert "No market snapshot yet." in render_text(r, None, empty)


def test_web_page_files_are_non_prescriptive_when_built():
    # The Pyodide demo runs this same report.py in-browser; its static template and
    # committed example data must also be free of prescriptive copy.
    checked = 0
    for rel in ("web/planner.html", "web/planner_examples.json", "docs/planner.html"):
        p = ROOT / rel
        if p.exists():
            checked += 1
            hits = _prescriptive_hits(p.read_text(encoding="utf-8"))
            assert not hits, f"{rel} has prescriptive wording: {hits}"
    if checked == 0:
        pytest.skip("web demo not built yet")
