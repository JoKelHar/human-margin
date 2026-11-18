# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Budget check: three plain-language answers from an advertiser's own numbers.

This is the calculator behind the "Check your creative budget" page. It does NOT
predict outcomes; it does arithmetic on numbers the user supplies and says where
each one sits. Three answers, in the page's order:

  1. YOUR HUMAN MARGIN - how many extra sales the human option must earn to pay for
     its higher production cost: ``ceil((human - ai) / price)``.
  2. CAN THIS BUDGET DO IT? - the most each sale can cost, and the "1 in N people
     who see the ad" that implies at the given CPM, placed against a rough range.
  3. IS THIS QUOTE NORMAL? - where the human quote sits in the format's owned band.

Python is the source of truth: :func:`compute` here, the plain-JS ``budget-core.js``
on the page, and ``scripts/budget.py`` (the CLI) must all agree. Parity is pinned
by golden cases generated from this module (``scripts/build_budget_demo.py``) and
asserted against the JS in ``tests/test_budget_check_parity.py``.

Cost bands are the owner-reviewed ``config/planner/formats.yaml`` bands. The "usual
1 in 3 000-10 000" conversion range and the 115 kr CPM are ROUGH, non-Norwegian
placeholders (see the assumptions register); the page and the copy label them so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .formats import load_costs

# Rough, non-Norwegian placeholders (flagged as assumptions in the register and on
# the page). Replace with sourced Norwegian figures when available.
TYP_LO = 3000          # "1 in 3 000" - optimistic end of a rough US-based range
TYP_HI = 10000         # "1 in 10 000" - pessimistic end
DEFAULT_CPM = 115      # kr per 1 000 views; rough US-based placeholder

# Industries only set the unit word; the bands depend on the FORMAT, not the trade.
INDUSTRIES = [
    {"key": "uteliv", "label": "Nightlife", "one": "ticket", "many": "tickets"},
    {"key": "events", "label": "Events and concerts", "one": "ticket", "many": "tickets"},
    {"key": "restaurant", "label": "Restaurant", "one": "booking", "many": "bookings"},
    {"key": "fitness", "label": "Fitness", "one": "membership", "many": "memberships"},
    {"key": "beauty", "label": "Beauty and skincare", "one": "order", "many": "orders"},
    {"key": "other", "label": "Other", "one": "sale", "many": "sales"},
]

# Page format key -> (formats.yaml format key, human label bits). The AI "version"
# band is the format's ai_generated band; studio_shoot has no AI cell, so it borrows
# the generic AI-scene band (ai_mockup / ai_generated).
_FORMAT_SPEC = [
    ("static", "static_image", "The photographer", "a static image set", "static_image"),
    ("video", "short_video", "The video shoot", "a short video", "short_video"),
    ("ugc", "ugc_talking_head", "The creator", "a creator video", "ugc_talking_head"),
    ("studio", "studio_shoot", "The studio shoot", "a studio shoot", "ai_mockup"),
]


def _band(costs, fmt_key: str, approach: str) -> dict:
    cell = costs.get((fmt_key, approach))
    if cell is None:
        return {"low": 0, "point": 0, "high": 0}
    return {"low": int(cell.nok.low), "point": int(cell.nok.point), "high": int(cell.nok.high)}


def formats() -> list[dict]:
    """The four page formats with their owner-reviewed human band and AI-version band."""
    costs = load_costs()
    out = []
    for key, human_fmt, who, noun, ai_fmt in _FORMAT_SPEC:
        out.append({
            "key": key, "label": _LABEL[key], "who": who, "noun": noun,
            "human": _band(costs, human_fmt, "human_led"),
            "ai": _band(costs, ai_fmt, "ai_generated"),
        })
    return out


_LABEL = {"static": "Static image", "video": "Short video",
          "ugc": "Creator (UGC)", "studio": "Studio shoot"}


# --- helpers (mirror budget-core.js exactly, for JS/Python parity) -----------

def _round(x: float) -> int:
    """Round half up, toward +inf for .5 - matches JS Math.round (not banker's)."""
    return math.floor(x + 0.5)


def kr(n: float) -> str:
    """Norwegian number: thousands grouped with a space. 4200 -> '4 200'."""
    n = _round(n)
    return ("-" if n < 0 else "") + f"{abs(int(n)):,}".replace(",", " ")


