"""Data ingestion [Phase 2 / 10].

CSV/XLSX mappers from each platform's standard ads export into the unified
placement-grain schema, behind a ``DataSource`` interface so CSV and (later) API
sources are interchangeable. Credentials for API sources come only from
environment variables — never logged, never committed.

Public surface:
    MappingSpec, CsvMapper, CsvDataSource, DataSource   — the mapping machinery
    SPECS                                               — per-platform specs
    const_fx, nok_only_fx                               — FX lookups
    assemble, ingest_into_db                            — combine + load helpers
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from ..schema import database
from .base import (
    CsvDataSource,
    CsvMapper,
    DataSource,
    FxLookup,
    MappingSpec,
    const_fx,
    nok_only_fx,
)
from .specs import META_SPEC, SNAPCHAT_SPEC, SPECS, TIKTOK_SPEC, YOUTUBE_SPEC

__all__ = [
    "CsvDataSource", "CsvMapper", "DataSource", "FxLookup", "MappingSpec",
    "const_fx", "nok_only_fx", "SPECS", "META_SPEC", "SNAPCHAT_SPEC",
    "TIKTOK_SPEC", "YOUTUBE_SPEC", "assemble", "ingest_into_db",
]

_DIM_PK = {
    "placement": "placement_id", "creative": "creative_id",
    "campaign": "campaign_id", "audience_segment": "segment_id",
}


def assemble(mapped: list[dict[str, pd.DataFrame]]) -> dict[str, pd.DataFrame]:
    """Concatenate mapped outputs from several sources, de-duplicating dims."""
    out: dict[str, pd.DataFrame] = {}
    for table in ("placement", "creative", "campaign", "audience_segment", "ad_performance"):
        parts = [m[table] for m in mapped if table in m and not m[table].empty]
        if not parts:
            continue
        df = pd.concat(parts, ignore_index=True)
        if table in _DIM_PK:
            df = df.drop_duplicates(subset=_DIM_PK[table], keep="first")
        out[table] = df.reset_index(drop=True)
    return out


def _build_date_dim(dates: set[dt.date]) -> pd.DataFrame:
    rows = []
    for d in sorted(dates):
        iso = d.isocalendar()
        rows.append({
            "date": d, "year": d.year, "quarter": (d.month - 1) // 3 + 1,
            "month": d.month, "day": d.day, "iso_year": iso.year,
            "iso_week": iso.week, "weekday": d.isoweekday(),
        })
    return pd.DataFrame(rows)


def _build_fx(frames: dict[str, pd.DataFrame], fx_lookup: FxLookup) -> pd.DataFrame:
    ad = frames.get("ad_performance")
    if ad is None or ad.empty:
        return pd.DataFrame(columns=["date", "currency", "nok_per_unit"])
    pairs = ad[["date", "currency"]].drop_duplicates()
    rows = [{"date": r.date, "currency": r.currency,
             "nok_per_unit": fx_lookup(r.date, r.currency)} for r in pairs.itertuples()]
    return pd.DataFrame(rows)


def ingest_into_db(con, sources: list[DataSource], account: dict,
                   fx_lookup: FxLookup = nok_only_fx) -> dict[str, int]:
    """Load one or more CSV sources for a single account into a DuckDB connection.

    Builds the account row, date_dim and fx_rate from the mapped data, creates
    the schema if needed, and loads everything in dependency order.
    """
    account_id = account["account_id"]
    mapped = [s.load(account_id, fx_lookup) for s in sources]
    frames = assemble(mapped)

    frames["account"] = pd.DataFrame([account])
    all_dates = set(frames["ad_performance"]["date"]) if "ad_performance" in frames else set()
    frames["date_dim"] = _build_date_dim(all_dates)
    frames["fx_rate"] = _build_fx(frames, fx_lookup)

    database.create_schema(con)
    return database.load_all(con, frames)
