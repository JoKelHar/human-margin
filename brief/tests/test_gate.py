# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The gate: fixture-mode approval records a non-human Decision; it refuses without the
env flag and without a TTY; an un-acknowledged item blocks approval; approval needs the
maker word; reject needs a reason."""

from __future__ import annotations

import io
import json

import pytest
from _fixtures import FIX, make_run, valid_brief_dict

from brief.approve import GateError, _interactive_answers, _items, run_gate
from brief.run import load_decision, load_run


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


def test_interactive_shows_each_item_before_its_question(tmp_path):
    """The reviewer must see an item's full text (and the figures/thresholds up front)
    before being asked to accept it -- the bug this guards against was a blind y/n."""
    run = load_run(make_run(tmp_path))
    items = _items(run.brief)
    assert items, "fixture must have at least one item to acknowledge"
    # Accept every item (y + empty note), then reject with a reason.
    feed = "".join("y\n\n" for _ in items) + "reject\nnot now\n"
    out = io.StringIO()
    _interactive_answers(run, io.StringIO(feed), out)
    text = out.getvalue()

    # Figures table and stance thresholds are shown before any item.
    assert "Figures the brief may cite:" in text
    assert "Decide stance thresholds" in text
    assert text.index("Figures the brief may cite:") < text.index("Item 1 of")

    # Every item's full text appears before the acknowledgement prompt that follows it.
    cursor = 0
    for i, (kind, _ref, item_text) in enumerate(items, 1):
        prompt = ("Do you accept this assumption? (y/n):" if kind == "assumption"
                  else "Is this a fair, correctly stated question to leave open? (y/n):")
        pos_item = text.find(item_text, cursor)
        assert pos_item != -1, f"item {i} text not shown: {item_text!r}"
        pos_q = text.find(prompt, pos_item)
        assert pos_q > pos_item, f"item {i} question not shown after its text"
        assert f"Item {i} of {len(items)}:" in text
        cursor = pos_q + 1

    # The decision options are spelled out.
    assert "Decision (type one word: approve, edit or reject):" in text


def test_interactive_reprompts_on_bad_input_without_crashing(tmp_path):
    """Bad y/n and a bad decision word re-ask instead of crashing or guessing."""
    run = load_run(make_run(tmp_path))
    items = _items(run.brief)
    assert items
    lines = ["maybe", "y", ""]                 # first item: junk, then yes, empty note
    for _ in items[1:]:
        lines += ["y", ""]                     # remaining items: yes, empty note
    lines += ["banana", "reject", "scope too broad"]   # junk decision, then reject + reason
    out = io.StringIO()
    answers = _interactive_answers(run, io.StringIO("".join(s + "\n" for s in lines)), out)
    text = out.getvalue()
    assert "Please answer y or n" in text
    assert "Please type exactly one of: approve, edit, reject" in text
    assert answers["outcome"] == "reject"
    assert all(v["acknowledged"] for v in answers["acks"].values())


def test_item_prompts_are_worded_by_type(tmp_path):
    """Assumptions and open questions get their own acknowledgement wording."""
    run = load_run(make_run(tmp_path))
    items = _items(run.brief)
    kinds = {kind for kind, _ref, _text in items}
    feed = "".join("y\n\n" for _ in items) + "reject\nx\n"
    out = io.StringIO()
    _interactive_answers(run, io.StringIO(feed), out)
    text = out.getvalue()
    if "assumption" in kinds:
        assert "Do you accept this assumption? (y/n):" in text
    if "open_question" in kinds:
        assert "Is this a fair, correctly stated question to leave open? (y/n):" in text


def test_figures_table_marks_calculated_and_drops_duplicate_goal(tmp_path):
    """Break-even and its ratio show source 'calculated'; the duplicate goal figure is gone."""
    run = load_run(make_run(tmp_path))
    items = _items(run.brief)
    feed = "".join("y\n\n" for _ in items) + "reject\nx\n"
    out = io.StringIO()
    _interactive_answers(run, io.StringIO(feed), out)
    text = out.getvalue()
    lines = text.splitlines()
    # The two figures derived from assumptions are labelled 'calculated'.
    for name in ("human-margin break-even", "break-even as a share of the goal"):
        row = next((ln for ln in lines if name in ln), None)
        assert row is not None, f"figure row not shown: {name!r}"
        assert "calculated" in row, f"derived figure not labelled calculated: {row!r}"
    # A plain assumption still reads 'assumption'.
    quote = next((ln for ln in lines if "human production quote" in ln), None)
    assert quote and "assumption" in quote
    # The duplicate goal figure is dropped (goal.target already shown once).
    assert "goal: target sales" not in text, "duplicate goal figure should be dropped"


def test_reject_requires_a_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIEF_ALLOW_NONINTERACTIVE", "1")
    d = make_run(tmp_path)
    with pytest.raises(GateError):
        run_gate(d, from_file=_answers(tmp_path, outcome="reject", reason=None), decided_by="x")
    dec = run_gate(d, from_file=_answers(tmp_path, outcome="reject", reason="scope too broad"),
                   decided_by="x")
    assert dec.outcome.value == "reject"
