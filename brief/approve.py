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

from brief.checks import check_brief, stance_of
from brief.config import THRESHOLDS
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


_ITEM_LABELS = {"assumption": "assumption", "open_question": "open question"}


def _figure_rows(brief, goal, position) -> list[tuple[str, object]]:
    """(name, Figure) for every number the reviewer should see, with its provenance."""
    rows = [("goal.target", goal.target), ("goal.budget", goal.budget),
            ("brief.budget", brief.budget), ("brief.success_measure", brief.success_measure)]
    rows += [(f.ref or "position figure", f) for f in position.figures]
    rows += [(f.ref or "brief assumption", f) for f in brief.assumptions]
    return rows


def _figure_table(name_figure_pairs) -> str:
    """A fixed-width table: name, value, unit, source, confidence."""
    headers = ["name", "value", "unit", "source", "confidence"]
    rows = [(name, f"{f.value:g}", f.unit, f.source.value, f.confidence.value)
            for name, f in name_figure_pairs]
    cols = list(zip(headers, *rows)) if rows else [(h,) for h in headers]
    widths = [max(len(str(c)) for c in col) for col in cols]

    def line(cells):
        return "  " + "  ".join(str(c).ljust(w) for c, w in zip(cells, widths))

    return "\n".join([line(headers), line(["-" * w for w in widths])]
                     + [line(r) for r in rows])


def _interactive_answers(run, stream_in, stream_out) -> dict:
    brief = run.brief

    def say(s=""):
        stream_out.write(s + "\n")
        stream_out.flush()

    def ask(prompt: str) -> str:
        # Flush the prompt to the screen before blocking on input (requirement 4).
        stream_out.write(prompt)
        stream_out.flush()
        raw = stream_in.readline()
        if raw == "":
            raise GateError("input closed before the gate was complete")
        return raw.rstrip("\n")

    say(render_summary(brief, run.context, run.goal, run.position))

    # 1. Every Figure the brief may cite, with provenance, then the stance thresholds.
    say("")
    say("Figures the brief may cite:")
    say(_figure_table(_figure_rows(brief, run.goal, run.position)))

    st = stance_of(run.position)
    say("")
    say("Decide stance thresholds (break-even as % of goal):")
    say(_figure_table(THRESHOLDS))
    say(f"  this brief: stance={st.maker.value}, ratio={st.ratio:.1f}%"
        f"{', NEAR BOUNDARY' if st.near_boundary else ''}")

    # 2. One item at a time: its type and full text FIRST, then the two questions.
    items = _items(brief)
    n = len(items)
    say("")
    say(f"Acknowledge each item ({n} total). Accept only what you have read and agree with.")
    acks = {}
    for i, (kind, ref, text) in enumerate(items, 1):
        say("")
        say(f"Item {i} of {n}: [{_ITEM_LABELS.get(kind, kind)}]")
        say(f"  {text}")
        ans = ask("Accept? (y/n): ").strip().lower()
        note = ask("Note (optional, press Enter to skip): ").strip()
        acks[ref] = {"acknowledged": ans.startswith("y"), "note": note or ""}

    # 3. The decision, with the options spelled out.
    say("")
    outcome = ask("Decision: type approve, edit or reject: ").strip().lower()
    maker_word = ""
    if outcome == "approve":
        rec = brief.maker_recommendation.maker.value
        maker_word = ask(f"To approve, retype the recommended maker word ({rec}): ") \
            .strip().lower()
    reason = ask("Reason (required for edit/reject or to approve against Decide's stance; "
                 "Enter to skip): ").strip() or None
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
