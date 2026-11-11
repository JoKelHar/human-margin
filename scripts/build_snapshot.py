# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Build dated, versioned market snapshots from a hand-coded CSV (manual fallback).

The manual alternative to scripts/fetch_ad_library.py when a Meta Ad Library API
token is not available. A maintainer tags 30-50 public Ad Library ads per industry
into a CSV (template: data/snapshots/manual_sample_template.csv; coding guide:
docs/snapshot-coding-guide.md); this aggregates per industry and writes
data/snapshots/<industry>.yaml with provenance public_snapshot, method
manual_sample, sample size N and as_of date. No performance data is stored.

    uv run python scripts/build_snapshot.py coded_sample.csv --market "Oslo nightlife"

`--market` may be given once (applied to every industry in the file) or omitted
(the industry key is used as the label). Existing snapshot files are overwritten
only after a short diff summary is printed; review and commit the result.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from mediekjop.planner.snapshot import load_manual_sample

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / "data" / "snapshots"


def main() -> None:
    ap = argparse.ArgumentParser(description="Build manual-sample snapshots from a coded CSV.")
    ap.add_argument("csv", help="path to the hand-coded CSV")
    ap.add_argument("--market", default=None, help="market label applied to every industry")
    args = ap.parse_args()

    snaps = load_manual_sample(args.csv, market=args.market)
    if not snaps:
        raise SystemExit("No rows found in the CSV.")

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    for ind, snap in snaps.items():
        doc = {
            "industry": snap.industry, "market": snap.market,
            "as_of": snap.as_of.isoformat() if snap.as_of else None,
            "n": snap.n, "status": snap.status, "provenance": snap.provenance,
            "source": snap.source, "method": snap.method,
            "median_run_days": snap.median_run_days,
            "content_type_share": {k: round(v, 4) for k, v in snap.content_type_share.items()},
        }
        out = SNAP_DIR / f"{ind}.yaml"
        out.write_text(
            "# Public ad-volume snapshot (manual sample). Maintainer-built, committed,\n"
            "# bundled to users. No performance data. See docs/snapshot-coding-guide.md.\n"
            + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        top = max(snap.content_type_share.items(), key=lambda kv: kv[1], default=("-", 0.0))
        print(f"Wrote {out}  (N={snap.n}, as_of {snap.as_of}, top {top[0]} ~{top[1] * 100:.0f}%, "
              f"median run {snap.median_run_days} days)")


if __name__ == "__main__":
    main()
