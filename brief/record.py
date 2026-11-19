# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Record a brief run, with the proposed/draft status rule enforced in code.

The brief skill drafts the Brief JSON and may retry; this module is the one place that
decides the recorded status. A brief that passes the checks is written status=proposed; a
brief that still fails is written status=draft with the failures listed in checks.json.
It never writes status=approved -- only the human gate can approve.

    uv run python -m brief.record <scenario-slug> <drafted-brief.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from brief.checks import CheckReport, check_brief
from brief.run import RUNS_DIR
from brief.scenarios import context_of, goal_of, load_position, load_scenario
from schema import Brief, Context, Goal, Position, Status


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def finalize_status(brief: Brief, report: CheckReport) -> Brief:
    """proposed when the checks pass, draft when they do not -- never approved."""
    brief.envelope.status = Status.proposed if report.ok else Status.draft
    return brief


def write_run(run_dir: Path, brief: Brief, context: Context, goal: Goal,
              position: Position) -> CheckReport:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report = check_brief(brief, context, goal, position)
    finalize_status(brief, report)
    _write_json(run_dir / "inputs.json", {
        "context": context.model_dump(mode="json"),
        "goal": goal.model_dump(mode="json"),
        "position": position.model_dump(mode="json")})
    _write_json(run_dir / "brief.json", brief.model_dump(mode="json"))
    _write_json(run_dir / "checks.json", report.to_dict())
    return report


def record_for_scenario(slug: str, brief_json: Path) -> CheckReport:
    scenario = load_scenario(slug)
    brief = Brief.model_validate_json(Path(brief_json).read_text(encoding="utf-8"))
    return write_run(RUNS_DIR / slug, brief, context_of(scenario), goal_of(scenario),
                     load_position(slug))


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: python -m brief.record <scenario-slug> <drafted-brief.json>",
              file=sys.stderr)
        return 2
    report = record_for_scenario(args[0], Path(args[1]))
    status = "proposed" if report.ok else "draft"
    print(f"recorded brief/runs/{args[0]}/ with status={status}")
    for f in report.findings:
        if not f.ok:
            print(f"  FAIL {f.check}: {f.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
