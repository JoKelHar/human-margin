<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright 2026 João Harrison
-->
# Product principle

**Human Margin is a sanity checker, not a platform that tells people how to run
ads.** It gives a single advertiser more information than they could gather
alone, then leaves the decision to them. **Every output compares and describes;
none instructs.**

This is the test for all copy in the README, the dashboard, the live demo, the
planner and the reports. If a line tells the reader what to do, it is wrong.

## Zero-integration first run

**Trying the tool needs no token, no account, no upload and no network call.** The
planner runs on bundled benchmarks, format priors and example scenarios; it works
fully offline, and with no market snapshot present it simply says "No market
snapshot yet" — no error, no prompt to connect.

Everything beyond the first run is **optional and opt-in**: linking an ad account,
contributing pooled data, and fetching or coding a public ad-volume snapshot. Each
adds evidence when the user chooses it; none is a precondition for getting a useful
position on day one.

## The three jobs it serves

1. **Gut-check** — a freelance marketer checks their feel for an industry, and
   their spend, against what is typical.
2. **Quote check** — a business owner going into an agency meeting checks a quote
   (content type, production approach, fee structure, payment plan) against
   typical practice.
3. **Saturation radar** — someone who wants to be ahead of the curve sees where
   content types (human UGC, studio, AI mock-up, and so on) are saturating across
   industries — volume, direction, speed — and where a different approach has
   started outperforming.

## How every answer is shaped

Four parts, in this order, everywhere:

1. **Your number** — the advertiser's own figure (or the scenario's).
2. **Typical range** — what is normal for that industry, band, channel and market.
3. **Where the range comes from** — its provenance and how many sources or
   accounts, which market, which date.
4. **How sure** — two separate tags, never one blended letter:
   - **Source quality (A–D)** — how good the underlying study or data is. Fixed
     per source; geography does **not** change it.
   - **Relevance (high / med / low)** — how well it fits the Norwegian user, with
     a reason for each step down (geography, industry, sample size, recency).
   - **Confidence** and the width of the range derive from both. A solid study
     from a far market reads as "C source · low relevance (US, 2024)", not "D".

**Position wording only.** The tool says where a number sits, not what to do:

- "within typical range", "above typical", "below typical", "not enough evidence".
- Never "you should", "do X", "shift", "avoid", "increase", "cut".

A pattern the data shows (for example, a different approach starting to pay off)
is presented **as an observed pattern with its evidence** — industries, number of
accounts, period, confidence — never as advice.

## Provenance tags

Every figure carries one of four provenance tiers, shown as a small, plain,
consistent tag (never alarming), with grade and source detail available on
hover or expand:

| Tier | Tag example | Meaning |
|------|-------------|---------|
| `own_account` | **Your data** | The advertiser's own measured figure. |
| `pooled` | **12 similar accounts · med relevance** | Aggregated, anonymised across linked accounts (minimum cell size enforced). |
| `public_benchmark` | **C source · low relevance (US, 2024)** | A cited public figure, with source quality, relevance, market and date. |
| `expert_estimate` | **C source · expert estimate · med relevance (NO, 2026)** | A named, dated estimate from experience where public data is thin. Ranked below public data, above a bare assumption. |
| `assumption` | **Assumption** | A placeholder with no source; needs real data. |
| `public_snapshot` | **120 sampled ads (Nov 2026)** | A dated, aggregate count of public ad volume from an official transparency product (Meta Ad Library), shown as context with its sample size; carries no performance data. |

Own data takes over as it accumulates; public benchmarks, expert estimates and
assumptions are the fallback, with relevance down-weighted the further they are
from Norway and the older they are.

## Legend (one line)

> Your data · pooled similar accounts · public benchmark · expert estimate ·
> assumption. Source quality A–D and relevance to Norway (high/med/low) shown
> separately; wider range = less certain.
