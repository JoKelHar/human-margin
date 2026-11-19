# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The human gate. Rubber-stamping is made impossible by construction.

    python -m brief.approve <run_id>

Flow: show the brief summary, every Figure (value, source, confidence), the assumptions
and the stance thresholds; then require a per-item acknowledgement of each assumption and
each open question; only then ask for an outcome. Any un-acknowledged item blocks
approval. Approving means typing the recommended maker word. A reason is required to
reject, to edit, and to approve against Decide's stance.

The gate refuses to run unless stdin is a TTY, except in test-only fixture mode
(--from-file answers.json) which needs BRIEF_ALLOW_NONINTERACTIVE=1 and records the
Decision with mode=fixture / decided_by="fixture" -- never a human sign-off.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from brief.checks import check_brief
from brief.review import item_ref, render_summary, shown_hash
from brief.run import load_run, write_decision
from schema import (
    Acknowledgement,
    Decision,
    DecisionMode,
    Envelope,
    MadeBy,
    Outcome,
    Status,
)


class GateError(RuntimeError):
    pass


def _items(brief) -> list[tuple[str, str, str]]:
    """(item_type, ref, text) for every assumption and open question to acknowledge."""
    out = [("assumption", item_ref(a.ref or str(a.value)),
            f"{a.value:.0f} {a.unit} ({a.source.value}, {a.confidence.value})")
           for a in brief.assumptions]
    out += [("open_question", item_ref(q), q) for q in brief.open_questions]
    return out


def _interactive_answers(run, stream_in, stream_out) -> dict:
    def say(s=""):
        print(s, file=stream_out)

    say(render_summary(run.brief, run.context, run.goal, run.position))
    say("\nAcknowledge each item (y/n), with an optional note:")
    acks = {}
    for kind, ref, text in _items(run.brief):
        raw = stream_in.readline()
        if raw == "":
            raise GateError("input closed before all items were acknowledged")
        ans = raw.strip().lower()
        acks[ref] = {"acknowledged": ans.startswith("y"), "note": ""}
        say(f"  [{kind}] {text} -> {'ack' if acks[ref]['acknowledged'] else 'NOT ack'}")
    outcome = stream_in.readline().strip().lower()
    maker_word = stream_in.readline().strip().lower() if outcome == "approve" else ""
    reason = stream_in.readline().strip() or None
    return {"mode": "interactive", "decided_by": "", "outcome": outcome,
            "maker_word": maker_word, "reason": reason, "acks": acks}


def decide(run, answers: dict, decided_by: str) -> Decision:
    """Turn answers (interactive or fixture) into a validated Decision, enforcing the gate."""
    items = _items(run.brief)
    acks = answers.get("acks", {})
    acknowledgements = []
    blocked = False
    for kind, ref, _text in items:
        a = acks.get(ref, {"acknowledged": False, "note": None})
        acknowledgements.append(Acknowledgement(item_type=kind, item_ref=ref,
                                                acknowledged=bool(a.get("acknowledged")),
                                                note=a.get("note") or None))
        blocked = blocked or not a.get("acknowledged")

    outcome = Outcome(answers["outcome"])
    reason = (answers.get("reason") or None)
    rec = run.brief.maker_recommendation.maker

    if outcome is Outcome.approve:
        if blocked:
            raise GateError("cannot approve: an assumption or open question was not acknowledged")
        if answers.get("maker_word", "").strip().lower() != rec.value:
            raise GateError(f"approval requires typing the recommended maker word: {rec.value!r}")
        # Divergence from Decide needs a reason (checks.py flags the divergence itself).
        from brief.checks import stance_of
        if rec != stance_of(run.position).maker and not reason:
            raise GateError("approving against Decide's stance requires a reason")
    elif not reason:
        raise GateError(f"{outcome.value} requires a reason")

    mode = DecisionMode(answers.get("mode", "interactive"))
    who = "fixture" if mode is DecisionMode.fixture else decided_by
    status = {Outcome.approve: Status.approved, Outcome.edit: Status.draft,
              Outcome.reject: Status.rejected}[outcome]
    return Decision(
        target_id=run.brief.envelope.id, outcome=outcome, reason=reason,
        edits=answers.get("edits"), decided_by=who,
        timestamp=dt.datetime.now(dt.timezone.utc), mode=mode,
        shown_hash=shown_hash(run.brief, run.context, run.goal, run.position),
        acknowledgements=acknowledgements,
        envelope=Envelope(made_by=MadeBy.human, status=status),
    )


def run_gate(run_id, from_file: Path | None, decided_by: str,
             stdin=sys.stdin, stdout=sys.stdout) -> Decision:
    run = load_run(run_id)
    # The gate re-runs the checks itself; a brief that fails cannot be gated, whatever a
    # recorded checks.json claims.
    rep = check_brief(run.brief, run.context, run.goal, run.position)
    if not rep.ok:
        raise GateError("brief fails checks, cannot be gated: "
                        + "; ".join(f.detail for f in rep.findings if not f.ok))
    if from_file is not None:
        if os.environ.get("BRIEF_ALLOW_NONINTERACTIVE") != "1":
            raise GateError("fixture mode (--from-file) needs BRIEF_ALLOW_NONINTERACTIVE=1")
        answers = json.loads(Path(from_file).read_text(encoding="utf-8"))
        answers.setdefault("mode", "fixture")
    else:
        if not stdin.isatty():
            raise GateError("refusing to run: stdin is not a TTY (use --from-file for tests)")
        answers = _interactive_answers(run, stdin, stdout)
    decision = decide(run, answers, decided_by)
    write_decision(run.path, decision)
    return decision


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Human review gate for a brief run.")
    ap.add_argument("run_id")
    ap.add_argument("--from-file", type=Path, default=None,
                    help="test-only answers JSON; needs BRIEF_ALLOW_NONINTERACTIVE=1")
    ap.add_argument("--decided-by", default=os.environ.get("USER", "reviewer"))
    args = ap.parse_args(argv)
    try:
        d = run_gate(args.run_id, args.from_file, args.decided_by)
    except GateError as e:
        print(f"gate: {e}", file=sys.stderr)
        return 2
    print(f"recorded {d.outcome.value} (mode={d.mode.value}, by {d.decided_by})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
