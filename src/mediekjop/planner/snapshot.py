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

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from ..config import repo_root

PROVENANCE = "public_snapshot"


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


def context_line(snap: Snapshot) -> str:
    """One plain-language context line (a position), or an honest 'not yet' note."""
    if not snap.populated:
        return (f"No public ad-volume snapshot for {snap.market} yet "
                f"(awaiting an official Ad Library fetch; nothing is assumed).")
    parts = []
    if snap.content_type_share:
        top = max(snap.content_type_share.items(), key=lambda kv: kv[1])
        parts.append(f"~{top[1] * 100:.0f}% were {top[0]}")
    if snap.median_run_days is not None:
        parts.append(f"median run length {snap.median_run_days:g} days")
    tail = "; ".join(parts) if parts else "content types pending tagging"
    when = f" ({snap.as_of:%b %Y})" if snap.as_of else ""
    return f"Of ~{snap.n} sampled {snap.market} ads{when}, {tail}. [{PROVENANCE}]"
