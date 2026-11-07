# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Unified placement-grain schema — single source of truth.

Column names, order and types are defined once here as ``TableSpec`` objects.
DuckDB DDL and the canonical column order for loading are both derived from
these specs, so the schema, the database and the data loaders can never drift
apart.

Design principles:
  * Grain is PLACEMENT level, never rolled up to campaign (ad_performance and
    organic_performance both carry placement_id).
  * Monetary values are stored in their ORIGINAL currency plus a NOK-normalised
    column, because the scope is the Norwegian consumer, not Norwegian locality
    (a Norwegian buying in EUR/USD is in scope).
  * Provenance / Norwegian-ness tags live on the ``creative`` dimension and are
    nullable: a NULL provenance with tag_source='untagged' is a first-class,
    reportable state — never guessed from performance.
  * Comment author identity is stored only as a salted hash (GDPR).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[tuple[str, str], ...]  # (column_name, duckdb_type)
    primary_key: tuple[str, ...] = ()

    @property
    def column_names(self) -> list[str]:
        return [c for c, _ in self.columns]

    def create_sql(self) -> str:
        cols = ",\n    ".join(f"{name} {dtype}" for name, dtype in self.columns)
        pk = f",\n    PRIMARY KEY ({', '.join(self.primary_key)})" if self.primary_key else ""
        return f"CREATE TABLE IF NOT EXISTS {self.name} (\n    {cols}{pk}\n);"


# --- dimensions --------------------------------------------------------------

ACCOUNT = TableSpec(
    "account",
    (
        ("account_id", "VARCHAR"),
        ("account_name", "VARCHAR"),
        ("brand", "VARCHAR"),
        ("home_currency", "VARCHAR"),
    ),
    primary_key=("account_id",),
)

