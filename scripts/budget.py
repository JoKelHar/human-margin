# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Budget check CLI - the same three answers as the web page, from the command line.

    uv run python scripts/budget.py                     # the example (Oslo club night)
    uv run python scripts/budget.py --all               # the four demo scenarios
    uv run python scripts/budget.py --price 250 --budget 5000 --goal 300 \\
        --format ugc --human 4200 --ai 300 --reuse 2    # your own numbers

Human/AI left unset fall back to the formats.yaml band (point), with the range
shown. Same Python source of truth as the page (mediekjop.planner.budget_check).
"""

from __future__ import annotations

import argparse
from dataclasses import replace

from mediekjop.planner.budget_check import EXAMPLE, SCENARIOS, Inputs, compute


def _render(name: str, inp: Inputs) -> str:
    r = compute(inp)
    out: list[str] = [f"=== {name} ==="]
    out.append("\nYOUR HUMAN MARGIN")
    out.append(f"  {r['a2']['big']} {r['a2']['unit']}".rstrip())
    out.append(f"  {r['a2']['text']}")
    if r["a2"]["has_context"]:
        out.append(f"  {r['a2']['context']}")
    if r["a2"]["note"]:
        out.append(f"  {r['a2']['note']}")

    out.append("\nCAN THIS BUDGET DO IT?")
    out.append(f"  {r['a1']['big']}")
    out.append(f"  {r['a1']['text']}")

    out.append("\nIS THIS QUOTE NORMAL?")
    out.append(f"  {r['a3']['big']}")
    out.append(f"  {r['a3']['text']}")

    out.append("\n  (Costs count money paid out, not your own time. These are positions, not "
               "advice; the ranges are rough.)")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Budget check - three answers from your own numbers.")
    ap.add_argument("--all", action="store_true", help="run the four demo scenarios")
    ap.add_argument("--industry", default=None)
    ap.add_argument("--goal-mode", dest="goal_mode", choices=["target", "max"], default=None)
    ap.add_argument("--goal", type=float, default=None)
    ap.add_argument("--price", type=float, default=None)
    ap.add_argument("--budget", type=float, default=None)
    ap.add_argument("--format", dest="fmt", choices=["static", "video", "ugc", "studio"], default=None)
    ap.add_argument("--human", type=float, default=None, help="human quote (unset = usual band)")
    ap.add_argument("--ai", type=float, default=None, help="AI version cost (unset = usual band)")
    ap.add_argument("--reuse", type=int, default=None)
    ap.add_argument("--cpm", type=float, default=None)
    args = ap.parse_args()

    if args.all:
        for i, (name, inp) in enumerate(SCENARIOS.items()):
            if i:
                print("\n" + "=" * 70 + "\n")
            print(_render(name, inp))
        return

    over = {k: v for k, v in vars(args).items()
            if k not in ("all",) and v is not None}
    inp = replace(EXAMPLE, **over) if over else EXAMPLE
    name = "Your numbers" if over else "Oslo club night (example)"
    print(_render(name, inp))


if __name__ == "__main__":
    main()
