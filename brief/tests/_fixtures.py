# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Shared fixture loading for the brief tests (not a test module)."""

from __future__ import annotations

import json
from pathlib import Path

FIX = Path(__file__).resolve().parent / "fixtures"


def load_json(name: str) -> dict | list:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def inputs_models():
    from schema import Context, Goal, Position
    i = load_json("aurora_inputs.json")
    return (Context.model_validate(i["context"]), Goal.model_validate(i["goal"]),
            Position.model_validate(i["position"]))


def valid_brief_dict() -> dict:
    return load_json("aurora_brief.json")


def make_run(tmp_path, brief_dict: dict | None = None) -> Path:
    d = tmp_path / "run"
    d.mkdir()
    (d / "inputs.json").write_text((FIX / "aurora_inputs.json").read_text(encoding="utf-8"),
                                   encoding="utf-8")
    bd = brief_dict if brief_dict is not None else valid_brief_dict()
    (d / "brief.json").write_text(json.dumps(bd, ensure_ascii=False), encoding="utf-8")
    return d
