# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Public ad-volume snapshot: provenance, date, N, and context rendering."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from mediekjop.planner.snapshot import (
    SnapshotError,
    context_line,
    load_snapshot,
    load_snapshots,
)

ROOT = Path(__file__).resolve().parents[1]


def test_shipped_placeholder_carries_date_n_and_provenance():
    snap = load_snapshot(ROOT / "data" / "snapshots" / "uteliv.yaml")
    assert snap.provenance == "public_snapshot"
    assert isinstance(snap.as_of, dt.date)
    assert snap.n == 0 and not snap.populated          # honest empty slot
    assert "No public ad-volume snapshot" in context_line(snap)


def test_populated_snapshot_renders_a_context_position(tmp_path):
    p = tmp_path / "uteliv.yaml"
    p.write_text(
        "industry: uteliv\nmarket: 'Oslo nightlife'\nas_of: 2026-11-01\nn: 120\n"
        "status: sampled\nprovenance: public_snapshot\n"
        "source: 'Meta Ad Library API (illustrative fixture)'\n"
        "method: 'API sample'\nmedian_run_days: 14\n"
        "content_type_share: {UGC-style: 0.42, studio: 0.31, static: 0.27}\n",
        encoding="utf-8")
    snap = load_snapshot(p)
    assert snap.populated and snap.n == 120
    line = context_line(snap)
    assert "~120 sampled" in line and "42%" in line and "14 days" in line
    assert "public_snapshot" in line


def test_bad_provenance_is_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("industry: x\nmarket: y\nstatus: sampled\nsource: s\nprovenance: scraped\n",
                 encoding="utf-8")
    with pytest.raises(SnapshotError):
        load_snapshot(p)


def test_load_snapshots_directory_keys_by_industry():
    snaps = load_snapshots()
    assert "uteliv" in snaps
