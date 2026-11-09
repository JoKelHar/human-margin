# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Render a weekly Markdown report from out/insights.json.

A lightweight preview of the Phase-9 report: the same evidence the dashboard
shows, as a plain-text brief a media buyer could paste into a weekly review.
Writes to stdout, or to --out.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSIGHTS = ROOT / "out" / "insights.json"

PROV = {"human_led": "Human-led", "ai_assisted": "AI-assisted", "ai_generated": "AI-generated"}


def render(d: dict) -> str:
    m, k = d["meta"], d["kpis"]
    L: list[str] = []
    L.append(f"# Weekly signal: {m['brand']}")
    L.append("")
    L.append(f"_Window {m['data_range'][0]} → {m['data_range'][1]} · generated {m['generated_at']}_")
    L.append("")
    L.append("> Recommend-only. Descriptive prototype on synthetic data, not the Phase-4 statistical engine.")
    L.append("")
    L.append("## Headline")
    L.append(f"- Spend (NOK-normalised): **{k['spend_nok']:,}** across {', '.join(k['currencies'])}")
    L.append(f"- Impressions: **{k['impressions']:,}** · Blended ROAS: **{k['blended_roas']}×**")
    warn = " ⚠️ above threshold — push to tag" if k["untagged_warn"] else " (within threshold)"
    L.append(f"- Untagged spend: **{k['untagged_spend_pct']}%**{warn}")
    L.append("")

    L.append("## Human vs AI, by provenance")
    L.append("")
    L.append("| Provenance | CTR ‰ | Saves ‰ | ROAS | Half-life (freq) |")
    L.append("|---|--:|--:|--:|--:|")
    for p in d["provenance"]:
        hl = f"{p['half_life']:.1f}" if p["half_life"] is not None else "—"
        L.append(f"| {PROV[p['provenance']]} | {p['ctr_permille']:.2f} | {p['save_permille']:.2f} "
                 f"| {p['roas']:.2f}× | {hl} |")
    L.append("")
    hl_h = next((p["half_life"] for p in d["provenance"] if p["provenance"] == "human_led"), None)
    hl_g = next((p["half_life"] for p in d["provenance"] if p["provenance"] == "ai_generated"), None)
    if hl_h and hl_g:
        L.append(f"AI-generated fatigues ≈**{hl_h / hl_g:.1f}×** faster than human-led "
                 "and trails on saves and ROAS, while winning raw clicks when fresh.")
        L.append("")

    L.append("## Decision matrix (channel × placement)")
    L.append("")
    L.append("| Channel | Placement | Verdict | Human ROAS | AI ROAS | Conf. |")
    L.append("|---|---|---|--:|--:|---|")
    for c in d["matrix"]:
        v = c["verdict"] + (f" · {c['sub_type'].replace('_', ' ')}" if c["sub_type"] else "")
        L.append(f"| {c['channel']} | {c['placement'].replace('_', ' ')} | {v} "
                 f"| {c['human_roas']:.2f}× | {c['ai_roas']:.2f}× | {c['confidence']} |")
    L.append("")

    if d["exhaustion_alerts"]:
        L.append("## AI exhaustion")
        for a in d["exhaustion_alerts"]:
            L.append(f"- **{a['segment']}** ({a['severity']}, gap +{a['widening_permille']}‰): "
                     f"{a['detail']} → _{a['action']}_")
        L.append("")

    L.append("## Opportunities")
    L.append("")
    L.append("Each names an advertiser category, a moment, a time window and a recommended approach.")
    L.append("")
    for c in d["calendar_alerts"][:4]:
        extra = f": {c['detail']}" if c.get("detail") else ""
        L.append(f"- **{c['category']} · {c['moment']}** ({c['window']}, {c['timing']}){extra} "
                 f"→ _{c['approach']}_")
    if d.get("opportunities_note"):
        L.append("")
        L.append(f"_{d['opportunities_note']}_")
    s = d["saturation"]
    L.append(f"- **Category saturation ({s['category']})**, _{s['label']}_: AI presence {s['trend']}, "
             f"level {s['level']}; classifier accuracy ≈{s['classifier_accuracy_pct']}% "
             f"±{s['classifier_accuracy_margin']}. Directional only, never a league table.")
    L.append("")

    comp = d["compliance"]
    L.append("## Compliance to review")
    L.append(f"- Kroppspress-merking: **{comp['kroppspress_review_count']}** AI creatives showing people")
    L.append(f"- Markedsføringsloven: **{comp['boosted_posts_labelling']}** boosted organic posts to label")
    L.append(f"- Influencer labelling: **{comp['creator_disclosure_count']}** creator-led creatives")
    L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="write Markdown here (default: stdout)")
    args = ap.parse_args()
    if not INSIGHTS.exists():
        raise SystemExit("Missing out/insights.json — run scripts/demo_insights.py first.")
    md = render(json.loads(INSIGHTS.read_text(encoding="utf-8")))
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
