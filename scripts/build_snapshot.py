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
    ap.add_argument("--source", default=None,
                    help="method note written verbatim to the snapshot's source field")
    args = ap.parse_args()

    snaps = load_manual_sample(args.csv, market=args.market, source=args.source)
    if not snaps:
        raise SystemExit("No rows found in the CSV.")

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    for ind, snap in snaps.items():
        doc = {
            "industry": snap.industry, "market": snap.market,
            "as_of": snap.as_of.isoformat() if snap.as_of else None,
            "n": snap.n, "status": snap.status, "provenance": snap.provenance,
            "source": snap.source, "method": snap.method,
            # Run length is days LIVE SO FAR (a lower bound): every ad is still running.
            "median_run_days": snap.median_run_days, "all_active": snap.all_active,
            "content_type_share": {k: round(v, 4) for k, v in snap.content_type_share.items()},
            "ai_read_share": {k: round(v, 4) for k, v in snap.ai_read_share.items()},
            "ai_read_basis": "coder judgement (perceived artificiality, not provenance)",
            "format_by_ai_read": {k: dict(v) for k, v in snap.format_by_ai_read.items()},
        }
        out = SNAP_DIR / f"{ind}.yaml"
        out.write_text(
            "# Public ad-volume snapshot (manual sample). Maintainer-built, committed,\n"
            "# bundled to users. No performance data. See docs/snapshot-coding-guide.md.\n"
            + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        print(f"Wrote {out}\n")
        _report(snap)


def _report(snap) -> None:
    """Print format share, ai_read share and the format x ai_read cross-tab, each with N."""
    n = snap.n
    run = (f"median {snap.median_run_days:g} days live so far (lower bound; all still active)"
           if snap.all_active else f"median run length {snap.median_run_days} days")
    print(f"  N={n}  as_of={snap.as_of}  {run}")

    print(f"\n  Format share (n={n}):")
    for k, v in sorted(snap.content_type_share.items(), key=lambda kv: -kv[1]):
        print(f"    {k:18} {v * 100:5.1f}%  ({round(v * n)})")

    print(f"\n  ai_read share (coder judgement; perceived artificiality, n={n}):")
    for k in ("none", "some", "heavy", "unsure"):
        if k in snap.ai_read_share:
            v = snap.ai_read_share[k]
            print(f"    {k:18} {v * 100:5.1f}%  ({round(v * n)})")

    reads = [r for r in ("none", "some", "heavy", "unsure")
             if any(r in row for row in snap.format_by_ai_read.values())]
    print(f"\n  Format x ai_read cross-tab (counts, n={n}):")
    print("    " + "format".ljust(18) + "".join(r.rjust(8) for r in reads) + "   total")
    for fmt, row in sorted(snap.format_by_ai_read.items(),
                           key=lambda kv: -sum(kv[1].values())):
        tot = sum(row.values())
        print("    " + fmt.ljust(18) + "".join(str(row.get(r, 0)).rjust(8) for r in reads)
              + f"   {tot}")


if __name__ == "__main__":
    main()
