# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Creative Approach Planner.

Recommends whether a campaign should use an AI-led, hybrid or human-led creative
approach, backed by transparent economics, cited benchmarks and honest
uncertainty. Standalone and offline: a scenario in, a recommendation out.

Phase 1 (here): the input schema, scenario YAML format and currency handling.
Later phases add the benchmark library, decision engine, modes, agency check,
outputs and interfaces.
"""

from __future__ import annotations

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

__all__ = [
    "Money", "FxRates", "load_fx_rates", "SUPPORTED",
    "Scenario", "ScenarioError", "Costs", "HumanCosts", "AiCosts", "AgencyQuote",
    "load_scenario", "scenario_from_dict", "load_industries", "price_band",
    "load_benchmarks", "load_weights", "estimate", "Estimate", "market_weight",
    "is_stale", "stale_entries", "BenchmarkError",
    "provenance", "tag", "LEGEND", "PROVENANCE_LABEL",
]
