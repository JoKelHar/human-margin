# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Record a brief run, with the proposed/draft status rule enforced in code.

The brief skill drafts the Brief JSON and may retry; this module is the one place that
decides the recorded status and the only way a run is written (no hand edits to
brief.json). A brief that passes the checks is written status=proposed; one that still
fails is written status=draft with the failures listed. It never writes status=approved.

Every attempt is kept under runs/<scenario>/attempts/attempt-N/ and summarised in
brief.md, so failures are never hidden.

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


def _next_attempt(run_dir: Path) -> int:
    adir = run_dir / "attempts"
    return 1 + len(list(adir.glob("attempt-*"))) if adir.exists() else 1


def _attempts_summary(run_dir: Path) -> list[str]:
    lines = []
    for ad in sorted((run_dir / "attempts").glob("attempt-*")):
        n = ad.name.split("-")[-1]
        checks = json.loads((ad / "checks.json").read_text(encoding="utf-8"))
        if checks["ok"]:
            lines.append(f"attempt {n} passed")
        else:
            fails = "; ".join(f"{f['check']}: {f['detail']}"
                              for f in checks["findings"] if not f["ok"])
            lines.append(f"attempt {n} failed: {fails}")
    return lines


def _render_md(slug: str, brief: Brief, context: Context, goal: Goal, position: Position,
               report: CheckReport, attempts: list[str]) -> str:
    from brief.checks import stance_of
    st = stance_of(position)
    status = brief.envelope.status.value
    md = [f"# Brief — {context.brand}", "",
          "_Illustrative inputs, not market data._", "",
          f"- **Category / market:** {context.category} / {context.market}",
          f"- **Decide stance:** {st.maker.value} (break-even {st.ratio:.1f}% of goal"
          f"{', near boundary' if st.near_boundary else ''})",
          f"- **Recorded status:** {status}", "",
          "## Attempts", ""]
    md += [f"- {line}" for line in attempts] or ["- (none recorded)"]
    md += ["", "## Brief", "",
           f"- **Objective:** {brief.objective}",
           f"- **Audience:** {brief.audience}",
           f"- **Insight:** {brief.insight}",
           f"- **Proposition:** {brief.proposition}",
           f"- **Maker:** {brief.maker_recommendation.maker.value} "
           f"(cites {brief.maker_recommendation.position_id}) — "
           f"{brief.maker_recommendation.rationale}",
           "- **Deliverables:** " + "; ".join(
               f"{d.count}× {d.format} ({d.maker.value})" for d in brief.deliverables),
           "- **Mandatories:** " + "; ".join(m.id for m in brief.mandatories),
           f"- **Tone:** {brief.tone}",
           f"- **Budget:** {brief.budget.value:.0f} {brief.budget.unit}",
           f"- **Success measure:** {brief.success_measure.value:.0f} {brief.success_measure.unit}",
           f"- **Hypothesis:** {brief.hypothesis}",
           "- **Copy lines:**"]
    md += [f"    - [{c.language}{', native review' if c.needs_native_review else ''}] {c.text}"
           for c in brief.copy_lines]
    md += ["- **Assumptions:** " + "; ".join(
        f"{a.value:.0f} {a.unit} ({a.source.value})" for a in brief.assumptions)]
    md += ["- **Open questions:**"]
    md += [f"    - {q}" for q in brief.open_questions]
    md += ["", "## Baseline", "",
           "A plain-Claude baseline can be added under `baseline/` (paste `baseline/PROMPT.md`",
           f"into a fresh chat, save the reply) and checked with `python -m brief.baseline {slug}`.",
           "", "## Status", "",
           "Proposed or draft only. Approval is a separate human step at a TTY "
           "(`python -m brief.approve`); no decision is recorded here.", ""]
    return "\n".join(md)


def write_run(run_dir: Path, brief: Brief, context: Context, goal: Goal,
              position: Position, slug: str | None = None) -> CheckReport:
    run_dir = Path(run_dir)
    slug = slug or run_dir.name
    run_dir.mkdir(parents=True, exist_ok=True)
    report = check_brief(brief, context, goal, position)
    finalize_status(brief, report)

    n = _next_attempt(run_dir)
    adir = run_dir / "attempts" / f"attempt-{n}"
    adir.mkdir(parents=True, exist_ok=True)
    _write_json(adir / "brief.json", brief.model_dump(mode="json"))
    _write_json(adir / "checks.json", report.to_dict())

    _write_json(run_dir / "inputs.json", {
        "context": context.model_dump(mode="json"),
        "goal": goal.model_dump(mode="json"),
        "position": position.model_dump(mode="json")})
    _write_json(run_dir / "brief.json", brief.model_dump(mode="json"))
    _write_json(run_dir / "checks.json", report.to_dict())
    (run_dir / "brief.md").write_text(
        _render_md(slug, brief, context, goal, position, report, _attempts_summary(run_dir)),
        encoding="utf-8")
    return report


def record_for_scenario(slug: str, brief_json: Path) -> CheckReport:
    scenario = load_scenario(slug)
    brief = Brief.model_validate_json(Path(brief_json).read_text(encoding="utf-8"))
    return write_run(RUNS_DIR / slug, brief, context_of(scenario), goal_of(scenario),
                     load_position(slug), slug=slug)


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: python -m brief.record <scenario-slug> <drafted-brief.json>",
              file=sys.stderr)
        return 2
    report = record_for_scenario(args[0], Path(args[1]))
    status = "proposed" if report.ok else "draft"
    print(f"recorded brief/runs/{args[0]}/ (attempt logged) with status={status}")
    for f in report.findings:
        if not f.ok:
            print(f"  FAIL {f.check}: {f.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
