# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Untagged-spend reporting and writing resolved tags back to the database.

Untagged spend is reported as a *share of total NOK spend*, compared against
``thresholds.untagged_spend_warn_share``. It is never silently imputed: the
whole point is to tell the buyer how much of their money is flowing through
creative whose provenance nobody has recorded, so they can go and tag it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .resolver import RESOLVED_COLUMNS, tag_creatives
from ..config import load_config


@dataclass
class UntaggedSpendReport:
    total_spend_nok: float
    untagged_spend_nok: float
    untagged_share: float
    untagged_creative_count: int
    total_creative_count: int
    warn_threshold: float
    over_threshold: bool

    def as_dict(self) -> dict:
        return asdict(self)


def untagged_spend(con, cfg: dict | None = None) -> UntaggedSpendReport:
    """Spend flowing through untagged creative, as a share of total NOK spend."""
    cfg = cfg or load_config()
    threshold = float(cfg["thresholds"]["untagged_spend_warn_share"])

    total_nok, untagged_nok = con.execute(
        """
        SELECT
            COALESCE(SUM(ap.spend_nok), 0.0),
            COALESCE(SUM(ap.spend_nok) FILTER (WHERE c.provenance IS NULL), 0.0)
        FROM ad_performance ap
        JOIN creative c USING (creative_id)
        """
    ).fetchone()

    total_cre, untagged_cre = con.execute(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE provenance IS NULL) FROM creative"
    ).fetchone()

    share = (untagged_nok / total_nok) if total_nok else 0.0
    return UntaggedSpendReport(
        total_spend_nok=round(float(total_nok), 2),
        untagged_spend_nok=round(float(untagged_nok), 2),
        untagged_share=round(share, 4),
        untagged_creative_count=int(untagged_cre),
        total_creative_count=int(total_cre),
        warn_threshold=threshold,
        over_threshold=share > threshold,
    )


def apply_to_db(con, cfg: dict | None = None, *,
                overrides: dict | None = None,
                platform_labels: dict | None = None,
                c2pa: dict | None = None) -> int:
    """Resolve tags for every creative in the DB and write them back in place.

    This is the ``ingest -> tagging`` step: Phase 2 loads creatives as
    ``untagged``; this fills provenance / sub-type / Norwegian-ness from the
    naming convention and any supplied overrides. Returns the row count tagged
    (resolved to a non-null provenance).
    """
    cfg = cfg or load_config()
    creatives = con.execute("SELECT * FROM creative").fetchdf()
    if creatives.empty:
        return 0

    tagged = tag_creatives(creatives, cfg, overrides=overrides,
                           platform_labels=platform_labels, c2pa=c2pa)

    # Write back only the resolved columns, keyed by creative_id, in one pass.
    con.register("_tagged", tagged[["creative_id", *RESOLVED_COLUMNS]])
    set_clause = ", ".join(f"{col} = t.{col}" for col in RESOLVED_COLUMNS)
    con.execute(
        f"UPDATE creative AS c SET {set_clause} "
        "FROM _tagged AS t WHERE c.creative_id = t.creative_id"
    )
    con.unregister("_tagged")

    (n_tagged,) = con.execute(
        "SELECT COUNT(*) FROM creative WHERE provenance IS NOT NULL"
    ).fetchone()
    return int(n_tagged)
