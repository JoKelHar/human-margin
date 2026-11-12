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
    assert "conversions per krone" in text or "sell out" in text


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_rendered_copy_uses_format_labels_never_keys(path):
    # Copy rule: user-facing text uses formats.yaml labels, never the raw keys.
    scn = load_scenario(path)
    r = plan(scn, draws=1500)
    text = render_text(r, check_agency(scn, r.leader), load_snapshots().get(scn.industry))
    assert not _format_key_hits(text), f"raw format key in copy: {_format_key_hits(text)}"


def test_every_output_carries_the_time_rule_and_breakeven_cost():
    scn = load_scenario(ROOT / "scenarios" / "examples" / "skincare_brand.yaml")
    r = plan(scn, draws=1500)
    text = render_text(r, check_agency(scn, r.leader), None)
    assert TIME_NOTE in text                                   # the fixed time-rule line
    assert "Break-even production cost" in text
    assert "matches AI at a production cost" in text
    assert "Including the longer-term brand effect" in text
    # skincare carries a human_quote, so a placement line is present.
    assert "Your quote of" in text and "sits" in text
    d = to_dict(r, check_agency(scn, r.leader), None)
    assert d["time_note"] == TIME_NOTE
    assert d["breakeven_cost"]["funnel_p50"] >= 0 and d["breakeven_cost"]["placement"] in (
        "above_both", "between", "below_both")


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
    pos = text.index("POSITION")
    assert text.index("of 300 sales") < text.index("costs the least to sell out", pos)


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
