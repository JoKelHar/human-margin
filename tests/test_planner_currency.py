# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Planner Phase 1: currency handling (NOK-internal, dated rates, fallback)."""

from __future__ import annotations

import datetime as dt

import pytest

from mediekjop.planner.currency import CurrencyError, FxRates, Money, load_fx_rates

FX = FxRates(rates={"NOK": 1.0, "EUR": 11.7, "USD": 10.8, "GBP": 13.6},
             as_of=dt.date(2026, 1, 1), is_fallback=True)


def test_money_rejects_unsupported_currency():
    with pytest.raises(CurrencyError):
        Money(100, "SEK")


def test_to_nok_and_back():
    assert FX.to_nok(Money(100, "EUR")) == 1170
    back = FX.from_nok(1170, "EUR")
    assert back.amount == 100 and back.currency == "EUR"


def test_convert_between_currencies_via_nok():
    usd = FX.convert(Money(100, "EUR"), "USD")
    assert usd.currency == "USD"
    assert round(usd.amount, 2) == round(1170 / 10.8, 2)


def test_missing_rate_raises():
    thin = FxRates(rates={"NOK": 1.0}, as_of=dt.date(2026, 1, 1), is_fallback=True)
    with pytest.raises(CurrencyError):
        thin.nok_per_unit("EUR")


def test_shipped_rates_load_and_flag():
    fx = load_fx_rates()
    assert fx.nok_per_unit("NOK") == 1.0
    assert fx.nok_per_unit("EUR") > 1
    assert isinstance(fx.is_fallback, bool)
    assert "FX as of" in fx.note()
