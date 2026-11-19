# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The no-naked-numbers engine: kr/percent incl. Norwegian formats, ranges, rounding to
the token's own precision, number words, multipliers, unit-compatible counts, and years
only in a date context."""

from __future__ import annotations

import pytest

from brief.numbers import unmatched

FIGS = [(90000.0, "NOK"), (800.0, "NOK"), (2500.0, "NOK"), (36.0, "orders"),
        (90.0, "orders"), (20000.0, "NOK"), (150000.0, "NOK"), (40.0, "percent")]


@pytest.mark.parametrize("text", [
    "about kr 90 000,- for the shoot",          # Norwegian "kr …,-"
    "a 2.500 kr value per order",               # Norwegian "." thousands
    "a 40 % share of the goal",                 # percent
    "needs 36 more orders",                     # bare count, right unit
    "the band runs 20 000-150 000 kr",          # range, both endpoints present
    "closes in 2026",                           # year in date context
])
def test_clean_numbers_pass(text):
    assert unmatched(text, FIGS) == []


@pytest.mark.parametrize("text,figs", [
    ("around 43 percent", [(42.5, "percent")]),   # rounds to integer
    ("about 40%", [(42.5, "percent")]),            # rounds to nearest ten
])
def test_rounding_to_token_precision_passes(text, figs):
    assert unmatched(text, figs) == []


@pytest.mark.parametrize("text,figs", [
    ("exactly 42.47%", [(42.5, "percent")]),       # invented precision
    ("spend 7 777 kr", FIGS),                      # invented number
    ("the shoot costs 40 kr", FIGS),               # wrong unit (40 is a percent figure)
    ("needs 36 memberships", FIGS),                # value matches, unit does not
    ("a studio shot can double the orders", FIGS), # multiplier with no backing figure
    ("reach 2030 orders", FIGS),                   # bare 4-digit, not a date
    ("the band 20 000-999 999 kr", FIGS),          # one range endpoint missing
    ("runs to kr 7.777,-", FIGS),                  # Norwegian format, no match
])
def test_naked_numbers_are_flagged(text, figs):
    assert unmatched(text, figs), f"expected a naked number in {text!r}"
