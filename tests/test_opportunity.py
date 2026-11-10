# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Phase 7 (preview): forward calendar patterns are descriptive, not prescriptive.

Every pattern names an advertiser category, a moment and a time window, then
states what has happened (the pattern) with its evidence. A moment with no obvious
advertiser category is dropped rather than reworded, and no item instructs.
"""

from __future__ import annotations

import copy
import datetime as dt

from mediekjop.opportunity import REQUIRED_FIELDS, upcoming_patterns

FIXED_TODAY = dt.date(2026, 11, 7)

# Words that would make an item prescriptive rather than descriptive.
PRESCRIPTIVE = ("you should", "best time", "opportunity", "avoid ", "shift ", "cap ")


def test_every_pattern_has_required_fields_and_evidence(con, cfg):
    pats = upcoming_patterns(con, cfg, FIXED_TODAY, min_impr=10000)
    assert pats, "expected at least one upcoming pattern"
    for p in pats:
        for field in REQUIRED_FIELDS:
            assert p.get(field), f"pattern missing '{field}': {p}"
        assert p["window"].count("to") == 1  # a real date range
        assert p.get("evidence")             # N / years / market / confidence line


def test_categoryless_moment_is_dropped(con, cfg):
    cfg2 = copy.deepcopy(cfg)
    for m in cfg2["calendar"]["moments"]:
        if m["key"] == "black_friday":
            m.pop("category", None)  # remove the only thing that makes it a pattern
    pats = upcoming_patterns(con, cfg2, FIXED_TODAY, min_impr=10000, limit=10)
    assert all(p["moment"] != "Black Friday" for p in pats)


def test_pattern_names_ai_subtype_where_relevant(con, cfg):
    pats = upcoming_patterns(con, cfg, FIXED_TODAY, min_impr=10000, limit=10)
    joined = " ".join(p["pattern"] for p in pats)
    # at least one pattern should reference an AI sub-type token
    assert any(tok in joined for tok in ("AA-PRD", "AA-CPY", "AG-UGC", "AG-SCN"))


def test_patterns_are_descriptive_not_prescriptive(con, cfg):
    pats = upcoming_patterns(con, cfg, FIXED_TODAY, min_impr=10000, limit=10)
    for p in pats:
        low = p["pattern"].lower()
        assert not any(w in low for w in PRESCRIPTIVE), f"prescriptive wording: {p['pattern']}"
