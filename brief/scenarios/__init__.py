# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Synthetic scenarios (fictional brands, Norwegian market).

Each ``brief/scenarios/<slug>/`` holds a hand-authored ``scenario.json`` (Context, Goal,
Decide inputs, changelog) and a generated ``position.json`` (Decide's Position, produced
by running decide/). :mod:`brief.scenarios.generate` writes the Positions; the committed
files must regenerate byte-for-byte (see brief/tests/test_scenarios.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from schema import Context, Goal, Position

SCENARIO_DIR = Path(__file__).resolve().parent


def slugs() -> list[str]:
    return sorted(p.parent.name for p in SCENARIO_DIR.glob("*/scenario.json"))


def load_scenario(slug: str) -> dict:
    return json.loads((SCENARIO_DIR / slug / "scenario.json").read_text(encoding="utf-8"))


def context_of(scenario: dict) -> Context:
    return Context.model_validate(scenario["context"])


def goal_of(scenario: dict) -> Goal:
    return Goal.model_validate(scenario["goal"])


def parent_ids_of(scenario: dict) -> list[str]:
    return [scenario["context"]["envelope"]["id"], scenario["goal"]["envelope"]["id"]]


def position_path(slug: str) -> Path:
    return SCENARIO_DIR / slug / "position.json"


def load_position(slug: str) -> Position:
    return Position.model_validate_json(position_path(slug).read_text(encoding="utf-8"))


def canonical_json(model) -> str:
    """Deterministic JSON for a model, so a regenerated artefact matches the committed file."""
    return json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True,
                      ensure_ascii=False) + "\n"


__all__ = [
    "SCENARIO_DIR", "slugs", "load_scenario", "context_of", "goal_of",
    "parent_ids_of", "position_path", "load_position", "canonical_json",
]
