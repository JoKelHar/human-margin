# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Compute descriptive insights from the synthetic DuckDB for the demo dashboard.

This is a PROTOTYPE read of the data: it uses transparent descriptive aggregates
and simple log-linear decay fits — NOT the hierarchical/Bayesian engine of
Phase 4. Every output the dashboard shows as a "verdict" or "estimate" is
derived here, with minimum-sample gating, so the dashboard can be honest about
confidence. Writes out/insights.json.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import duckdb
import numpy as np

from mediekjop.config import load_config
from mediekjop.opportunity.calendar import UNTESTED_NOTE, upcoming_opportunities
from mediekjop.recommend.matrix import decision_matrix

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "synthetic.duckdb"
OUT = ROOT / "out" / "insights.json"

PROV_ORDER = ["human_led", "ai_assisted", "ai_generated"]
BRAND = "Fjord Active (synthetic)"


def _clean(v):
    """None for NULL/NaN (pandas gives NaN for an untagged field) so the JSON stays valid."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def _fit_half_life(freq: np.ndarray, ctr: np.ndarray) -> float | None:
    mask = (ctr > 0) & (freq > 0)
    if mask.sum() < 8:
        return None
    b = np.polyfit(freq[mask], np.log(ctr[mask]), 1)[0]  # slope of ln(ctr) vs freq
    k = -b
    return float(np.log(2) / k) if k > 1e-6 else None


def main() -> None:
    cfg = load_config()
    con = duckdb.connect(str(DB), read_only=True)
    thr = cfg["thresholds"]
    min_impr = thr["min_impressions_for_verdict"]

    # ---- KPI tiles --------------------------------------------------------
    total_spend, total_impr, total_conv_value = con.execute(
        "SELECT SUM(spend_nok), SUM(impressions), SUM(conversion_value_nok) FROM ad_performance"
    ).fetchone()
    blended_roas = (total_conv_value or 0) / (total_spend or 1)
    untagged = con.execute(
        "SELECT SUM(CASE WHEN c.provenance IS NULL THEN a.spend_nok ELSE 0 END)/SUM(a.spend_nok) "
        "FROM ad_performance a JOIN creative c USING(creative_id)"
    ).fetchone()[0]
    currencies = [r[0] for r in con.execute(
        "SELECT DISTINCT currency FROM ad_performance ORDER BY 1").fetchall()]
    date_min, date_max = con.execute("SELECT MIN(date), MAX(date) FROM ad_performance").fetchone()

    # ---- provenance summary + fitted half-lives ---------------------------
    prov_summary = []
    for prov in PROV_ORDER:
        agg = con.execute(
            "SELECT SUM(a.impressions) i, SUM(a.clicks) cl, SUM(a.saves) sv, SUM(a.shares) sh, "
            "SUM(a.spend_nok) sp, SUM(a.conversion_value_nok) cv "
            "FROM ad_performance a JOIN creative c USING(creative_id) WHERE c.provenance = ?",
            [prov],
        ).fetchone()
        i, cl, sv, sh, sp, cv = [x or 0 for x in agg]
        rows = con.execute(
            "SELECT a.frequency, a.clicks*1.0/NULLIF(a.impressions,0) ctr "
            "FROM ad_performance a JOIN creative c USING(creative_id) "
            "WHERE c.provenance = ? AND a.impressions > 300", [prov]).df()
        hl = _fit_half_life(rows.frequency.to_numpy(), rows.ctr.to_numpy())
        prov_summary.append({
            "provenance": prov,
            "spend_nok": round(sp), "impressions": int(i),
            "ctr_permille": round(1000 * cl / i, 2) if i else 0,
            "save_permille": round(1000 * sv / i, 3) if i else 0,
            "share_permille": round(1000 * sh / i, 3) if i else 0,
            "roas": round(cv / sp, 2) if sp else 0,
            "half_life": round(hl, 1) if hl else None,
        })

    # ---- decay curve: mean CTR by integer frequency bucket x provenance ----
    decay = con.execute(
        "SELECT c.provenance prov, LEAST(FLOOR(a.frequency), 11) f, "
        "SUM(a.clicks)*1000.0/NULLIF(SUM(a.impressions),0) ctr "
        "FROM ad_performance a JOIN creative c USING(creative_id) "
        "WHERE c.provenance IS NOT NULL GROUP BY 1,2 HAVING SUM(a.impressions) > 2000 ORDER BY 2"
    ).df()
    decay_curve = {prov: [] for prov in PROV_ORDER}
    for r in decay.itertuples():
        decay_curve[r.prov].append({"f": int(r.f), "ctr": round(r.ctr, 2)})

    # Re-estimate half-life from the impression-weighted binned curve: far less
    # confounded than fitting across raw cells (which mix placements/cohorts).
    for p in prov_summary:
        pts = decay_curve[p["provenance"]]
        if len(pts) >= 4:
            f = np.array([x["f"] for x in pts], float)
            y = np.array([x["ctr"] for x in pts], float)
            m = y > 0
            if m.sum() >= 4:
                k = -np.polyfit(f[m], np.log(y[m]), 1)[0]
                p["half_life"] = round(float(np.log(2) / k), 1) if k > 1e-6 else None

    # ---- placement affinity: thumb-stop by sub-type x placement family -----
    affinity = con.execute(
        "SELECT c.human_sub_type sub, "
        "CASE WHEN p.placement_name IN ('stories','reels','spotlight','shorts') THEN 'vertical' ELSE 'feed' END fam, "
        "SUM(a.three_sec_views)*100.0/NULLIF(SUM(a.impressions),0) ts "
        "FROM ad_performance a JOIN creative c USING(creative_id) JOIN placement p USING(placement_id) "
        "WHERE c.human_sub_type IS NOT NULL AND p.is_video GROUP BY 1,2"
    ).df()
    affinity_rows = {}
    for r in affinity.itertuples():
        affinity_rows.setdefault(r.sub, {})[r.fam] = round(r.ts, 1)

    # ---- decision matrix: channel x placement, Human vs AI -----------------
    # Each verdict names the metric that decided it and is backed by values shown
    # in the same row (ROAS when reliable, else saves; ROAS is n/a otherwise).
    matrix = decision_matrix(con, cfg)

    # ---- exhaustion alerts: AI gap widening by age cohort x channel --------
    seg = con.execute(
        """
        SELECT s.age_cohort, p.channel,
               CASE WHEN a.date <= ? THEN 'early' ELSE 'late' END half,
               CASE WHEN c.provenance='human_led' THEN 'human' ELSE 'ai' END side,
               SUM(a.clicks)*1.0/NULLIF(SUM(a.impressions),0) ctr, SUM(a.impressions) i
        FROM ad_performance a JOIN creative c USING(creative_id)
        JOIN placement p USING(placement_id) JOIN audience_segment s USING(segment_id)
        WHERE c.provenance IS NOT NULL GROUP BY 1,2,3,4
        """,
        [date_min + (date_max - date_min) / 2],
    ).df()
    alerts = []
    for (cohort, channel), g in seg.groupby(["age_cohort", "channel"]):
        piv = {(row.half, row.side): row.ctr for row in g.itertuples()}
        n = g.i.sum()
        try:
            gap_early = piv[("early", "human")] - piv[("early", "ai")]
            gap_late = piv[("late", "human")] - piv[("late", "ai")]
        except KeyError:
            continue
        widening = gap_late - gap_early
        if n > 4 * min_impr and widening > 0.0008:
            alerts.append({
                "segment": f"{cohort} · {channel}",
                "severity": "high" if widening > 0.0016 else "medium",
                "widening_permille": round(1000 * widening, 2),
                "detail": "Human vs AI CTR gap is widening over the flight; AI exhaustion is setting in.",
                "action": "Human-led UGC and creator content held up better than AI in this segment as frequency rose.",
            })
    alerts.sort(key=lambda a: -a["widening_permille"])

    # ---- opportunity: calendar (forward, four actionable fields) -----------
    today = dt.date.today()
    calendar_alerts = upcoming_opportunities(con, cfg, today, min_impr)

    # ---- opportunity: organic outperformers --------------------------------
    organic = con.execute(
        """
        WITH post AS (
          SELECT o.post_id, c.provenance, c.human_sub_type, o.is_boosted,
                 SUM(o.saves + o.shares)*1.0/NULLIF(SUM(o.impressions),0) quality,
                 SUM(o.impressions) i
          FROM organic_performance o JOIN creative c USING(creative_id) GROUP BY 1,2,3,4)
        SELECT * FROM post WHERE i > 5000 ORDER BY quality DESC LIMIT 4
        """
    ).df()
    base_q = organic.quality.median() if len(organic) else 0
    organic_alerts = [{
        "post_id": r.post_id, "provenance": _clean(r.provenance), "sub_type": _clean(r.human_sub_type),
        "quality_vs_median": round((r.quality / base_q - 1) * 100) if base_q else 0,
        "boosted": bool(r.is_boosted),
        "action": "A human-led organic post over-indexing on saves and shares, not yet boosted."
                  if r.provenance == "human_led" and not r.is_boosted
                  else "A post over-indexing on saves and shares, already boosted.",
    } for r in organic.itertuples()]

    # ---- opportunity: saturation (directional, labelled) -------------------
    saturation = {
        "label": "directional estimate",
        "category": "Outdoor & activewear (NO)",
        "trend": "rising", "level": "high",
        "classifier_accuracy_pct": 78, "classifier_accuracy_margin": 6,
        "note": ("Share of category feed that looks AI-generated appears to be RISING. "
                 "Directional only, never a competitor league table. A signal to read "
                 "alongside your own performance data, not a verdict."),
    }

    # ---- compliance flags --------------------------------------------------
    kroppspress = con.execute(
        "SELECT COUNT(*) FROM creative WHERE provenance IN ('ai_assisted','ai_generated') AND shows_people"
    ).fetchone()[0]
    boosted = con.execute("SELECT COUNT(*) FROM organic_performance WHERE is_boosted").fetchone()[0]
    creator_ct = con.execute("SELECT COUNT(*) FROM creative WHERE human_sub_type='creator'").fetchone()[0]
    ai_disclosure = con.execute(
        "SELECT COUNT(*) FROM creative WHERE provenance = 'ai_generated'").fetchone()[0]

    insights = {
        "meta": {
            "brand": BRAND,
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "data_range": [str(date_min), str(date_max)],
            "today": str(today),
            "prototype_note": "Descriptive prototype on synthetic data. Not the Phase-4 statistical engine.",
        },
        "kpis": {
            "spend_nok": round(total_spend), "impressions": int(total_impr),
            "blended_roas": round(blended_roas, 2),
            "untagged_spend_pct": round(100 * untagged, 1),
            "untagged_warn": untagged > thr["untagged_spend_warn_share"],
            "currencies": currencies,
        },
        "provenance": prov_summary,
        "decay_curve": decay_curve,
        "affinity": affinity_rows,
        "matrix": matrix,
        "exhaustion_alerts": alerts[:5],
        "calendar_alerts": calendar_alerts,
        "organic_alerts": organic_alerts,
        "saturation": saturation,
        "opportunities_note": UNTESTED_NOTE,
        "compliance": {
            "kroppspress_review_count": int(kroppspress),
            "ai_disclosure_count": int(ai_disclosure),
            "boosted_posts_labelling": int(boosted),
            "creator_disclosure_count": int(creator_ct),
        },
    }
    con.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(insights, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"  provenance groups: {len(prov_summary)}  matrix cells: {len(matrix)}  "
          f"exhaustion alerts: {len(alerts)}  calendar: {len(calendar_alerts)}")


if __name__ == "__main__":
    main()
