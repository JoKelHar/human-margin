# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The brief checks: the valid fixture passes all five; each failing fixture fails its
named check (invented number, wrong unit, rounding, multiplier, bare year, Norwegian
format, bare-count unit, unflagged Norwegian line, maker mismatch, missing AI labelling)."""

from __future__ import annotations

from _fixtures import inputs_models, load_json, valid_brief_dict

from brief.checks import check_brief
from schema import Brief


def test_valid_brief_passes_all_checks():
    ctx, goal, pos = inputs_models()
    rep = check_brief(Brief.model_validate(valid_brief_dict()), ctx, goal, pos)
    assert rep.ok, rep.to_dict()
    assert {f.check for f in rep.findings} == \
        {"schema", "no_naked_numbers", "maker_match", "native_review", "ai_labelling"}


def test_ai_labelling_is_a_default_mandatory_for_ai_and_hybrid():
    ctx, goal, pos = inputs_models()
    base = valid_brief_dict()
    no_label = [{"id": "retouch_label", "text": "altered-body ads carry the label."}]

    def run(maker, deliverable_maker, mandatories):
        b = {**base,
             "maker_recommendation": {**base["maker_recommendation"], "maker": maker},
             "deliverables": [{"format": "static", "count": 1, "maker": deliverable_maker}],
             "mandatories": mandatories}
        # Keep the maker check happy when we flip the recommendation away from Decide's ai.
        if maker != "ai":
            b["open_questions"] = base["open_questions"] + [
                f"maker {maker} differs from Decide's stance; why we diverge"]
        rep = check_brief(Brief.model_validate(b), ctx, goal, pos)
        return next(f for f in rep.findings if f.check == "ai_labelling").ok

    # AI and hybrid briefs must carry a labelling mandatory.
    assert run("ai", "ai", no_label) is False
    assert run("hybrid", "hybrid", no_label) is False
    assert run("ai", "ai", base["mandatories"]) is True
    # A hybrid where only a deliverable is AI still needs it.
    assert run("human", "ai", no_label) is False
    # A fully human brief does not.
    assert run("human", "human", no_label) is True


def test_each_failing_fixture_fails_its_named_check():
    ctx, goal, pos = inputs_models()
    valid = valid_brief_dict()
    cases = load_json("failing_cases.json")
    assert len(cases) >= 9
    for case in cases:
        rep = check_brief(Brief.model_validate({**valid, **case["patch"]}), ctx, goal, pos)
        failed = {f.check for f in rep.findings if not f.ok}
        assert not rep.ok, case["name"]
        assert case["check"] in failed, f"{case['name']}: expected {case['check']}, got {failed}"
