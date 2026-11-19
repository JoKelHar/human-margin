# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Run the text checks against a plain-Claude baseline draft.

A baseline is a creative brief written in a fresh chat from baseline/PROMPT.md, as
markdown or JSON. This runs the two text checks on it -- no-naked-numbers (against the
scenario's Figures) and native-review (Norwegian copy present) -- and marks the
structural checks (schema, maker field) n/a for unstructured input, never as failures.
Writes brief/runs/<scenario>/baseline/checks.json so the baseline is measured by the
same rules as the pipeline's own briefs.

    uv run python -m brief.baseline <scenario-slug> [draft.md|draft.json]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from brief.checks import _canon_unit
from brief.numbers import unmatched
from brief.run import RUNS_DIR
from brief.scenarios import goal_of, load_position, load_scenario

_NO_CHARS = re.compile(r"[æøå]", re.I)
# Distinctly-Norwegian words only; common English/Norwegian homographs (e.g. "for") are
# left out to avoid flagging English body copy. Norwegian lines are caught by æøå too.
_NO_WORDS = re.compile(r"\b(og|din|deg|med|ikke|du|vi|som|til|har|kan|når|sammen)\b", re.I)


def _figure_pool(slug: str) -> list[tuple[float, str]]:
    scenario = load_scenario(slug)
    goal = goal_of(scenario)
    figs = [goal.target, goal.budget] + list(load_position(slug).figures)
    return [(f.value, _canon_unit(f.unit)) for f in figs]


def _text_of(path: Path) -> str:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    out: list[str] = []

    def walk(o):
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return "\n".join(out)


def _norwegian_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and (_NO_CHARS.search(ln) or _NO_WORDS.search(ln))]


def check_baseline(slug: str, draft_path: Path) -> dict:
    text = _text_of(draft_path)
    naked = unmatched(text, _figure_pool(slug))
    no_lines = _norwegian_lines(text)
    findings = [
        {"check": "schema", "ok": True, "detail": "n/a for unstructured input"},
        {"check": "maker_match", "ok": True, "detail": "n/a for unstructured input"},
        {"check": "no_naked_numbers", "ok": not naked,
         "detail": "every number is backed by a scenario Figure" if not naked
         else "naked numbers (no matching Figure value+unit): " + "; ".join(naked)},
        {"check": "native_review", "ok": not no_lines,
         "detail": "no Norwegian copy detected" if not no_lines
         else "Norwegian copy present; unstructured input carries no "
              "needs_native_review flag: " + " | ".join(no_lines)},
    ]
    return {"ok": all(f["ok"] for f in findings),
            "not_applicable": ["schema", "maker_match"], "findings": findings}


def write_baseline(slug: str, draft_path: Path) -> dict:
    out = RUNS_DIR / slug / "baseline"
    out.mkdir(parents=True, exist_ok=True)
    report = check_baseline(slug, draft_path)
    (out / "checks.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return report


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not 1 <= len(args) <= 2:
        print("usage: python -m brief.baseline <scenario-slug> [draft.md|draft.json]",
              file=sys.stderr)
        return 2
    slug = args[0]
    draft = Path(args[1]) if len(args) == 2 else RUNS_DIR / slug / "baseline" / "draft.md"
    if not draft.exists():
        print(f"no baseline draft at {draft}: paste baseline/PROMPT.md into a fresh chat "
              "and save the reply there first", file=sys.stderr)
        return 2
    report = write_baseline(slug, draft)
    print(f"wrote brief/runs/{slug}/baseline/checks.json (ok={report['ok']})")
    for f in report["findings"]:
        if not f["ok"]:
            print(f"  FAIL {f['check']}: {f['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
