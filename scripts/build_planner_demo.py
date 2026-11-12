# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Build the planner web demo data.

Writes two JSON files the demo page consumes:

  web/planner_examples.json  the four example scenarios' full output (to_dict),
                             pre-rendered server-side. Instant to show, works
                             with no JavaScript runtime, and the static fallback.
  web/planner_fs.json        a {path: content} map of the duckdb-free planner
                             package plus its config/data, so the page can mount
                             them into Pyodide's virtual filesystem and run the
                             REAL engine in-browser (numpy + pyyaml only).

Then copies web/planner.html to docs/planner.html for GitHub Pages.

    uv run python scripts/build_planner_demo.py
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from mediekjop.planner import load_fx_rates, load_scenario
from mediekjop.planner.agency import check_agency
from mediekjop.planner.engine import DEFAULT_DRAWS, DEFAULT_SEED, plan
from mediekjop.planner.report import to_dict
from mediekjop.planner.snapshot import load_snapshots

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "scenarios" / "examples").glob("*.yaml"))

# Files the planner needs at runtime, as repo-relative paths (so repo_root() -
# parents[2] of config.py - resolves correctly once mounted under one root).
FS_FILES = [
    "src/mediekjop/__init__.py",
    "src/mediekjop/config.py",
    "src/mediekjop/planner/__init__.py",
    "src/mediekjop/planner/currency.py",
    "src/mediekjop/planner/schema.py",
    "src/mediekjop/planner/benchmarks.py",
    "src/mediekjop/planner/formats.py",
    "src/mediekjop/planner/engine.py",
    "src/mediekjop/planner/agency.py",
    "src/mediekjop/planner/report.py",
    "src/mediekjop/planner/snapshot.py",
    "config/planner/industries.yaml",
    "config/planner/weights.yaml",
    "config/planner/formats.yaml",
    "data/benchmarks/benchmarks.yaml",
    "data/fx/rates.yaml",
    "data/snapshots/uteliv.yaml",
]


def build_examples() -> dict:
    fx = load_fx_rates()
    snaps = load_snapshots()
    out = []
    for p in EXAMPLES:
        scn = load_scenario(p, fx)
        r = plan(scn, fx=fx, draws=DEFAULT_DRAWS, seed=DEFAULT_SEED)
        ac = check_agency(scn, r.leader, level=r.level, level_pair=r.level_pair)
        out.append(to_dict(r, ac, snaps.get(scn.industry)))
    return {
        "generated": dt.date.today().isoformat(),
        "fx_note": fx.note(), "draws": DEFAULT_DRAWS, "seed": DEFAULT_SEED,
        "disclaimer": "Benchmarks are mostly US/global proxies and labelled assumptions; "
                      "confidence is shown per figure. Positions describe where a number sits, "
                      "never what to do.",
        "scenarios": out,
    }


def build_fs() -> dict:
    fs = {}
    for rel in FS_FILES:
        p = ROOT / rel
        fs[rel] = p.read_text(encoding="utf-8")
    return fs


def main() -> None:
    web = ROOT / "web"
    web.mkdir(exist_ok=True)
    (web / "planner_examples.json").write_text(
        json.dumps(build_examples(), ensure_ascii=False, indent=2), encoding="utf-8")
    (web / "planner_fs.json").write_text(
        json.dumps(build_fs(), ensure_ascii=False), encoding="utf-8")

    src = web / "planner.html"
    if src.exists():
        (ROOT / "docs" / "planner.html").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        for name in ("planner_examples.json", "planner_fs.json"):
            (ROOT / "docs" / name).write_text((web / name).read_text(encoding="utf-8"),
                                              encoding="utf-8")
    print("Wrote web/planner_examples.json, web/planner_fs.json"
          + (" and copied the page + data to docs/." if src.exists() else " (planner.html not built yet)."))


if __name__ == "__main__":
    main()
