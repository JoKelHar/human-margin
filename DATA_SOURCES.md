<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright 2026 João Harrison
-->
# Data sources and citation policy

This repository mixes code (Apache-2.0) with a small, versioned set of **data and
benchmarks** (CC BY 4.0; see `LICENSE-DATA`). This file records where figures come
from, how they are cited, and the terms of the public sources the tool is designed
to use. It is the companion to the provenance model in
[docs/principles.md](docs/principles.md) and the pooled-evidence design in
[docs/design/pooled-evidence.md](docs/design/pooled-evidence.md).

## Citation policy for the benchmark library

`data/benchmarks/benchmarks.yaml` holds **individual cited figures, never reproduced
tables.** Each figure carries a provenance tier (see principles.md):

- `public_benchmark` — a cited public figure with `source_name`, `source_url`,
  `published` date, market (`geography`) and a source-quality grade (A–D). Source
  quality is fixed per study; distance from Norway lowers *relevance*, not the grade.
- `expert_estimate` — a **named, dated** estimate used where credible public data is
  thin. It may omit `source_url` but must name the estimator in `source_name` and
  carry a date; it is ranked below public data and above a bare assumption. Unfilled
  slots are listed by `scripts/assumptions.py`.
- `assumption` — a labelled placeholder (quality D, no source), with a deliberately
  wide range, pending real data.

`config/planner/industries.yaml` applies the same tiers per price band
(`bands_tier`, `bands_source`). Run `scripts/assumptions.py` for the full register of
what is still an assumption or an unfilled expert slot.

Where a figure is a proxy (US/global for Norway), that is stated in the entry's
`notes` and reflected in its relevance, never hidden.

## Public sources the tool is designed to use

Used **only through each platform's official transparency product, within its
published terms — no scraping.** These provide **ad volume/supply** (who is running
what kind of creative), classified by our own tagging module. They carry **no
performance data**.

| Source | What we take | Terms / access | Notes |
|--------|--------------|----------------|-------|
| **Meta Ad Library / EU DSA ad repositories** | Ad volume & content type by industry over time | Meta Research Tools / Ad Library terms; gated API | Norway is EEA. Public creatives only; **no advertiser performance.** |
| **TikTok Commercial Content Library (EU/UK)** | Ad volume (EU/UK) | Application + review; carries no engagement/spend/audience data | Norway via EEA. Commercial eligibility to be confirmed. |
| **Snap Ads Gallery** | (potential) ad volume | **Terms not yet located — do not use until checked.** | Flagged open in the design doc §9. |
| **Google Trends** | Category/interest demand over time (relative) | Free; relative, not absolute | Context/prior only. |
| **SSB (Statistics Norway)** | Prices, retail/consumption, population, regions | Open data, attribution | Source for some industry price-band anchors. |
| **Norges Bank** | FX rates | Open data | Already used by the planner's currency layer. |

## Pooled data (designed, off by default)

Pooled "similar accounts" figures are **not** pulled from any platform API. They are
aggregates each account computes locally from its **own exports** and contributes
opt-in, above a minimum-5-accounts floor, carrying no names, IDs, creatives, copy or
personal data. The full model, anonymity rules and the single remaining legal step
are in [docs/design/pooled-evidence.md](docs/design/pooled-evidence.md); the
contributor terms are in [docs/contributing-data.md](docs/contributing-data.md).
Pooling stays off until that legal review is complete.

## Specific anchors cited in this repo

- **Hotel room rate (hotel_travel band):** SSB hotel price-per-room (StatBank table
  12897); The Local (2023) citing SSB — Oslo ~1,232 / Bergen ~1,076 NOK per night
  ex. VAT.
- **New-car average (automotive band):** OFV (Opplysningsrådet for veitrafikken) via
  tek.no (2024) — average new passenger car ~560,000 NOK.
- **Cinema ticket (culture hint only):** FILM&KINO (2021, via Statista) — ~120 NOK;
  one narrow point, used only as a hint in an expert_estimate slot.
- Benchmark-library figures (CPM/CTR/CVR/ROAS, perf multipliers) each carry their own
  `source_url` in `data/benchmarks/benchmarks.yaml`.

**This is not legal advice.** Platform terms change; verify against the platforms'
current terms before relying on any source above.
