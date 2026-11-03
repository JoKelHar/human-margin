# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Unified placement-grain schema and DuckDB storage.

Public surface:
    enums        controlled vocabularies (Channel, Provenance, ...)
    ddl.TABLES   the schema definition (single source of truth)
    database.*   connect / create_schema / load_all / table_counts
"""

from . import database, ddl, enums  # noqa: F401
from .ddl import TABLES, TABLES_BY_NAME  # noqa: F401

__all__ = ["database", "ddl", "enums", "TABLES", "TABLES_BY_NAME"]
