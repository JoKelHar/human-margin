# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Packaging: the standalone planner installs and runs without DuckDB.

DuckDB is the agent's data store, not the planner's. These tests pin the split so
a core install (planner only) and the full agent install (`--extra agent`) both
stay honest: the planner never imports duckdb, and the extra is where duckdb lives.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_duckdb_is_not_a_core_dependency():
    deps = _pyproject()["project"]["dependencies"]
    assert not any("duckdb" in d for d in deps), "duckdb must be an optional extra, not core"


def test_duckdb_is_declared_in_the_agent_extra():
    extras = _pyproject()["project"]["optional-dependencies"]
    assert "agent" in extras
    assert any("duckdb" in d for d in extras["agent"]), "the agent extra must provide duckdb"


def test_planner_source_has_no_duckdb_import():
    planner = ROOT / "src" / "mediekjop" / "planner"
    for py in planner.glob("*.py"):
        assert "import duckdb" not in py.read_text(encoding="utf-8"), f"{py.name} imports duckdb"


def test_planner_imports_without_loading_duckdb():
    # A core install has no duckdb. Prove the planner import path never pulls it,
    # in a clean subprocess so other tests' imports don't mask it.
    code = (
        "import sys; import mediekjop.planner as p; "
        "from mediekjop.planner import estimate, load_scenario, tag; "
        "assert 'duckdb' not in sys.modules, sorted(m for m in sys.modules if 'duck' in m)"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
