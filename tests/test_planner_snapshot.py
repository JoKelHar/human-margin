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
    load_manual_sample,
    load_snapshot,
    load_snapshots,
)

ROOT = Path(__file__).resolve().parents[1]


def test_shipped_placeholder_carries_date_n_and_provenance():
    snap = load_snapshot(ROOT / "data" / "snapshots" / "uteliv.yaml")
    assert snap.provenance == "public_snapshot"
    assert isinstance(snap.as_of, dt.date)
    assert snap.n == 0 and not snap.populated          # honest empty slot
    # One quiet line, nothing else, no prompt to connect (zero-integration).
    assert context_line(snap) == "No market snapshot yet."


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


# --- manual-sample loader (no-API fallback) --------------------------------

_SAMPLE = (
    "ad_url,industry,content_type,start_date,still_active,coder,date_coded\n"
    "https://x/?id=1,uteliv,ugc_talking_head,2026-10-01,y,ab,2026-11-11\n"
    "https://x/?id=2,uteliv,ugc_talking_head,2026-10-11,y,ab,2026-11-11\n"
    "https://x/?id=3,uteliv,short_video,2026-09-01,n,ab,2026-11-11\n"
    "https://x/?id=4,uteliv,static_image,2026-10-21,y,ab,2026-11-11\n"
)


def test_manual_sample_builds_a_public_snapshot(tmp_path):
    p = tmp_path / "coded.csv"
    p.write_text(_SAMPLE, encoding="utf-8")
    snaps = load_manual_sample(p, market="Oslo nightlife")
    snap = snaps["uteliv"]
    assert snap.provenance == "public_snapshot"       # same tier as the API pull
    assert snap.method == "manual_sample"
    assert snap.n == 4 and snap.populated
    assert isinstance(snap.as_of, dt.date)
    # shares sum to 1 and UGC is the modal type (2 of 4).
    assert snap.content_type_share["ugc_talking_head"] == 0.5
    assert abs(sum(snap.content_type_share.values()) - 1.0) < 1e-9
    assert snap.median_run_days is not None
    line = context_line(snap)
    assert "~4 sampled" in line and "public_snapshot" in line


def test_manual_sample_rejects_unknown_content_type(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text(
        "ad_url,industry,content_type,start_date,still_active,coder,date_coded\n"
        "https://x/?id=1,uteliv,carousel,2026-10-01,y,ab,2026-11-11\n",
        encoding="utf-8")
    with pytest.raises(SnapshotError):
        load_manual_sample(p)                          # never silently dropped
