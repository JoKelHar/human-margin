# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""What the gate shows a reviewer, and the hash that proves it.

``shown_payload`` is the canonical record of everything put in front of the reviewer --
the brief, every Figure with its provenance, the assumptions, the open questions and the
stance thresholds. ``shown_hash`` is its SHA-256. The gate stores the hash on the
Decision; the loader recomputes it from the current brief and refuses the brief if it no
longer matches, so an approval can never be detached from the exact content approved.
"""

from __future__ import annotations

import hashlib
import json

from brief.checks import figure_pool, stance_of
from brief.config import THRESHOLDS
from schema import Brief, Context, Goal, Position


def item_ref(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def shown_payload(brief: Brief, context: Context, goal: Goal, position: Position) -> dict:
    """Everything the reviewer is shown, in a canonical, hashable form."""
    st = stance_of(position)
    return {
        "brief": brief.model_dump(mode="json"),
        "context": context.model_dump(mode="json"),
        "goal": goal.model_dump(mode="json"),
        "position_id": position.envelope.id,
        "decide_stance": {"maker": st.maker.value, "ratio": round(st.ratio, 1),
                          "near_boundary": st.near_boundary},
        "figures": [{"value": v, "unit": u} for v, u in figure_pool(brief, goal, position)],
        "assumptions": [{"ref": item_ref(f.ref or str(f.value)),
                         "value": f.value, "unit": f.unit, "source": f.source.value,
                         "confidence": f.confidence.value} for f in brief.assumptions],
        "open_questions": [{"ref": item_ref(q), "text": q} for q in brief.open_questions],
        "thresholds": [{"name": n, "value": f.value, "unit": f.unit,
                        "source": f.source.value, "confidence": f.confidence.value}
                       for n, f in THRESHOLDS],
    }


def shown_hash(brief: Brief, context: Context, goal: Goal, position: Position) -> str:
    payload = shown_payload(brief, context, goal, position)
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def render_summary(brief: Brief, context: Context, goal: Goal, position: Position) -> str:
    """A plain-text summary for the reviewer (and the head of brief.md)."""
    st = stance_of(position)
    lines = [
        f"Brief for {context.brand} ({context.category}, {context.market})",
        f"  objective:   {brief.objective}",
        f"  proposition: {brief.proposition}",
        f"  maker:       {brief.maker_recommendation.maker.value}  "
        f"(Decide stance: {st.maker.value}, ratio {st.ratio:.1f}%"
        f"{', NEAR BOUNDARY' if st.near_boundary else ''})",
        f"  budget:      {brief.budget.value:.0f} {brief.budget.unit}",
        f"  success:     {brief.success_measure.value:.0f} {brief.success_measure.unit}",
        f"  hypothesis:  {brief.hypothesis}",
    ]
    return "\n".join(lines)


__all__ = ["item_ref", "shown_payload", "shown_hash", "render_summary"]
