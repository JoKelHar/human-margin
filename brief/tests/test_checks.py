# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The brief checks: the valid fixture passes all four; each failing fixture fails its
named check (invented number, wrong unit, rounding, multiplier, bare year, Norwegian
format, bare-count unit, unflagged Norwegian line, maker mismatch)."""

from __future__ import annotations

from _fixtures import inputs_models, load_json, valid_brief_dict

from brief.checks import check_brief
from schema import Brief


def test_valid_brief_passes_all_checks():
    ctx, goal, pos = inputs_models()
    rep = check_brief(Brief.model_validate(valid_brief_dict()), ctx, goal, pos)
    assert rep.ok, rep.to_dict()
    assert {f.check for f in rep.findings} == \
        {"schema", "no_naked_numbers", "maker_match", "native_review"}


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
