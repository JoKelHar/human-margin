<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright 2026 João Harrison
-->
# Contributing to Human Margin

Thank you for considering a contribution. This project is useful in direct
proportion to how good its benchmarks are, so **benchmark figures with solid
sources are as welcome as code.** Please also read our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Developer Certificate of Origin (DCO)

We use the [Developer Certificate of Origin](https://developercertificate.org/)
instead of a contributor licence agreement. The DCO is a lightweight statement
that you wrote the contribution, or otherwise have the right to submit it under
the project's licences. You certify it by **signing off** every commit:

```bash
git commit -s -m "Your message"
```

That adds a `Signed-off-by: Your Name <your@email>` line to the commit message,
which must match the commit author. By signing off you agree to the DCO for that
contribution. Pull requests whose commits are not signed off will be asked to
amend before merge.

## What licence your contribution is under

This repository is **dual-licensed**, and which licence applies depends on what
you contribute:

- **Code and documentation** → [Apache License 2.0](LICENSE).
- **Benchmark data** (anything under `data/benchmarks/`) → the
  [Creative Commons Attribution 4.0 International](LICENSE-DATA) licence, and it
  must follow the citation policy in [DATA_SOURCES.md](DATA_SOURCES.md).

By contributing you agree your contribution is offered under the licence that
covers that part of the repository.

## Code contributions

1. Open an issue first for anything non-trivial, so we can agree the approach.
2. Fork, branch, and keep changes focused.
3. Add or update tests. The suite must pass:
   ```bash
   uv sync
   uv run pytest -q
   ```
4. Add the SPDX header to any new source file:
   ```python
   # SPDX-License-Identifier: Apache-2.0
   # Copyright 2026 João Harrison
   ```
5. Sign off your commits (`git commit -s`) and open a pull request. Fill in the
   PR checklist.

## Contributing a benchmark figure

Benchmarks live in a **versioned data file** (`data/benchmarks/benchmarks.yaml`)
— never scraped live at runtime, never pulled from paywalled content. Every
figure is an **individual cited value**, not a reproduction of a whole table or
dataset (see [DATA_SOURCES.md](DATA_SOURCES.md) for why this matters legally).

Each entry carries: the metric, the industry, the price band, the channel, the
geography, the value or range, the source name and URL, the publication date,
and a quality grade (A–D). Example:

```yaml
- metric: cvr                      # cpm | ctr | cvr | cpa | roas | agency_fee
  industry: beauty_skincare
  price_band: high                 # low | mid | high
  channel: meta                    # meta | snapchat | tiktok | youtube | any
  geography: NO                    # ISO country, or a region note
  value: { low: 0.018, point: 0.024, high: 0.031 }   # a range, not a false point
  unit: ratio                      # ratio | nok | permille | multiplier
  source_name: "Example Industry Benchmark Report 2025"
  source_url: "https://example.org/report-2025"
  published: 2025-06-01
  quality: B                       # A = primary/measured, D = rough assumption
  notes: "Nordic e-commerce sample; normalise for purchasing power before use."
```

Guidelines:

- **Cite one figure, not a table.** If a report has a table of twenty numbers,
  contribute only the one you are actually using, with a link to the report.
- **Prefer Norwegian, then Nordic, then wider sources** (the engine weights by
  market similarity, but the provenance must be honest).
- **No invented numbers and no invented sources.** If a credible figure does not
  exist, leave it out — the engine already falls back to a clearly labelled
  assumption with a wide range.
- **Flag stale data.** Entries older than 18 months are surfaced by
  `scripts/refresh_benchmarks.py`; update or annotate them.

## Reporting bugs and requesting features

Use the issue templates. For bugs, include your scenario file (with any private
figures redacted), what you expected, and what happened.
