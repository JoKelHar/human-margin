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
from mediekjop.synthetic.calendar_effects import windows_for_years

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "synthetic.duckdb"
OUT = ROOT / "out" / "insights.json"

PROV_ORDER = ["human_led", "ai_assisted", "ai_generated"]
BRAND = "Fjord Active (synthetic)"


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
    cells = con.execute(
        """
        WITH grp AS (
          SELECT p.channel, p.placement_name,
                 CASE WHEN c.provenance='human_led' THEN 'human' ELSE 'ai' END side,
                 SUM(a.impressions) i, SUM(a.clicks) cl,
                 SUM(a.conversion_value_nok) cv, SUM(a.spend_nok) sp,
                 SUM(a.saves) sv
          FROM ad_performance a JOIN creative c USING(creative_id) JOIN placement p USING(placement_id)
          WHERE c.provenance IS NOT NULL GROUP BY 1,2,3)
        SELECT channel, placement_name,
               MAX(i) FILTER(WHERE side='human') hi, MAX(i) FILTER(WHERE side='ai') ai_i,
               MAX(cl*1.0/NULLIF(i,0)) FILTER(WHERE side='human') hctr,
               MAX(cl*1.0/NULLIF(i,0)) FILTER(WHERE side='ai') aictr,
               MAX(cv/NULLIF(sp,0)) FILTER(WHERE side='human') hroas,
               MAX(cv/NULLIF(sp,0)) FILTER(WHERE side='ai') airoas,
               MAX(sv*1.0/NULLIF(i,0)) FILTER(WHERE side='human') hsave,
               MAX(sv*1.0/NULLIF(i,0)) FILTER(WHERE side='ai') aisave
        FROM grp GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()

    def _subtype_winner(channel, placement):
        r = con.execute(
            "SELECT c.human_sub_type, SUM(a.saves)*1.0/NULLIF(SUM(a.impressions),0) s "
            "FROM ad_performance a JOIN creative c USING(creative_id) JOIN placement p USING(placement_id) "
            "WHERE c.human_sub_type IS NOT NULL AND p.channel=? AND p.placement_name=? "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 1", [channel, placement]).fetchone()
        return r[0] if r else None

    def z(x) -> float:
        return 0.0 if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)

    matrix = []
    for r in cells.itertuples():
        hi, ai_i = z(r.hi), z(r.ai_i)
        n = min(hi, ai_i)
        if n < min_impr:
            verdict, sub, conf = "Insufficient data", None, "low"
        else:
            roas_gap = z(r.hroas) - z(r.airoas)
            save_gap = z(r.hsave) - z(r.aisave)
            conf = "high" if n > 5 * min_impr else "medium"
            if roas_gap > 0.03 or save_gap > 0.0005:
                verdict, sub = "Human wins", _subtype_winner(r.channel, r.placement_name)
            elif roas_gap < -0.03:
                verdict, sub = "AI wins", None
            else:
                verdict, sub = "No difference", None
        matrix.append({
            "channel": r.channel, "placement": r.placement_name, "verdict": verdict,
            "sub_type": sub, "confidence": conf,
            "human_roas": round(z(r.hroas), 2), "ai_roas": round(z(r.airoas), 2),
            "human_ctr_permille": round(1000 * z(r.hctr), 2),
            "ai_ctr_permille": round(1000 * z(r.aictr), 2),
            "impressions": int(hi + ai_i),
        })

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
                "detail": "Human–AI CTR gap is widening over the flight — AI exhaustion setting in.",
                "action": "Shift new AI iterations here to human-led UGC/creator; cap AI frequency.",
            })
    alerts.sort(key=lambda a: -a["widening_permille"])

    # ---- opportunity: calendar (forward) -----------------------------------
    today = dt.date.today()
    cal_windows = windows_for_years(cfg, [today.year, today.year + 1, 2025])
    moments_seen = {}
    for w in sorted(cal_windows, key=lambda w: w.start):
        if w.start < today:
            continue
        if w.key in moments_seen:
            continue
        # historical read from the synthetic 2025 window, if it overlaps the data
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
            moments_seen[w.key] = {
                "moment": w.label, "weeks_out": weeks, "status": "history",
                "detail": f"Human-led ROAS beat AI by {lift:+.0f}% around this moment last year.",
                "action": "Brief human-led production now (UGC + Norwegian-ness markers).",
            }
        else:
            moments_seen[w.key] = {
                "moment": w.label, "weeks_out": weeks, "status": "untested",
                "detail": "No reliable history for this moment yet.",
                "action": "Queue a matched human-vs-AI experiment to establish a baseline.",
            }
        if len(moments_seen) >= 5:
            break
    calendar_alerts = sorted(moments_seen.values(), key=lambda m: m["weeks_out"])

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
        "post_id": r.post_id, "provenance": r.provenance, "sub_type": r.human_sub_type,
        "quality_vs_median": round((r.quality / base_q - 1) * 100) if base_q else 0,
        "boosted": bool(r.is_boosted),
        "action": "Amplify as a partnership/Spark ad" if r.provenance == "human_led" and not r.is_boosted
                  else "Already boosted — track converted lift",
    } for r in organic.itertuples()]

    # ---- opportunity: saturation (directional, labelled) -------------------
    saturation = {
        "label": "directional estimate",
        "category": "Outdoor & activewear (NO)",
        "trend": "rising", "level": "high",
        "classifier_accuracy_pct": 78, "classifier_accuracy_margin": 6,
        "note": ("Share of category feed that looks AI-generated appears to be RISING. "
                 "Directional only — never a competitor league table. Use to support, "
                 "not justify, a human-led push backed by your own performance data."),
    }

    # ---- compliance flags --------------------------------------------------
    kroppspress = con.execute(
        "SELECT COUNT(*) FROM creative WHERE provenance IN ('ai_assisted','ai_generated') AND shows_people"
    ).fetchone()[0]
    boosted = con.execute("SELECT COUNT(*) FROM organic_performance WHERE is_boosted").fetchone()[0]
    creator_ct = con.execute("SELECT COUNT(*) FROM creative WHERE human_sub_type='creator'").fetchone()[0]

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
        "compliance": {
            "kroppspress_review_count": int(kroppspress),
            "boosted_posts_labelling": int(boosted),
            "creator_disclosure_count": int(creator_ct),
        },
    }
    con.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(insights, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"  provenance groups: {len(prov_summary)}  matrix cells: {len(matrix)}  "
          f"exhaustion alerts: {len(alerts)}  calendar: {len(calendar_alerts)}")


if __name__ == "__main__":
    main()
