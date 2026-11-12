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
QUALITY_RANK = {"A": 3, "B": 2, "C": 1, "D": 0}
# Provenance tiers, most trustworthy first. Ranks order a blend's overall tier
# and place `expert_estimate` between public data and a bare assumption.
PROV_RANK = {"own_account": 4, "pooled": 3, "public_benchmark": 2,
             "expert_estimate": 1, "assumption": 0}
RELEVANCE_WEIGHT = {"high": 1.0, "med": 0.6, "low": 0.3}
STALE_MONTHS = 18

# Plain-language channel labels for tags and relevance reasons.
CHANNEL_LABEL = {"meta": "Meta", "tiktok": "TikTok", "snapchat": "Snapchat",
                 "youtube": "YouTube"}


def _channel_label(ch: str) -> str:
    return CHANNEL_LABEL.get(ch, ch.title())


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
        if e.get("provenance") and e["provenance"] not in PROV_RANK:
            raise BenchmarkError(f"benchmark {i}: bad provenance {e['provenance']!r}")
        # Provenance of the figure: a public figure must cite a source URL. Two
        # kinds may omit it: a labelled D assumption, and a named `expert_estimate`
        # (no public URL, but a named estimator in source_name and a date). An
        # expert slot left blank for the owner to fill is marked value.filled: false.
        tier = e.get("provenance")
        exempt = e["quality"] == "D" or tier in ("expert_estimate", "assumption")
        if not e.get("source_url") and not exempt:
            raise BenchmarkError(f"benchmark {i} ({e['metric']}): no source_url and not a labelled assumption or expert estimate")
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
    markets: list[str]            # geographies the estimate drew on ('assumption' = a guess)
    # Two separate tags, never one blended letter (see docs/principles.md):
    source_quality: str          # A..D — how good the underlying study/data is. Fixed
                                 # per source; geography does NOT change it.
    relevance: str               # high | med | low — fit to the Norwegian user.
    relevance_reasons: list[str] # why relevance stepped down: geography / industry /
                                 # sample / recency, each with its detail. For expand.
    confidence: str              # high | medium | low — derived from source_quality,
                                 # relevance and staleness together.
    provenance: str              # own_account | pooled | public_benchmark |
                                 # expert_estimate | assumption
    primary_market: str          # the market of the strongest contributing source
    year: int | None             # publication year of that source (for the tag)
    n_sources: int
    any_stale: bool
    channel_note: str = ""       # set when the figure fell back to another channel
                                 # (e.g. "Meta/TikTok proxy"); shown in the tag so a
                                 # cross-channel borrow is never silent.


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
    # Cross-channel fallback: the requested channel has no figure for this metric,
    # but it is a channel the library knows elsewhere, so borrow the other channels
    # rather than return nothing - and flag the borrow (never blend silently). An
    # entirely unknown channel (not attested anywhere) still returns None.
    channel_fallback = False
    if not matches and channel != "any" and channel in {e["channel"] for e in rows}:
        matches = [e for e in rows if _applies(e, metric, industry, "any", band, True)]
        if not matches:
            matches = [e for e in rows if _applies(e, metric, industry, "any", band, False)]
        channel_fallback = bool(matches)
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
    # Did a specific-industry query fall back to generic ('any') rows? That lowers
    # relevance (an industry proxy), without touching source quality.
    generic_proxy = industry != "any" and all(e["industry"] == "any" for e in matches)

    low = point = high = tot_w = mw_num = 0.0
    markets: set[str] = set()
    stale = False
    best_score = -1.0
    best_entry = matches[0]
    unit = matches[0]["unit"]
    for e in matches:
        mw = market_weight(e["geography"], wcfg)
        score = mw * QUALITY_WEIGHT[e["quality"]]   # blend weight: market fit x study quality
        if score <= 0:
            continue
        v = e["value"]
        norm = (lambda x: _norm_price_level(x, e["geography"], wcfg)) if metric in price_dependent else (lambda x: x)
        low += norm(v.get("low", v["point"])) * score
        point += norm(v["point"]) * score
        high += norm(v.get("high", v["point"])) * score
        tot_w += score
        mw_num += mw * score
        markets.add(e["geography"])
        stale = stale or is_stale(e, as_of)
        if score > best_score:          # strongest contributor names the market/year
            best_score, best_entry = score, e
    if tot_w == 0:
        return None

    pt, blo, bhi = point / tot_w, low / tot_w, high / tot_w
    avg_mw = mw_num / tot_w
    distance = max(0.0, 1.0 - avg_mw)   # 0 at Norway, up to ~0.8 for an assumption

    # --- two separate tags, never one blended letter -------------------------
    # Source quality is the best underlying study; geography does NOT change it.
    source_quality = max((e["quality"] for e in matches), key=lambda q: QUALITY_RANK[q])
    # Relevance to the Norwegian user, with a reason for each step down.
    reasons: list[str] = []
    rel = avg_mw
    mk_sourced = sorted(m for m in markets if m != "assumption")
    if markets == {"assumption"}:
        reasons.append("geography: assumption, no market data")
    elif avg_mw < 0.95:
        reasons.append(f"geography: {'/'.join(mk_sourced) or 'mixed'}, not Norway")
    if generic_proxy:
        rel *= 0.85
        reasons.append("industry: generic proxy, not industry-specific")
    channel_note = ""
    if channel_fallback:
        used = sorted({e["channel"] for e in matches if e["channel"] != "any"})
        if used:
            lbl = "/".join(_channel_label(c) for c in used)
            channel_note = f"{lbl} proxy"
            rel *= 0.85
            reasons.append(f"channel: {lbl} proxy, not {_channel_label(channel)}")
    if len(matches) == 1:
        rel *= 0.90
        reasons.append("sample: single source")
    if stale:
        rel *= 0.90
        reasons.append("recency: older than 18 months")
    relevance = "high" if rel >= 0.80 else "med" if rel >= 0.45 else "low"

    # Distance from Norway and staleness WIDEN the range, so a single far-market
    # match is not reported as if it were local and certain.
    widen = 1.0 + 0.6 * distance + (0.2 if stale else 0.0)
    lo = max(round(pt - (pt - blo) * widen, 3), round(pt * 0.25, 3))   # floor, not absurd
    hi = round(pt + (bhi - pt) * widen, 3)

    # Confidence combines how good the source is with how relevant it is.
    c = QUALITY_WEIGHT[source_quality] * RELEVANCE_WEIGHT[relevance] * (0.8 if stale else 1.0)
    confidence = "high" if c >= 0.55 else "medium" if c >= 0.30 else "low"

    # Overall provenance tier = the most trustworthy tier present (assumptions are
    # already dropped when any sourced figure matches).
    prov = max((provenance(e) for e in matches), key=lambda t: PROV_RANK[t])
    year = best_entry["published"].year if isinstance(best_entry["published"], dt.date) else None
    return Estimate(
        metric=metric, low=lo, point=round(pt, 3), high=hi, unit=unit,
        markets=sorted(markets), source_quality=source_quality, relevance=relevance,
        relevance_reasons=reasons, confidence=confidence, provenance=prov,
        primary_market=best_entry["geography"], year=year,
        n_sources=len(matches), any_stale=stale, channel_note=channel_note,
    )


