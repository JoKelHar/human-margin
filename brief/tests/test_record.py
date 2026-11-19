# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The status rule is enforced in code, not just in the skill prompt: a brief that passes
is recorded status=proposed; a brief that fails is recorded status=draft with the
failures listed, and never proposed or approved."""

from __future__ import annotations

import json

from _fixtures import inputs_models, valid_brief_dict

from brief.record import write_run
from schema import Brief


def test_passing_brief_is_recorded_proposed(tmp_path):
    ctx, goal, pos = inputs_models()
    report = write_run(tmp_path / "run", Brief.model_validate(valid_brief_dict()), ctx, goal, pos)
    assert report.ok
    brief = json.loads((tmp_path / "run" / "brief.json").read_text(encoding="utf-8"))
    assert brief["envelope"]["status"] == "proposed"


def test_failing_brief_is_recorded_draft_with_failures_never_proposed(tmp_path):
    ctx, goal, pos = inputs_models()
    bad = valid_brief_dict()
    bad["proposition"] = "a premium studio look that earns 7 777 orders"   # naked number
    report = write_run(tmp_path / "run", Brief.model_validate(bad), ctx, goal, pos)
    assert not report.ok
    brief = json.loads((tmp_path / "run" / "brief.json").read_text(encoding="utf-8"))
    checks = json.loads((tmp_path / "run" / "checks.json").read_text(encoding="utf-8"))
    assert brief["envelope"]["status"] == "draft"
    assert brief["envelope"]["status"] not in ("proposed", "approved")
    assert checks["ok"] is False
    assert any(not f["ok"] for f in checks["findings"])


def test_every_attempt_is_recorded_and_summarised(tmp_path):
    ctx, goal, pos = inputs_models()
    run = tmp_path / "run"
    bad = valid_brief_dict()
    bad["proposition"] = "a premium studio look that earns 7 777 orders"
    write_run(run, Brief.model_validate(bad), ctx, goal, pos)        # attempt 1 fails
    write_run(run, Brief.model_validate(valid_brief_dict()), ctx, goal, pos)  # attempt 2 passes
    assert (run / "attempts" / "attempt-1" / "checks.json").exists()
    assert (run / "attempts" / "attempt-2" / "checks.json").exists()
    md = (run / "brief.md").read_text(encoding="utf-8")
    assert "attempt 1 failed" in md and "attempt 2 passed" in md   # failures not hidden
    assert json.loads((run / "brief.json").read_text())["envelope"]["status"] == "proposed"
