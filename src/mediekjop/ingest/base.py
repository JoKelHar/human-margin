# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Source-agnostic ingestion: map any platform export into the unified schema.

A platform export (Meta, Snapchat, TikTok, Google/YouTube) differs in column
names, placement vocabulary, currency handling and which metrics exist — but the
*shape* of the mapping is the same everywhere. So platform differences are
expressed declaratively as a ``MappingSpec`` and a single generic ``CsvMapper``
applies any spec. Adding a platform is a spec, not new code.

Everything is kept at PLACEMENT grain (and at demographic grain where the export
carries an age/region breakdown). Money is mapped in its original currency and
normalised to NOK via an injected FX lookup, because the scope is the Norwegian
consumer, not Norwegian locality.

The ``DataSource`` protocol is the seam that lets CSV sources (now) and API
connectors (Phase 10) be interchangeable: both return unified-schema frames.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

import pandas as pd

from ..schema import database
from ..schema.ddl import TABLES_BY_NAME
from ..schema.enums import AudienceType, TagSource

# source age bucket (lowercased) -> unified age cohort
AGE_MAP: dict[str, str] = {
    "13-17": "age_13_17", "18-24": "age_18_24", "25-34": "age_25_34",
    "35-44": "age_35_44", "45-54": "age_45_54", "55-64": "age_55_plus",
    "65+": "age_55_plus", "55+": "age_55_plus", "unknown": None, "": None,
}

# FX lookup: (date, currency) -> NOK per unit. NOK is always 1.0.
FxLookup = Callable[[dt.date, str], float]


def nok_only_fx(date: dt.date, currency: str) -> float:
    if currency == "NOK":
        return 1.0
    raise KeyError(f"No FX rate for {currency} on {date}; supply an fx_lookup.")


def const_fx(rates: dict[str, float]) -> FxLookup:
    """Build an FX lookup from a flat currency->rate map (constant over time)."""
    def _lookup(date: dt.date, currency: str) -> float:
        if currency == "NOK":
            return 1.0
        return rates[currency]
    return _lookup


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")[:60]


@dataclass(frozen=True)
class MappingSpec:
    platform: str
    channel: str
    # grain / dimension columns in the source file
    col_campaign: str
    col_ad: str          # ad name -> creative.raw_name
    col_date: str
    col_placement: str
    col_adset: str | None = None
    col_age: str | None = None
    col_region: str | None = None
    # money
    col_spend: str = "spend"
    col_currency: str | None = None
    currency_const: str | None = None
    spend_scale: float = 1.0            # e.g. micro-currency exports use 1e-6
    # unified metric column -> source column (only those the platform provides)
    metric_map: dict[str, str] = field(default_factory=dict)
    # source placement (lowercased) -> (publisher, placement_name)
    placement_map: dict[str, tuple[str, str]] = field(default_factory=dict)
    date_formats: tuple[str, ...] = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")

    def placement_id(self, source_placement: str) -> str:
        key = str(source_placement).strip().lower()
        if key not in self.placement_map:
            raise KeyError(
                f"{self.platform}: unmapped placement {source_placement!r}. "
                f"Add it to the spec's placement_map."
            )
        publisher, name = self.placement_map[key]
        return f"{self.channel}:{publisher}:{name}", publisher, name


# all metric columns in ad_performance that are counts/values (filled with 0)
_METRIC_DEFAULT_COLS = [
    "impressions", "reach", "clicks", "link_clicks", "three_sec_views",
    "video_plays", "video_completions", "likes", "comments_count", "shares",
    "saves", "hides", "not_interested", "negative_feedback", "unfollows",
    "conversions",
]


