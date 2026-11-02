"""Shared pytest fixtures: a small synthetic dataset and an in-memory DuckDB."""

from __future__ import annotations

import datetime as dt

import duckdb
import pytest

from mediekjop.config import load_config
from mediekjop.schema import database
from mediekjop.synthetic import GeneratorConfig, generate


@pytest.fixture(scope="session")
def cfg() -> dict:
    return load_config()


@pytest.fixture(scope="session")
def dataset(cfg):
    gc = GeneratorConfig(seed=123, n_accounts=1, start_date=dt.date(2025, 3, 1),
                         days=70, n_creatives_per_account=14)
    return generate(gc, cfg)


@pytest.fixture()
def con(dataset) -> duckdb.DuckDBPyConnection:
    c = database.connect(None)  # in-memory
    database.create_schema(c)
    database.load_all(c, dataset.frames)
    yield c
    c.close()
