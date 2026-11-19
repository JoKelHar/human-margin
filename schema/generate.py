# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Generate JSON Schema for the v0.1 artefact models into schema/json/.

Run it after any change to schema/models.py:

    uv run python schema/generate.py

Output is deterministic (sorted keys, trailing newline) so the committed files are a
reviewable diff and schema/tests/test_schema.py can assert they are up to date.
"""

from __future__ import annotations

import json
from pathlib import Path

from schema.briefs import BRIEF_MODELS
from schema.models import MODELS as _CORE_MODELS

# v0.1 value objects + artefacts, then the v0.2 Brief/Decision artefacts.
MODELS = _CORE_MODELS + BRIEF_MODELS

JSON_DIR = Path(__file__).resolve().parent / "json"


def schema_for(model: type) -> dict:
    return model.model_json_schema()


def write_all(out_dir: Path = JSON_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model in MODELS:
        path = out_dir / f"{model.__name__.lower()}.json"
        text = json.dumps(schema_for(model), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    written = write_all()
    print(f"Wrote {len(written)} JSON Schema file(s) to {JSON_DIR}:")
    for p in written:
        print(f"  {p.relative_to(JSON_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
