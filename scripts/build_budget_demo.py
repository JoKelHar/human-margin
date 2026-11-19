# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Build the budget-check page data and the JS/Python parity golden cases.

Writes, from config/planner/formats.yaml via the Python source of truth
(mediekjop.planner.budget_check):

  web/budget-data.js          the bands, industries and placeholder constants as
                              HM_DATA, so budget-core.js (browser + Node) and the
                              page never hand-copy the numbers.
  tests/golden/budget_check.json  input -> expected-output cases, generated from
                              Python; the JS is asserted against these in
                              tests/test_budget_check_parity.py.

Then copies the page and its scripts to docs/ for GitHub Pages.

    uv run python scripts/build_budget_demo.py
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from mediekjop.planner import budget_check as bc

ROOT = Path(__file__).resolve().parents[1]


def _data() -> dict:
    return {
        "industries": bc.INDUSTRIES,
        "formats": bc.formats(),
        "typ_lo": bc.TYP_LO,
        "typ_hi": bc.TYP_HI,
        "default_cpm": bc.DEFAULT_CPM,
    }


def _golden_inputs() -> list[dict]:
    """A matrix of JS-shaped inputs that exercises every branch and boundary."""
    cases: list[dict] = []
    ex = asdict(bc.EXAMPLE)
    base = {"industry": ex["industry"], "goalMode": ex["goal_mode"], "goal": ex["goal"],
            "price": ex["price"], "budget": ex["budget"], "fmt": ex["fmt"],
            "human": ex["human"], "ai": ex["ai"], "reuse": ex["reuse"], "cpm": ex["cpm"],
            "margin": None, "marginUnit": "kr", "otherNoun": None}
    cases.append(dict(base))                                             # the example (target unreachable)

    cases.append({**base, "human": None})                               # blank human quote (typical)
    cases.append({**base, "ai": None})                                  # blank AI cost (typical)
    cases.append({**base, "human": None, "ai": None})                   # both blank ("only my budget")
    cases.append({**base, "human": 300, "ai": 4200})                    # no-gap (human <= AI)
    cases.append({**base, "goalMode": "max"})                           # as-many-as-possible
    cases.append({**base, "goalMode": "max", "human": None, "ai": None})
    cases.append({**base, "price": 0})                                  # no price
    cases.append({**base, "budget": 0})                                 # no budget
    cases.append({**base, "cpm": 0})                                    # no CPM
    cases.append({**base, "reuse": 1})                                  # single campaign
    cases.append({**base, "reuse": 5})                                  # many campaigns
    cases.append({**base, "goal": 5, "budget": 60000, "reuse": 1})     # target reachable (share shown)
    cases.append({**base, "goal": 5, "budget": 60000, "human": 400, "reuse": 1})  # singular + share
    cases.append({**base, "margin": 100})                               # margin in kr
    cases.append({**base, "margin": 40, "marginUnit": "pct"})           # margin in %
    cases.append({**base, "industry": "other", "otherNoun": "signup"})  # free-text noun
    cases.append({**base, "industry": "other"})                         # free-text noun default

    for fmt in ("static", "video", "ugc", "studio"):
        f = next(x for x in bc.formats() if x["key"] == fmt)
        lo, hi = f["human"]["low"], f["human"]["high"]
        cases.append({**base, "fmt": fmt, "human": lo - 1})             # below band
        cases.append({**base, "fmt": fmt, "human": (lo + hi) // 2})     # inside band
        cases.append({**base, "fmt": fmt, "human": hi + 1, "ai": 500})  # above band
        cases.append({**base, "fmt": fmt, "human": None, "ai": None})   # band fallback per format

    for ind in bc.INDUSTRIES:                                           # every noun, target + max
        cases.append({**base, "industry": ind["key"]})
        cases.append({**base, "industry": ind["key"], "goalMode": "max"})
    return cases


def _to_inputs(d: dict) -> bc.Inputs:
    return bc.Inputs(industry=d["industry"], goal_mode=d["goalMode"], goal=d["goal"],
                     price=d["price"], budget=d["budget"], fmt=d["fmt"],
                     human=d["human"], ai=d["ai"], reuse=d["reuse"], cpm=d["cpm"],
                     margin=d.get("margin"), margin_unit=d.get("marginUnit", "kr"),
                     other_noun=d.get("otherNoun"))


def build_golden() -> list[dict]:
    return [{"input": d, "output": bc.compute(_to_inputs(d))} for d in _golden_inputs()]


def _creator_inputs() -> list[dict]:
    ex = asdict(bc.CREATOR_EXAMPLE)
    base = {"fmt": ex["fmt"], "price": ex["price"], "usageMonths": ex["usage_months"],
            "revisions": ex["revisions"], "rawFiles": ex["raw_files"],
            "exampleIndustry": ex["example_industry"], "examplePrice": None,
            "margin": None, "marginUnit": "kr"}
    cases = [dict(base)]
    cases.append({**base, "price": 0})                               # no price
    cases.append({**base, "price": 1000})                            # below band (ugc 2000)
    cases.append({**base, "price": 9000})                            # above band
    cases.append({**base, "price": 200})                             # no-gap (< typical AI 310)
    cases.append({**base, "rawFiles": True})                         # inclusions line
    cases.append({**base, "examplePrice": 500})                      # custom example price
    cases.append({**base, "margin": 40, "marginUnit": "pct"})        # margin option
    cases.append({**base, "margin": 120, "marginUnit": "kr"})
    for fmt in ("static", "video", "ugc", "studio"):
        cases.append({**base, "fmt": fmt, "price": 15000})
    for ind in bc.INDUSTRIES:
        cases.append({**base, "exampleIndustry": ind["key"]})
    return cases


def _to_creator(d: dict) -> bc.CreatorInputs:
    return bc.CreatorInputs(fmt=d["fmt"], price=d["price"], usage_months=d["usageMonths"],
                            revisions=d["revisions"], raw_files=d["rawFiles"],
                            example_industry=d["exampleIndustry"], example_price=d["examplePrice"],
                            margin=d.get("margin"), margin_unit=d.get("marginUnit", "kr"))


def build_creator_golden() -> list[dict]:
    return [{"input": d, "output": bc.creator_compute(_to_creator(d))} for d in _creator_inputs()]


def build_ai_golden() -> list[dict]:
    """AI-options card cases (format x AI cost x date) for JS/Python parity."""
    out = []
    for fmt in ("static", "video", "ugc", "studio"):
        for ai_cost in (0, 300, 2000):
            for today in ("2026-11-18", "2027-03-01"):   # fresh and stale
                out.append({
                    "input": {"fmt": fmt, "ai_cost": ai_cost, "today": today},
                    "output": bc.ai_options(fmt, ai_cost,
                                            today=__import__("datetime").date.fromisoformat(today)),
                })
    return out


def main() -> None:
    web = ROOT / "web"
    web.mkdir(exist_ok=True)
    data_js = ("// Generated by scripts/build_budget_demo.py from config/planner/formats.yaml.\n"
               "// Do not edit by hand; run the build script.\n"
               "var HM_DATA = " + json.dumps(_data(), ensure_ascii=False, indent=2) + ";\n"
               "if (typeof module !== 'undefined' && module.exports) { module.exports = HM_DATA; }\n"
               "if (typeof window !== 'undefined') { window.HM_DATA = HM_DATA; }\n")
    (web / "budget-data.js").write_text(data_js, encoding="utf-8")

    ai_js = ("// Generated by scripts/build_budget_demo.py from data/ai_tools.yaml.\n"
             "// Do not edit by hand; run the build script.\n"
             "var HM_AI = " + json.dumps(bc.load_ai_tools(), ensure_ascii=False, indent=2) + ";\n"
             "if (typeof module !== 'undefined' && module.exports) { module.exports = HM_AI; }\n"
             "if (typeof window !== 'undefined') { window.HM_AI = HM_AI; }\n")
    (web / "budget-ai-data.js").write_text(ai_js, encoding="utf-8")

    (ROOT / "tests" / "golden").mkdir(parents=True, exist_ok=True)
    (ROOT / "tests" / "golden" / "budget_check.json").write_text(
        json.dumps(build_golden(), ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "tests" / "golden" / "ai_options.json").write_text(
        json.dumps(build_ai_golden(), ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "tests" / "golden" / "creator.json").write_text(
        json.dumps(build_creator_golden(), ensure_ascii=False, indent=2), encoding="utf-8")
    golden = build_golden()

    # Copy the page + scripts to docs/ for GitHub Pages. The budget check is the home
    # page: it is served both as budget.html and as index.html (the landing).
    docs = ROOT / "docs"
    for name in ("budget.html", "budget-core.js", "budget-data.js", "budget-ai-data.js"):
        src = web / name
        if src.exists():
            (docs / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    page = web / "budget.html"
    if page.exists():
        (docs / "index.html").write_text(page.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Wrote web/budget-data.js, tests/golden/budget_check.json ({len(golden)} cases)"
          + (" and copied page + scripts to docs/." if (web / "budget.html").exists()
             else " (budget.html not built yet)."))


if __name__ == "__main__":
    main()
