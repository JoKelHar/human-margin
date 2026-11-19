# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Load a brief only if a human really approved this exact content.

Status is not proof. A brief loads only when its run carries a Decision that is
approve + mode=interactive + made_by=human, whose shown_hash recomputes to the current
brief. A fixture-mode Decision, an agent-made Decision, a reject/edit, or any edit to the
brief after approval all make the loader refuse.
"""

from __future__ import annotations

from brief.checks import check_brief
from brief.review import shown_hash
from brief.run import Run, load_decision, load_run
from schema import Brief, DecisionMode, MadeBy, Outcome


class NotApproved(RuntimeError):
    pass


def load_approved_brief(run_id) -> Brief:
    run: Run = load_run(run_id)
    decision = load_decision(run.path)
    if decision is None:
        raise NotApproved("no Decision: the brief has not been through the gate")
    if decision.outcome is not Outcome.approve:
        raise NotApproved(f"Decision outcome is {decision.outcome.value}, not approve")
    if decision.mode is not DecisionMode.interactive:
        raise NotApproved(f"Decision mode is {decision.mode.value}, not interactive "
                          "(a fixture is never a human sign-off)")
    if decision.envelope.made_by is not MadeBy.human:
        raise NotApproved("Decision is not made_by=human")
    recomputed = shown_hash(run.brief, run.context, run.goal, run.position)
    if decision.shown_hash != recomputed:
        raise NotApproved("shown_hash does not match the current brief: it changed after "
                          "approval, so the approval no longer applies")
    # Re-run the checks regardless of any recorded checks.json: a brief that fails never
    # loads, even with an approval attached.
    rep = check_brief(run.brief, run.context, run.goal, run.position)
    if not rep.ok:
        raise NotApproved("brief no longer passes checks: "
                          + "; ".join(f.detail for f in rep.findings if not f.ok))
    return run.brief


__all__ = ["NotApproved", "load_approved_brief"]
