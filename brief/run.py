# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""A recorded run on disk: inputs.json (context, goal, position), brief.json, and the
checks.json / decision.json the checks and the gate write. Read by the gate and loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from schema import Brief, Context, Decision, Goal, Position

RUNS_DIR = Path(__file__).resolve().parent / "runs"


@dataclass
class Run:
    path: Path
    context: Context
    goal: Goal
    position: Position
    brief: Brief


def resolve(run_id: str | Path) -> Path:
    p = Path(run_id)
    return p if p.exists() else RUNS_DIR / str(run_id)


def load_run(run_id: str | Path) -> Run:
    path = resolve(run_id)
    inputs = json.loads((path / "inputs.json").read_text(encoding="utf-8"))
    brief = Brief.model_validate_json((path / "brief.json").read_text(encoding="utf-8"))
    return Run(
        path=path,
        context=Context.model_validate(inputs["context"]),
        goal=Goal.model_validate(inputs["goal"]),
        position=Position.model_validate(inputs["position"]),
        brief=brief,
    )


def load_decision(path: Path) -> Decision | None:
    f = path / "decision.json"
    if not f.exists():
        return None
    return Decision.model_validate_json(f.read_text(encoding="utf-8"))


def write_decision(path: Path, decision: Decision) -> None:
    (path / "decision.json").write_text(
        json.dumps(decision.model_dump(mode="json"), indent=2, sort_keys=True,
                   ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = ["RUNS_DIR", "Run", "resolve", "load_run", "load_decision", "write_decision"]
