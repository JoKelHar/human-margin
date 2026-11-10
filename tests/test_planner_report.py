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
from mediekjop.planner.report import PRESCRIPTIVE, render_text, to_dict
from mediekjop.planner.snapshot import load_snapshots

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "scenarios" / "examples").glob("*.yaml"))


def _prescriptive_hits(text: str) -> list[str]:
    low = text.lower()
    return [w for w in PRESCRIPTIVE if w in low]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_cli_text_is_a_position_not_a_pick(path):
    scn = load_scenario(path)
    r = plan(scn, draws=1500)
    snaps = load_snapshots()
    text = render_text(r, check_agency(scn, r.leader), snaps.get(scn.industry))
    assert not _prescriptive_hits(text), f"prescriptive wording: {_prescriptive_hits(text)}"
    assert "conversions per krone" in text or "sell out" in text


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_dict_is_json_serialisable_and_non_prescriptive(path):
    scn = load_scenario(path)
    r = plan(scn, draws=1500)
    d = to_dict(r, check_agency(scn, r.leader), load_snapshots().get(scn.industry))
    blob = json.dumps(d)                       # must serialise
    assert not _prescriptive_hits(blob)
    assert d["cells"] and d["position"] and d["confidence"] in ("low", "medium", "high")


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
