# Baseline (plain-Claude) — aurora

An independent, plain-Claude baseline draft goes here, added by a human:

1. Paste `PROMPT.md` into a fresh Claude chat (no access to this repo or its checks).
2. Save the reply as `draft.md` (or `draft.json`) in this folder.
3. Run: `uv run python -m brief.baseline aurora`

That writes `checks.json` here: no-naked-numbers (against this scenario's Figures) and
native-review run on the text; schema and the maker field are marked n/a for
unstructured input, never as failures.

Do not generate the baseline with the pipeline — the point is an independent draft.
