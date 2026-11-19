# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The v0.1 contracts: construction, the Envelope requirement, the no-bare-numbers
rule, JSON round-trip, and that the committed JSON Schema is up to date."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schema import (
    SCHEMA_VERSION,
    Confidence,
    Context,
    Envelope,
    Figure,
    Goal,
    MadeBy,
    Position,
    Source,
    Status,
)
from schema.generate import JSON_DIR, schema_for
from schema.models import MODELS

TODAY = dt.date(2026, 11, 19)


def a_figure(value: float = 2.5, unit: str = "percent") -> Figure:
    return Figure(value=value, unit=unit, source=Source.assumption,
                  confidence=Confidence.low, as_of=TODAY)


def an_envelope() -> Envelope:
    return Envelope(made_by=MadeBy.agent, status=Status.draft)


def test_figure_requires_its_provenance_fields():
    f = a_figure()
    assert f.value == 2.5 and f.source is Source.assumption and f.as_of == TODAY
    with pytest.raises(ValidationError):           # unit / source / confidence / as_of required
        Figure(value=1.0)


def test_envelope_defaults_version_id_and_status():
    e = an_envelope()
    assert e.schema_version == SCHEMA_VERSION == "0.1"
    assert e.parent_ids == [] and e.status is Status.draft
    assert isinstance(e.id, str) and len(e.id) >= 8
    assert an_envelope().id != an_envelope().id      # unique per instance


def _context(envelope=None, **kw):
    return Context(brand="synthetic-brand", language="nb-NO", category="nightlife",
                   **({"envelope": envelope} if envelope is not None else {}), **kw)


def _goal(envelope=None, **kw):
    return Goal(objective="fill the room", kpi="tickets",
                target=a_figure(200, "tickets"), budget=a_figure(5000, "NOK"),
                horizon="4 weeks",
                **({"envelope": envelope} if envelope is not None else {}), **kw)


def _position(envelope=None, **kw):
    return Position(claim="the rate sits inside the usual range", figures=[a_figure()],
                    confidence=Confidence.low, what_would_change_it="a real client price",
                    **({"envelope": envelope} if envelope is not None else {}), **kw)


@pytest.mark.parametrize("build", [_context, _goal, _position])
def test_every_artefact_carries_an_envelope(build):
    art = build(an_envelope())
    assert art.envelope.made_by is MadeBy.agent
    with pytest.raises(ValidationError):           # envelope is required on every artefact
        build(None)


def test_no_bare_numbers_a_figure_is_required_where_a_number_would_go():
    # Goal.target/budget and Position.figures are typed as Figure, so a raw number
    # is rejected -- every quantity on an artefact must carry its unit and source.
    with pytest.raises(ValidationError):
        Goal(objective="o", kpi="k", target=200, budget=5000, horizon="h", envelope=an_envelope())
    with pytest.raises(ValidationError):
        Position(claim="c", figures=[1200], confidence=Confidence.low,
                 what_would_change_it="w", envelope=an_envelope())


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        Figure(value=1.0, unit="NOK", source=Source.own, confidence=Confidence.high,
               as_of=TODAY, currency="NOK")           # 'currency' is not a field


def test_json_round_trip_is_stable():
    pos = Position(claim="the rate sits inside the usual range",
                   figures=[a_figure(1200, "NOK"), a_figure(10, "tickets")],
                   confidence=Confidence.low,
                   what_would_change_it="a real client price for this brand",
                   envelope=Envelope(made_by=MadeBy.agent, status=Status.proposed,
                                     parent_ids=["abc123"]))
    again = Position.model_validate(json.loads(pos.model_dump_json()))
    assert again == pos


def test_committed_json_schema_is_up_to_date():
    for model in MODELS:
        path = JSON_DIR / f"{model.__name__.lower()}.json"
        assert path.exists(), f"missing generated schema: {path.name} (run schema/generate.py)"
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk == schema_for(model), \
            f"{path.name} is stale -- run: uv run python schema/generate.py"
