# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Benchmark library: load, validate, query and market-similarity weighting.

The library (``data/benchmarks/benchmarks.yaml``) is a versioned set of cited
figures. This module loads and validates it (every real figure must cite a
source; only labelled ``D`` assumptions may omit a URL), queries it by
metric/industry/channel/band, and blends matching figures into one estimate,
weighting each by how similar its market is to Norway (``weights.yaml``) and by
its quality grade. Price-dependent metrics are purchasing-power normalised first.

The estimate reports which markets it drew on, an overall grade and whether any
figure is stale (older than 18 months), so the planner can be honest about how
much the number rests on Norwegian data versus proxies.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import repo_root

REQUIRED = ("metric", "industry", "price_band", "channel", "geography",
            "value", "unit", "source_name", "published", "quality")
QUALITY_WEIGHT = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.3}
STALE_MONTHS = 18


class BenchmarkError(ValueError):
    """Raised for a malformed library entry (missing fields or uncited figure)."""


def _bench_path() -> Path:
    return repo_root() / "data" / "benchmarks" / "benchmarks.yaml"


def _weights_path() -> Path:
    return repo_root() / "config" / "planner" / "weights.yaml"


def load_weights(path: str | Path | None = None) -> dict:
    p = Path(path) if path else _weights_path()
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def load_benchmarks(path: str | Path | None = None) -> list[dict]:
    p = Path(path) if path else _bench_path()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = data.get("benchmarks") or []
    for i, e in enumerate(rows):
        missing = [k for k in REQUIRED if k not in e]
        if missing:
            raise BenchmarkError(f"benchmark {i} missing field(s): {missing}")
        if e["quality"] not in QUALITY_WEIGHT:
            raise BenchmarkError(f"benchmark {i}: bad quality {e['quality']!r}")
        # Provenance: a real figure must cite a source URL; only a labelled D
        # assumption may omit it (and must explain itself in notes).
        if not e.get("source_url") and e["quality"] != "D":
            raise BenchmarkError(f"benchmark {i} ({e['metric']}): no source_url and not a labelled assumption")
        if "point" not in (e.get("value") or {}):
            raise BenchmarkError(f"benchmark {i}: value needs a 'point'")
        if isinstance(e["published"], str):
            e["published"] = dt.date.fromisoformat(e["published"])
    return rows


def market_weight(geography: str, weights: dict) -> float:
    gw = (weights.get("geography_weight") or {}).get(geography)
    return float(gw["weight"]) if gw else 0.3


def is_stale(entry: dict, as_of: dt.date | None = None, months: int = STALE_MONTHS) -> bool:
    as_of = as_of or dt.date.today()
    return entry["published"] < as_of - dt.timedelta(days=months * 30)


def _applies(e: dict, metric: str, industry: str, channel: str, band: str) -> bool:
    if e["metric"] != metric:
        return False

    def ok(field: str, q: str) -> bool:
        return q == "any" or e[field] in (q, "any")

    return ok("industry", industry) and ok("channel", channel) and ok("price_band", band)


def _specificity(e: dict, industry: str, channel: str) -> int:
    s = 0
    if industry != "any" and e["industry"] == industry:
        s += 2
    if channel != "any" and e["channel"] == channel:
        s += 1
    return s


def _norm_price_level(value: float, geography: str, weights: dict) -> float:
    pl = weights.get("price_level_vs_norway") or {}
    g = pl.get(geography, pl.get("global", 0.7))
    no = pl.get("NO", 1.0)
    return value * (no / g) if g else value


@dataclass
class Estimate:
    metric: str
    low: float
    point: float
    high: float
    unit: str
    markets: list[str]     # geographies the estimate drew on
    grade: str             # overall A..D from the weighted evidence
    n_sources: int
    any_stale: bool


def estimate(metric: str, industry: str = "any", channel: str = "any", band: str = "any", *,
             benchmarks: list[dict] | None = None, weights: dict | None = None,
             as_of: dt.date | None = None) -> Estimate | None:
    """Blend matching benchmarks into one market-weighted estimate, or None."""
    rows = benchmarks if benchmarks is not None else load_benchmarks()
    wcfg = weights if weights is not None else load_weights()
    price_dependent = set(wcfg.get("price_dependent_metrics") or [])

    matches = [e for e in rows if _applies(e, metric, industry, channel, band)]
    if not matches:
        return None
    # Prefer the most specific figures when industry/channel-specific ones exist.
    max_spec = max(_specificity(e, industry, channel) for e in matches)
    if max_spec > 0:
        matches = [e for e in matches if _specificity(e, industry, channel) == max_spec]

    tot_w = low = point = high = 0.0
    qsum = mwsum = 0.0
    markets: set[str] = set()
    stale = False
    unit = matches[0]["unit"]
    for e in matches:
        mw = market_weight(e["geography"], wcfg)
        w = mw * QUALITY_WEIGHT[e["quality"]]
        if w <= 0:
            continue
        v = e["value"]
        norm = (lambda x: _norm_price_level(x, e["geography"], wcfg)) if metric in price_dependent else (lambda x: x)
        low += norm(v.get("low", v["point"])) * w
        point += norm(v["point"]) * w
        high += norm(v.get("high", v["point"])) * w
        tot_w += w
        qsum += QUALITY_WEIGHT[e["quality"]] * mw
        mwsum += mw
        markets.add(e["geography"])
        stale = stale or is_stale(e, as_of)
    if tot_w == 0:
        return None

    wq = qsum / mwsum if mwsum else 0.0
    grade = "A" if wq >= 0.9 else "B" if wq >= 0.7 else "C" if wq >= 0.5 else "D"
    return Estimate(
        metric=metric,
        low=round(low / tot_w, 3), point=round(point / tot_w, 3), high=round(high / tot_w, 3),
        unit=unit, markets=sorted(markets), grade=grade,
        n_sources=len(matches), any_stale=stale,
    )


def stale_entries(benchmarks: list[dict] | None = None, as_of: dt.date | None = None) -> list[dict]:
    rows = benchmarks if benchmarks is not None else load_benchmarks()
    return [e for e in rows if is_stale(e, as_of)]
