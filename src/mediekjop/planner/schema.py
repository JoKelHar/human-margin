# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Planner input schema: scenario YAML -> validated dataclasses.

A scenario is the single input to the planner. One scenario names one campaign:
its industry, price, objective, budget, production costs and (optionally) an
agency quote. Every money amount is in the scenario's own ``currency``; the
planner converts to NOK for calculation and displays back in that currency.

This module only loads and validates inputs and derives the price band. The
decision engine (Phase 3) consumes a validated :class:`Scenario`; it does not
live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..config import repo_root
from .currency import SUPPORTED, FxRates, Money, load_fx_rates


class ScenarioError(ValueError):
    """Raised when a scenario file is missing fields or has invalid values."""


# --- industries / vocab config ----------------------------------------------

@lru_cache(maxsize=2)
def load_industries(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else repo_root() / "config" / "planner" / "industries.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _industry_map(cfg: dict) -> dict[str, dict]:
    return {row["key"]: row for row in cfg.get("industries", [])}


def price_band(price_nok: float, industry_row: dict) -> str:
    """low / mid / high from the industry's thresholds (NOK)."""
    if price_nok <= industry_row["low_max"]:
        return "low"
    if price_nok >= industry_row["high_min"]:
        return "high"
    return "mid"


# --- cost line items --------------------------------------------------------

@dataclass
class HumanCosts:
    photographer: float = 0.0
    videographer: float = 0.0
    ugc_creator: float = 0.0
    talent: float = 0.0
    designer: float = 0.0
    editing: float = 0.0
    location: float = 0.0
    usage_rights_months: int = 0   # short usage rights can limit later reuse

    def upfront(self) -> float:
        return (self.photographer + self.videographer + self.ugc_creator + self.talent
                + self.designer + self.editing + self.location)


@dataclass
class AiCosts:
    tool_subscriptions: float = 0.0
    hours: float = 0.0
    hourly_rate: float = 0.0
    agency_freelancer_fee: float = 0.0   # AI is not free; model the labour behind it

    def upfront(self) -> float:
        return self.tool_subscriptions + self.hours * self.hourly_rate + self.agency_freelancer_fee


@dataclass
class Costs:
    human: HumanCosts = field(default_factory=HumanCosts)
    ai: AiCosts = field(default_factory=AiCosts)


@dataclass
class AgencyQuote:
    setup_fee: float = 0.0
    monthly_management_fee: float = 0.0
    media_management_pct: float = 0.0      # % of media spend
    creative_production_fee: float = 0.0
    stated_approach: str = "unknown"       # see industries.yaml agency_approaches


# --- scenario ---------------------------------------------------------------

@dataclass
class Scenario:
    name: str
    industry: str
    objective: str
    brand_positioning: str
    currency: str
    price: float
    budget: float
    costs: Costs
    geography: str = ""
    audience_size: int | None = None
    lead_time_weeks: float = 0.0
    capacity: int | None = None
    margin: float | None = None               # gross margin fraction 0..1
    value_per_conversion: float | None = None  # overrides price/margin if given
    reuse_campaigns: int = 1                   # for production-cost amortisation
    existing_assets: list[str] = field(default_factory=list)
    agency: AgencyQuote | None = None

    # derived (filled by resolve); all *_nok are NOK
    price_nok: float = 0.0
    budget_nok: float = 0.0
    band: str = "mid"
    value_per_conversion_nok: float = 0.0
    value_is_assumed_from_price: bool = False
    industry_label: str = ""

    def is_capacity_capped(self) -> bool:
        return self.capacity is not None


def _money_nok(amount: float, currency: str, fx: FxRates) -> float:
    return fx.to_nok(Money(float(amount), currency))


def resolve(scn: Scenario, fx: FxRates, industries_cfg: dict | None = None) -> Scenario:
    """Validate vocab, convert money to NOK and derive the price band in place."""
    cfg = industries_cfg or load_industries()
    imap = _industry_map(cfg)

    if scn.currency not in SUPPORTED:
        raise ScenarioError(f"currency {scn.currency!r} not in {SUPPORTED}")
    if scn.industry not in imap:
        raise ScenarioError(f"unknown industry {scn.industry!r}; see config/planner/industries.yaml")
    if scn.objective not in cfg.get("objectives", []):
        raise ScenarioError(f"unknown objective {scn.objective!r}")
    if scn.brand_positioning not in cfg.get("brand_positioning", []):
        raise ScenarioError(f"unknown brand_positioning {scn.brand_positioning!r}")
    if scn.agency and scn.agency.stated_approach not in cfg.get("agency_approaches", []):
        raise ScenarioError(f"unknown agency stated_approach {scn.agency.stated_approach!r}")
    if scn.price < 0 or scn.budget < 0:
        raise ScenarioError("price and budget must be non-negative")
    if scn.margin is not None and not (0.0 <= scn.margin <= 1.0):
        raise ScenarioError("margin must be a fraction between 0 and 1")

    row = imap[scn.industry]
    scn.industry_label = row["label"]
    scn.price_nok = _money_nok(scn.price, scn.currency, fx)
    scn.budget_nok = _money_nok(scn.budget, scn.currency, fx)
    scn.band = price_band(scn.price_nok, row)

    # value per conversion: explicit override, else margin x price, else price as
    # revenue (flagged as an assumption).
    if scn.value_per_conversion is not None:
        scn.value_per_conversion_nok = _money_nok(scn.value_per_conversion, scn.currency, fx)
    elif scn.margin is not None:
        scn.value_per_conversion_nok = scn.price_nok * scn.margin
    else:
        scn.value_per_conversion_nok = scn.price_nok
        scn.value_is_assumed_from_price = True
    return scn


def _costs_from_dict(d: dict) -> Costs:
    human = HumanCosts(**(d.get("human_led") or d.get("human") or {}))
    ai = AiCosts(**(d.get("ai_driven") or d.get("ai") or {}))
    return Costs(human=human, ai=ai)


def scenario_from_dict(d: dict, fx: FxRates | None = None,
                       industries_cfg: dict | None = None) -> Scenario:
    fx = fx or load_fx_rates()
    required = ["name", "industry", "objective", "brand_positioning", "currency", "price", "budget"]
    missing = [k for k in required if k not in d]
    if missing:
        raise ScenarioError(f"scenario missing required field(s): {', '.join(missing)}")
    agency = AgencyQuote(**d["agency"]) if d.get("agency") else None
    scn = Scenario(
        name=d["name"], industry=d["industry"], objective=d["objective"],
        brand_positioning=d["brand_positioning"], currency=d["currency"],
        price=float(d["price"]), budget=float(d["budget"]),
        costs=_costs_from_dict(d.get("costs") or {}),
        geography=d.get("geography", ""), audience_size=d.get("audience_size"),
        lead_time_weeks=float(d.get("lead_time_weeks", 0.0)),
        capacity=d.get("capacity"),
        margin=d.get("margin"), value_per_conversion=d.get("value_per_conversion"),
        reuse_campaigns=int(d.get("reuse_campaigns", 1)),
        existing_assets=list(d.get("existing_assets") or []),
        agency=agency,
    )
    return resolve(scn, fx, industries_cfg)


def load_scenario(path: str | Path, fx: FxRates | None = None) -> Scenario:
    """Load and validate one scenario YAML file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return scenario_from_dict(data, fx)
