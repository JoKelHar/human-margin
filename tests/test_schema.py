# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Schema creation, DDL integrity and load round-trip."""

from __future__ import annotations

import duckdb
import pytest

from mediekjop.schema import database
from mediekjop.schema.ddl import AD_PERFORMANCE, TABLES, TABLES_BY_NAME


def test_all_tables_created(con):
    existing = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    for spec in TABLES:
        assert spec.name in existing


def test_facts_carry_placement_grain():
    # Both fact tables must keep placement_id (never rolled up to campaign).
    assert "placement_id" in TABLES_BY_NAME["ad_performance"].column_names
    assert "placement_id" in TABLES_BY_NAME["organic_performance"].column_names


def test_money_columns_are_dual_currency():
    cols = TABLES_BY_NAME["ad_performance"].column_names
    for c in ("currency", "spend", "spend_nok", "conversion_value", "conversion_value_nok"):
        assert c in cols


def test_comment_has_hash_not_identity():
    cols = TABLES_BY_NAME["comment"].column_names
    assert "author_hash" in cols
    assert "author" not in cols and "author_id" not in cols


def test_load_rejects_missing_columns():
    import pandas as pd
    c = database.connect(None)
    database.create_schema(c)
    with pytest.raises(ValueError):
        database.load_table(c, "account", pd.DataFrame({"account_id": ["x"]}))
    c.close()


def test_ad_performance_grain_is_unique(con):
    pk = list(AD_PERFORMANCE.primary_key)
    n_total = con.execute("SELECT COUNT(*) FROM ad_performance").fetchone()[0]
    n_distinct = con.execute(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT {', '.join(pk)} FROM ad_performance)"
    ).fetchone()[0]
    assert n_total == n_distinct > 0
