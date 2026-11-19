# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The loader proves a human approved this exact brief: it loads only on an interactive
human approve whose shown_hash still matches, and refuses a missing, fixture-mode,
or post-edit-stale Decision. No committed run may carry a fixture-mode Decision."""

from __future__ import annotations

import json

import pytest
from _fixtures import FIX, make_run, valid_brief_dict

from brief.approve import decide
from brief.loader import NotApproved, load_approved_brief
from brief.run import RUNS_DIR, load_run, write_decision
from schema import Decision


def _mint(run_dir, mode="interactive", outcome="approve", decided_by="joão") -> Decision:
    answers = json.loads((FIX / "approve_answers.json").read_text(encoding="utf-8"))
    answers["mode"] = mode
    answers["outcome"] = outcome
    return decide(load_run(run_dir), answers, decided_by)


def test_interactive_human_approval_loads(tmp_path):
    d = make_run(tmp_path)
    write_decision(d, _mint(d, mode="interactive"))
    assert load_approved_brief(d).envelope.id == "aurora-brief"


def test_no_decision_is_refused(tmp_path):
    d = make_run(tmp_path)
    with pytest.raises(NotApproved):
        load_approved_brief(d)


def test_fixture_mode_decision_is_refused(tmp_path):
    d = make_run(tmp_path)
    write_decision(d, _mint(d, mode="fixture"))
    with pytest.raises(NotApproved):
        load_approved_brief(d)


def test_brief_edited_after_approval_is_refused(tmp_path):
    d = make_run(tmp_path)
    write_decision(d, _mint(d, mode="interactive"))
    bd = valid_brief_dict()
    bd["objective"] = "something changed after the human approved"
    (d / "brief.json").write_text(json.dumps(bd, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(NotApproved):
        load_approved_brief(d)


def test_loader_refuses_a_failing_brief_even_if_checksjson_claims_pass(tmp_path):
    bad = valid_brief_dict()
    bad["proposition"] = "a premium studio look that earns 7 777 orders"   # naked number
    d = make_run(tmp_path, bad)
    write_decision(d, _mint(d, mode="interactive"))        # a (bypassed) human approval
    (d / "checks.json").write_text(json.dumps({"ok": True, "findings": []}), encoding="utf-8")
    with pytest.raises(NotApproved):
        load_approved_brief(d)


def test_no_committed_run_carries_a_fixture_mode_decision():
    for f in RUNS_DIR.glob("**/decision.json"):
        dec = Decision.model_validate_json(f.read_text(encoding="utf-8"))
        assert dec.mode.value != "fixture", f
