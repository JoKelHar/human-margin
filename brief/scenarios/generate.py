# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Generate each scenario's Decide Position by running decide/.

    uv run python -m brief.scenarios.generate

Reads every brief/scenarios/<slug>/scenario.json, validates its Context and Goal, runs
Decide on its inputs, maps the output onto a Position with a deterministic envelope, and
writes brief/scenarios/<slug>/position.json. The output is deterministic, so the
committed files regenerate byte-for-byte (brief/tests/test_scenarios.py enforces it).
"""

from __future__ import annotations

from brief.decide_link import position_from
from brief.scenarios import (
    canonical_json,
    context_of,
    goal_of,
    load_scenario,
    parent_ids_of,
    position_path,
    slugs,
)


def build_position(slug: str):
    scenario = load_scenario(slug)
    context_of(scenario)   # validate the Context ...
    goal_of(scenario)      # ... and the Goal before generating.
    return position_from(slug, scenario["decide_inputs"], parent_ids_of(scenario))


def write_all() -> list[str]:
    written = []
    for slug in slugs():
        pos = build_position(slug)
        position_path(slug).write_text(canonical_json(pos), encoding="utf-8")
        written.append(slug)
    return written


def main() -> None:
    for slug in write_all():
        print(f"wrote brief/scenarios/{slug}/position.json")


if __name__ == "__main__":
    main()
