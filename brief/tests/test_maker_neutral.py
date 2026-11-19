# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The checks are maker-neutral: the same rules apply whether the brief commits to ai,
human or hybrid. A clean brief passes for every maker; an invented number fails for
every maker. The AI brief commits to AI as firmly as the human brief commits to human."""

from __future__ import annotations

import pytest
from _fixtures import inputs_models, valid_brief_dict

from brief.checks import check_brief
from schema import Brief


def _with_maker(maker: str) -> dict:
    bd = valid_brief_dict()
    bd["maker_recommendation"] = {**bd["maker_recommendation"], "maker": maker}
    if maker != "ai":   # diverging from Decide's ai stance must be explained
        bd["open_questions"] = bd["open_questions"] + [
            f"this brief differs from Decide's stance; {maker} chosen deliberately"]
    return bd


@pytest.mark.parametrize("maker", ["ai", "human", "hybrid"])
def test_clean_brief_passes_for_every_maker(maker):
    ctx, goal, pos = inputs_models()
    rep = check_brief(Brief.model_validate(_with_maker(maker)), ctx, goal, pos)
    assert rep.ok, (maker, rep.to_dict())


@pytest.mark.parametrize("maker", ["ai", "human", "hybrid"])
def test_invented_number_fails_for_every_maker(maker):
    ctx, goal, pos = inputs_models()
    bd = _with_maker(maker)
    bd["proposition"] = "a premium studio look that earns 7 777 orders"
    rep = check_brief(Brief.model_validate(bd), ctx, goal, pos)
    assert not rep.ok
    assert any(f.check == "no_naked_numbers" and not f.ok for f in rep.findings)
