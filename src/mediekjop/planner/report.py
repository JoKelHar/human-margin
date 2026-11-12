# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Render a plan as a position, never a pick.

Two renderers over the same content: :func:`render_text` for the CLI and
:func:`to_dict` for the web demo and JSON. Both obey the product principle
(docs/principles.md): every line describes where a number sits and how sure it
is; none instructs. The :data:`PRESCRIPTIVE` tuple is the shared guard the tests
assert against, for the CLI and the web page alike.
"""

from __future__ import annotations

from .agency import AgencyCheck
from .engine import APPROACH_LABEL, PlanResult
from .formats import load_formats
from .snapshot import Snapshot, context_line

# Words that would turn a position into advice. The tests assert no rendered
# output contains any of these (case-insensitive).
PRESCRIPTIVE = (
    "you should", "we recommend", "recommended", "choose ", "best option",
    "best time", "opportunity", "avoid ", "shift ", "increase ", "cut ",
    "pick ", "go with", "the winner",
)

# The fixed time-rule line every rendered output carries: costs are money paid out
# only; the buyer's own time is never counted, which slightly flatters AI.
TIME_NOTE = (
    "Costs count money paid out only, not your own time sourcing, comparing or "
    "prompting. AI work usually carries more of that uncounted time, so this "
    "slightly flatters AI."
)


def format_keys() -> tuple[str, ...]:
    """The raw format keys (e.g. ``static_image``) that must NEVER appear in rendered
    copy - user-facing text uses the formats.yaml labels. Asserted by the copy guard."""
    return tuple(load_formats().keys())


def _nok(x: float) -> str:
    return f"{x:,.0f} NOK".replace(",", " ")


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt_label(key: str) -> str:
    f = load_formats().get(key)
    return f.label if f else key


def confidence_clause(r: PlanResult) -> str:
    markets = sorted({m for mu in r.metrics if mu.est for m in mu.est.markets if m != "assumption"})
    if not markets:
        where = "proxies and assumptions"
    elif len(markets) == 1:
        where = f"{markets[0]} proxies"
    else:
        where = ", ".join(markets[:-1]) + f" and {markets[-1]} proxies"
    return f"Confidence: {r.confidence} — the funnel rests on {where}."


def _reachable(r: PlanResult) -> bool:
    """Whether the budget can actually reach capacity. When it can't, the objective
    is the lowest cost per sale, not selling out (which the budget cannot do)."""
    scn = r.scenario
    if not (r.capacity_capped and scn.capacity):
        return True
    return r.reach_p50 >= scn.capacity * 0.995


def position_line(r: PlanResult) -> str:
    # Capacity-capped basis: "sell out" only when the budget can reach capacity;
    # otherwise "cost per sale" (the budget cannot sell out, so never say it can).
    if r.capacity_capped:
        basis = "cost to sell out" if _reachable(r) else "cost per sale"
    else:
        basis = "conversions per krone"

    # The level/lead is driven by the best cell; its format may differ from the priced
    # (headline) format the break-even runs on. When it does, say so, so the position
    # and the break-even never look like they disagree.
    best_fmt = max(r.cells, key=lambda c: c.conv_per_1000).fmt if r.cells else r.headline_format
    mismatch = best_fmt != r.headline_format
    at = f"At their best format ({_fmt_label(best_fmt)}), " if mismatch else "On these inputs, "
    tail = (f" Your priced format ({_fmt_label(r.headline_format)}) is a different case "
            f"— see the break-even below." if mismatch else "")

    if r.level and len(r.level_pair) >= 2:
        a, b = (APPROACH_LABEL.get(x, x) for x in r.level_pair[:2])
        return (f"{at}{a} and {b} are effectively level on {basis} "
                f"(within ~5%); no single approach leads.{tail}")
    if r.capacity_capped:
        verb = "costs the least to sell out" if _reachable(r) else "delivers the lowest cost per sale"
    else:
        verb = "delivers the most conversions per krone"
    span = "" if mismatch else " (p50 across the formats it can produce)"
    return (f"{at}{APPROACH_LABEL.get(r.leader, r.leader)} creative "
            f"{verb}{span}.{tail}")


_PLACE = {"above_both": "above both break-evens", "between": "between them", "below_both": "below both"}


def breakeven_cost_lines(r: PlanResult) -> list[str]:
    """The headline break-even expressed as a production cost: what human-led can
    cost and still match the best AI option, funnel-only and with the brand effect.
    The scenario's own human cost at the headline format is placed automatically; an
    optional override quote tests a second figure. Position only."""
    bc = r.breakeven_cost
    x, (lo, _, hi), w = bc.funnel[1], bc.funnel, bc.with_brand[1]
    brand_hi = bc.with_brand[2]
    # The single AI comparator, named, so the basis is explicit and nothing contradicts.
    vs = f"AI's strongest option here ({bc.ai_label})" if bc.ai_label else "AI's strongest option here"
    fully_clamped = brand_hi <= 0           # no production cost closes the gap, even with brand
    if hi <= 0:
        # Fully clamped: human-led never matches the comparator on the funnel, at any cost.
        base = f"Compared with {vs}, human-led does not match it at any production cost on these inputs"
        if fully_clamped:
            lines = [f"{base}, even with the longer-term brand effect.",
                     "No production cost closes the gap on these inputs, so any quote for this "
                     "format sits behind AI's strongest option on the short-term numbers."]
        else:
            lines = [f"{base} on the funnel alone; including the longer-term brand effect it "
                     f"matches at ~{_nok(w)} (low confidence)."]
    elif lo <= 0:
        # Lower bound clamps at 0: in some draws human-led can't match at any cost.
        lines = [f"Compared with {vs}, human-led matches at a production cost of ~{_nok(x)} "
                 f"(up to ~{_nok(hi)}; in some draws human-led doesn't match even at zero "
                 f"production cost). Including the longer-term brand effect: ~{_nok(w)} (low confidence)."]
    else:
        lines = [f"Compared with {vs}, human-led matches at a production cost of ~{_nok(x)} "
                 f"(likely {_nok(lo)}–{_nok(hi)}). Including the longer-term brand effect: "
                 f"~{_nok(w)} (low confidence)."]
    if not bc.feasible:
        lines.append("(The scenario's format is AI-only; shown for the nearest "
                     "human-capable format.)")
    # Placement only when a break-even exists to place against. When no production cost
    # closes the gap, the sentence above already says where any quote sits.
    if not fully_clamped:
        if bc.own_cost_nok and bc.own_placement:
            lines.append(f"Your cost of {_nok(bc.own_cost_nok)} sits {_PLACE[bc.own_placement]}.")
        if bc.quote_nok and bc.placement:
            lines.append(f"An alternative quote of {_nok(bc.quote_nok)} being tested sits "
                         f"{_PLACE[bc.placement]}.")
    return lines


def response_lift_lines(r: PlanResult) -> list[str]:
    """The same human-vs-AI trade-off expressed as a response gap (detail, under the
    headline production-cost break-even). Non-capacity only."""
    be = r.breakeven
    delta = be.prod_human - be.prod_ai
    if be.lift[1] <= 0:
        lines = [f"In {_fmt_label(be.fmt)}, human-led already matches or sits ahead of "
                 f"AI-generated on margin on these inputs (its production cost here is at or "
                 f"below AI-generated's), so no response lift is needed to justify it."]
    else:
        lines = [f"In {_fmt_label(be.fmt)}, human-led would need its response to beat "
                 f"AI-generated by about {_pct(be.lift[1])} "
                 f"(p10-p90 {_pct(be.lift[0])}-{_pct(be.lift[2])}) to match on margin, because "
                 f"it costs ~{_nok(max(delta, 0))} more to produce per reuse. Below that, "
                 f"AI-generated sits ahead on margin; above it, human-led does."]
    if not be.feasible:
        lines.append("(No single format is produced by both; shown for the nearest cells.)")
    return lines


def sanity_lines(r: PlanResult) -> list[str]:
    """Plain budget-vs-reality flags that lead the POSITION block (position wording,
    never advice): the budget cannot reach capacity; the cost per sale exceeds value."""
    scn = r.scenario
    lines: list[str] = []
    if r.capacity_capped and scn.capacity and r.reach_p50 < scn.capacity * 0.995:
        lines.append(f"On this budget: ~{r.reach_p50:.0f} of {scn.capacity} sales "
                     f"(the budget reaches well under capacity).")
    if r.over_value:
        present = {c.approach for c in r.cells}
        worth = "the ticket price" if scn.value_is_assumed_from_price else "the value per conversion"
        if set(r.over_value) >= present:
            lines.append(f"Cost per sale sits above {worth} for every approach on these inputs.")
        else:
            who = ", ".join(APPROACH_LABEL.get(a, a) for a in r.over_value)
            lines.append(f"Cost per sale sits above {worth} for {who} on these inputs.")
    return lines


# --- text (CLI) -------------------------------------------------------------

def render_text(r: PlanResult, agency: AgencyCheck | None = None,
                snapshot: Snapshot | None = None) -> str:
    scn = r.scenario
    out: list[str] = []
    out.append(f"=== {scn.name} ===")
    out.append(f"Industry: {scn.industry_label} ({scn.brand_positioning}) · price band "
               f"{scn.band.upper()} · budget {_nok(scn.budget_nok)}")
    out.append(f"Headline format: {_fmt_label(r.headline_format)}  "
               f"(every format was scored — see the matrix below)")
    if r.capacity_capped:
        obj = "lowest cost to sell out" if _reachable(r) else "lowest cost per sale"
        out.append(f"Capacity-capped at {scn.capacity}: the objective is {obj}.")

    out.append("\nPOSITION")
    for ln in sanity_lines(r):
        out.append(ln)
    out.append(position_line(r))
    out.append(confidence_clause(r))
    out.append(TIME_NOTE)

    out.append("\nBreak-even production cost (the headline)")
    for ln in breakeven_cost_lines(r):
        out.append(f"  {ln}")

    if r.capacity_capped:
        hcells = [c for c in r.cells if c.approach == "human_led"]
        acells = [c for c in r.cells if c.approach == "ai_generated"]
        header = "Cost to sell out" if _reachable(r) else "Cost per sale"
        out.append(f"\n{header} (the headline, capacity-capped)")
        if hcells and acells:
            ch = min(c.cost_per_conv for c in hcells)
            ca = min(c.cost_per_conv for c in acells)
            cap = r.scenario.capacity
            vol = min(r.reach_p50, cap)
            out.append(f"  Capacity is {cap}; on this budget the campaign reaches ~{r.reach_p50:.0f} "
                       f"sales. At the cheapest format for each: AI-generated ~{_nok(ca)}/sale, "
                       f"human-led ~{_nok(ch)}/sale — a gap of ~{_nok(abs(ch - ca) * vol)} over the "
                       f"~{vol:.0f} sales this budget reaches.")

    br = r.brand
    out.append("\nLonger-term brand effect (NOT in the numbers above)")
    if br.worth_to_close <= 1:
        out.append(f"  A human memory/brand edge is cited but kept out of the funnel. Here the "
                   f"funnel already favours human-led, so no brand premium is needed to close a "
                   f"gap; the modelled edge (~{_nok(br.brand_value)}) would sit on top. "
                   f"Tag: {br.mb_tag}.")
    else:
        vs = f" to {br.ai_label}" if br.ai_label else ""
        out.append(f"  A human memory/brand edge is cited but kept out of the funnel. On these "
                   f"inputs it would need to be worth about {_nok(br.worth_to_close)} over the "
                   f"campaign to close the funnel-margin gap{vs} (modelled brand value "
                   f"~{_nok(br.brand_value)}). Tag: {br.mb_tag}.")

    out.append("\nConversions per krone, by approach x format  (p50; wider ranges = less certain)")
    for c in sorted(r.cells, key=lambda c: -c.conv_per_1000):
        star = "" if c.prod_filled else "  [draft cost — pending promotion]"
        out.append(f"  {APPROACH_LABEL.get(c.approach, c.approach):20} {_fmt_label(c.fmt):28} "
                   f"{c.conv_per_1000:6.2f} conv/1000kr · cost/conv {c.cost_per_conv:,.0f} NOK"
                   .replace(",", " ") + star)

    if not r.capacity_capped:
        out.append("\nDetail — break-even as a response gap")
        for ln in response_lift_lines(r):
            out.append(f"  {ln}")

    out.append("\nWhat this hinges on")
    drivers = ", ".join(s.driver for s in r.sensitivity)
    out.append(f"  The answer moves most with: {drivers}. These are where your own data would "
               f"change the picture most.")

    rc = r.roas
    out.append("\nROAS cross-check")
    if r.capacity_capped:
        out.append("  Not meaningful when capacity-capped (value saturates at capacity); "
                   "the cost-to-sell-out figure above is the relevant one.")
    else:
        bench = f"~{rc.benchmark:.1f}" if rc.benchmark else "n/a"
        out.append(f"  Funnel-implied ROAS ~{rc.implied:.1f} (benchmark {bench}). {rc.note}")

    out.append("\nEvidence (how sure, per figure)")
    for mu in r.metrics:
        out.append(f"  {mu.name:26} {mu.tag}")

    if snapshot is not None:
        out.append("\nMarket context (public ad volume, no performance data)")
        out.append(f"  {context_line(snapshot)}")

    for n in r.notes:
        out.append(f"\nNote: {n}")

    if agency and agency.present:
        out.append("\n--- Agency quote check ---")
        out.append(f"Loaded cost ~{_nok(agency.loaded_total_nok)}/period "
                   f"(management + media% + amortised setup/creative).")
        for fl in agency.lines:
            tr = (f"typical {fl.typical[0]:g}-{fl.typical[2]:g}{fl.unit}"
                  if fl.typical else "no typical figure")
            out.append(f"  {fl.name}: {fl.your_value:g}{fl.unit} — {fl.position} ({tr}; {fl.tag}).")
            if fl.detail:
                out.append(f"      {fl.detail}")
        if agency.approach_note:
            out.append(f"  {agency.approach_note}")
        for n in agency.notes:
            out.append(f"  Note: {n}")

    return "\n".join(out)


# --- dict (web / JSON) ------------------------------------------------------

def to_dict(r: PlanResult, agency: AgencyCheck | None = None,
            snapshot: Snapshot | None = None) -> dict:
    scn = r.scenario
    d: dict = {
        "scenario": {
            "name": scn.name, "industry": scn.industry_label, "positioning": scn.brand_positioning,
            "band": scn.band, "budget_nok": round(scn.budget_nok),
            "capacity_capped": r.capacity_capped, "capacity": scn.capacity,
            "channel": scn.channel,
        },
        "headline_format": r.headline_format,
        "headline_format_label": _fmt_label(r.headline_format),
        "position": position_line(r),
        "sanity": sanity_lines(r),
        "time_note": TIME_NOTE,
        "level": r.level,
        "level_pair": r.level_pair,
        "channel": r.channel,
        "reach_p50": r.reach_p50,
        "over_value": r.over_value,
        "confidence": r.confidence,
        "confidence_clause": confidence_clause(r),
        "leader": r.leader,
        "breakeven": {
            "format": r.breakeven.fmt, "format_label": _fmt_label(r.breakeven.fmt),
            "lift_p10": r.breakeven.lift[0], "lift_p50": r.breakeven.lift[1],
            "lift_p90": r.breakeven.lift[2], "prod_human": r.breakeven.prod_human,
            "prod_ai": r.breakeven.prod_ai, "feasible": r.breakeven.feasible,
        },
        "breakeven_cost": {
            "format": r.breakeven_cost.fmt, "format_label": _fmt_label(r.breakeven_cost.fmt),
            "funnel_p10": r.breakeven_cost.funnel[0], "funnel_p50": r.breakeven_cost.funnel[1],
            "funnel_p90": r.breakeven_cost.funnel[2],
            "brand_p10": r.breakeven_cost.with_brand[0], "brand_p50": r.breakeven_cost.with_brand[1],
            "brand_p90": r.breakeven_cost.with_brand[2],
            "feasible": r.breakeven_cost.feasible,
            "ai_label": r.breakeven_cost.ai_label,
            "own_cost_nok": r.breakeven_cost.own_cost_nok,
            "own_placement": r.breakeven_cost.own_placement,
            "quote_nok": r.breakeven_cost.quote_nok, "placement": r.breakeven_cost.placement,
            "lines": breakeven_cost_lines(r),
        },
        "brand": {
            "worth_to_close": r.brand.worth_to_close, "brand_value": r.brand.brand_value,
            "funnel_gap": r.brand.funnel_gap, "tag": r.brand.mb_tag, "tier": r.brand.mb_tier,
            "ai_label": r.brand.ai_label,
        },
        "cells": [
            {
                "approach": c.approach, "approach_label": APPROACH_LABEL.get(c.approach, c.approach),
                "format": c.fmt, "format_label": _fmt_label(c.fmt),
                "conv_p10": c.conv[0], "conv_p50": c.conv[1], "conv_p90": c.conv[2],
                "margin_p50": c.margin[1], "conv_per_1000": c.conv_per_1000,
                "cost_per_conv": c.cost_per_conv, "prod_tier": c.prod_tier,
                "prod_filled": c.prod_filled,
            }
            for c in sorted(r.cells, key=lambda c: -c.conv_per_1000)
        ],
        "sensitivity": [{"driver": s.driver, "swing": s.swing} for s in r.sensitivity],
        "roas": {"implied": r.roas.implied, "benchmark": r.roas.benchmark, "note": r.roas.note},
        "evidence": [{"name": mu.name, "tag": mu.tag} for mu in r.metrics],
        "notes": list(r.notes),
        "draws": r.draws, "seed": r.seed,
    }
    if agency and agency.present:
        d["agency"] = {
            "loaded_total_nok": agency.loaded_total_nok, "monthly_fee_nok": agency.monthly_fee_nok,
            "lines": [
                {"name": fl.name, "your_value": fl.your_value, "unit": fl.unit,
                 "typical": fl.typical, "position": fl.position, "tag": fl.tag, "detail": fl.detail}
                for fl in agency.lines
            ],
            "approach_note": agency.approach_note, "notes": agency.notes,
        }
    if snapshot is not None:
        d["market_context"] = {
            "line": context_line(snapshot), "populated": snapshot.populated,
            "n": snapshot.n, "as_of": snapshot.as_of.isoformat() if snapshot.as_of else None,
            "provenance": snapshot.provenance, "status": snapshot.status,
        }
    return d
