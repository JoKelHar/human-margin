# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Currency handling for the planner.

The planner runs every calculation in **NOK** and displays in the user's
currency, always alongside the rate and its date. Rates ship in
``data/fx/rates.yaml`` so the tool works offline; ``scripts/refresh_fx.py``
updates them from Norges Bank. A fallback flag records whether the rates are
live or the shipped approximations.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import repo_root

# The currencies the planner accepts (brief: NOK, EUR, USD, GBP).
SUPPORTED = ("NOK", "EUR", "USD", "GBP")


class CurrencyError(ValueError):
    """Raised for an unsupported currency or a missing rate."""


@dataclass(frozen=True)
class Money:
    """An amount in a specific currency."""

    amount: float
    currency: str

    def __post_init__(self) -> None:
        if self.currency not in SUPPORTED:
            raise CurrencyError(
                f"unsupported currency {self.currency!r}; use one of {', '.join(SUPPORTED)}")

    def __str__(self) -> str:
        return f"{self.amount:,.0f} {self.currency}"


@dataclass(frozen=True)
class FxRates:
    """NOK-per-unit rates with their quote date and a live/fallback flag."""

    rates: dict[str, float]
    as_of: dt.date
    is_fallback: bool
    source: str = ""

    def nok_per_unit(self, currency: str) -> float:
        if currency not in SUPPORTED:
            raise CurrencyError(f"unsupported currency {currency!r}")
        try:
            return float(self.rates[currency])
        except KeyError as e:
            raise CurrencyError(f"no FX rate for {currency} (as of {self.as_of})") from e

    # -- conversions (everything routes through NOK) ------------------------
    def to_nok(self, money: Money) -> float:
        return money.amount * self.nok_per_unit(money.currency)

    def from_nok(self, amount_nok: float, currency: str) -> Money:
        return Money(round(amount_nok / self.nok_per_unit(currency), 2), currency)

    def convert(self, money: Money, to_currency: str) -> Money:
        return self.from_nok(self.to_nok(money), to_currency)

    def note(self) -> str:
        """One line stating the rate basis, for display next to any converted figure."""
        kind = "fallback (not live)" if self.is_fallback else "Norges Bank"
        return f"FX as of {self.as_of} ({kind})"


def _rates_path() -> Path:
    return repo_root() / "data" / "fx" / "rates.yaml"


def load_fx_rates(path: str | Path | None = None) -> FxRates:
    """Load the shipped (or given) FX rates file."""
    p = Path(path) if path else _rates_path()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rates = {k: float(v) for k, v in (data.get("rates") or {}).items()}
    rates.setdefault("NOK", 1.0)
    as_of = data.get("as_of")
    if isinstance(as_of, str):
        as_of = dt.date.fromisoformat(as_of)
    elif not isinstance(as_of, dt.date):
        as_of = dt.date.today()
    return FxRates(
        rates=rates,
        as_of=as_of,
        is_fallback=bool(data.get("is_fallback", True)),
        source=str(data.get("source", "")),
    )
