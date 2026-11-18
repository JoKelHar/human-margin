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

import datetime as dt
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..config import repo_root
from .formats import load_costs

# Rough, non-Norwegian placeholders (flagged as assumptions in the register and on
# the page). Replace with sourced Norwegian figures when available.
TYP_LO = 3000          # "1 in 3 000" - optimistic end of a rough US-based range
TYP_HI = 10000         # "1 in 10 000" - pessimistic end
DEFAULT_CPM = 115      # kr per 1 000 views; rough US-based placeholder

# Industries only set the NOUN and the price-field wording; the bands depend on the
# FORMAT, not the trade. Every templated sentence stays verb-neutral - only the noun
# changes per industry (no "buy"/"sell"/"book"). `price_label` words the price field;
# `hint` is small muted help under it. "other" takes a free-text noun.
INDUSTRIES = [
    {"key": "nightlife", "label": "Nightlife", "one": "ticket", "many": "tickets",
     "price_label": "Price per ticket", "hint": "Entry price, or average spend per guest"},
    {"key": "events", "label": "Events and concerts", "one": "ticket", "many": "tickets",
     "price_label": "Price per ticket", "hint": "Average ticket price"},
    {"key": "culture", "label": "Culture (theatre, museums, festivals)", "one": "ticket",
     "many": "tickets", "price_label": "Price per ticket", "hint": "Average ticket price"},
    {"key": "restaurant", "label": "Restaurant and café", "one": "booking", "many": "bookings",
     "price_label": "Value per booking", "hint": "Covers × average spend"},
    {"key": "hotel", "label": "Hotel and travel", "one": "booking", "many": "bookings",
     "price_label": "Value per booking", "hint": "Nights × average room rate"},
    {"key": "fitness", "label": "Fitness and wellness", "one": "membership", "many": "memberships",
     "price_label": "Value per membership", "hint": "Monthly fee × months a member typically stays"},
    {"key": "beauty", "label": "Beauty and skincare", "one": "order", "many": "orders",
     "price_label": "Average order value", "hint": ""},
    {"key": "fashion", "label": "Fashion and retail", "one": "order", "many": "orders",
     "price_label": "Average order value", "hint": ""},
    {"key": "services", "label": "Services (salon, clinic, trades)", "one": "booking",
     "many": "bookings", "price_label": "Value per booking", "hint": "Average job or appointment value"},
    {"key": "courses", "label": "Courses and education", "one": "sign-up", "many": "sign-ups",
     "price_label": "Value per sign-up", "hint": "Course price"},
    {"key": "other", "label": "Other", "one": "sale", "many": "sales",
     "price_label": "Value per sale", "hint": "", "free_noun": True},
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


def _sig2(x: float) -> float:
    """Round to 2 significant figures - for ROUGH, CPM-derived estimates (views, "1 in
    N", likely ranges). Exact inputs and exact maths are never passed through this.
    Uses the integer digit count (not log10) so Python and JS agree bit-for-bit."""
    x = float(x)
    if x == 0:
        return 0.0
    neg = x < 0
    ax = abs(x)
    digits = len(str(int(ax))) if ax >= 1 else 1
    factor = 10 ** (digits - 2)
    val = _round(ax / factor) * factor
    return -val if neg else val


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
    industry: str = "nightlife"
    goal_mode: str = "target"          # "target" | "max"
    goal: float = 0.0
    price: float = 0.0
    budget: float = 0.0
    fmt: str = "ugc"
    human: float | None = None         # None/empty -> use the band point (typical)
    ai: float | None = None
    reuse: int = 1
    cpm: float = DEFAULT_CPM
    margin: float | None = None        # optional margin per sale; replaces price when set
    margin_unit: str = "kr"            # "kr" | "pct"
    other_noun: str | None = None      # free-text noun for the "other" industry


EXAMPLE = Inputs(industry="nightlife", goal_mode="target", goal=300, price=250, budget=5000,
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


def _nouns(inp: Inputs, ind: dict) -> tuple[str, str]:
    """Singular/plural noun for the industry; "other" takes a free-text noun."""
    if ind.get("free_noun"):
        base = (str(inp.other_noun).strip() if inp.other_noun else "") or ind["one"]
        return base, base + "s"
    return ind["one"], ind["many"]


def _value_per(price: float, inp: Inputs) -> tuple[float, bool]:
    """The per-sale value the human-margin maths divides by: the margin when the user
    gave one (kr, or % of price), else the full price. Returns (value, margin_used)."""
    m = _num(inp.margin)
    if inp.margin is not None and str(inp.margin).strip() != "" and m > 0:
        return (m if inp.margin_unit == "kr" else price * m / 100.0), True
    return price, False


def _who_typical(who: str) -> str:
    return "a typical " + (who[4:] if who.startswith("The ") else who.lower())


def compute(inp: Inputs) -> dict:
    """The three answers for one set of inputs, as plain data the page and CLI render."""
    ind = _industry(inp.industry)
    fmt = _format(inp.fmt)
    one, many = _nouns(inp, ind)
    price, goal, budget = _num(inp.price), _num(inp.goal), _num(inp.budget)
    reuse = max(1, _round(_num(inp.reuse)) or 1)
    cpm = _num(inp.cpm)
    is_target = inp.goal_mode == "target"
    value_per, margin_used = _value_per(price, inp)

    # Blank human/AI quotes fall back to the format's band point, read as "typical".
    human_blank = inp.human is None or str(inp.human).strip() == "" or _num(inp.human) <= 0
    ai_blank = inp.ai is None or str(inp.ai).strip() == "" or _num(inp.ai) <= 0
    human = fmt["human"]["point"] if human_blank else _num(inp.human)
    ai = fmt["ai"]["point"] if ai_blank else _num(inp.ai)

    # Feasibility: if the budget would need a better-than-usual conversion rate to hit the
    # target (1-in-N below the usual floor), the target is not reachable, so the human
    # margin never quotes a share of it.
    views = budget / cpm * 1000 if cpm > 0 else 0
    one_in = _round(views / goal) if (is_target and goal > 0 and views > 0) else None
    reachable = one_in is not None and one_in >= TYP_LO

    a2 = _answer_human_margin(human, ai, value_per, margin_used, reuse, goal, reachable,
                              one, many, fmt, human_blank, ai_blank)
    a1 = _answer_budget(budget, cpm, goal, is_target, views, one_in, one, many)
    a3 = _answer_quote(human_blank, human, fmt)

    return {
        "unit_one": one, "unit_many": many,
        "human_eff": human, "ai_eff": ai, "value_per": value_per, "margin_used": margin_used,
        "human_blank": human_blank, "ai_blank": ai_blank, "reachable": reachable,
        "a1": a1, "a2": a2, "a3": a3,
    }


def _blank_note(human_blank: bool, ai_blank: bool, fmt: dict) -> str:
    hb, ab = fmt["human"], fmt["ai"]
    if human_blank and ai_blank:
        return (f"Typical ranges — human {kr(hb['low'])}–{kr(hb['high'])} kr, "
                f"AI {kr(ab['low'])}–{kr(ab['high'])} kr. Put in your quotes for a sharper answer.")
    if human_blank:
        return (f"Typical range: {kr(hb['low'])}–{kr(hb['high'])} kr. "
                f"Put in your quote for a sharper answer.")
    if ai_blank:
        return (f"Typical AI cost: {kr(ab['low'])}–{kr(ab['high'])} kr. "
                f"Put in your figure for a sharper answer.")
    return ""


def _answer_human_margin(human, ai, value_per, margin_used, reuse, goal, reachable,
                         one, many, fmt, human_blank, ai_blank):
    diff = human - ai
    note = _blank_note(human_blank, ai_blank, fmt)
    subject = _who_typical(fmt["who"]) if human_blank else fmt["who"]
    subject = subject[0].upper() + subject[1:]
    ai_name = "a typical AI version" if ai_blank else "the AI version"
    about = "about " if (human_blank or ai_blank) else ""
    if value_per <= 0:
        return {"big": "—", "unit": "", "text": f"Add a value per {one} to see this.",
                "has_context": False, "context": "", "how": "", "note": note}
    if diff <= 0:
        return {
            "big": "0", "unit": f"extra {many}",
            "text": f"{subject} costs no more than {ai_name}, so it needs no extra {many} "
                    f"to pay for itself.",
            "has_context": False, "context": "",
            "how": f"{subject} {kr(human)} kr, {ai_name} {kr(ai)} kr: no cost gap to cover.\n"
                   f"Costs count money paid out, not your own time.",
            "note": note,
        }
    extra = math.ceil(diff / value_per)
    per = math.ceil(diff / (value_per * reuse))
    # Share uses the DISPLAYED per-campaign figure, so the two numbers in one sentence agree.
    share = _round(per / goal * 100) if reachable else None
    if reuse > 1:
        body = (f"Across {reuse} campaigns, the human version needs {kr(extra)} more {many} than "
                f"{ai_name} to pay for itself, about {per} per campaign.")
    else:
        body = (f"The human version needs {kr(extra)} more {one if extra == 1 else many} than "
                f"{ai_name} to pay for itself.")
    context = ""
    if share is not None:
        context = (f"That is {'under 1' if share < 1 else share}% of your {kr(goal)}-{one} "
                   f"target per campaign. Whether a human version earns that is your call.")
    basis = f"{kr(value_per)} kr margin per {one}" if margin_used else f"{kr(value_per)} kr per {one}"
    margin_line = ("Uses your margin per " + one + ".\n" if margin_used
                   else "Uses the full price. If you know your margin per " + one
                        + ", use that instead: the number goes up.\n")
    how = (f"{kr(diff)} kr extra ÷ {basis} = {kr(extra)} {many} (rounded up).\n"
           + (f"Spread over {reuse} campaigns: about {per} each.\n" if reuse > 1 else "")
           + margin_line
           + "A longer-term brand effect for human work is cited in research but kept out of "
             "this number (low confidence).")
    return {
        "big": kr(extra), "unit": f"more {one if extra == 1 else many}",
        "text": f"{subject} costs {about}{kr(diff)} kr more than {ai_name}. {body}",
        "has_context": share is not None, "context": context, "how": how, "note": note,
    }


def _answer_budget(budget, cpm, goal, is_target, views, one_in, one, many):
    if budget <= 0 or cpm <= 0:
        return {"big": "—", "text": "Add a media budget to see this.", "how": ""}
    # CPM-derived estimates are rounded to 2 significant figures (rough); the exact
    # inputs (budget, goal, CPM) and exact maths (max cost per sale) stay exact.
    vd = kr(_sig2(views))
    if is_target and goal > 0:
        max_cps = budget / goal
        if one_in < TYP_LO:
            pos = "well above what paid campaigns usually achieve"
        elif one_in <= TYP_HI:
            pos = "within what paid campaigns usually achieve"
        else:
            pos = "comfortably inside what paid campaigns usually achieve"
        oi = kr(_sig2(one_in))
        return {
            "big": f"{kr(max_cps)} kr per {one}",
            "text": f"To reach {kr(goal)} {many} on {kr(budget)} kr, each can cost at most "
                    f"{kr(max_cps)} kr. That means about 1 in {oi} ad views would need to "
                    f"become a {one}: {pos} (usually 1 in {kr(TYP_LO)}–{kr(TYP_HI)}).",
            "how": f"Max cost per {one}: {kr(budget)} kr ÷ {kr(goal)} = {kr(max_cps)} kr.\n"
                   f"Views: {kr(budget)} kr at a {kr(cpm)} kr CPM ≈ {vd} (one person may see "
                   f"the ad more than once).\n"
                   f"Needed: {kr(goal)} {many} from {vd} views ≈ 1 in {oi}.\n"
                   f"Usual range is a rough US-based estimate. Put in your own CPM under "
                   f"“I know my own numbers”.",
        }
    lo = math.floor(views / TYP_HI)
    hi = math.ceil(views / TYP_LO)
    cps_lo = budget / hi if hi > 0 else 0
    cps_hi = budget / lo if lo > 0 else 0
    lod, hid = kr(_sig2(lo)), kr(_sig2(hi))
    return {
        "big": f"Usually {lod}–{hid} {many}",
        "text": f"At a typical CPM, {kr(budget)} kr covers about {vd} views. Paid campaigns "
                f"usually turn 1 in {kr(TYP_LO)}–{kr(TYP_HI)} views into a {one}, so roughly "
                f"{lod}–{hid} {many}" + (f", at {kr(_sig2(cps_lo))}–{kr(_sig2(cps_hi))} kr each."
                                         if lo > 0 else "."),
        "how": f"Views: {kr(budget)} kr at a {kr(cpm)} kr CPM ≈ {vd}.\n"
               f"Usual conversion: 1 in {kr(TYP_LO)}–{kr(TYP_HI)} views (rough US-based estimate).\n"
               f"Put in your own CPM under “I know my own numbers”.",
    }


def _answer_quote(human_blank, human, fmt):
    low, high = fmt["human"]["low"], fmt["human"]["high"]
    scale_max = high * 1.3
    def pct(x):
        return max(0.0, min(100.0, x / scale_max * 100)) if scale_max > 0 else 0.0
    how = ("Usual range: owner-reviewed estimate for Oslo, November 2026. Money paid out, "
           "including usage rights for paid social.\nYour own quote always replaces the range "
           "in the other answers.")
    if human_blank:
        return {
            "big": "Typical range",
            "text": f"No quote entered — {fmt['noun']} in Oslo usually runs {kr(low)}–{kr(high)} kr. "
                    f"Put in your quote to place it.",
            "blank": True, "low": low, "high": high, "human": human,
            "scale_max": scale_max, "pct_low": pct(low), "pct_high": pct(high),
            "pct_human": pct(human), "how": how,
        }
    where = "below the usual range" if human < low else (
        "above the usual range" if human > high else "inside the usual range")
    big = "Below usual" if human < low else ("Above usual" if human > high else "Inside usual range")
    return {
        "big": big,
        "text": f"{kr(human)} kr for {fmt['noun']} sits {where} in Oslo ({kr(low)}–{kr(high)} kr).",
        "blank": False, "low": low, "high": high, "human": human,
        "scale_max": scale_max, "pct_low": pct(low), "pct_high": pct(high), "pct_human": pct(human),
        "how": how,
    }


# --- "If you go AI" tool options (data/ai_tools.yaml) ------------------------
# Positions only: tools are listed in price order, with no affiliate links and no
# paid placement. The YAML is the single source; the JS data is generated from it.

_RULE_LABEL = {"retouch_label": "retouch label", "misleading": "misleading marketing",
               "ai_act": "EU AI Act"}
# The voice-over row is shown only for video and UGC (brief), not for every format
# the YAML lists it under.
_VOICE_FORMATS = ("video", "ugc")
_BADGE = {"confirmed": "Norwegian: confirmed", "likely": "Norwegian: likely",
          "unverified": "Norwegian: not confirmed"}


@lru_cache(maxsize=2)
def load_ai_tools(path: str | None = None) -> dict:
    p = Path(path) if path else repo_root() / "data" / "ai_tools.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    # PyYAML parses bare YYYY-MM-DD as date objects; normalise to ISO strings so the
    # data is JSON-serialisable (for the JS) and comparisons are plain strings.
    for k in ("checked", "review_by"):
        if isinstance(data.get(k), (dt.date, dt.datetime)):
            data[k] = data[k].isoformat()[:10]
    return data


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _checked_display(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def _tool_view(t: dict, ai_cost: float) -> dict:
    return {
        "name": t["name"],
        "price_nok": t["price_nok"],
        "price_text": f"about {kr(t['price_nok'])} kr/month",
        "includes": t.get("includes", ""),
        "badge": _BADGE.get(t.get("norwegian")),         # None for n/a
        "jurisdiction": t.get("jurisdiction", ""),
        "billing_note": t.get("billing_note", ""),
        "pros": list(t.get("pros", [])),
        "cons": list(t.get("cons", [])),
        "rules": [{"id": r, "label": _RULE_LABEL.get(r, r)} for r in t.get("rules", [])],
        "fits": ai_cost > 0 and t["price_nok"] <= ai_cost,
        "source": t.get("source", ""),
    }


def ai_options(fmt: str, ai_cost: float = 0.0, today: dt.date | None = None,
               data: dict | None = None) -> dict:
    """The "AI options for <format>" card: the tools for one creative format in price
    order, the Norwegian voice-over options for video/UGC, the free baseline, the
    Norway rules those tools point to, and the prices-checked footer."""
    data = data or load_ai_tools()
    today = today or dt.date.today()
    ucs = {uc["key"]: uc for uc in data.get("use_cases", [])}
    fmt_label = next((f["label"] for f in formats() if f["key"] == fmt), fmt)

    main = next((uc for uc in data.get("use_cases", [])
                 if uc["key"] != "voice" and fmt in uc.get("format_keys", [])), None)
    tools = [_tool_view(t, ai_cost) for t in (main["tools"] if main else [])]

    voice = None
    if fmt in _VOICE_FORMATS and "voice" in ucs:
        voice = {"label": ucs["voice"]["label"],
                 "tools": [_tool_view(t, ai_cost) for t in ucs["voice"]["tools"]]}

    # The Norway rules any shown tool references, in first-seen order, for the block
    # the per-tool lines link up to.
    seen: list[str] = []
    for t in tools + (voice["tools"] if voice else []):
        for r in t["rules"]:
            if r["id"] not in seen:
                seen.append(r["id"])
    rules_by_id = {r["id"]: r for r in data.get("norway_rules", [])}
    rules = [{"id": rid, "label": _RULE_LABEL.get(rid, rid), **rules_by_id[rid]}
             for rid in seen if rid in rules_by_id]

    fb = data.get("free_baseline", {})
    review_by = data.get("review_by", "")
    return {
        "format": fmt, "format_label": fmt_label,
        "use_case_label": main["label"] if main else "",
        "card_note": (main or {}).get("card_note", ""),
        "free_baseline": {"name": fb.get("name", ""), "price": fb.get("price", ""),
                          "note": fb.get("note", ""), "source": fb.get("source", "")},
        "rules": rules,
        "tools": tools,
        "voice": voice,
        "alternatives": [{"name": a["name"], "price_text": f"about {kr(a['price_nok'])} kr/month",
                          "note": a.get("note", ""), "source": a.get("source", "")}
                         for a in (main.get("alternatives", []) if main else [])],
        "checked_display": _checked_display(data.get("checked", "")) if data.get("checked") else "",
        "review_by": review_by,
        "stale": bool(review_by) and today.isoformat() > review_by,
    }