class CsvMapper:
    """Applies a MappingSpec to a platform export dataframe."""

    def __init__(self, spec: MappingSpec):
        self.spec = spec

    # -- parsing helpers ----------------------------------------------------
    def _parse_date(self, raw) -> dt.date:
        if isinstance(raw, (dt.date, dt.datetime)):
            return raw.date() if isinstance(raw, dt.datetime) else raw
        s = str(raw).strip()
        for fmt in self.spec.date_formats:
            try:
                return dt.datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return pd.to_datetime(s).date()

    def _num(self, row: pd.Series, source_col: str | None) -> float:
        if not source_col or source_col not in row:
            return 0.0
        val = pd.to_numeric(str(row[source_col]).replace(" ", "").replace(",", ""),
                            errors="coerce")
        return 0.0 if pd.isna(val) else float(val)

    # -- main ---------------------------------------------------------------
    def map(self, raw: pd.DataFrame, account_id: str,
            fx_lookup: FxLookup = nok_only_fx) -> dict[str, pd.DataFrame]:
        spec = self.spec
        ad_rows, creatives, campaigns, placements, segments = [], {}, {}, {}, {}

        for _, row in raw.iterrows():
            date = self._parse_date(row[spec.col_date])
            placement_id, publisher, placement_name = spec.placement_id(row[spec.col_placement])
            placements[placement_id] = {
                "placement_id": placement_id, "channel": spec.channel,
                "publisher": publisher, "placement_name": placement_name,
                "format": "video", "is_video": True,
            }

            ad_name = str(row[spec.col_ad])
            creative_id = f"{account_id}:{slug(ad_name)}"
            creatives.setdefault(creative_id, {
                "creative_id": creative_id, "account_id": account_id,
                "raw_name": ad_name, "created_date": date,
                # provenance/Norwegian-ness resolved in Phase 3 — untagged for now
                "provenance": None, "human_sub_type": None, "ai_sub_type": None,
                "tag_source": TagSource.UNTAGGED.value, "tag_confidence": 0.0,
                "language": None, "dialect_present": None, "dialect_region": None,
                "norwegian_locations": None, "norwegian_faces": None,
                "norwegian_cultural_refs": None, "shows_people": None,
            })

            campaign_name = str(row[spec.col_campaign])
            campaign_id = f"{account_id}:{slug(campaign_name)}"
            campaigns.setdefault(campaign_id, {
                "campaign_id": campaign_id, "account_id": account_id,
                "name": campaign_name, "objective": None, "funnel_stage": None,
                "flight_start": date, "flight_end": date,
            })
            # extend flight window as we see more dates
            if date < campaigns[campaign_id]["flight_start"]:
                campaigns[campaign_id]["flight_start"] = date
            if date > campaigns[campaign_id]["flight_end"]:
                campaigns[campaign_id]["flight_end"] = date

            age_cohort = None
            if spec.col_age and spec.col_age in row:
                age_cohort = AGE_MAP.get(str(row[spec.col_age]).strip().lower())
            region = str(row[spec.col_region]).strip().lower() if spec.col_region and spec.col_region in row else None
            adset = str(row[spec.col_adset]) if spec.col_adset and spec.col_adset in row else campaign_name
            segment_id = f"{account_id}:{slug(adset)}:{age_cohort or 'all'}:{region or 'no'}"
            segments.setdefault(segment_id, {
                "segment_id": segment_id, "account_id": account_id,
                "age_cohort": age_cohort, "gender": "all", "region": region,
                "audience_type": AudienceType.PROSPECTING.value, "market": "NO",
            })

            # money
            currency = spec.currency_const or (
                str(row[spec.col_currency]).strip() if spec.col_currency and spec.col_currency in row else "NOK")
            spend = self._num(row, spec.col_spend) * spec.spend_scale
            conv_value = self._num(row, spec.metric_map.get("conversion_value"))
            rate = fx_lookup(date, currency)
            spend_nok = spend * rate
            conv_value_nok = conv_value * rate

            metrics = {col: int(round(self._num(row, spec.metric_map.get(col))))
                       for col in _METRIC_DEFAULT_COLS}
            reach = metrics["reach"]
            freq = self._num(row, spec.metric_map.get("frequency"))
            if not freq and reach:
                freq = metrics["impressions"] / reach if reach else 0.0
            avg_watch = self._num(row, spec.metric_map.get("avg_watch_time_sec"))

            ad_rows.append({
                "account_id": account_id, "campaign_id": campaign_id,
                "creative_id": creative_id, "placement_id": placement_id,
                "segment_id": segment_id, "date": date,
                **metrics, "frequency": round(freq, 3), "avg_watch_time_sec": avg_watch,
                "currency": currency, "spend": round(spend, 2),
                "conversion_value": round(conv_value, 2),
                "spend_nok": round(spend_nok, 2), "conversion_value_nok": round(conv_value_nok, 2),
            })

        ad_df = pd.DataFrame(ad_rows)
        # enforce exact ad_performance column set/order
        ad_cols = TABLES_BY_NAME["ad_performance"].column_names
        for c in ad_cols:
            if c not in ad_df.columns:
                ad_df[c] = 0
        ad_df = ad_df[ad_cols]

        return {
            "placement": pd.DataFrame(placements.values()),
            "creative": pd.DataFrame(creatives.values()),
            "campaign": pd.DataFrame(campaigns.values()),
            "audience_segment": pd.DataFrame(segments.values()),
            "ad_performance": ad_df,
        }


@runtime_checkable
class DataSource(Protocol):
    """The seam between CSV (now) and API (Phase 10) sources."""

    name: str

    def load(self, account_id: str, fx_lookup: FxLookup = ...) -> dict[str, pd.DataFrame]:
        ...


@dataclass
class CsvDataSource:
    """A CSV export file plus the spec that maps it."""

    spec: MappingSpec
    path: str | Path

    @property
    def name(self) -> str:
        return f"csv:{self.spec.platform}"

    def load(self, account_id: str, fx_lookup: FxLookup = nok_only_fx) -> dict[str, pd.DataFrame]:
        raw = pd.read_csv(self.path)
        return CsvMapper(self.spec).map(raw, account_id, fx_lookup)
