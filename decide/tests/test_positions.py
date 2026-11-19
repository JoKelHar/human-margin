# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Decide's outputs map onto the shared Position contract.

For every golden case (all buying, ai-options and creator cases), map Decide's
existing output onto a :class:`schema.Position` and assert it validates. Every number
in the output is wrapped as a :class:`schema.Figure`, so the resulting Position holds
no bare numbers -- the only raw numbers left are each Figure's ``value``.

This maps Decide's output only. It does not call or change Decide's maths: the golden
files are exactly what ``decide.compute`` produces, pinned by the parity tests.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from schema import Confidence, Envelope, Figure, MadeBy, Position, Source, Status

DECIDE = Path(__file__).resolve().parents[1]
GOLDEN = DECIDE / "tests" / "golden"
TODAY = dt.date(2026, 11, 19)

# A string that is nothing but a number, optionally space-grouped and unit-suffixed:
# "10", "3 500", "1 200 kr", "40%", "2.5". Prose that merely contains a number is not
# matched -- that text becomes the Position's claim, not a Figure.
_NUM_STR = re.compile(r"^\s*(\d[\d  ]*(?:[.,]\d+)?)\s*(kr|%)?\s*$")


def _unit_for(key: str | None, suffix: str | None) -> str:
    if suffix == "kr":
        return "NOK"
    if suffix == "%":
        return "percent"
    k = (key or "").lower()
    if any(t in k for t in ("price", "cost", "budget", "margin", "kr", "spend")):
        return "NOK"
    if any(t in k for t in ("pct", "percent", "share", "fraction")):
        return "percent"
    return "count"


def _figure(value: float, key: str | None, suffix: str | None, ref: str) -> Figure:
    return Figure(value=float(value), unit=_unit_for(key, suffix), source=Source.assumption,
                  confidence=Confidence.low, as_of=TODAY, ref=ref)


def _wrap_numbers(obj, key: str | None = None, ref: str = "$") -> list[Figure]:
    """Every number in `obj` (real int/float, or a string that is purely a number)
    becomes a Figure. Booleans and prose strings are left for the claim text."""
    figures: list[Figure] = []
    if isinstance(obj, bool):
        return figures
    if isinstance(obj, (int, float)):
        figures.append(_figure(obj, key, None, ref))
    elif isinstance(obj, str):
        m = _NUM_STR.match(obj)
        if m:
            num = float(m.group(1).replace(" ", "").replace(" ", "").replace(",", "."))
            figures.append(_figure(num, key, m.group(2), ref))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            figures.extend(_wrap_numbers(v, k, f"{ref}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            figures.extend(_wrap_numbers(v, key, f"{ref}[{i}]"))
    return figures


def _first_claim(obj) -> str:
    """A representative sentence from the output for the Position's claim."""
    if isinstance(obj, dict):
        for k in ("text", "big", "title", "label"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip() and not _NUM_STR.match(v):
                return v
        for v in obj.values():
            c = _first_claim(v)
            if c:
                return c
    elif isinstance(obj, list):
        for v in obj:
            c = _first_claim(v)
            if c:
                return c
    return ""


def _numeric_leaf_paths(obj, path: str = "$") -> list[str]:
    """Paths of every raw number in a dumped model -- to prove they all sit in a Figure."""
    out: list[str] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        return [path]
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_numeric_leaf_paths(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_numeric_leaf_paths(v, f"{path}[{i}]"))
    return out


def _position_from(output: dict) -> Position:
    figures = _wrap_numbers(output)
    return Position(
        claim=_first_claim(output) or "Decide position",
        figures=figures,
        confidence=Confidence.low,                 # Decide's figures are assumption-based
        what_would_change_it=("real campaign data for this brand -- the account's own "
                              "conversion rate, CPM and client prices -- replacing the "
                              "assumed ranges"),
        envelope=Envelope(made_by=MadeBy.agent, status=Status.draft),
    )


def _cases(name: str) -> list[dict]:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


ALL_CASES = (
    [("buying", c) for c in _cases("budget_check.json")]
    + [("ai_options", c) for c in _cases("ai_options.json")]
    + [("creator", c) for c in _cases("creator.json")]
)


def test_there_are_cases_from_every_suite():
    suites = {s for s, _ in ALL_CASES}
    assert suites == {"buying", "ai_options", "creator"}
    assert len(ALL_CASES) == 56 + 24 + 24            # tracks the parity runner's counts


@pytest.mark.parametrize("suite,case", ALL_CASES,
                         ids=[f"{s}-{i}" for i, (s, _) in enumerate(ALL_CASES)])
def test_decide_output_validates_as_a_position(suite, case):
    output = case["output"]
    pos = _position_from(output)

    # It is a valid Position and survives a JSON round-trip.
    again = Position.model_validate(json.loads(pos.model_dump_json()))
    assert again == pos

    # Every number Decide emitted is wrapped: the count matches, and in the dumped
    # Position every raw number sits inside a figure's `value` (no bare numbers).
    assert len(pos.figures) == len(_wrap_numbers(output))
    dumped = pos.model_dump(mode="python")
    for p in _numeric_leaf_paths(dumped):
        assert p.endswith(".value") and ".figures[" in p, f"bare number at {p}"
