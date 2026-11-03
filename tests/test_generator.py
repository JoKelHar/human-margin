# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Synthetic generator: determinism, referential integrity, encoded effects."""

from __future__ import annotations

import datetime as dt

from mediekjop.config import load_config
from mediekjop.schema.enums import Provenance
from mediekjop.synthetic import GeneratorConfig, generate


def test_determinism_same_seed(cfg):
    gc = GeneratorConfig(seed=7, days=50, n_creatives_per_account=10)
    a = generate(gc, cfg)
    b = generate(gc, cfg)
    assert a.row_counts() == b.row_counts()
    # spend totals match to the cent
    assert round(a.frames["ad_performance"].spend_nok.sum(), 2) == \
        round(b.frames["ad_performance"].spend_nok.sum(), 2)


def test_core_tables_non_empty(dataset):
    counts = dataset.row_counts()
    for t in ("ad_performance", "organic_performance", "comment", "creative",
              "placement", "audience_segment", "campaign", "fx_rate", "date_dim"):
        assert counts.get(t, 0) > 0


def test_referential_integrity(con):
    for child_col, parent, parent_col in [
        ("placement_id", "placement", "placement_id"),
        ("creative_id", "creative", "creative_id"),
        ("segment_id", "audience_segment", "segment_id"),
        ("campaign_id", "campaign", "campaign_id"),
    ]:
        orphans = con.execute(
            f"SELECT COUNT(*) FROM ad_performance a "
            f"LEFT JOIN {parent} p ON a.{child_col} = p.{parent_col} "
            f"WHERE p.{parent_col} IS NULL"
        ).fetchone()[0]
        assert orphans == 0, f"orphan {child_col}"


def test_provenance_values_valid(con):
    vals = {r[0] for r in con.execute(
        "SELECT DISTINCT provenance FROM creative WHERE provenance IS NOT NULL").fetchall()}
    assert vals <= set(Provenance.values())


def test_untagged_spend_is_present_and_bounded(con):
    share = con.execute(
        "SELECT SUM(CASE WHEN c.provenance IS NULL THEN a.spend_nok ELSE 0 END)"
        " / SUM(a.spend_nok) FROM ad_performance a JOIN creative c USING (creative_id)"
    ).fetchone()[0]
    assert 0.0 < share < 0.4  # some untagged spend to flag, but not most of it


def test_multi_currency_and_nok_normalisation(con):
    currencies = {r[0] for r in con.execute(
        "SELECT DISTINCT currency FROM ad_performance").fetchall()}
    assert "NOK" in currencies
    assert len(currencies) >= 2  # foreign-currency campaigns exist

    # spend_nok must equal spend * fx rate for the row's date & currency
    bad = con.execute(
        "SELECT COUNT(*) FROM ad_performance a JOIN fx_rate f "
        "ON a.date = f.date AND a.currency = f.currency "
        "WHERE abs(a.spend_nok - a.spend * f.nok_per_unit) > 0.05 * a.spend_nok + 1"
    ).fetchone()[0]
    assert bad == 0


def test_ai_wins_clicks_loses_saves(con):
    # Engagement-quality contrast. "AI wins clicks" holds at LOW frequency
    # (fresh exposure); aggregate CTR can flip below human once exhaustion sets
    # in, which is itself the intended signal. Save rate is frequency-independent
    # in the model, so AI < human on saves holds in aggregate.
    df = con.execute(
        "SELECT c.provenance, a.frequency, a.clicks, a.impressions, a.saves "
        "FROM ad_performance a JOIN creative c USING (creative_id) "
        "WHERE c.provenance IS NOT NULL AND a.impressions > 0"
    ).df()

    def low_freq_ctr(prov):
        sub = df[df.provenance == prov]
        lo = sub[sub.frequency <= sub.frequency.quantile(0.25)]
        return lo.clicks.sum() / lo.impressions.sum()

    assert low_freq_ctr("ai_generated") > low_freq_ctr("human_led"), "AI should win clicks when fresh"

    save_rate = df.groupby("provenance").apply(
        lambda g: g.saves.sum() / g.impressions.sum(), include_groups=False)
    assert save_rate["ai_generated"] < save_rate["human_led"], "AI should lose on saves"


def test_ai_fatigue_faster_than_human(con):
    # CTR should fall more with frequency for AI than for human-led creative.
    # Compare low-frequency vs high-frequency CTR per provenance.
    df = con.execute(
        "SELECT c.provenance, a.frequency, a.clicks, a.impressions "
        "FROM ad_performance a JOIN creative c USING (creative_id) "
        "WHERE c.provenance IS NOT NULL AND a.impressions > 0"
    ).df()
    drops = {}
    for prov in ("human_led", "ai_generated"):
        sub = df[df.provenance == prov]
        lo = sub[sub.frequency <= sub.frequency.quantile(0.25)]
        hi = sub[sub.frequency >= sub.frequency.quantile(0.75)]
        lo_ctr = lo.clicks.sum() / lo.impressions.sum()
        hi_ctr = hi.clicks.sum() / hi.impressions.sum()
        drops[prov] = (lo_ctr - hi_ctr) / lo_ctr
    assert drops["ai_generated"] > drops["human_led"]


def test_comment_authors_are_hashed(con):
    # author_hash is a fixed-length hex hash, never a plausible raw username.
    sample = [r[0] for r in con.execute(
        "SELECT author_hash FROM comment LIMIT 20").fetchall()]
    assert sample
    for h in sample:
        assert len(h) == 16 and all(ch in "0123456789abcdef" for ch in h)


def test_raw_names_follow_naming_convention(con):
    # Tagged creatives carry a provenance token; untagged ones don't.
    tagged = con.execute(
        "SELECT raw_name FROM creative WHERE tag_source = 'naming_convention' LIMIT 5"
    ).fetchall()
    assert tagged
    for (name,) in tagged:
        assert any(tok in name for tok in ("HL-", "_AA_", "_AG_"))
