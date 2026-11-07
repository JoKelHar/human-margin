# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Human-vs-AI decision matrix at channel x placement grain.

Every verdict states the metric that decided it and is backed by values shown in
the same row:

  * **ROAS** decides when both sides have enough conversions to make ROAS
    reliable (``thresholds.min_conversions_for_cpa``); the row shows both ROAS
    figures.
  * Otherwise the verdict falls back to **saves** (engagement quality), the row
    shows both saves figures, and ROAS is reported as ``None`` (rendered
    ``n/a``) rather than a misleading near-zero number.
  * Below ``thresholds.min_impressions_for_verdict`` impressions the cell is
    **insufficient data** and gets no verdict.

This is a descriptive prototype, not the Phase-4 statistical engine.
"""

from __future__ import annotations

import math

# Verdict thresholds on the deciding-metric gap (human minus AI).
MIN_GAP_ROAS = 0.15             # ROAS points
MIN_GAP_SAVE_PERMILLE = 0.50    # saves per thousand impressions

_CELLS_SQL = """
WITH grp AS (
  SELECT p.channel, p.placement_name,
         CASE WHEN c.provenance = 'human_led' THEN 'human' ELSE 'ai' END side,
         SUM(a.impressions) i, SUM(a.clicks) cl, SUM(a.conversions) conv,
         SUM(a.conversion_value_nok) cv, SUM(a.spend_nok) sp, SUM(a.saves) sv
  FROM ad_performance a JOIN creative c USING (creative_id)
  JOIN placement p USING (placement_id)
  WHERE c.provenance IS NOT NULL
  GROUP BY 1, 2, 3)
SELECT channel, placement_name,
  MAX(i)    FILTER (WHERE side='human') hi,    MAX(i)    FILTER (WHERE side='ai') ai_i,
  MAX(conv) FILTER (WHERE side='human') hconv, MAX(conv) FILTER (WHERE side='ai') aiconv,
  MAX(cv/NULLIF(sp,0))     FILTER (WHERE side='human') hroas, MAX(cv/NULLIF(sp,0))     FILTER (WHERE side='ai') airoas,
  MAX(sv*1000.0/NULLIF(i,0)) FILTER (WHERE side='human') hsave, MAX(sv*1000.0/NULLIF(i,0)) FILTER (WHERE side='ai') aisave,
  MAX(cl*1000.0/NULLIF(i,0)) FILTER (WHERE side='human') hctr,  MAX(cl*1000.0/NULLIF(i,0)) FILTER (WHERE side='ai') aictr
FROM grp GROUP BY 1, 2 ORDER BY 1, 2
"""


def _z(x) -> float:
    return 0.0 if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def _subtype_winner(con, channel, placement, column, is_human) -> str | None:
    side = "= 'human_led'" if is_human else "!= 'human_led'"
    row = con.execute(
        f"SELECT c.{column} s, SUM(a.conversion_value_nok)/NULLIF(SUM(a.spend_nok),0) roas "
        f"FROM ad_performance a JOIN creative c USING (creative_id) "
        f"JOIN placement p USING (placement_id) "
        f"WHERE c.{column} IS NOT NULL AND c.provenance {side} "
        f"AND p.channel = ? AND p.placement_name = ? "
        f"GROUP BY 1 HAVING SUM(a.impressions) > 1000 ORDER BY 2 DESC NULLS LAST LIMIT 1",
        [channel, placement],
    ).fetchone()
    return row[0] if row else None


def decision_matrix(con, cfg: dict) -> list[dict]:
    """Build the human-vs-AI verdict per channel x placement, with its deciding metric."""
    thr = cfg["thresholds"]
    min_impr = thr["min_impressions_for_verdict"]
    min_conv = thr.get("min_conversions_for_cpa", 25)

    rows = con.execute(_CELLS_SQL).df()
    out = []
    for r in rows.itertuples():
        hi, ai_i = _z(r.hi), _z(r.ai_i)
        hconv, aiconv = _z(r.hconv), _z(r.aiconv)
        hroas, airoas = _z(r.hroas), _z(r.airoas)
        hsave, aisave = _z(r.hsave), _z(r.aisave)
        n_impr = min(hi, ai_i)
        roas_reliable = hconv >= min_conv and aiconv >= min_conv

        decided_by = None
        sub = None
        if n_impr < min_impr:
            verdict = "Insufficient data"
            confidence = "low"
        else:
            confidence = "high" if n_impr > 5 * min_impr else "medium"
            if roas_reliable:
                decided_by = "ROAS"
                gap = hroas - airoas
            else:
                decided_by = "saves"
                gap = hsave - aisave
            floor = MIN_GAP_ROAS if decided_by == "ROAS" else MIN_GAP_SAVE_PERMILLE
            if gap > floor:
                verdict = "Human wins"
                sub = _subtype_winner(con, r.channel, r.placement_name, "human_sub_type", True)
            elif gap < -floor:
                verdict = "AI wins"
                sub = _subtype_winner(con, r.channel, r.placement_name, "ai_sub_type", False)
            else:
                verdict = "No difference"

        out.append({
            "channel": r.channel,
            "placement": r.placement_name,
            "verdict": verdict,
            "decided_by": decided_by,
            "sub_type": sub,
            "confidence": confidence,
            # ROAS is shown only when reliable; otherwise None -> rendered "n/a"
            "human_roas": round(hroas, 2) if roas_reliable else None,
            "ai_roas": round(airoas, 2) if roas_reliable else None,
            "human_save_permille": round(hsave, 2),
            "ai_save_permille": round(aisave, 2),
            "human_ctr_permille": round(_z(r.hctr), 2),
            "ai_ctr_permille": round(_z(r.aictr), 2),
            "impressions": int(hi + ai_i),
        })
    return out
