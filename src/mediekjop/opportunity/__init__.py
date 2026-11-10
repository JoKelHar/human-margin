# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Forward-looking pattern detection [Phase 7].

  * calendar  — Norwegian cultural calendar; forward patterns with lead time,
    stated descriptively (what has happened + evidence), never as advice.
  * organic   — early-warning on organic outperformers (described, not pushed).
  * saturation — category AI-saturation index, presented ALWAYS as a directional
    estimate (never a scoreboard or competitor league table), with the
    classifier's estimated accuracy shown alongside it.
"""

from .calendar import REQUIRED_FIELDS, UNTESTED_NOTE, upcoming_patterns

__all__ = ["upcoming_patterns", "REQUIRED_FIELDS", "UNTESTED_NOTE"]
