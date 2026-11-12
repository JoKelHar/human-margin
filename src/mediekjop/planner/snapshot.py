# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Public ad-volume snapshots (day-one context layer).

A *snapshot* is a dated, versioned summary of the public ad volume for a planner
industry in Norway, taken from an official transparency product (Meta Ad Library
/ EU DSA) within its terms - never scraped. It carries no performance data: just
how many ads were sampled, what content types they are (tagged with the existing
tagging module), and a run-length longevity proxy. Its provenance tier is
``public_snapshot``: public, aggregate, dated, with the sample size always shown.

The planner shows a snapshot as *context* only, as a position ("of N sampled
Oslo nightlife ads, ~X% were UGC-style; median run length Y days"; N is an exact
count so it carries no "~", the shares do), never as a recommendation. A snapshot is populated by ``scripts/fetch_ad_library.py`` (which
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

# Columns every coded row must carry. `ai_read` and `advertiser` are optional
# (added for next round); a missing `ai_read` is read as "unsure".
_MANUAL_COLUMNS = ("ad_url", "industry", "content_type", "start_date",
                   "still_active", "coder", "date_coded")
_TRUE = {"y", "yes", "true", "1", "active"}

# content_type is a FORMAT only. ai_mockup stays a planner format but is NOT a
# snapshot coding option (you cannot reliably tell a mock-up from the public
# library), so it is excluded here; `other` catches anything that fits none.
_EXCLUDE_FROM_CODING = {"ai_mockup"}

# ai_read = how artificial the ad READS to an experienced coder (perceived
# artificiality), NOT a claim about how it was actually made. Always tagged
# "coder judgement". A missing value is "unsure" (counted, never dropped).
AI_READ_VALUES = ("none", "some", "heavy", "unsure")
AI_READ_TAG = "coder judgement"
_AI_READ_DEFAULT = "unsure"


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
    content_type_share: dict[str, float] = field(default_factory=dict)  # format -> share 0..1
    median_run_days: float | None = None
    method: str = ""                  # how the sample was taken (manual / API)
    provenance: str = PROVENANCE
    ai_read_share: dict[str, float] = field(default_factory=dict)       # ai_read -> share 0..1
    format_by_ai_read: dict[str, dict[str, int]] = field(default_factory=dict)  # format x ai_read counts
    all_active: bool = False          # every sampled ad was still running (run length is a lower bound)

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
        ai_read_share=dict(d.get("ai_read_share") or {}),
        format_by_ai_read={k: dict(v) for k, v in (d.get("format_by_ai_read") or {}).items()},
        all_active=bool(d.get("all_active", False)),
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
    return (set(load_formats().keys()) - _EXCLUDE_FROM_CODING) | {"other"}


def _ctype_label(key: str) -> str:
    """Display label for a content_type: the formats.yaml label (lower-cased for
    mid-sentence copy), never the raw key. Falls back to the key for `other` or any
    non-format code (the copy rule: user-facing text uses labels, not keys)."""
    f = load_formats().get(key)
    return f.label.lower() if f else key


def _parse_date(s: str, where: str) -> date:
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except (ValueError, AttributeError) as exc:
        raise SnapshotError(f"{where}: bad date {s!r} (want YYYY-MM-DD)") from exc


def _norm(s: str | None) -> str:
    """Normalise a categorical cell: trim and lower-case. The literal string
    'None' is a value (e.g. ai_read reads as none/real), never treated as missing."""
    return (s or "").strip().lower()


def _ai_read(row: dict, where: str) -> str:
    """Perceived-artificiality tag for one row. A missing/blank value is 'unsure'
    (counted, never dropped); an unknown non-blank value is rejected, not guessed."""
    if "ai_read" not in row:
        return _AI_READ_DEFAULT
    v = _norm(row.get("ai_read"))
    if v == "":
        return _AI_READ_DEFAULT
    if v not in AI_READ_VALUES:
        raise SnapshotError(
            f"{where}: ai_read {row.get('ai_read')!r} is not one of {AI_READ_VALUES} "
            f"(see docs/snapshot-coding-guide.md)")
    return v


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
    and provenance ``public_snapshot``: content-type (format) shares, an ``ai_read``
    perception share, the format x ai_read cross-tab, a run-length longevity proxy
    (``date_coded - start_date``, in days) and the sample size N. No performance data
    is read or stored. ``content_type`` must be one of the snapshot coding formats
    (or ``other``); an unknown content_type or ai_read value raises rather than being
    silently dropped. Case is normalised on load; a start date later than its coding
    date is rejected; the literal string ``"None"`` is a value, never "missing".
    """
    rows = list(csv.DictReader(Path(csv_path).read_text(encoding="utf-8").splitlines()))
    valid = _valid_content_types()
    by_industry: dict[str, list[dict]] = {}
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        missing = [c for c in _MANUAL_COLUMNS if c not in row]
        if missing:
            raise SnapshotError(f"manual sample {csv_path} row {i}: missing column(s) {missing}")
        where = f"manual sample row {i} ({row.get('ad_url', '?')})"
        ind = _norm(row["industry"])
        ctype = _norm(row["content_type"])
        if not ind:
            raise SnapshotError(f"{where}: empty industry")
        if ctype not in valid:
            raise SnapshotError(
                f"{where}: content_type {row['content_type']!r} is not a snapshot coding "
                f"format (expected one of {sorted(valid)}; see docs/snapshot-coding-guide.md)")
        start = _parse_date(row["start_date"], where)
        coded = _parse_date(row["date_coded"], where)
        if start > coded:
            raise SnapshotError(
                f"{where}: start_date {start} is after the coding date {coded} "
                f"(a future start date is rejected, not clamped)")
        row["_industry"] = ind
        row["_content_type"] = ctype
        row["_ai_read"] = _ai_read(row, where)
        row["_start"] = start
        row["_coded"] = coded
        row["_active"] = _norm(row["still_active"]) in _TRUE
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
        n = len(items)
        content_share = {k: v / n for k, v in Counter(r["_content_type"] for r in items).items()}
        ai_read_share = {k: v / n for k, v in Counter(r["_ai_read"] for r in items).items()}
        cross: dict[str, dict[str, int]] = {}
        for r in items:
            cross.setdefault(r["_content_type"], {})
            cross[r["_content_type"]][r["_ai_read"]] = cross[r["_content_type"]].get(r["_ai_read"], 0) + 1
        runs = [float(max((r["_coded"] - r["_start"]).days, 0)) for r in items]
        out[ind] = Snapshot(
            industry=ind, market=_market_for(ind), as_of=max(r["_coded"] for r in items),
            n=n, status="sampled", source=src,
            content_type_share=content_share,
            median_run_days=float(statistics.median(runs)) if runs else None,
            method="manual_sample",
            ai_read_share=ai_read_share, format_by_ai_read=cross,
            all_active=all(r["_active"] for r in items),
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
        parts.append(f"~{top[1] * 100:.0f}% were {_ctype_label(top[0])}")
    if snap.ai_read_share:
        touched = snap.ai_read_share.get("some", 0.0) + snap.ai_read_share.get("heavy", 0.0)
        parts.append(f"~{touched * 100:.0f}% read as AI-touched ({AI_READ_TAG})")
    if snap.median_run_days is not None:
        # All Ad Library ads here are still live (Norway ads are not retained once
        # stopped), so the run length is days live so far - a lower bound, not a total.
        run = (f"median {snap.median_run_days:g} days live so far (lower bound; all still running)"
               if snap.all_active else f"median run length {snap.median_run_days:g} days")
        parts.append(run)
    tail = "; ".join(parts) if parts else "content types pending tagging"
    when = f" ({snap.as_of:%b %Y})" if snap.as_of else ""
    # N is an exact count, so no "~" on it (the copy rule); the shares keep "~".
    return f"Of {snap.n} sampled {snap.market} ads{when}, {tail}. [{PROVENANCE}]"
