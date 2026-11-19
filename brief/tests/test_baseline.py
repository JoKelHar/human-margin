# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The baseline checker runs the text checks (no-naked-numbers, native-review) on an
unstructured plain-Claude draft and marks the structural checks (schema, maker field)
n/a -- never as failures."""

from __future__ import annotations

import json

from brief.baseline import check_baseline, write_baseline


def _draft(tmp_path, text: str, name: str = "draft.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _finding(report, check):
    return next(f for f in report["findings"] if f["check"] == check)


def test_structural_checks_are_na_not_failures(tmp_path):
    p = _draft(tmp_path, "launch for 90 orders on 40 000 kr")
    rep = check_baseline("aurora", p)
    assert rep["not_applicable"] == ["schema", "maker_match"]
    assert _finding(rep, "schema")["ok"] and _finding(rep, "maker_match")["ok"]
    assert "n/a" in _finding(rep, "schema")["detail"]


def test_backed_numbers_and_no_norwegian_pass(tmp_path):
    p = _draft(tmp_path, "Aim for 90 orders on a 40 000 kr budget at 2 500 kr per order.")
    rep = check_baseline("aurora", p)
    assert _finding(rep, "no_naked_numbers")["ok"]
    assert _finding(rep, "native_review")["ok"]
    assert rep["ok"]


def test_invented_number_is_flagged(tmp_path):
    p = _draft(tmp_path, "We will drive 5 000 orders fast.")
    rep = check_baseline("aurora", p)
    assert not _finding(rep, "no_naked_numbers")["ok"]


def test_norwegian_copy_is_surfaced_for_review(tmp_path):
    p = _draft(tmp_path, "Ren glød, laget for huden din")
    rep = check_baseline("aurora", p)
    assert not _finding(rep, "native_review")["ok"]


def test_write_baseline_emits_checks_json(tmp_path, monkeypatch):
    # Redirect RUNS_DIR so the test does not touch committed runs.
    import brief.baseline as B
    monkeypatch.setattr(B, "RUNS_DIR", tmp_path)
    p = _draft(tmp_path, "90 orders on 40 000 kr")
    B.write_baseline("aurora", p)
    out = json.loads((tmp_path / "aurora" / "baseline" / "checks.json").read_text(encoding="utf-8"))
    assert set(out["not_applicable"]) == {"schema", "maker_match"}
