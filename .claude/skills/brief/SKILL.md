---
name: brief
description: Draft a creative brief and a test hypothesis from a scenario (Context + Goal) and Decide's Position, validate it against brief/checks.py, and record the run for the human gate. The agent drafts and records only; it never approves, and it never writes status=approved.
---

# Brief

Turn one scenario (`Context` + `Goal`) plus Decide's `Position` into a creative brief and a
testable hypothesis, then **stop for a human decision**. You draft; Python validates and
records; only the human gate (`python -m brief.approve`) can approve. Never approve your
own output.

## Inputs

Pick a scenario slug (`aurora`, `fjellbre`, `verftet`) and load it in Python:

```python
import brief.scenarios as S
scenario = S.load_scenario(slug)        # Context, Goal, decide_inputs, changelog (illustrative inputs)
context  = S.context_of(scenario)
goal     = S.goal_of(scenario)
position = S.load_position(slug)        # Decide's Position (envelope id "{slug}-pos")
```

Decide's maker verdict for the scenario:

```python
from brief.checks import stance_of
stance = stance_of(position)            # stance.maker, stance.ratio, stance.near_boundary
```

## Draft the Brief (as JSON for `schema.Brief`, v0.2)

Fill every field. Hold to these rules, which the checks enforce:

- **No naked numbers.** Every number in a *text* field (objective, audience, insight,
  proposition, the maker rationale, hypothesis, tone, copy lines, open questions) must be
  backed by a `Figure` — one already in the inputs (`goal.target`, `goal.budget`, the
  `position.figures`) or one you add to `assumptions[]`. Each assumption must have
  `source="assumption"`. Prefer naming no number you cannot back.
- **Maker recommendation.** `maker_recommendation.maker` must equal `stance.maker`, **or**
  you must state in `open_questions` why you disagree (mention the stance). Set
  `maker_recommendation.position_id` to `position.envelope.id`. If `stance.near_boundary`
  is true, you must raise an open question about the close call.
- **Mandatories.** Cite the relevant `norway_rules` ids from `decide/data/ai_tools.yaml`
  (`retouch_label`, `misleading`, `ai_act`) and `ai_disclosure` as applicable. Legal text
  goes here; mandatories are not scanned for numbers.
- **AI-content labelling is a default mandatory.** Where the risk is lopsided — a missing
  label can mislead, an unnecessary one rarely harms — the safe option is the default. So
  **any brief with an AI or hybrid maker** (the recommendation *or* any deliverable) must
  carry an AI-content labelling mandatory (`ai_disclosure` or `ai_act`). It is never an
  open question, and the `ai_labelling` check fails a brief that omits it. Dropping the
  label is not the agent's call: it is an explicit human **opt-out at the gate**, recorded
  in the Decision (as the reviewer's reason, via an `edit`). Draft it in; never leave it
  out to save the reviewer a step.
- **Norwegian copy.** Any `copy_lines` entry in Norwegian (`nb-NO`/`nn-NO`) must have
  `needs_native_review: true`.
- **Envelope.** `made_by: "agent"`, `parent_ids: [context, goal, position]` ids. Leave the
  status out or `draft`; the recorder sets it.

## Validate, fix, and record (status rule is in code)

Write the draft to a temp JSON file and record it:

```
uv run python -m brief.record <slug> <draft-brief.json>
```

**Run the checks with the command only. Don't open or read `brief/checks.py`,
`brief/numbers.py`, or the fixtures; treat the checks as a black box. Fix drafts using the
failure messages alone.**

`brief.record.write_run` runs `brief/checks.py` and **sets the status itself**:

- checks pass → the run is written **`status=proposed`**.
- checks fail → the run is written **`status=draft`** with the failures listed in
  `checks.json`.

If it reports failures, read them, fix the draft, and record again — **at most 2 retries**
(3 attempts total). After the last attempt, leave the run as the recorder wrote it:
`proposed` if clean, otherwise `draft` with the failures. **Never edit the status to
`proposed` or `approved` by hand**, and never hand-write a `decision.json`.

## Stop

The run now holds `inputs.json`, `brief.json`, `checks.json`. Approval is a separate human
step at a TTY — do not run it for the user and do not pipe answers into it:

```
python -m brief.approve <slug>
```

## After the gate: `edit` → brief v2

The gate has three outcomes: `approve`, `edit`, `reject`. **`edit` is the revise loop** —
the reviewer accepts the direction but wants changes. Here is what happens, and what you
(the agent) do:

1. **The reviewer picks `edit`** and types their notes as the decision reason; per-item
   notes they leave on an assumption or open question are kept too. The gate records a
   `Decision` with `outcome=edit`, sets the brief back to `status=draft`, and stores the
   reason and the acknowledgements. It does **not** approve anything.
2. **You draft brief v2** from those notes: read the recorded `decision.json` (its `reason`
   and the per-item notes), revise the draft, and record it again with
   `uv run python -m brief.record <slug> <v2.json>`. The recorder logs v2 as the next
   `attempts/attempt-N/` and updates `brief.json` to v2 — **v1 stays** at
   `attempts/attempt-1/`, so both versions live in the run and nothing is overwritten away.
3. **The reviewer reviews v2** by re-running `python -m brief.approve <slug>`. Because the
   content changed, the gate computes a new `shown_hash`, so an approval can only ever
   attach to the exact version the reviewer saw — a v1 approval can never ride on v2.

Repeat 1–3 until the outcome is `approve` or `reject`. You still never approve: you only
draft, record, and hand back to the gate. If the reviewer's notes ask to drop the
AI-content labelling mandatory, that is their opt-out to make and it is already recorded in
the Decision's reason — do not remove labelling on your own initiative in any version.
