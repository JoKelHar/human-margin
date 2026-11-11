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

## Public ad-volume snapshots (day-one context layer)

The planner can show a dated, versioned **snapshot** of public ad volume for a
Norwegian industry (provenance tier `public_snapshot`), taken only through the
**Meta Ad Library API** (`ads_archive`, `ad_type=ALL`, `country=NO`) within its
terms — no scraping. It carries **no performance data**: sample size, content-type
shares (tagged manually/semi-automatically), and a run-length longevity proxy.

Access (verified Nov 2026; confirm against Meta's current docs): the Ad Library
API needs a token from a **personal** account that has completed **identity
verification** (government ID at facebook.com/ID); until approved, every query
returns "Identity verification required". In the EEA (Norway qualifies) commercial
ads are returned with `ad_type=ALL`, with coverage widely reported as incomplete,
so the sample size is always shown. Shipped snapshots are empty placeholders
(`status: awaiting_fetch`, `n: 0`) until fetched with `scripts/fetch_ad_library.py`;
nothing is invented. If a token or the terms block this, the project stops and
says so rather than scraping.

**Maintainer-built and bundled.** A snapshot is produced by the maintainer — fetched
(or hand-coded, below), committed as a dated versioned file under `data/snapshots/`,
and shipped to users bundled. No user ever needs a token or an account to benefit;
with no snapshot present, the planner just says "No market snapshot yet" (see
[docs/principles.md](docs/principles.md), zero-integration first run).

**Manual-sample fallback (no API).** When a token is not available, a snapshot can
be built by tagging 30–50 ads per industry **by hand** from the public Ad Library
website into a CSV (template: `data/snapshots/manual_sample_template.csv`), then
`uv run python scripts/build_snapshot.py <coded.csv> --market "…"`. Provenance is the
same `public_snapshot` tier with `method: manual_sample` and the sample size shown.
Reading the public transparency product and recording an aggregate count is not
scraping. The coding procedure and content-type definitions (matching
`formats.yaml`) are in [docs/snapshot-coding-guide.md](docs/snapshot-coding-guide.md).

## Production costs and content-format priors (Creative Approach Planner)

`config/planner/formats.yaml` holds per-(format × approach) production costs and
per-format response priors, each tiered. No single public source gives Norwegian
commercial creative day rates, so solid anchors are cited and the owner's domains
carry **drafted** provisional bands pending owner review (`scripts/assumptions.py`
lists drafts and empty slots separately):

- **Production-cost anchors (cited):** Norwegian film-industry collective **minimum
  daily rates**, valid 2025-06-01, 7.5h day (focal.ch rate table) — stills
  ~2,301–3,395 NOK, camera operator ~2,726 NOK+ (crew **floors**, not commercial
  market rates); Oslo studio package pricing (firmafotografen.no, nordfotograf.com)
  — product/business stills from ~3,490–4,900 NOK ex VAT; UGC marketplace asking
  prices (Influee) — ~$121/30s in Norway, Nordic premium +15–25% (InfluenceFlow),
  usage rights +30–50%; AI-tool subscriptions (vendor pricing, monthly): Midjourney
  $10/30/60/120, Runway ~$12–76, ElevenLabs $6/22/99.
- **Drafted cost bands (owner to review):** the four commercial human/hybrid
  day-rate cells (static/short-video/studio human-led, short-video AI-assisted)
  carry a drafted band (`tier: assumption`, `filled: false`, `source: "Claude draft,
  2026-11, pending owner review"`): static human-led 6k–12k–25k, short-video
  human-led 15k–30k–60k, short-video AI-assisted 4k–8k–15k, studio human-led
  40k–80k–200k NOK. Provisional starting points, never presented as sourced; the
  owner confirms and promotes them to `expert_estimate`.
- **Content-format priors (C source, low relevance):** static vs video CTR
  ~1.1–1.18% vs ~1.6–1.9% (67k-ad Meta analysis; AdAmigo 2026); UGC vs polished
  +27% CTR / +19% CVR (webtonic), 2.64% vs 1.78% (foundrycro). The often-cited
  "4× UGC CTR" claim could not be traced to a named study and is excluded. These
  conflict across sources and are carried as wide ranges, as multipliers vs a
  static baseline; pooled Norwegian data replaces them.

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
