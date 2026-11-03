<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright 2026 João Harrison
-->
# Data sources and citation policy

The benchmark library (`data/benchmarks/`) is what lets this tool give useful
answers with no ad account connected. Its credibility — and its legal standing —
depends on how its figures are sourced. This document explains the policy.

## What the CC BY 4.0 licence here covers

The benchmark library is licensed under
[Creative Commons Attribution 4.0 International](LICENSE-DATA). That licence
covers **our compilation and structure** — the selection, arrangement,
normalisation and grading of the figures, and the schema around them.

It does **not** grant any rights over the underlying third-party facts, nor over
the original reports, datasets or sources those facts come from. Each figure
points back to its own source; that source keeps whatever rights it has. If you
reuse the library, attribute *this project* for the compilation, and cite the
*original source* for any individual figure you rely on.

## How figures must be cited

Every entry is an **individually cited value** and carries, at minimum:

- the **metric**, **industry**, **price band**, **channel** and **geography** it
  applies to,
- a **value or range** with its **unit**,
- a **source name** and **source URL**,
- a **publication date**, and
- a **quality grade** (A–D).

## Third-party data hygiene (the important part)

- **No whole-table or whole-dataset reproduction.** We store individual figures
  we actually use, each linked to its source — never a copy of a report's full
  table, chart or dataset. In Norway and the wider EEA, databases can carry
  *sui generis* database protection independent of copyright, so reproducing a
  substantial part of someone's dataset is not ours to relicense. Reduce it to
  the specific cited figures, or leave it out.
- **No paywalled content.** Do not copy figures from behind a paywall. Cite only
  what is publicly available, or a public summary of it.
- **No invented figures or sources.** Missing data is shown as missing, with a
  clearly labelled, editable assumption and a wide range. The engine is built to
  do this honestly rather than guess.
- **Facts vs expression.** Individual facts (a single CPM figure) are generally
  not copyrightable, but their original *expression* and *compilation* can be.
  Our policy stays on the safe side of that line by citing discrete figures.

## Quality grades

| Grade | Meaning |
|-------|---------|
| **A** | Primary, measured data for the relevant Norwegian market and segment. |
| **B** | Credible published benchmark, close market/segment (e.g. Nordic proxy). |
| **C** | Wider proxy (EU/UK/global) or older figure, used with adjustment. |
| **D** | Rough, explicitly labelled assumption with a wide editable range. |

## Market-similarity weighting

Price-dependent figures are normalised for purchasing power and currency before
use, and proxies are weighted by similarity to Norway for the given industry and
price band (Norway → Sweden/Denmark/Finland → wider EU/UK → global). The weights
and the reasoning behind them live in `config/planner/weights.yaml`, and every
estimate shows the user which markets it drew on.

## Refreshing and staleness

`scripts/refresh_benchmarks.py` helps refresh the library from public sources and
flags any entry older than **18 months** as stale. It never scrapes paywalled
content.
