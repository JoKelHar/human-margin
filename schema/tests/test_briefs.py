# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Brief and Decision (schema v0.2): construction, the human-only Decision rule,
fixture-mode provenance, the reason requirement, no-bare-numbers typing, round-trip,
and that schema/json/ for the two new models is current."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from pydantic import ValidationError

from schema import (
    Acknowledgement,
    Brief,
    Confidence,
    CopyLine,
    Decision,
    DecisionMode,
    Deliverable,
    Envelope,
    Figure,
    Maker,
    MadeBy,
    MakerRecommendation,
    Mandatory,
    Outcome,
    Source,
    Status,
)
from schema.briefs import BRIEF_MODELS
from schema.generate import JSON_DIR, schema_for

TODAY = dt.date(2026, 11, 19)


def a_figure(value=1500, unit="NOK", source=Source.own):
    return Figure(value=value, unit=unit, source=source, confidence=Confidence.low, as_of=TODAY)


def an_assumption(value=250, unit="count"):
    return a_figure(value, unit, source=Source.assumption)


def a_brief(**over) -> Brief:
    kw = dict(
        objective="fill mid-week courses", audience="adults 25-45 near Bergen",
        insight="people book a course when a friend already has", proposition="learn it together",
        maker_recommendation=MakerRecommendation(maker=Maker.human, position_id="pos123",
                                                 rationale="the human premium clears easily"),
        deliverables=[Deliverable(format="video", count=3, maker=Maker.human)],
        mandatories=[Mandatory(id="ai_disclosure", text="label AI-made assets")],
        tone="warm, plain", budget=a_figure(40000), success_measure=a_figure(250, "bookings"),
        hypothesis="a friend-referral angle lifts sign-ups vs a generic promo",
        copy_lines=[CopyLine(text="Ta kurset sammen", language="nb-NO", needs_native_review=True)],
        assumptions=[an_assumption()], open_questions=["is the goal reachable on this budget?"],
        envelope=Envelope(made_by=MadeBy.agent, status=Status.proposed),
    )
    kw.update(over)
    return Brief(**kw)


def a_decision(**over) -> Decision:
    kw = dict(
        target_id="brief123", outcome=Outcome.approve, reason=None, edits=None,
        decided_by="joão", timestamp=dt.datetime(2026, 11, 19, 20, 0),
        mode=DecisionMode.interactive, shown_hash="deadbeef",
        acknowledgements=[Acknowledgement(item_type="assumption", item_ref="h1", acknowledged=True)],
        envelope=Envelope(made_by=MadeBy.human, status=Status.approved),
    )
    kw.update(over)
    return Decision(**kw)


def test_brief_constructs_and_carries_an_envelope():
    b = a_brief()
    assert b.envelope.status is Status.proposed and b.maker_recommendation.maker is Maker.human
    with pytest.raises(ValidationError):
        a_brief(envelope=None)


def test_brief_assumptions_must_be_source_assumption():
    with pytest.raises(ValidationError):
        a_brief(assumptions=[a_figure(250, "count", source=Source.own)])


def test_brief_budget_and_success_measure_are_figures_not_bare_numbers():
    with pytest.raises(ValidationError):
        a_brief(budget=40000)
    with pytest.raises(ValidationError):
        a_brief(success_measure=250)


def test_decision_must_be_made_by_human():
    with pytest.raises(ValidationError):
        a_decision(envelope=Envelope(made_by=MadeBy.agent, status=Status.approved))


def test_fixture_mode_forces_decided_by_fixture():
    # fixture mode with a human name is rejected ...
    with pytest.raises(ValidationError):
        a_decision(mode=DecisionMode.fixture, decided_by="joão")
    # ... and is accepted only as decided_by='fixture'.
    d = a_decision(mode=DecisionMode.fixture, decided_by="fixture")
    assert d.mode is DecisionMode.fixture and d.decided_by == "fixture"


@pytest.mark.parametrize("outcome", [Outcome.reject, Outcome.edit])
def test_reject_and_edit_require_a_reason(outcome):
    with pytest.raises(ValidationError):
        a_decision(outcome=outcome, reason=None)
    assert a_decision(outcome=outcome, reason="scope too broad").reason


def test_round_trip():
    b = a_brief()
    assert Brief.model_validate(json.loads(b.model_dump_json())) == b
    d = a_decision(outcome=Outcome.reject, reason="not now")
    assert Decision.model_validate(json.loads(d.model_dump_json())) == d


def test_committed_json_schema_is_up_to_date():
    for model in BRIEF_MODELS:
        path = JSON_DIR / f"{model.__name__.lower()}.json"
        assert path.exists(), f"missing {path.name} (run schema/generate.py)"
        assert json.loads(path.read_text(encoding="utf-8")) == schema_for(model), \
            f"{path.name} is stale -- run: uv run python schema/generate.py"
