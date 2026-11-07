# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Build the demo dashboard by injecting insights.json into the template.

Produces two self-contained outputs from one source (web/dashboard.html):
  * docs/index.html         — standalone HTML document (served by GitHub Pages)
  * out/dashboard_page.html — fragment with data inlined (for publishing as an
                              Artifact, which supplies its own document skeleton)

Run `scripts/demo_insights.py` first to refresh out/insights.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "web" / "dashboard.html"
INSIGHTS = ROOT / "out" / "insights.json"
STANDALONE = ROOT / "docs" / "index.html"
ARTIFACT = ROOT / "out" / "dashboard_page.html"

HEAD = (
    "<!doctype html>\n<html lang=\"en\">\n<head>\n"
    "<meta charset=\"utf-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
    "<style>:root{color-scheme:light}body{margin:0;font:14px \"Helvetica Neue\",Helvetica,Arial,sans-serif}"
    "img{max-width:100%}[hidden]{display:none!important}</style>\n</head>\n<body>\n"
)
FOOT = "\n</body>\n</html>\n"


def main() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    if not INSIGHTS.exists():
        raise SystemExit("Missing out/insights.json — run scripts/demo_insights.py first.")
    data = json.loads(INSIGHTS.read_text(encoding="utf-8"))
    # compact JSON, safe to embed inside a <script> block
    payload = json.dumps(data, ensure_ascii=False).replace("</script", "<\\/script")
    rendered = template.replace("__INSIGHTS_JSON__", payload)

    STANDALONE.parent.mkdir(parents=True, exist_ok=True)
    STANDALONE.write_text(HEAD + rendered + FOOT, encoding="utf-8")
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {STANDALONE.relative_to(ROOT)} ({STANDALONE.stat().st_size // 1024} KB)")
    print(f"Wrote {ARTIFACT.relative_to(ROOT)} (artifact fragment)")


if __name__ == "__main__":
    main()
