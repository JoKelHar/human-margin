# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Creative Approach Planner CLI.

Loads a scenario YAML (or every example), runs the decision engine and prints a
*position* on the AI-vs-hybrid-vs-human trade-off: which approach delivers the
most conversions per krone on these inputs, the break-even response lift, a
separate brand line, what the answer hinges on, and the agency-quote check. It
never tells you what to do; it says where the numbers sit and how sure they are.

    uv run python scripts/plan.py scenarios/examples/skincare_brand.yaml
    uv run python scripts/plan.py --all
    uv run python scripts/plan.py scenarios/examples/club_night.yaml --format ugc_talking_head
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mediekjop.planner import load_fx_rates, load_scenario
from mediekjop.planner.agency import check_agency
from mediekjop.planner.currency import Money
from mediekjop.planner.engine import DEFAULT_DRAWS, DEFAULT_SEED, plan
from mediekjop.planner.report import render_text
from mediekjop.planner.snapshot import load_snapshots

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "scenarios" / "examples"


def main() -> None:
    ap = argparse.ArgumentParser(description="Creative Approach Planner (recommend-only).")
    ap.add_argument("scenario", nargs="?", help="path to a scenario YAML")
    ap.add_argument("--all", action="store_true", help="run every example scenario")
    ap.add_argument("--format", dest="content_format", default=None,
                    help="override the headline content format (a key from formats.yaml)")
    ap.add_argument("--quote", type=float, default=None,
                    help="a human-led production quote (scenario currency) to place "
                         "against the break-even cost")
    ap.add_argument("--draws", type=int, default=DEFAULT_DRAWS, help="Monte Carlo draws")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (fixed by default)")
    args = ap.parse_args()

    fx = load_fx_rates()
    print(f"FX basis: {fx.note()}  (NOK per unit: "
          + ", ".join(f"{c} {fx.nok_per_unit(c):g}" for c in ("EUR", "USD", "GBP")) + ")")
    print(f"Monte Carlo: {args.draws} draws, seed {args.seed} (fixed -> reproducible).\n")

    if args.all or not args.scenario:
        paths = sorted(EXAMPLES.glob("*.yaml"))
    else:
        paths = [Path(args.scenario)]

    snapshots = load_snapshots()
    for i, p in enumerate(paths):
        scn = load_scenario(p, fx)
        if args.content_format:
            scn.content_format = args.content_format
        if args.quote is not None:
            scn.human_quote = args.quote
            scn.human_quote_nok = fx.to_nok(Money(args.quote, scn.currency))
        r = plan(scn, fx=fx, draws=args.draws, seed=args.seed)
        ac = check_agency(scn, r.leader, level=r.level, level_pair=r.level_pair)
        if i:
            print("\n" + "=" * 78 + "\n")
        print(render_text(r, ac, snapshots.get(scn.industry)))


if __name__ == "__main__":
    main()
