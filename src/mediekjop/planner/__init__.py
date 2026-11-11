# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Creative Approach Planner.

Recommends whether a campaign should use an AI-led, hybrid or human-led creative
approach, backed by transparent economics, cited benchmarks and honest
uncertainty. Standalone and offline: a scenario in, a recommendation out.

Now in: the input schema and currency handling (schema, currency); the cited
benchmark library with market-similarity weighting (benchmarks); content formats
and the production-cost matrix (formats); the decision engine with Monte Carlo
uncertainty, break-even, a separate brand line and sensitivity (engine); the
agency-quote check (agency); the public ad-volume snapshot context layer
(snapshot); and the position-only renderers (report).
"""

from __future__ import annotations

from .agency import AgencyCheck, check_agency
from .benchmarks import (
    LEGEND,
    PROVENANCE_LABEL,
    BenchmarkError,
    Estimate,
    estimate,
    is_stale,
    load_benchmarks,
    load_weights,
    market_weight,
    provenance,
    stale_entries,
    tag,
)
from .currency import FxRates, Money, SUPPORTED, load_fx_rates
from .engine import PlanResult, plan
from .formats import (
    FormatError,
    drafted_cost_slots,
    load_costs,
    load_formats,
    unfilled_cost_slots,
)
from .report import PRESCRIPTIVE, render_text, to_dict
from .schema import (
    AgencyQuote,
    AiCosts,
    Costs,
    HumanCosts,
    Scenario,
    ScenarioError,
    load_industries,
    load_scenario,
    price_band,
    scenario_from_dict,
)
from .snapshot import (
    Snapshot,
    SnapshotError,
    context_line,
    load_manual_sample,
    load_snapshot,
    load_snapshots,
)

__all__ = [
    "Money", "FxRates", "load_fx_rates", "SUPPORTED",
    "Scenario", "ScenarioError", "Costs", "HumanCosts", "AiCosts", "AgencyQuote",
    "load_scenario", "scenario_from_dict", "load_industries", "price_band",
    "load_benchmarks", "load_weights", "estimate", "Estimate", "market_weight",
    "is_stale", "stale_entries", "BenchmarkError",
    "provenance", "tag", "LEGEND", "PROVENANCE_LABEL",
    "load_formats", "load_costs", "unfilled_cost_slots", "drafted_cost_slots", "FormatError",
    "plan", "PlanResult",
    "check_agency", "AgencyCheck",
    "Snapshot", "SnapshotError", "load_snapshot", "load_snapshots",
    "load_manual_sample", "context_line",
    "render_text", "to_dict", "PRESCRIPTIVE",
]