# --- provenance tags (plain-language, for every figure shown) ----------------

PROVENANCE_LABEL = {
    "own_account": "Your data",
    "pooled": "Pooled accounts",
    "public_benchmark": "Public benchmark",
    "expert_estimate": "Expert estimate",
    "assumption": "Assumption",
}

LEGEND = ("Your data · pooled similar accounts · public benchmark · expert estimate · "
          "assumption. Source quality A-D and relevance to Norway (high/med/low) are "
          "shown separately; a wider range means less certain.")


def provenance(entry: dict) -> str:
    """Provenance tier of a single library entry.

    An entry may name its tier explicitly (``provenance:`` in the YAML); otherwise
    it is derived. ``expert_estimate`` is a named, dated figure with no public URL,
    ranked between ``public_benchmark`` and a bare ``assumption``. ``own_account``
    and ``pooled`` arrive once linked-account data is aggregated (see the design doc).
    """
    explicit = entry.get("provenance")
    if explicit in PROV_RANK:
        return explicit
    if entry["geography"] == "assumption" or (not entry.get("source_url") and entry["quality"] == "D"):
        return "assumption"
    return "public_benchmark"


def _market_year(est: Estimate) -> str:
    mk = est.primary_market if est.primary_market != "assumption" else "no market"
    base = f"{mk}, {est.year}" if est.year else mk
    return f"{base}, {est.channel_note}" if est.channel_note else base


def tag(est: Estimate) -> str:
    """A short, plain-language, two-part tag for an estimate (CLI/UI).

    Source quality and relevance are shown separately, never blended into one
    letter, e.g. ``C source · low relevance (US, 2024)``. The full breakdown
    (``relevance_reasons``) is for an expanded view.
    """
    if est.provenance == "assumption":
        return "Assumption"
    if est.provenance == "own_account":
        return "Your data"
    if est.provenance == "pooled":
        return f"{est.n_sources} similar accounts · {est.relevance} relevance"
    kind = "expert estimate · " if est.provenance == "expert_estimate" else ""
    return f"{est.source_quality} source · {kind}{est.relevance} relevance ({_market_year(est)})"


def stale_entries(benchmarks: list[dict] | None = None, as_of: dt.date | None = None) -> list[dict]:
    rows = benchmarks if benchmarks is not None else load_benchmarks()
    return [e for e in rows if is_stale(e, as_of)]
