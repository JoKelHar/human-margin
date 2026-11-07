# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Build the demo pages from the template and the sample weekly brief.

Produces, from web/dashboard.html and samples/weekly_report_sample.md:
  * docs/index.html         standalone dashboard (served by GitHub Pages)
  * docs/sample-brief.html  the sample weekly brief, in the dashboard's styles
  * out/dashboard_page.html  fragment with data inlined (for an Artifact)

Run scripts/demo_insights.py first to refresh out/insights.json. This script is
presentation only: it renders existing content and never computes analysis.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "web" / "dashboard.html"
INSIGHTS = ROOT / "out" / "insights.json"
SAMPLE_MD = ROOT / "samples" / "weekly_report_sample.md"
STANDALONE = ROOT / "docs" / "index.html"
SAMPLE_HTML = ROOT / "docs" / "sample-brief.html"
ARTIFACT = ROOT / "out" / "dashboard_page.html"

SITE = "https://jokelhar.github.io/mediekjop-signal/"
OG_DESC = ("Recommend-only analysis tool for Norwegian B2C media buyers deciding "
           "between AI-led, hybrid and human-led creative. Prototype on synthetic data.")

# Norwegian calendar moments kept as proper nouns, with a short English gloss.
MOMENT_GLOSS = {
    "Julebordsesong": "Julebordsesong (Christmas party season)",
    "Første snø": "Første snø (first snow)",
    "Advent og jul": "Advent og jul (Advent and Christmas)",
    "Vinterferie": "Vinterferie (winter break)",
    "Russetid": "Russetid (graduation season)",
    "17. mai": "17. mai (Constitution Day)",
    "Påske": "Påske (Easter)",
    "Fellesferie": "Fellesferie (common summer holiday)",
    "Skolestart": "Skolestart (back to school)",
}

SYNTHNOTE = ('<p class="synthnote">Demonstration on <b>synthetic data with '
             'deliberately planted patterns</b>, a prototype, not real campaign '
             'results.</p>\n')

ATTRIBUTION = (
    '<span>Built by João Harrison</span>'
    '<span><a href="https://github.com/JoKelHar/mediekjop-signal">GitHub</a> · '
    '<a href="https://www.linkedin.com/in/joaoharrison">LinkedIn</a></span>'
)

# --- shared document head (charset, viewport, share-preview meta, favicon) ----

def page_head(title: str, canonical: str, *, extra_style: str = "") -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        f"<title>{html.escape(title)}</title>\n"
        f"<meta name=\"description\" content=\"{html.escape(OG_DESC)}\">\n"
        "<meta property=\"og:type\" content=\"website\">\n"
        f"<meta property=\"og:title\" content=\"{html.escape(title)}\">\n"
        f"<meta property=\"og:description\" content=\"{html.escape(OG_DESC)}\">\n"
        f"<meta property=\"og:url\" content=\"{canonical}\">\n"
        f"<meta property=\"og:image\" content=\"{SITE}og-image.png\">\n"
        "<meta name=\"twitter:card\" content=\"summary_large_image\">\n"
        f"<meta name=\"twitter:title\" content=\"{html.escape(title)}\">\n"
        f"<meta name=\"twitter:description\" content=\"{html.escape(OG_DESC)}\">\n"
        f"<meta name=\"twitter:image\" content=\"{SITE}og-image.png\">\n"
        "<link rel=\"icon\" href=\"favicon.svg\" type=\"image/svg+xml\">\n"
        + extra_style + "</head>\n<body>\n"
    )


INDEX_STYLE = ("<style>:root{color-scheme:light}body{margin:0;font:14px \"Helvetica Neue\","
               "Helvetica,Arial,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>\n")

# --- sample-brief styling (same tokens as the dashboard) ----------------------

BRIEF_CSS = """<style>
:root{--bg:#eef0f4;--surface:#ffffff;--surface-2:#f7f8fb;--ink:#0b1020;--ink-2:#565d70;
  --ink-3:#8a90a2;--line:#e4e7ee;--accent:#4f46e5;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#080a10;--surface:#121724;
  --surface-2:#0e131e;--ink:#eceef4;--ink-2:#a3abbd;--ink-3:#6e7689;--line:#232a3b;--accent:#818cf8;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#080a10;--surface:#121724;--surface-2:#0e131e;--ink:#eceef4;
  --ink-2:#a3abbd;--ink-3:#6e7689;--line:#232a3b;--accent:#818cf8;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);line-height:1.5;margin:0;
  font-family:"Helvetica Neue",Helvetica,Arial,"Liberation Sans",sans-serif;-webkit-font-smoothing:antialiased}
.brief{max-width:820px;margin:0 auto;padding-block:28px 48px;
  padding-left:max(20px,env(safe-area-inset-left,0px));padding-right:max(20px,env(safe-area-inset-right,0px))}
h1{font-size:26px;letter-spacing:-.02em;margin:0 0 4px}
h2{font-size:17px;margin:28px 0 10px;letter-spacing:-.01em}
h3{font-size:14px;margin:18px 0 8px}
p{margin:10px 0;max-width:72ch}
em{color:var(--ink-2);font-style:normal}
b{font-weight:700}
blockquote{margin:14px 0;padding:10px 14px;border-left:3px solid var(--accent);
  background:var(--surface-2);color:var(--ink-2);border-radius:0 8px 8px 0}
blockquote p{margin:0;max-width:none}
ul{margin:10px 0;padding-left:20px}
li{margin:6px 0}
.synthnote{font-size:12px;color:var(--ink-2);border-left:3px solid var(--accent);
  padding:4px 0 4px 10px;margin:0 0 22px;max-width:72ch}
.tablewrap{overflow-x:auto;margin:12px 0}
table{width:100%;border-collapse:collapse;font-size:13.5px;background:var(--surface);
  border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:right;padding:8px 11px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-3);font-weight:700}
tbody tr:last-child td{border-bottom:none}
.page-foot{margin-top:32px;padding-top:16px;border-top:1px solid var(--line);
  font-size:12px;color:var(--ink-3);display:flex;flex-wrap:wrap;gap:6px 18px}
.page-foot a{color:var(--ink-2);text-decoration:underline}
</style>
"""


