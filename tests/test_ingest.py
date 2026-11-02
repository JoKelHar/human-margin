"""Phase 2: CSV mappers map platform exports into the unified schema correctly."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediekjop.config import load_config
from mediekjop.ingest import (
    SPECS,
    CsvDataSource,
    const_fx,
    ingest_into_db,
)
from mediekjop.schema import database
from mediekjop.schema.ddl import AD_PERFORMANCE, TABLES_BY_NAME

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "exports"
FIXTURE = {
    "meta": SAMPLES / "meta_ads_export.csv",
    "snapchat": SAMPLES / "snapchat_ads_export.csv",
    "tiktok": SAMPLES / "tiktok_ads_export.csv",
    "youtube": SAMPLES / "google_ads_youtube_export.csv",
}
FX = const_fx({"EUR": 11.5})


@pytest.fixture(scope="module")
def config_placements():
    cfg = load_config()
    return {f"{p['channel']}:{p['publisher']}:{p['name']}" for p in cfg["placements"]}


@pytest.mark.parametrize("platform", list(FIXTURE))
def test_each_platform_maps_to_unified_schema(platform, config_placements):
    src = CsvDataSource(SPECS[platform], FIXTURE[platform])
    frames = src.load(account_id="acc_demo", fx_lookup=FX)
    ad = frames["ad_performance"]

    # exact schema columns, in order
    assert list(ad.columns) == AD_PERFORMANCE.column_names
    assert len(ad) > 0

    # every mapped placement exists in the canonical config placement set
    mapped = set(frames["placement"]["placement_id"])
    assert mapped <= config_placements, f"{platform}: unknown placements {mapped - config_placements}"

    # grain is unique (placement level preserved, not rolled up)
    pk = list(AD_PERFORMANCE.primary_key)
    assert len(ad) == len(ad.drop_duplicates(subset=pk))

    # CSV-ingested creatives are untagged until Phase 3 resolves provenance
    assert frames["creative"]["provenance"].isna().all()
    assert (frames["creative"]["tag_source"] == "untagged").all()


def test_meta_row_values_mapped():
    frames = CsvDataSource(SPECS["meta"], FIXTURE["meta"]).load("acc_demo")
    ad = frames["ad_performance"]
    # first fixture row: Instagram Reels, 48210 impressions, spend 2890.50 NOK
    row = ad[(ad.placement_id == "meta:instagram:reels")].iloc[0]
    assert row.impressions == 48210
    assert row.currency == "NOK"
    assert row.spend == 2890.50
    assert row.spend_nok == 2890.50  # NOK -> no conversion
    assert row.saves == 154 and row.shares == 96


def test_youtube_currency_normalised_to_nok():
    frames = CsvDataSource(SPECS["youtube"], FIXTURE["youtube"]).load("acc_demo", fx_lookup=FX)
    ad = frames["ad_performance"]
    assert (ad.currency == "EUR").all()
    row = ad.iloc[0]
    # 220.50 EUR * 11.5 = 2535.75 NOK
    assert row.spend == 220.50
    assert abs(row.spend_nok - 220.50 * 11.5) < 0.01


def test_full_ingest_into_db_referential_integrity():
    con = database.connect(None)
    sources = [CsvDataSource(SPECS[p], FIXTURE[p]) for p in FIXTURE]
    account = {"account_id": "acc_demo", "account_name": "Demo",
               "brand": "demo", "home_currency": "NOK"}
    counts = ingest_into_db(con, sources, account, fx_lookup=FX)

    assert counts["ad_performance"] == 29  # 10 + 8 + 6 + 5 fixture rows
    for child, parent, pcol in [
        ("placement_id", "placement", "placement_id"),
        ("creative_id", "creative", "creative_id"),
        ("campaign_id", "campaign", "campaign_id"),
        ("segment_id", "audience_segment", "segment_id"),
    ]:
        orphans = con.execute(
            f"SELECT COUNT(*) FROM ad_performance a LEFT JOIN {parent} p "
            f"ON a.{child} = p.{pcol} WHERE p.{pcol} IS NULL"
        ).fetchone()[0]
        assert orphans == 0, child

    # all four channels present, placement grain intact
    channels = {r[0] for r in con.execute(
        "SELECT DISTINCT channel FROM placement").fetchall()}
    assert channels == {"meta", "snapchat", "tiktok", "youtube"}
    con.close()


def test_api_source_shares_interface():
    # CsvDataSource satisfies the DataSource protocol (so an API source can swap in)
    from mediekjop.ingest import DataSource
    src = CsvDataSource(SPECS["meta"], FIXTURE["meta"])
    assert isinstance(src, DataSource)
    assert src.name == "csv:meta"
