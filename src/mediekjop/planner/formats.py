# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Content formats, per-format response priors and the production-cost matrix.

A content *format* (static image, short video, UGC talking-head, studio shoot,
AI mock-up) is a dimension alongside the creative *approach* (human_led /
ai_assisted / ai_generated). Format moves both response (CTR/CVR, as multipliers
vs a static baseline) and production cost (upfront NOK per creative set, per
format x approach). Both are tiered for provenance and carried as triangular
``{low, point, high}`` ranges so the engine can sample them.

This module only loads and validates ``config/planner/formats.yaml`` and exposes
small typed accessors. The economics live in :mod:`mediekjop.planner.engine`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..config import repo_root

APPROACHES = ("human_led", "ai_assisted", "ai_generated")
TIERS = ("public_benchmark", "expert_estimate", "assumption")


class FormatError(ValueError):
    """Raised when formats.yaml is missing fields or has invalid values."""


@dataclass(frozen=True)
class Tri:
    """A triangular range: low <= point <= high (used for Monte Carlo draws)."""
    low: float
    point: float
    high: float

    def __post_init__(self) -> None:
        if not (self.low <= self.point <= self.high):
            raise FormatError(f"range not ordered low<=point<=high: {self}")


@dataclass(frozen=True)
class CostCell:
    """Production cost for one (format, approach) cell."""
    fmt: str
    approach: str
    nok: Tri
    tier: str
    filled: bool            # expert_estimate slots are provisional until filled
    source: str
    note: str


@dataclass(frozen=True)
class Format:
    key: str
    label: str
    approaches: tuple[str, ...]
    ctr_mult: Tri
    cvr_mult: Tri
    priors_tier: str
    priors_source: str
    priors_note: str


def _tri(d: dict, where: str) -> Tri:
    if not isinstance(d, dict) or "point" not in d:
        raise FormatError(f"{where}: expected a {{low, point, high}} range, got {d!r}")
    pt = float(d["point"])
    return Tri(float(d.get("low", pt)), pt, float(d.get("high", pt)))


def _formats_path() -> Path:
    return repo_root() / "config" / "planner" / "formats.yaml"


@lru_cache(maxsize=2)
def _load_raw(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else _formats_path()
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def load_formats(path: str | None = None) -> dict[str, Format]:
    """Load and validate the format list (keyed by format key, in file order)."""
    cfg = _load_raw(path)
    out: dict[str, Format] = {}
    for i, f in enumerate(cfg.get("formats") or []):
        for k in ("key", "label", "approaches", "ctr_mult", "cvr_mult"):
            if k not in f:
                raise FormatError(f"format {i} missing field {k!r}")
        apps = tuple(f["approaches"])
        bad = [a for a in apps if a not in APPROACHES]
        if bad:
            raise FormatError(f"format {f['key']}: unknown approach(es) {bad}")
        tier = f.get("priors_tier", "assumption")
        if tier not in TIERS:
            raise FormatError(f"format {f['key']}: bad priors_tier {tier!r}")
        out[f["key"]] = Format(
            key=f["key"], label=f["label"], approaches=apps,
            ctr_mult=_tri(f["ctr_mult"], f"{f['key']}.ctr_mult"),
            cvr_mult=_tri(f["cvr_mult"], f"{f['key']}.cvr_mult"),
            priors_tier=tier, priors_source=f.get("priors_source", ""),
            priors_note=f.get("priors_note", ""),
        )
    if not out:
        raise FormatError("formats.yaml defines no formats")
    base = cfg.get("baseline_format")
    if base and base not in out:
        raise FormatError(f"baseline_format {base!r} is not a defined format")
    return out


def baseline_format(path: str | None = None) -> str:
    cfg = _load_raw(path)
    return cfg.get("baseline_format") or next(iter(load_formats(path)))


def load_costs(path: str | None = None) -> dict[tuple[str, str], CostCell]:
    """Load the production-cost matrix, keyed by (format_key, approach)."""
    cfg = _load_raw(path)
    costs = cfg.get("costs") or {}
    out: dict[tuple[str, str], CostCell] = {}
    for fmt, by_approach in costs.items():
        for approach, cell in (by_approach or {}).items():
            if approach not in APPROACHES:
                raise FormatError(f"costs.{fmt}: unknown approach {approach!r}")
            tier = cell.get("tier", "assumption")
            if tier not in TIERS:
                raise FormatError(f"costs.{fmt}.{approach}: bad tier {tier!r}")
            out[(fmt, approach)] = CostCell(
                fmt=fmt, approach=approach, nok=_tri(cell["nok"], f"costs.{fmt}.{approach}.nok"),
                tier=tier, filled=bool(cell.get("filled", tier != "expert_estimate")),
                source=cell.get("source", ""), note=cell.get("note", ""),
            )
    return out


def unfilled_cost_slots(path: str | None = None) -> list[CostCell]:
    """Expert-estimate cost cells that are still empty (no drafted value)."""
    return [c for c in load_costs(path).values()
            if c.tier == "expert_estimate" and not c.filled]


def drafted_cost_slots(path: str | None = None) -> list[CostCell]:
    """Cost cells carrying a *drafted* placeholder value awaiting owner review.

    Distinct from :func:`unfilled_cost_slots`: these have a concrete starting band
    and a ``source`` marked "pending owner review", to be confirmed and promoted
    to ``expert_estimate`` by the owner. Surfaced separately by the assumptions
    register so a drafted figure is never mistaken for an empty slot or for
    sourced data.
    """
    return [c for c in load_costs(path).values()
            if not c.filled and "pending owner review" in c.source.lower()]
