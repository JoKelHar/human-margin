# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Forward calendar opportunities, each one actionable.

Every opportunity names four things so a buyer can act without further
interpretation: the **advertiser category**, the **moment**, the **time window**
and the **recommended creative approach** (naming the AI sub-type where it is
relevant). A moment with no obvious advertiser category is **dropped**, not
reworded, so the list never pads itself with vague entries.

Advertiser category and approach are configured per calendar moment in
``config.calendar.moments``; the time window and lead time come from the dated
calendar windows, and a short history read tells history from untested.
"""

from __future__ import annotations

import datetime as dt

from ..synthetic.calendar_effects import windows_for_years

# The four fields every opportunity must carry.
REQUIRED_FIELDS = ("category", "moment", "window", "approach")

# One shared rationale for the untested moments, instead of repeating it per card.
UNTESTED_NOTE = ("Where there is no reliable history yet, queue a matched "
                 "human-vs-AI test to establish a baseline.")


def _timing(weeks: int) -> str:
    """Plain-language lead time instead of '~Nw out'."""
    if weeks <= 0:
        return "starts this week"
    if weeks == 1:
        return "in 1 week"
    return f"in {weeks} weeks"


def upcoming_opportunities(con, cfg: dict, today: dt.date, min_impr: int,
                           limit: int = 5) -> list[dict]:
    """Return up to ``limit`` upcoming, fully-actionable calendar opportunities.

    ``con`` is a DuckDB connection over the (synthetic) data, used only for the
    optional history read; the opportunities themselves are driven by config.
    """
    moment_meta = {m["key"]: m for m in cfg["calendar"]["moments"]}
    cal_windows = windows_for_years(cfg, [today.year, today.year + 1, 2025])
    seen: dict[str, dict] = {}
    for w in sorted(cal_windows, key=lambda w: w.start):
        if w.start < today or w.key in seen:
            continue
        meta = moment_meta.get(w.key, {})
        category = meta.get("category")
        if not category:
            continue  # no obvious advertiser category -> drop the moment

        hist = con.execute(
            "SELECT 1, "
            "SUM(a.conversion_value_nok) FILTER(WHERE c.provenance='human_led')/"
            "NULLIF(SUM(a.spend_nok) FILTER(WHERE c.provenance='human_led'),0) hroas, "
            "SUM(a.conversion_value_nok) FILTER(WHERE c.provenance!='human_led')/"
            "NULLIF(SUM(a.spend_nok) FILTER(WHERE c.provenance!='human_led'),0) airoas, "
            "SUM(a.impressions) i FROM ad_performance a JOIN creative c USING(creative_id) "
            "WHERE a.date BETWEEN ? AND ?",
            [w.start.replace(year=2025) if w.start.year != 2025 else w.start,
             w.end.replace(year=2025) if w.end.year != 2025 else w.end],
        ).fetchone()
        weeks = max(0, (w.start - today).days // 7)
        if hist and hist[3] and hist[3] > min_impr and hist[1] and hist[2]:
            lift = (hist[1] - hist[2]) / hist[2] * 100
            status = "history"
            detail = f"Human-led ROAS beat AI by {lift:+.0f}% here last year."
        else:
            status = "untested"
            detail = None  # the single shared UNTESTED_NOTE covers these

        seen[w.key] = {
            "category": category,
            "moment": w.label,
            "window": f"{w.start.isoformat()} to {w.end.isoformat()}",
            "timing": _timing(weeks),
            "approach": meta.get("approach", ""),
            "weeks_out": weeks,
            "status": status,
            "detail": detail,
        }
        if len(seen) >= limit:
            break
    return sorted(seen.values(), key=lambda m: m["weeks_out"])