def _num(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(str(v).replace(" ", "").strip() or 0)
    except ValueError:
        return 0.0


@dataclass
class Inputs:
    industry: str = "uteliv"
    goal_mode: str = "target"          # "target" | "max"
    goal: float = 0.0
    price: float = 0.0
    budget: float = 0.0
    fmt: str = "ugc"
    human: float | None = None         # None/empty -> use the band point
    ai: float | None = None
    reuse: int = 1
    cpm: float = DEFAULT_CPM


EXAMPLE = Inputs(industry="uteliv", goal_mode="target", goal=300, price=250, budget=5000,
                 fmt="ugc", human=4200, ai=300, reuse=2, cpm=115)

# The four demo scenarios (the planner examples, as budget-check inputs). Used by the
# CLI --all and the report; the human quote is the scenario's paid human production.
SCENARIOS = {
    "Oslo club night": EXAMPLE,
    "Local gym memberships": Inputs(industry="fitness", goal_mode="max", goal=0, price=1800,
                                    budget=15000, fmt="video", human=5000, ai=400, reuse=3, cpm=115),
    "Exclusive Oslo dinner": Inputs(industry="events", goal_mode="target", goal=40, price=1500,
                                    budget=8000, fmt="static", human=8000, ai=400, reuse=1, cpm=115),
    "Premium skincare brand": Inputs(industry="beauty", goal_mode="max", goal=0, price=900,
                                     budget=40000, fmt="studio", human=30000, ai=1200, reuse=4, cpm=115),
}


def _industry(key: str) -> dict:
    for i in INDUSTRIES:
        if i["key"] == key:
            return i
    return INDUSTRIES[0]


def _format(key: str) -> dict:
    fs = formats()
    for f in fs:
        if f["key"] == key:
            return f
    return fs[2]


def compute(inp: Inputs) -> dict:
    """The three answers for one set of inputs, as plain data the page and CLI render."""
    ind = _industry(inp.industry)
    fmt = _format(inp.fmt)
    one, many = ind["one"], ind["many"]
    price, goal, budget = _num(inp.price), _num(inp.goal), _num(inp.budget)
    reuse = max(1, _round(_num(inp.reuse)) or 1)
    cpm = _num(inp.cpm)
    is_target = inp.goal_mode == "target"

    # Blank human/AI quotes fall back to the format's band point (range shown, labelled).
    human_blank = inp.human is None or str(inp.human).strip() == "" or _num(inp.human) <= 0
    ai_blank = inp.ai is None or str(inp.ai).strip() == "" or _num(inp.ai) <= 0
    human = fmt["human"]["point"] if human_blank else _num(inp.human)
    ai = fmt["ai"]["point"] if ai_blank else _num(inp.ai)

    blank_note = _blank_note(human_blank, ai_blank, fmt)

    a2 = _answer_human_margin(human, ai, price, reuse, goal, is_target, one, many, fmt, blank_note)
    a1 = _answer_budget(budget, cpm, goal, is_target, one, many)
    a3 = _answer_quote(inp.human, human_blank, human, fmt, one)

    return {
        "unit_one": one, "unit_many": many,
        "human_eff": human, "ai_eff": ai,
        "human_blank": human_blank, "ai_blank": ai_blank,
        "a1": a1, "a2": a2, "a3": a3,
    }


def _blank_note(human_blank: bool, ai_blank: bool, fmt: dict) -> str:
    hb, ab = fmt["human"], fmt["ai"]
    if human_blank and ai_blank:
        return (f"Using the usual ranges — human {kr(hb['low'])}–{kr(hb['high'])} kr, "
                f"AI {kr(ab['low'])}–{kr(ab['high'])} kr. Put in your quotes for a sharper answer.")
    if human_blank:
        return (f"Using the usual range: {kr(hb['low'])}–{kr(hb['high'])} kr. "
                f"Put in your quote for a sharper answer.")
    if ai_blank:
        return (f"Using the usual AI cost: {kr(ab['low'])}–{kr(ab['high'])} kr. "
                f"Put in your figure for a sharper answer.")
    return ""


def _answer_human_margin(human, ai, price, reuse, goal, is_target, one, many, fmt, blank_note):
    diff = human - ai
    if price <= 0:
        return {"big": "—", "unit": "", "text": f"Add a price per {one} to see this.",
                "has_context": False, "context": "", "how": "", "note": blank_note}
    if diff <= 0:
        return {
            "big": "0", "unit": f"extra {many}",
            "text": f"The human option costs no more than the AI version, so it needs no "
                    f"extra {many} to pay for itself.",
            "has_context": False, "context": "",
            "how": f"Human quote {kr(human)} kr, AI version {kr(ai)} kr: no cost gap to cover.\n"
                   f"Costs count money paid out, not your own time.",
            "note": blank_note,
        }
    extra = math.ceil(diff / price)
    per = math.ceil(diff / (price * reuse))
    share = _round(extra / reuse / goal * 100) if (is_target and goal > 0) else None
    if reuse > 1:
        body = (f"Across {reuse} campaigns, it needs to sell {kr(extra)} more {many} than the "
                f"AI version to pay for itself, about {per} per campaign.")
    else:
        body = (f"It needs to sell {kr(extra)} more {one if extra == 1 else many} than the AI "
                f"version to pay for itself.")
    context = ""
    if share is not None:
        context = (f"That is {'under 1' if share < 1 else share}% of your {kr(goal)}-{one} "
                   f"target per campaign. Whether a human version earns that is your call.")
    how = (f"{kr(diff)} kr extra ÷ {kr(price)} kr per {one} = {kr(extra)} {many} (rounded up).\n"
           + (f"Spread over {reuse} campaigns: about {per} each.\n" if reuse > 1 else "")
           + f"Uses the full price. If you know your margin per {one}, use that instead: "
             f"the number goes up.\n"
           + "A longer-term brand effect for human work is cited in research but kept out of "
             "this number (low confidence).")
    return {
        "big": kr(extra), "unit": f"more {one if extra == 1 else many}", "text": f"{fmt['who']} "
        f"costs {kr(diff)} kr more than the AI version. {body}",
        "has_context": share is not None, "context": context, "how": how, "note": blank_note,
    }


def _answer_budget(budget, cpm, goal, is_target, one, many):
    views = budget / cpm * 1000 if cpm > 0 else 0
    if budget <= 0 or cpm <= 0:
        return {"big": "—", "text": "Add a media budget to see this.", "how": ""}
    if is_target and goal > 0:
        max_cps = budget / goal
        one_in = _round(views / goal)
        if one_in < TYP_LO:
            pos = "well above what paid campaigns usually achieve"
        elif one_in <= TYP_HI:
            pos = "within what paid campaigns usually achieve"
        else:
            pos = "comfortably inside what paid campaigns usually achieve"
        return {
            "big": f"{kr(max_cps)} kr per {one}",
            "text": f"To sell {kr(goal)} {many} on {kr(budget)} kr, each can cost at most "
                    f"{kr(max_cps)} kr. That means about 1 in {kr(one_in)} people who see the ad "
                    f"buys: {pos} (usually 1 in {kr(TYP_LO)}–{kr(TYP_HI)}).",
            "how": f"Max cost per {one}: {kr(budget)} kr ÷ {kr(goal)} = {kr(max_cps)} kr.\n"
                   f"Views: {kr(budget)} kr at a {kr(cpm)} kr CPM ≈ {kr(views)}.\n"
                   f"Needed: {kr(goal)} {many} from {kr(views)} views ≈ 1 in {kr(one_in)}.\n"
                   f"Usual range is a rough US-based estimate. Put in your own CPM under "
                   f"“I know my own numbers”.",
        }
    lo = math.floor(views / TYP_HI)
    hi = math.ceil(views / TYP_LO)
    cps_lo = budget / hi if hi > 0 else 0
    cps_hi = budget / lo if lo > 0 else 0
    return {
        "big": f"Usually {kr(lo)}–{kr(hi)} {many}",
        "text": f"At a typical CPM, {kr(budget)} kr buys about {kr(views)} views. Paid campaigns "
                f"usually convert 1 in {kr(TYP_LO)}–{kr(TYP_HI)}, so roughly {kr(lo)}–{kr(hi)} "
                f"{many}" + (f", at {kr(cps_lo)}–{kr(cps_hi)} kr each." if lo > 0 else "."),
        "how": f"Views: {kr(budget)} kr at a {kr(cpm)} kr CPM ≈ {kr(views)}.\n"
               f"Usual conversion: 1 in {kr(TYP_LO)}–{kr(TYP_HI)} views (rough US-based estimate).\n"
               f"Put in your own CPM under “I know my own numbers”.",
    }


def _answer_quote(raw_human, human_blank, human, fmt, one):
    low, high = fmt["human"]["low"], fmt["human"]["high"]
    scale_max = high * 1.3
    def pct(x):
        return max(0.0, min(100.0, x / scale_max * 100)) if scale_max > 0 else 0.0
    if human_blank:
        return {
            "big": "Using the usual range",
            "text": f"No quote entered — for {fmt['noun']} in Oslo the usual range is "
                    f"{kr(low)}–{kr(high)} kr. Put in your quote to place it.",
            "blank": True, "low": low, "high": high, "human": human,
            "scale_max": scale_max, "pct_low": pct(low), "pct_high": pct(high),
            "pct_human": pct(human),
            "how": "Usual range: owner-reviewed estimate for Oslo, November 2026. Money paid out, "
                   "including usage rights for paid social.\nYour own quote always replaces the "
                   "range in the other answers.",
        }
    where = "below the usual range" if human < low else (
        "above the usual range" if human > high else "inside the usual range")
    big = "Below usual" if human < low else ("Above usual" if human > high else "Inside usual range")
    return {
        "big": big,
        "text": f"{kr(human)} kr for {fmt['noun']} sits {where} in Oslo ({kr(low)}–{kr(high)} kr).",
        "blank": False, "low": low, "high": high, "human": human,
        "scale_max": scale_max, "pct_low": pct(low), "pct_high": pct(high), "pct_human": pct(human),
        "how": "Usual range: owner-reviewed estimate for Oslo, November 2026. Money paid out, "
               "including usage rights for paid social.\nYour own quote always replaces the range "
               "in the other answers.",
    }
