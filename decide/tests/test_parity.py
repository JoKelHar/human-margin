# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""JS/Python parity: the plain-JS budget core must match the Python golden exactly,
and the budget page's copy must stay a position, not advice."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mediekjop.planner.report import PRESCRIPTIVE

ROOT = Path(__file__).resolve().parents[1]          # the decide/ app root
REPO = Path(__file__).resolve().parents[2]           # repo root (GitHub Pages serves /docs from here)


def _prescriptive_hits(text: str) -> list[str]:
    low = text.lower()
    return [w for w in PRESCRIPTIVE if w in low]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_matches_python_golden_and_url_round_trips():
    # Runs decide/build/parity_node.js: asserts budget-core.js reproduces every
    # golden case from Python and that URL encode/decode is stable.
    proc = subprocess.run(["node", str(ROOT / "build" / "parity_node.js")],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "OK:" in proc.stdout


def test_budget_page_and_core_are_non_prescriptive_when_built():
    checked = 0
    targets = [(ROOT, "web/budget.html"), (ROOT, "web/budget-core.js"),
               (REPO, "docs/budget.html"), (REPO, "docs/budget-core.js")]
    for base, rel in targets:
        p = base / rel
        if p.exists():
            checked += 1
            hits = _prescriptive_hits(p.read_text(encoding="utf-8"))
            assert not hits, f"{rel} has prescriptive wording: {hits}"
    if checked == 0:
        pytest.skip("budget page not built yet")
