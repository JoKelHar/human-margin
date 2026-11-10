# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Planner Phase 2: benchmark library, provenance, market-similarity weighting."""

from __future__ import annotations

import datetime as dt

import pytest

from mediekjop.planner.benchmarks import (
    BenchmarkError,
    estimate,
    is_stale,
    load_benchmarks,
    load_weights,
    market_weight,
)

AS_OF = dt.date(2026, 11, 10)


def test_library_loads_and_every_figure_is_cited_or_labelled():
    rows = load_benchmarks()
    assert len(rows) >= 10
    for e in rows:
        assert e["value"].get("point") is not None
        # a real figure cites a source; only a labelled D assumption may omit it
        assert e.get("source_url") or e["quality"] == "D"
        assert isinstance(e["published"], dt.date)


def test_perf_multiplier_priors_present_and_centred():
    priors = {e.get("effect"): e for e in load_benchmarks() if e["metric"] == "perf_multiplier"}
    assert set(priors) >= {"response", "memory_brand"}
    assert abs(priors["response"]["value"]["point"] - 1.0) < 1e-6   # response at parity
    assert priors["memory_brand"]["value"]["point"] > 1.0           # modest human advantage


def test_estimate_reports_markets_grade_confidence_and_unit():
    est = estimate("cvr", industry="beauty_skincare", channel="meta")
    assert est is not None
    assert est.unit == "percent"
    assert 2.0 <= est.point <= 5.0
    assert est.markets and est.grade in ("A", "B", "C", "D")
    assert est.confidence in ("high", "medium", "low")


def test_assumption_is_not_credited_to_norway():
    est = estimate("cpm", channel="snapchat")   # only a labelled assumption matches
    assert est is not None
    assert est.markets == ["assumption"]         # not ['NO']
    assert est.grade == "D" and est.confidence == "low"


def test_generic_query_does_not_pull_industry_specific_rows():
    generic = estimate("cpm", industry="any", channel="meta")   # uses the 'any' meta row only
    beauty = estimate("cpm", industry="beauty_skincare", channel="meta")  # beauty row ($8)
    assert generic is not None and beauty is not None
    # the generic estimate reflects the generic (~$13) row, not the lower beauty row
    assert generic.point > beauty.point


def test_distance_from_norway_widens_the_range():
    est = estimate("cvr", industry="beauty_skincare", channel="meta")  # global source
    # widened well beyond the raw 2.3-4.6 span (2.3)
    assert (est.high - est.low) > 2.5


def test_distant_source_grades_low():
    # all current sources are US/global, so evidence for Norway is weak -> D / low
    est = estimate("cvr", industry="beauty_skincare", channel="meta")
    assert est.grade == "D" and est.confidence == "low"


def test_market_weight_priority_norway_first():
    w = load_weights()
    assert (market_weight("NO", w) > market_weight("SE", w) > market_weight("EU", w)
            > market_weight("US", w) >= market_weight("global", w))


def test_price_dependent_metric_is_normalised_up_toward_norway():
    est = estimate("cpm", industry="beauty_skincare", channel="meta")
    assert est is not None and est.unit == "usd"
    # beauty meta CPM raw point is 8 (US); normalised by NO/US price level (~1.11)
    assert est.point > 8.0


def test_industry_specific_beats_generic():
    est = estimate("cvr", industry="beauty_skincare", channel="meta")
    # beauty CVR (~3.3%) is used, not the lower fashion figure
    assert est.point > 2.6


def test_staleness_flagging():
    rows = load_benchmarks()
    assert any(is_stale(e, AS_OF) for e in rows)       # 2024 figures are stale by Nov 2026
    assert not all(is_stale(e, AS_OF) for e in rows)   # 2026 assumptions are not


def test_no_match_returns_none():
    assert estimate("cpm", channel="pinterest") is None


def test_uncited_non_assumption_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "benchmarks:\n"
        "  - metric: cpm\n    industry: any\n    price_band: any\n    channel: meta\n"
        "    geography: US\n    value: {point: 9}\n    unit: usd\n"
        "    source_name: X\n    source_url: \"\"\n    published: 2025-01-01\n    quality: C\n",
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkError):
        load_benchmarks(bad)