def _tidy(text: str) -> str:
    """Presentation-only copy clean-up: gloss moments, drop dash punctuation and emoji."""
    for src, dst in MOMENT_GLOSS.items():
        text = text.replace(src, dst)
    text = text.replace("Human–AI", "Human vs AI")
    text = re.sub(r"\s[—–]\s", ", ", text)
    text = text.replace("⚠️", "").replace("⚠", "")
    return re.sub(r"  +", " ", text).strip()


def _inline(text: str) -> str:
    t = html.escape(_tidy(text), quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", t)
    return t


def render_markdown(md: str) -> str:
    """A small Markdown subset renderer: headings, blockquote, lists, tables, bold/italic."""
    lines = md.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            header = [c.strip() for c in s.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append('<div class="tablewrap"><table><thead><tr>'
                       + "".join(f"<th>{_inline(h)}</th>" for h in header)
                       + "</tr></thead><tbody>")
            out += ["<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows]
            out.append("</tbody></table></div>")
            continue
        if s.startswith("#"):
            m = re.match(r"^(#+)\s*(.*)$", s)
            lvl = min(len(m.group(1)), 3)
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if s.startswith(">"):
            out.append(f"<blockquote><p>{_inline(s[1:].strip())}</p></blockquote>")
            i += 1
            continue
        if s.startswith(("- ", "* ")):
            items = []
            while i < n and lines[i].strip().startswith(("- ", "* ")):
                items.append(lines[i].strip()[2:])
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(it)}</li>" for it in items) + "</ul>")
            continue
        out.append(f"<p>{_inline(s)}</p>")
        i += 1
    return "\n".join(out)


def build_dashboard(template: str) -> None:
    data = json.loads(INSIGHTS.read_text(encoding="utf-8"))
    payload = json.dumps(data, ensure_ascii=False).replace("</script", "<\\/script")
    rendered = template.replace("__INSIGHTS_JSON__", payload)
    head = page_head("Mediekjøp Signal", SITE, extra_style=INDEX_STYLE)
    STANDALONE.parent.mkdir(parents=True, exist_ok=True)
    STANDALONE.write_text(head + rendered + "\n</body>\n</html>\n", encoding="utf-8")
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {STANDALONE.relative_to(ROOT)} ({STANDALONE.stat().st_size // 1024} KB)")
    print(f"Wrote {ARTIFACT.relative_to(ROOT)} (artifact fragment)")


def build_sample_brief() -> None:
    body = render_markdown(SAMPLE_MD.read_text(encoding="utf-8"))
    head = page_head("Sample weekly brief · Mediekjøp Signal", SITE + "sample-brief.html",
                     extra_style=BRIEF_CSS)
    foot = (
        '<div class="page-foot">'
        '<span>Recommend-only · evidence over opinion</span>'
        + ATTRIBUTION
        + '<span><a href="index.html">Back to the dashboard</a></span>'
        '</div>\n'
    )
    theme = ('<script>try{var t=localStorage.getItem("mk-theme");'
             'if(t)document.documentElement.setAttribute("data-theme",t);}catch(e){}</script>\n')
    page = (head + '<main class="brief">\n' + SYNTHNOTE + "<article>\n" + body
            + "\n</article>\n" + foot + "</main>\n" + theme + "</body>\n</html>\n")
    SAMPLE_HTML.write_text(page, encoding="utf-8")
    print(f"Wrote {SAMPLE_HTML.relative_to(ROOT)} ({SAMPLE_HTML.stat().st_size // 1024} KB)")


def main() -> None:
    if not INSIGHTS.exists():
        raise SystemExit("Missing out/insights.json — run scripts/demo_insights.py first.")
    build_dashboard(TEMPLATE.read_text(encoding="utf-8"))
    build_sample_brief()


if __name__ == "__main__":
    main()
