# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Forward calendar **patterns** — descriptive, never prescriptive.

Each pattern names an **advertiser category**, a **moment** and a **time window**,
then states **what has happened** in that window (the observed pattern) and the
**evidence** behind it: how many accounts, how many prior years, which market and
how much confidence. It never tells the reader what to do — no "opportunity",
"should" or "best time to". A moment with no obvious advertiser category is
**dropped**, not reworded, so the list never pads itself with vague entries.

Advertiser category and the observed pattern are configured per calendar moment in
``config.calendar.moments``; the time window and lead time come from the dated
calendar windows, and a short history read fills in the evidence line.
"""

from __future__ import annotations

import datetime as dt

from ..synthetic.calendar_effects import windows_for_years

# The fields every pattern must carry.
REQUIRED_FIELDS = ("category", "moment", "window", "pattern")

# One shared line for moments with no established history, instead of repeating it.
# Descriptive, not an instruction: it states the absence of a pattern.
UNTESTED_NOTE = ("Some moments have no reliable history yet, so no pattern is "
                 "established for them — a blank, not a recommendation.")


def _timing(weeks: int) -> str:
    """Plain-language lead time instead of '~Nw out'."""
    if weeks <= 0:
        return "starts this week"
    if weeks == 1:
        return "in 1 week"
    return f"in {weeks} weeks"


def upcoming_patterns(con, cfg: dict, today: dt.date, min_impr: int,
                      limit: int = 5) -> list[dict]:
    """Return up to ``limit`` upcoming calendar **patterns** (descriptive).

    ``con`` is a DuckDB connection over the (synthetic) data, used only for the
    optional history read; the patterns themselves are driven by config. Each
    item carries a ``pattern`` (what has happened) and an ``evidence`` line
    (accounts, prior years, market, confidence) — never an instruction.
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
            # What happened + the evidence behind it (N, years, market, confidence).
            evidence = (f"Human-led ROAS ran {lift:+.0f}% vs AI in this window last "
                        f"year · 1 synthetic account · 1 prior year · NO · low confidence")
        else:
            status = "untested"
            evidence = "No established history · 0 prior years · no pattern yet"

        seen[w.key] = {
            "category": category,
            "moment": w.label,
            "window": f"{w.start.isoformat()} to {w.end.isoformat()}",
            "timing": _timing(weeks),
            "pattern": meta.get("pattern", meta.get("approach", "")),
            "evidence": evidence,
            "weeks_out": weeks,
            "status": status,
        }
        if len(seen) >= limit:
            break
    return sorted(seen.values(), key=lambda m: m["weeks_out"])
