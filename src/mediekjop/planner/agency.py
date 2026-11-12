# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Agency quote check (Phase 5).

Takes an agency quote attached to a scenario and places it against typical
practice: the management fee as a percent of media spend, the creative
production fee as a percent of media, and the quote's stated creative approach
against the approach the engine finds leads on conversions per krone.

Position only. It says where a number sits ("above typical for this spend
level"), never what to do about it. Every figure carries its four-part shape:
your number, the typical range, where that range comes from, and how sure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import benchmarks as bm
from .engine import APPROACH_LABEL
from .schema import Scenario

# Agency `stated_approach` vocab -> the engine's approach keys (for the position
# note only; an agency's label is not a measured approach).
_STATED_TO_APPROACH = {
    "human_shoot": "human_led",
    "ugc": "human_led",
    "ai_generated": "ai_generated",
    "templated": "ai_assisted",
    "mixed": "ai_assisted",
    "unknown": None,
}


@dataclass
class FeeLine:
    name: str
    your_value: float            # the quote's figure (percent)
    unit: str
    typical: tuple[float, float, float] | None   # low/point/high, or None if no evidence
    position: str                # "within typical" | "above typical" | "below typical" | "not enough evidence"
    tag: str                     # provenance tag for the typical range
    detail: str = ""             # one line of context (where the range comes from)


@dataclass
class AgencyCheck:
    present: bool
    monthly_fee_nok: float       # management + media% of this budget (one period)
    loaded_total_nok: float      # + amortised setup + creative over reuse_campaigns
    lines: list[FeeLine]
    approach_note: str
    notes: list[str] = field(default_factory=list)


def _sub_range(rows: list[dict], sub: str):
    """The agency_fee benchmark for one sub-metric, as a range + provenance tag."""
    matches = [e for e in rows if e["metric"] == "agency_fee" and e.get("sub") == sub]
    if not matches:
        return None, "not enough evidence"
    e = matches[0]
    v = e["value"]
    est = bm.Estimate(
        metric=f"agency_fee/{sub}", low=float(v.get("low", v["point"])), point=float(v["point"]),
        high=float(v.get("high", v["point"])), unit=e["unit"], markets=[e["geography"]],
        source_quality=e["quality"], relevance="low",
        relevance_reasons=["geography: global, not Norway"], confidence="low",
        provenance=bm.provenance(e), primary_market=e["geography"],
        year=e["published"].year if hasattr(e["published"], "year") else None,
        n_sources=1, any_stale=bm.is_stale(e),
    )
    return est, bm.tag(est)


def _position(value: float, lo: float, hi: float) -> str:
    if value > hi:
        return "above typical"
    if value < lo:
        return "below typical"
    return "within typical"


def check_agency(scn: Scenario, leader: str | None = None, *,
                 level: bool = False, level_pair: list[str] | None = None,
                 benchmarks: list[dict] | None = None) -> AgencyCheck:
    rows = benchmarks if benchmarks is not None else bm.load_benchmarks()
    q = scn.agency
    if q is None:
        return AgencyCheck(present=False, monthly_fee_nok=0.0, loaded_total_nok=0.0,
                           lines=[], approach_note="")

    budget = scn.budget_nok
    # Fees expressed as a percent of media spend, so the comparison is spend-agnostic.
    mgmt_pct = q.media_management_pct
    creative_pct = (q.creative_production_fee / budget * 100.0) if budget else 0.0

    lines: list[FeeLine] = []
    mgmt_est, mgmt_tag = _sub_range(rows, "media_management_pct")
    if mgmt_est:
        pos = _position(mgmt_pct, mgmt_est.low, mgmt_est.high)
        lines.append(FeeLine(
            name="Management fee (% of media spend)", your_value=round(mgmt_pct, 1), unit="%",
            typical=(mgmt_est.low, mgmt_est.point, mgmt_est.high), position=pos, tag=mgmt_tag,
            detail="Agency fees slide down with budget (nearer the high end below ~$10k/mo, "
                   "the low end above ~$50k/mo).",
        ))
    creative_est, creative_tag = _sub_range(rows, "creative_production_pct")
    if creative_est:
        pos = _position(creative_pct, creative_est.low, creative_est.high)
        lines.append(FeeLine(
            name="Creative production (% of media spend)", your_value=round(creative_pct, 1),
            unit="%", typical=(creative_est.low, creative_est.point, creative_est.high),
            position=pos, tag=creative_tag,
            detail="Often quoted as a separate statement of work; the typical figure here is an "
                   "unverified assumption.",
        ))

    monthly = q.monthly_management_fee + budget * mgmt_pct / 100.0
    R = max(scn.reuse_campaigns, 1)
    loaded = monthly + q.setup_fee / R + q.creative_production_fee / R

    approach_note = ""
    mapped = _STATED_TO_APPROACH.get(q.stated_approach)
    if level and mapped:
        # Same logic as the headline: when the leaders are effectively level, name no
        # single leader — the quote's approach sits level with human-led on these inputs.
        approach_note = (f"The quote's stated approach ({q.stated_approach}, "
                         f"{APPROACH_LABEL.get(mapped, mapped)}) sits level with human-led on "
                         f"these inputs; no single approach leads.")
    elif leader and mapped:
        if mapped == leader:
            approach_note = (f"The quote's stated approach ({q.stated_approach}) matches the "
                             f"approach that leads on conversions per krone on these inputs "
                             f"({APPROACH_LABEL.get(leader, leader)}).")
        else:
            approach_note = (f"The quote's stated approach ({q.stated_approach}) differs from the "
                             f"approach that leads on conversions per krone on these inputs "
                             f"({APPROACH_LABEL.get(leader, leader)}); both carry low confidence.")
    elif q.stated_approach == "unknown":
        approach_note = "The quote does not state a creative approach."

    notes = ["Fee ranges are global proxies (no Norway-specific agency-fee source found); "
             "relevance to Norway is low."]
    return AgencyCheck(present=True, monthly_fee_nok=round(monthly), loaded_total_nok=round(loaded),
                       lines=lines, approach_note=approach_note, notes=notes)
