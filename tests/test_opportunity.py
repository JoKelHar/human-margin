# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Phase 7 (preview): forward calendar opportunities are actionable.

Every opportunity must name four things — advertiser category, moment, time
window and recommended approach — and a moment with no obvious advertiser
category is dropped rather than reworded.
"""

from __future__ import annotations

import copy
import datetime as dt

from mediekjop.opportunity import REQUIRED_FIELDS, upcoming_opportunities

FIXED_TODAY = dt.date(2026, 11, 7)


def test_every_opportunity_has_four_fields(con, cfg):
    ops = upcoming_opportunities(con, cfg, FIXED_TODAY, min_impr=10000)
    assert ops, "expected at least one upcoming opportunity"
    for o in ops:
        for field in REQUIRED_FIELDS:
            assert o.get(field), f"opportunity missing '{field}': {o}"
        assert o["window"].count("to") == 1  # a real date range


def test_categoryless_moment_is_dropped(con, cfg):
    cfg2 = copy.deepcopy(cfg)
    for m in cfg2["calendar"]["moments"]:
        if m["key"] == "black_friday":
            m.pop("category", None)  # remove the only thing that makes it actionable
    ops = upcoming_opportunities(con, cfg2, FIXED_TODAY, min_impr=10000, limit=10)
    assert all(o["moment"] != "Black Friday" for o in ops)


def test_approach_names_ai_subtype_where_relevant(con, cfg):
    ops = upcoming_opportunities(con, cfg, FIXED_TODAY, min_impr=10000, limit=10)
    joined = " ".join(o["approach"] for o in ops)
    # at least one approach should reference an AI sub-type token
    assert any(tok in joined for tok in ("AA-PRD", "AA-CPY", "AG-UGC", "AG-SCN"))
