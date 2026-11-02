"""Fatigue / decay model used by the synthetic generator.

A creative's response rate (CTR, thumb-stop) decays as cumulative frequency
rises. We model this as exponential decay:

    rate(f) = rate0 * exp(-k * f)

where f is cumulative frequency and k is the decay constant. The half-life in
frequency units is ln(2) / k: the frequency at which the rate halves.

The headline AI-exhaustion signal the agent must later *recover from data* is
encoded here as ground truth: AI-generated creative decays faster (larger k,
shorter half-life) than human-led creative at equal frequency, and faster still
in younger, more AI-literate cohorts. The generator writes these intended
values to ground_truth.json so Phase 4 can be validated against them.
"""

from __future__ import annotations

import math

# Base decay constants by provenance (per unit of cumulative frequency).
# Larger k => faster decay => shorter half-life.
BASE_DECAY_K: dict[str, float] = {
    "human_led": 0.045,
    "ai_assisted": 0.065,
    "ai_generated": 0.095,
}

# Cohorts assumed more AI-literate exhaust AI creative faster. This multiplies
# k for ai_* provenance only (human creative is roughly cohort-stable).
COHORT_AI_SENSITIVITY: dict[str, float] = {
    "age_13_17": 1.35,
    "age_18_24": 1.30,
    "age_25_34": 1.15,
    "age_35_44": 1.00,
    "age_45_54": 0.90,
    "age_55_plus": 0.85,
}


def decay_k(provenance: str, age_cohort: str) -> float:
    """Effective decay constant for a provenance x cohort."""
    k = BASE_DECAY_K.get(provenance, BASE_DECAY_K["human_led"])
    if provenance in ("ai_assisted", "ai_generated"):
        k *= COHORT_AI_SENSITIVITY.get(age_cohort, 1.0)
    return k


def decayed_rate(rate0: float, k: float, frequency: float, trend_boost: float = 0.0) -> float:
    """Response rate at a given cumulative frequency.

    trend_boost (>=0) inflates the effective decay to simulate exhaustion
    *worsening over time* within a segment — a widening human-AI gap — as
    distinct from a stable gap (trend_boost = 0).
    """
    k_eff = k * (1.0 + trend_boost)
    return rate0 * math.exp(-k_eff * max(frequency, 0.0))


def half_life(k: float) -> float:
    """Frequency at which the response rate halves."""
    return math.log(2.0) / k
