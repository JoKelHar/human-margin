# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Refresh data/fx/rates.yaml from Norges Bank's open exchange-rate data.

Opt-in: the planner ships with fallback rates and works offline; run this only
to update them. It fetches the latest NOK-per-unit quote for EUR, USD and GBP,
writes the file with the quote date and clears the fallback flag. On any network
error it leaves the existing file untouched and says so.

    uv run python scripts/refresh_fx.py
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATES = ROOT / "data" / "fx" / "rates.yaml"
CURRENCIES = ("EUR", "USD", "GBP")
API = "https://data.norges-bank.no/api/data/EXR/B.{cur}.NOK.SP?format=csv&lastNObservations=1"


def _fetch_one(cur: str) -> tuple[float, dt.date]:
    url = API.format(cur=cur)
    with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310 (fixed, trusted host)
        text = resp.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    row = next(reader)
    # Column names vary slightly; find the observation value and date.
    value = next(v for k, v in row.items() if k.upper() in ("OBS_VALUE", "VALUE"))
    date = next(v for k, v in row.items() if k.upper() in ("TIME_PERIOD", "TIME"))
    return float(value.replace(",", ".")), dt.date.fromisoformat(date)


def main() -> None:
    try:
        rates = {"NOK": 1.0}
        as_of = dt.date.today()
        for cur in CURRENCIES:
            rate, date = _fetch_one(cur)
            rates[cur] = round(rate, 4)
            as_of = max(as_of, date) if date else as_of
    except Exception as e:  # noqa: BLE001 - any network/parse failure leaves the file as-is
        raise SystemExit(f"Could not refresh FX from Norges Bank ({e}); existing {RATES} kept.")

    lines = [
        "# Refreshed from Norges Bank's open exchange-rate data by scripts/refresh_fx.py.",
        "# NOK per 1 unit of the given currency.",
        f"as_of: {as_of.isoformat()}",
        'source: "Norges Bank (data.norges-bank.no)"',
        "is_fallback: false",
        "",
        "rates:",
    ] + [f"  {cur}: {rates[cur]}" for cur in ("NOK", *CURRENCIES)]
    RATES.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {RATES.relative_to(ROOT)} (as of {as_of}): "
          + ", ".join(f"{c} {rates[c]}" for c in CURRENCIES))


if __name__ == "__main__":
    main()