CAMPAIGN = TableSpec(
    "campaign",
    (
        ("campaign_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("name", "VARCHAR"),
        ("objective", "VARCHAR"),
        ("funnel_stage", "VARCHAR"),
        ("flight_start", "DATE"),
        ("flight_end", "DATE"),
    ),
    primary_key=("campaign_id",),
)

PLACEMENT = TableSpec(
    "placement",
    (
        ("placement_id", "VARCHAR"),
        ("channel", "VARCHAR"),
        ("publisher", "VARCHAR"),
        ("placement_name", "VARCHAR"),
        ("format", "VARCHAR"),
        ("is_video", "BOOLEAN"),
    ),
    primary_key=("placement_id",),
)

AUDIENCE_SEGMENT = TableSpec(
    "audience_segment",
    (
        ("segment_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("age_cohort", "VARCHAR"),
        ("gender", "VARCHAR"),
        ("region", "VARCHAR"),
        ("audience_type", "VARCHAR"),
        ("market", "VARCHAR"),  # consumer market, default 'NO'
    ),
    primary_key=("segment_id",),
)

# The creative dimension carries provenance + Norwegian-ness. All tag columns
# are nullable: NULL + tag_source='untagged' means "not yet tagged".
CREATIVE = TableSpec(
    "creative",
    (
        ("creative_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("raw_name", "VARCHAR"),         # the ad/post name as it appears on-platform
        ("created_date", "DATE"),
        # provenance (Phase 3 resolves these; nullable = untagged)
        ("provenance", "VARCHAR"),       # human_led | ai_assisted | ai_generated | NULL
        ("human_sub_type", "VARCHAR"),   # ugc | creator | staff_founder | documentary | studio_polished | NULL
        ("ai_sub_type", "VARCHAR"),      # product_imagery | copy_variants | synthetic_ugc | synthetic_scene | NULL
        ("tag_source", "VARCHAR"),       # naming_convention | csv_override | platform_label | c2pa | untagged
        ("tag_confidence", "DOUBLE"),    # 0..1
        # Norwegian-ness (optional descriptive dimension, never a scope filter)
        ("language", "VARCHAR"),         # bokmal | nynorsk | dialect | english | mixed | NULL
        ("dialect_present", "BOOLEAN"),
        ("dialect_region", "VARCHAR"),
        ("norwegian_locations", "BOOLEAN"),
        ("norwegian_faces", "BOOLEAN"),
        ("norwegian_cultural_refs", "BOOLEAN"),
        # compliance helper: does the creative show people? (kroppspress review)
        ("shows_people", "BOOLEAN"),
    ),
    primary_key=("creative_id",),
)

DATE_DIM = TableSpec(
    "date_dim",
    (
        ("date", "DATE"),
        ("year", "INTEGER"),
        ("quarter", "INTEGER"),
        ("month", "INTEGER"),
        ("day", "INTEGER"),
        ("iso_year", "INTEGER"),
        ("iso_week", "INTEGER"),
        ("weekday", "INTEGER"),  # Monday=1 .. Sunday=7
    ),
    primary_key=("date",),
)

FX_RATE = TableSpec(
    "fx_rate",
    (
        ("date", "DATE"),
        ("currency", "VARCHAR"),
        ("nok_per_unit", "DOUBLE"),  # 1 unit of `currency` = nok_per_unit NOK
    ),
    primary_key=("date", "currency"),
)

# --- facts (placement grain) -------------------------------------------------

AD_PERFORMANCE = TableSpec(
    "ad_performance",
    (
        # grain keys
        ("account_id", "VARCHAR"),
        ("campaign_id", "VARCHAR"),
        ("creative_id", "VARCHAR"),
        ("placement_id", "VARCHAR"),
        ("segment_id", "VARCHAR"),
        ("date", "DATE"),
        # delivery
        ("impressions", "BIGINT"),
        ("reach", "BIGINT"),
        ("frequency", "DOUBLE"),
        # clicks / attention
        ("clicks", "BIGINT"),
        ("link_clicks", "BIGINT"),
        ("three_sec_views", "BIGINT"),       # thumb-stops
        ("video_plays", "BIGINT"),
        ("video_completions", "BIGINT"),
        ("avg_watch_time_sec", "DOUBLE"),
        # social engagement
        ("likes", "BIGINT"),
        ("comments_count", "BIGINT"),
        ("shares", "BIGINT"),
        ("saves", "BIGINT"),
        # negative signals
        ("hides", "BIGINT"),
        ("not_interested", "BIGINT"),
        ("negative_feedback", "BIGINT"),
        ("unfollows", "BIGINT"),
        # outcomes
        ("conversions", "BIGINT"),
        # money (original currency + NOK-normalised)
        ("currency", "VARCHAR"),
        ("spend", "DOUBLE"),
        ("conversion_value", "DOUBLE"),
        ("spend_nok", "DOUBLE"),
        ("conversion_value_nok", "DOUBLE"),
    ),
    primary_key=("account_id", "campaign_id", "creative_id", "placement_id", "segment_id", "date"),
)

ORGANIC_PERFORMANCE = TableSpec(
    "organic_performance",
    (
        ("account_id", "VARCHAR"),
        ("post_id", "VARCHAR"),
        ("creative_id", "VARCHAR"),  # organic posts link to the creative dimension too
        ("placement_id", "VARCHAR"),
        ("date", "DATE"),
        ("impressions", "BIGINT"),
        ("reach", "BIGINT"),
        ("likes", "BIGINT"),
        ("comments_count", "BIGINT"),
        ("shares", "BIGINT"),
        ("saves", "BIGINT"),
        ("video_plays", "BIGINT"),
        ("video_completions", "BIGINT"),
        ("avg_watch_time_sec", "DOUBLE"),
        ("is_boosted", "BOOLEAN"),
        ("boosted_date", "DATE"),
    ),
    primary_key=("account_id", "post_id", "placement_id", "date"),
)

COMMENT = TableSpec(
    "comment",
    (
        ("comment_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("ref_type", "VARCHAR"),   # ad | organic
        ("ref_id", "VARCHAR"),     # creative_id or post_id
        ("channel", "VARCHAR"),
        ("date", "DATE"),
        ("author_hash", "VARCHAR"),  # salted hash — never a raw identity (GDPR)
        ("language", "VARCHAR"),
        ("text", "VARCHAR"),
    ),
    primary_key=("comment_id",),
)


# Ordered so that dimensions are created/loaded before facts that reference them.
TABLES: tuple[TableSpec, ...] = (
    ACCOUNT,
    CAMPAIGN,
    PLACEMENT,
    AUDIENCE_SEGMENT,
    CREATIVE,
    DATE_DIM,
    FX_RATE,
    AD_PERFORMANCE,
    ORGANIC_PERFORMANCE,
    COMMENT,
)

TABLES_BY_NAME: dict[str, TableSpec] = {t.name: t for t in TABLES}


def all_create_sql() -> str:
    return "\n\n".join(t.create_sql() for t in TABLES)
