# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Decision-matrix integrity: every verdict is backed by the metric it names.

A verdict must never be shown with zero or missing values for its deciding
metric. ROAS decides only when it is reliable; otherwise the verdict falls back
to saves and ROAS is reported as None (rendered n/a), never a misleading zero.
"""

from __future__ import annotations

import copy

from mediekjop.recommend.matrix import decision_matrix

_REAL_VERDICTS = {"Human wins", "AI wins", "No difference"}


def test_verdict_is_backed_by_its_deciding_metric(con, cfg):
    cells = decision_matrix(con, cfg)
    assert cells
    for c in cells:
        if c["verdict"] == "Insufficient data":
            assert c["decided_by"] is None
            continue
        assert c["verdict"] in _REAL_VERDICTS
        assert c["decided_by"] in ("ROAS", "saves")
        if c["decided_by"] == "ROAS":
            hr, ar = c["human_roas"], c["ai_roas"]
            assert hr is not None and ar is not None, f"ROAS verdict with missing ROAS: {c}"
            assert not (hr == 0 and ar == 0), f"ROAS verdict with 0/0 ROAS: {c}"
        else:
            hs, as_ = c["human_save_permille"], c["ai_save_permille"]
            assert hs is not None and as_ is not None, f"saves verdict with missing saves: {c}"
            assert not (hs == 0 and as_ == 0), f"saves verdict with 0/0 saves: {c}"


def test_insufficient_data_below_impression_threshold(con, cfg):
    cfg2 = copy.deepcopy(cfg)
    cfg2["thresholds"]["min_impressions_for_verdict"] = 10 ** 15  # nothing clears it
    for c in decision_matrix(con, cfg2):
        assert c["verdict"] == "Insufficient data"
        assert c["decided_by"] is None


def test_roas_is_na_and_saves_decide_when_conversions_scarce(con, cfg):
    cfg2 = copy.deepcopy(cfg)
    cfg2["thresholds"]["min_conversions_for_cpa"] = 10 ** 12  # ROAS never reliable
    decided = [c for c in decision_matrix(con, cfg2) if c["verdict"] in _REAL_VERDICTS]
    assert decided
    for c in decided:
        assert c["decided_by"] == "saves"
        assert c["human_roas"] is None and c["ai_roas"] is None  # ROAS shown as n/a
        assert c["human_save_permille"] is not None and c["ai_save_permille"] is not None
