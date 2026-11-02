"""DuckDB storage: create the schema and load dataframes into it.

Column order is taken from the TableSpec, so loaders never have to match the
DDL by hand. Loading validates that every required column is present and loads
them in canonical order.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .ddl import TABLES, TABLES_BY_NAME, TableSpec


def connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open (or create) a DuckDB database. None -> in-memory."""
    target = ":memory:" if db_path is None else str(db_path)
    return duckdb.connect(target)


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create all tables (idempotent)."""
    for spec in TABLES:
        con.execute(spec.create_sql())


def _coerce_dates(df: pd.DataFrame, spec: TableSpec) -> pd.DataFrame:
    """Ensure DATE columns arrive as date objects, not strings/timestamps."""
    date_cols = [c for c, t in spec.columns if t == "DATE"]
    for c in date_cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c]).dt.date
    return df


def load_table(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> int:
    """Insert a dataframe into `table`, selecting columns in canonical order.

    Returns the number of rows inserted. Raises if required columns are missing.
    """
    spec = TABLES_BY_NAME.get(table)
    if spec is None:
        raise KeyError(f"Unknown table: {table}")

    missing = [c for c in spec.column_names if c not in df.columns]
    if missing:
        raise ValueError(f"{table}: dataframe missing columns {missing}")

    ordered = _coerce_dates(df.copy(), spec)[spec.column_names]
    con.register("_load_df", ordered)
    try:
        con.execute(f"INSERT INTO {table} SELECT * FROM _load_df")
    finally:
        con.unregister("_load_df")
    return len(ordered)


def load_all(con: duckdb.DuckDBPyConnection, frames: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Load a mapping of table-name -> dataframe, in dependency order."""
    counts: dict[str, int] = {}
    for spec in TABLES:  # dependency order
        if spec.name in frames:
            counts[spec.name] = load_table(con, spec.name, frames[spec.name])
    return counts


def table_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Row counts for every known table that exists."""
    existing = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    return {
        spec.name: con.execute(f"SELECT COUNT(*) FROM {spec.name}").fetchone()[0]
        for spec in TABLES
        if spec.name in existing
    }
