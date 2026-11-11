# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Public ad-volume snapshots (day-one context layer).

A *snapshot* is a dated, versioned summary of the public ad volume for a planner
industry in Norway, taken from an official transparency product (Meta Ad Library
/ EU DSA) within its terms - never scraped. It carries no performance data: just
how many ads were sampled, what content types they are (tagged with the existing
tagging module), and a run-length longevity proxy. Its provenance tier is
``public_snapshot``: public, aggregate, dated, with the sample size always shown.

The planner shows a snapshot as *context* only, as a position ("of ~N sampled
Oslo nightlife ads, ~X% were UGC-style; median run length Y days"), never as a
recommendation. A snapshot is populated by ``scripts/fetch_ad_library.py`` (which
needs a Meta Ad Library API token); until then its status is ``awaiting_fetch``
and nothing is invented.
"""

from __future__ import annotations

import csv
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from ..config import repo_root
from .formats import load_formats

PROVENANCE = "public_snapshot"

# Content types a coder may record in a manual sample. The format keys from
# formats.yaml, plus "other" for anything that fits none (kept, never dropped).
_MANUAL_COLUMNS = ("ad_url", "industry", "content_type", "start_date",
                   "still_active", "coder", "date_coded")
_TRUE = {"y", "yes", "true", "1", "active"}


class SnapshotError(ValueError):
    """Raised for a malformed snapshot file."""


@dataclass
class Snapshot:
    industry: str
    market: str                       # e.g. "Oslo nightlife", "Norway"
    as_of: date | None
    n: int                            # sample size (0 until fetched)
    status: str                       # "awaiting_fetch" | "sampled"
    source: str                       # which transparency product + access
    content_type_share: dict[str, float] = field(default_factory=dict)  # tag -> share 0..1
    median_run_days: float | None = None
    method: str = ""                  # how the sample was taken (manual / API)
    provenance: str = PROVENANCE

    @property
    def populated(self) -> bool:
        return self.status == "sampled" and self.n > 0


def _snapshots_dir() -> Path:
    return repo_root() / "data" / "snapshots"


def load_snapshot(path: str | Path) -> Snapshot:
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for k in ("industry", "market", "status", "source"):
        if k not in d:
            raise SnapshotError(f"snapshot {path} missing field {k!r}")
    as_of = d.get("as_of")
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    prov = d.get("provenance", PROVENANCE)
    if prov != PROVENANCE:
        raise SnapshotError(f"snapshot provenance must be {PROVENANCE!r}, got {prov!r}")
    return Snapshot(
        industry=d["industry"], market=d["market"], as_of=as_of, n=int(d.get("n", 0)),
        status=d["status"], source=d["source"],
        content_type_share=dict(d.get("content_type_share") or {}),
        median_run_days=d.get("median_run_days"), method=d.get("method", ""), provenance=prov,
    )


def load_snapshots(directory: str | Path | None = None) -> dict[str, Snapshot]:
    """Load every snapshot in data/snapshots/, keyed by industry."""
    d = Path(directory) if directory else _snapshots_dir()
    out: dict[str, Snapshot] = {}
    if not d.exists():
        return out
    for p in sorted(d.glob("*.yaml")):
        snap = load_snapshot(p)
        out[snap.industry] = snap
    return out


def _valid_content_types() -> set[str]:
    return set(load_formats().keys()) | {"other"}


def _parse_date(s: str, where: str) -> date:
    try:
        return date.fromisoformat(s.strip()[:10])
    except (ValueError, AttributeError) as exc:
        raise SnapshotError(f"{where}: bad date {s!r} (want YYYY-MM-DD)") from exc


def load_manual_sample(
    csv_path: str | Path,
    *,
    market: str | dict[str, str] | None = None,
    source: str | None = None,
) -> dict[str, Snapshot]:
    """Build snapshots from a hand-coded CSV of public Ad Library ads.

    The manual fallback to :mod:`scripts.fetch_ad_library` when an API token is
    not available: a maintainer tags 30-50 ads per industry straight from the
    public Ad Library website into a CSV (template at
    ``data/snapshots/manual_sample_template.csv``; coding guide at
    ``docs/snapshot-coding-guide.md``). Columns: ``ad_url, industry,
    content_type, start_date, still_active, coder, date_coded``.

    Aggregates per industry into a :class:`Snapshot` with ``method="manual_sample"``
    and provenance ``public_snapshot``: content-type shares, a run-length
    longevity proxy (``date_coded - start_date``, in days) and the sample size N.
    No performance data is read or stored. ``content_type`` must be one of the
    formats in formats.yaml (or ``other``); an unknown value raises rather than
    being silently dropped.
    """
    rows = list(csv.DictReader(Path(csv_path).read_text(encoding="utf-8").splitlines()))
    valid = _valid_content_types()
    by_industry: dict[str, list[dict]] = {}
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        missing = [c for c in _MANUAL_COLUMNS if c not in row]
        if missing:
            raise SnapshotError(f"manual sample {csv_path} row {i}: missing column(s) {missing}")
        ind = (row["industry"] or "").strip()
        ctype = (row["content_type"] or "").strip()
        if not ind:
            raise SnapshotError(f"manual sample row {i}: empty industry")
        if ctype not in valid:
            raise SnapshotError(
                f"manual sample row {i}: content_type {ctype!r} is not a known format "
                f"(expected one of {sorted(valid)}; see docs/snapshot-coding-guide.md)")
        by_industry.setdefault(ind, []).append(row)

    def _market_for(ind: str) -> str:
        if isinstance(market, dict):
            return market.get(ind, ind)
        return market or ind

    src = source or (
        "Manual sample, tagged by hand from the public Meta Ad Library website "
        "(no API, no scraping); official transparency product, within terms.")
    out: dict[str, Snapshot] = {}
    for ind, items in by_industry.items():
        shares = Counter((r["content_type"] or "").strip() for r in items)
        n = len(items)
        content_share = {k: v / n for k, v in shares.items()}
        runs: list[float] = []
        coded_dates: list[date] = []
        for r in items:
            start = _parse_date(r["start_date"], f"row for {r.get('ad_url', '?')}")
            coded = _parse_date(r["date_coded"], f"row for {r.get('ad_url', '?')}")
            coded_dates.append(coded)
            runs.append(float(max((coded - start).days, 0)))
        out[ind] = Snapshot(
            industry=ind, market=_market_for(ind), as_of=max(coded_dates),
            n=n, status="sampled", source=src,
            content_type_share=content_share,
            median_run_days=float(statistics.median(runs)) if runs else None,
            method="manual_sample",
        )
    return out


def context_line(snap: Snapshot) -> str:
    """One plain-language context line (a position), or one quiet 'not yet' line.

    When no snapshot is populated the planner says one quiet line and nothing
    else - no error, no prompt to connect or fetch. Trying the tool never needs a
    token, an account or a network call (docs/principles.md, zero-integration).
    """
    if not snap.populated:
        return "No market snapshot yet."
    parts = []
    if snap.content_type_share:
        top = max(snap.content_type_share.items(), key=lambda kv: kv[1])
        parts.append(f"~{top[1] * 100:.0f}% were {top[0]}")
    if snap.median_run_days is not None:
        parts.append(f"median run length {snap.median_run_days:g} days")
    tail = "; ".join(parts) if parts else "content types pending tagging"
    when = f" ({snap.as_of:%b %Y})" if snap.as_of else ""
    return f"Of ~{snap.n} sampled {snap.market} ads{when}, {tail}. [{PROVENANCE}]"
