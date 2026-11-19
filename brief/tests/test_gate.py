# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The gate: fixture-mode approval records a non-human Decision; it refuses without the
env flag and without a TTY; an un-acknowledged item blocks approval; approval needs the
maker word; reject needs a reason."""

from __future__ import annotations

import json

import pytest
from _fixtures import FIX, make_run, valid_brief_dict

from brief.approve import GateError, run_gate
from brief.run import load_decision


class _NoTTY:
    def isatty(self):
        return False

    def readline(self):
        return ""


def _answers(tmp_path, **over):
    a = json.loads((FIX / "approve_answers.json").read_text(encoding="utf-8"))
    a.update(over)
    p = tmp_path / "answers.json"
    p.write_text(json.dumps(a), encoding="utf-8")
    return p


def test_fixture_mode_approves_and_records_a_non_human_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIEF_ALLOW_NONINTERACTIVE", "1")
    d = make_run(tmp_path)
    dec = run_gate(d, from_file=FIX / "approve_answers.json", decided_by="joão")
    assert dec.outcome.value == "approve"
    assert dec.mode.value == "fixture" and dec.decided_by == "fixture"
    assert dec.shown_hash and all(a.acknowledged for a in dec.acknowledgements)
    assert load_decision(d) is not None


def test_fixture_mode_needs_the_env_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("BRIEF_ALLOW_NONINTERACTIVE", raising=False)
    d = make_run(tmp_path)
    with pytest.raises(GateError):
        run_gate(d, from_file=FIX / "approve_answers.json", decided_by="x")


def test_interactive_refuses_without_a_tty(tmp_path):
    d = make_run(tmp_path)
    with pytest.raises(GateError):
        run_gate(d, from_file=None, decided_by="x", stdin=_NoTTY())


def test_unacknowledged_item_blocks_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIEF_ALLOW_NONINTERACTIVE", "1")
    d = make_run(tmp_path)
    a = json.loads((FIX / "approve_answers.json").read_text(encoding="utf-8"))
    a["acks"][next(iter(a["acks"]))]["acknowledged"] = False
    p = tmp_path / "ans.json"
    p.write_text(json.dumps(a), encoding="utf-8")
    with pytest.raises(GateError):
        run_gate(d, from_file=p, decided_by="x")


def test_approval_requires_the_maker_word(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIEF_ALLOW_NONINTERACTIVE", "1")
    d = make_run(tmp_path)
    with pytest.raises(GateError):
        run_gate(d, from_file=_answers(tmp_path, maker_word="human"), decided_by="x")


def test_gate_refuses_a_failing_brief_even_if_checksjson_claims_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIEF_ALLOW_NONINTERACTIVE", "1")
    bad = valid_brief_dict()
    bad["proposition"] = "a premium studio look that earns 7 777 orders"   # naked number
    d = make_run(tmp_path, bad)
    (d / "checks.json").write_text(json.dumps({"ok": True, "findings": []}), encoding="utf-8")
    with pytest.raises(GateError):
        run_gate(d, from_file=FIX / "approve_answers.json", decided_by="x")


def test_reject_requires_a_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIEF_ALLOW_NONINTERACTIVE", "1")
    d = make_run(tmp_path)
    with pytest.raises(GateError):
        run_gate(d, from_file=_answers(tmp_path, outcome="reject", reason=None), decided_by="x")
    dec = run_gate(d, from_file=_answers(tmp_path, outcome="reject", reason="scope too broad"),
                   decided_by="x")
    assert dec.outcome.value == "reject"
