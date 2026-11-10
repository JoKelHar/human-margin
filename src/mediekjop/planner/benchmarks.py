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


def _applies(e: dict, metric: str, industry: str, channel: str, band: str,
             generic_industry_only: bool = True) -> bool:
    if e["metric"] != metric:
        return False
    # A generic industry query uses generic ('any') rows, not industry-specific
    # ones, unless the caller relaxes this because no generic row exists.
    if industry == "any":
        ind_ok = e["industry"] == "any" if generic_industry_only else True
    else:
        ind_ok = e["industry"] in (industry, "any")
    chan_ok = channel == "any" or e["channel"] in (channel, "any")
    band_ok = band == "any" or e["price_band"] in (band, "any")
    return ind_ok and chan_ok and band_ok


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
    markets: list[str]     # geographies the estimate drew on ('assumption' = a guess)
    grade: str             # A..D, lowered by distance from Norway and by staleness
    confidence: str        # high | medium | low (distance + staleness)
    n_sources: int
    any_stale: bool


def estimate(metric: str, industry: str = "any", channel: str = "any", band: str = "any", *,
             benchmarks: list[dict] | None = None, weights: dict | None = None,
             as_of: dt.date | None = None) -> Estimate | None:
    """Blend matching benchmarks into one market-weighted estimate, or None."""
    rows = benchmarks if benchmarks is not None else load_benchmarks()
    wcfg = weights if weights is not None else load_weights()
    price_dependent = set(wcfg.get("price_dependent_metrics") or [])

    # Generic industry queries use generic rows; fall back to specific only if none.
    matches = [e for e in rows if _applies(e, metric, industry, channel, band, True)]
    if not matches:
        matches = [e for e in rows if _applies(e, metric, industry, channel, band, False)]
    if not matches:
        return None
    # Prefer the most specific figures when industry/channel-specific ones exist.
    max_spec = max(_specificity(e, industry, channel) for e in matches)
    if max_spec > 0:
        matches = [e for e in matches if _specificity(e, industry, channel) == max_spec]
    # A labelled assumption is used only when no sourced figure matches, so a D
    # assumption can never outweigh (or dilute) a sourced figure.
    sourced = [e for e in matches if e["geography"] != "assumption"]
    if sourced:
        matches = sourced

    low = point = high = tot_w = eff_num = mw_num = 0.0
    markets: set[str] = set()
    stale = False
    unit = matches[0]["unit"]
    for e in matches:
        mw = market_weight(e["geography"], wcfg)
        score = mw * QUALITY_WEIGHT[e["quality"]]   # evidence: geography feeds it
        if score <= 0:
            continue
        v = e["value"]
        norm = (lambda x: _norm_price_level(x, e["geography"], wcfg)) if metric in price_dependent else (lambda x: x)
        low += norm(v.get("low", v["point"])) * score
        point += norm(v["point"]) * score
        high += norm(v.get("high", v["point"])) * score
        tot_w += score
        eff_num += score * score
        mw_num += mw * score
        markets.add(e["geography"])
        stale = stale or is_stale(e, as_of)
    if tot_w == 0:
        return None

    pt, blo, bhi = point / tot_w, low / tot_w, high / tot_w
    eff = eff_num / tot_w          # effective evidence (dominated by the strongest sources)
    avg_mw = mw_num / tot_w
    distance = max(0.0, 1.0 - avg_mw)   # 0 at Norway, up to ~0.8 for an assumption
    # Distance from Norway and staleness WIDEN the range and lower confidence, so a
    # single far-market match is not reported as if it were local and certain.
    widen = 1.0 + 0.6 * distance + (0.2 if stale else 0.0)
    lo = max(round(pt - (pt - blo) * widen, 3), round(pt * 0.25, 3))   # floor, not absurd
    hi = round(pt + (bhi - pt) * widen, 3)

    grade = "A" if eff >= 0.75 else "B" if eff >= 0.50 else "C" if eff >= 0.25 else "D"
    confidence = "high" if (eff >= 0.60 and not stale) else "medium" if eff >= 0.30 else "low"
    return Estimate(
        metric=metric, low=lo, point=round(pt, 3), high=hi, unit=unit,
        markets=sorted(markets), grade=grade, confidence=confidence,
        n_sources=len(matches), any_stale=stale,
    )


def stale_entries(benchmarks: list[dict] | None = None, as_of: dt.date | None = None) -> list[dict]:
    rows = benchmarks if benchmarks is not None else load_benchmarks()
    return [e for e in rows if is_stale(e, as_of)]
