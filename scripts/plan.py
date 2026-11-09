# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Creative Approach Planner CLI (Phase 1 preview).

Loads and validates a scenario YAML (or every example), and prints the parsed
inputs with the currency converted to NOK and back. The decision engine arrives
in Phase 3; for now this shows that the input schema, scenario format and
currency handling work end to end.

    uv run python scripts/plan.py scenarios/examples/oslo_dinner.yaml
    uv run python scripts/plan.py --all
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mediekjop.planner import Money, load_fx_rates, load_scenario

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "scenarios" / "examples"


def _fmt(amount_nok: float, scn, fx) -> str:
    """Show an NOK amount in the scenario's own currency, with NOK alongside."""
    if scn.currency == "NOK":
        return f"{amount_nok:,.0f} NOK"
    disp = fx.from_nok(amount_nok, scn.currency)
    return f"{disp.amount:,.0f} {scn.currency} ({amount_nok:,.0f} NOK)"


def show(scn, fx) -> None:
    print(f"\n=== {scn.name} ===")
    print(f"  Industry        {scn.industry_label} ({scn.industry})")
    print(f"  Objective       {scn.objective} · positioning {scn.brand_positioning}")
    print(f"  Price           {_fmt(scn.price_nok, scn, fx)}  ->  band: {scn.band.upper()}")
    vpc = _fmt(scn.value_per_conversion_nok, scn, fx)
    assumed = "  (assumed = price; no margin given)" if scn.value_is_assumed_from_price else ""
    print(f"  Value / conv.   {vpc}{assumed}")
    if scn.is_capacity_capped():
        print(f"  Capacity        {scn.capacity} (objective becomes: sell out at lowest cost)")
    print(f"  Media budget    {_fmt(scn.budget_nok, scn, fx)}")
    print(f"  Lead time       {scn.lead_time_weeks:g} weeks · audience ~{scn.audience_size:,}"
          if scn.audience_size else f"  Lead time       {scn.lead_time_weeks:g} weeks")
    print(f"  Reuse           {scn.reuse_campaigns} campaign(s) · assets: "
          f"{', '.join(scn.existing_assets) or 'none'}")

    h = scn.costs.human
    a = scn.costs.ai
    print(f"  Production      human-led {h.upfront():,.0f} {scn.currency} "
          f"(usage rights {h.usage_rights_months}m) · AI {a.upfront():,.0f} {scn.currency}")
    if scn.agency:
        ag = scn.agency
        print(f"  Agency          setup {ag.setup_fee:,.0f} · mgmt {ag.monthly_management_fee:,.0f}/mo "
              f"· media {ag.media_management_pct:g}% · creative {ag.creative_production_fee:,.0f} "
              f"· approach: {ag.stated_approach}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Creative Approach Planner (Phase 1 preview).")
    ap.add_argument("scenario", nargs="?", help="path to a scenario YAML")
    ap.add_argument("--all", action="store_true", help="run every example scenario")
    args = ap.parse_args()

    fx = load_fx_rates()
    print(f"FX basis: {fx.note()}  (NOK per unit: "
          + ", ".join(f"{c} {fx.nok_per_unit(c):g}" for c in ("EUR", "USD", "GBP")) + ")")
    print("Phase 1 preview: inputs validated and converted to NOK. The decision "
          "engine (recommendation) arrives in Phase 3.")

    if args.all or not args.scenario:
        paths = sorted(EXAMPLES.glob("*.yaml"))
    else:
        paths = [Path(args.scenario)]
    for p in paths:
        show(load_scenario(p, fx), fx)


if __name__ == "__main__":
    main()
