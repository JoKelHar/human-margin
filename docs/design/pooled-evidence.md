<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright 2026 João Harrison
-->
# Design: the pooled evidence layer

**Status: design only, no code.** How linked ad accounts and public, time-relevant
data combine into one evidence layer that serves the three jobs in
[principles.md](../principles.md), **without revealing anything about any account**
(name, industry, ads, copy, IDs). Everything here describes and compares; it never
instructs.

The tool is a **sanity checker**. The evidence layer exists so that every answer
can show where it came from and how sure it is, and so that the quality of that
answer rises as more accounts link, without any account's data leaking.

---

## 1. What each job needs, and how it grows with scale

The three jobs degrade gracefully: each works from public data on day one and
sharpens as pooled accounts accumulate.

| Job | Question | Evidence it needs | 0 accounts | 1 | 5 | 20 | 100 |
|-----|----------|-------------------|-----------|---|---|----|-----|
| **Quote check** | Is this agency quote (content type, approach, fee, terms) typical? | Fee ranges, production-cost ranges, content-type norms | Runs on public fee/cost ranges + the agency-questions checklist | Same, plus the user's own quotes | Pooled fee/production ranges start to form | Fee ranges by budget band | Fee ranges by budget band and category |
| **Gut-check** | Is my feel for this industry, and my spend, typical? | CPM/CTR/CVR/ROAS ranges by industry, band, channel, market | Public benchmarks (graded, down-weighted for Norway) | Your own account as the anchor | Pooled "similar accounts" ranges appear (min cell size) | Ranges tighten; Norway-specific cells | Own-data-led with pooled context |
| **Saturation radar** | Where are content types saturating, and where has a different approach started outperforming? | Volume per content type (public) + response per content type (pooled) | Volume from public ad libraries; response = not enough evidence | Volume live; response from your account only (weak) | Response direction from pooled cells | Direction + speed with confidence | Established patterns per industry bucket |

**Takeaway:** quote check and saturation *volume* run on public data from day one;
saturation *response* and the sharper gut-check ranges need pooled accounts.

---

## 2. Saturation has two halves

A single "saturated" label hides the useful signal. Split it:

**Volume / supply — how many advertisers run a content type.** Source: public ad
repositories, classified with our own tagging module (the same human/AI sub-type
convention):
- **Meta Ad Library** (EEA/EU transparency; Norway is EEA).
- **EU DSA ad repositories** (DSA transparency database and platform repositories).
- **TikTok Commercial Content Library** (EU/UK; Norway covered via EEA).
- Snap Ads Gallery (transparency repository; access terms unverified, see §9).

We classify each creative by content type (human UGC, studio, AI mock-up, synthetic
UGC, …) and count advertisers and creatives per industry bucket over time. Report
**volume, direction and speed** (for example, "AI mock-up share in outerwear rose
from ~X% to ~Y% over the last two quarters"), not a binary label.

**Response — is it still working.** Source: **pooled accounts only** (public
libraries carry no performance). Per content type × cell: CTR decay, fatigue onset,
CPA drift, save/share quality. Report direction and speed of change, with N and
confidence. If there aren't enough accounts in a cell, the honest answer is *not
enough evidence*, never a guess.

Saturation is the join of the two: **a lot of supply AND falling response** is the
interesting state, and each half carries its own evidence.

---

## 3. "A different approach started paying off"

Presented strictly as an **observed pattern with its evidence**, never as advice
(per the principle):

> Pattern: in [industry bucket], [content type B] has moved from level with to
> ahead of [content type A] on [metric] over [period]. Evidence: N accounts,
> [market], confidence [low/med/high].

No "switch to B", no "do X". The reader draws the conclusion. "Established" is shown
only above the thresholds in §5.

---

## 4. Evidence model: partial pooling

Every number is the blend of a ladder, weighted so that better, closer, fresher,
larger-sample evidence dominates and **own data takes over as it accumulates**:

```
own account  ->  pooled similar cells  ->  public benchmarks  ->  assumptions
```

Weight of each source = f(**N** (sample size / accounts), **recency** via a
half-life decay, **market similarity** to Norway, **grade**). This is the shrinkage
idea behind partial pooling (a cell with little own data leans on the pool and the
public priors; as its own N grows, it relies on itself). The planner already does a
simpler version of this blend for public benchmarks; the pooled tier slots in above
`public_benchmark` with the `pooled` provenance tag.

---

## 5. The evidence graph

A graph so every answer can show where it came from.

- **Nodes:** content types, formats, channels, industry buckets, price bands,
  markets, periods, and outcomes (fatigue onset, CTR decay, CPA drift, save-rate).
- **Edges:** carry an effect size, uncertainty, N, provenance and last-updated.
- An edge is **"established"** only above thresholds (minimum N, minimum recency,
  confidence floor); below that it is "emerging" or "not enough evidence".

**Storage: DuckDB tables, not a graph DB (I agree with your lean).** The graph is
small, append-only aggregates, queried by filters (industry × band × channel ×
period), which is exactly what columnar SQL does well; it already underpins the
agent; it keeps the project a single local file with no server. A property-graph DB
would add an operational dependency for traversals we don't need (we query cells,
we don't walk long paths). Model it as a few tables: `nodes`, `edges`
(effect, uncertainty, n, provenance, updated_at), and `cell_aggregates`.

---

## 6. Anonymity

**Nothing raw ever leaves an account. Aggregates only.**

- **Minimum cell size:** a pooled figure is used or shown only when a cell has at
  least **5 accounts** (k-anonymity style). Below that: *not enough evidence*.
- **Norway is small.** Where a fine cell could identify an advertiser (for example
  "Oslo nightlife, high band"), **coarsen the bucket** (drop the city, widen the
  band, widen the period) until the 5-account floor is met, or suppress it.
- **Optional noise** (differential-privacy-style) on small or sensitive cells, so a
  single account can't be reverse-engineered from a published aggregate.
- **Opt-in and revocable.** An account pools only on explicit opt-in; revoking
  removes its contribution going forward and from recomputed aggregates.
- No account name, industry label at identifying granularity, creative, copy or ID
  is ever stored in or derivable from the shared layer.

---

## 7. Reflexivity

If users act on the same saturation signal, the tool helps create the next
saturation (everyone shown "AI mock-ups are over-supplied in outerwear" who then
avoids them changes the supply). Handle it **honestly, by describing not steering**:

- Show the signal as an observed state with its date, not a call to act.
- Show **direction and speed**, so a reader sees a trend they might be part of.
- Consider a lightweight note when a signal is widely viewed ("this pattern is
  visible to many accounts"), so no one treats it as private alpha.
- Never personalise into "move before others do" — that is advice, and it
  manufactures the herd the tool claims to observe.

---

## 8. Architecture

**Today:** the tool is local, offline and downloadable. The planner and agent run
on one machine against local files; nothing leaves it.

**Pooling needs a shared aggregate store.** Options:

| Option | What it is | Effect on open-source positioning |
|--------|------------|-----------------------------------|
| **A. Local-only (no pooling)** | Ship as-is; users rely on public + own data | Fully open, fully offline, but no pooled tier (the core virtue) |
| **B. Client-side aggregation + opt-in push to a hosted aggregate store** | The local app computes per-account aggregates and pushes only min-cell-size-safe aggregates to a shared service that returns pooled cells | Code stays open; the hosted aggregate service is the one network dependency (optional, opt-in). Keeps "offline by default" |
| **C. Federated / privacy-preserving aggregation** | Accounts contribute to aggregates without a central party seeing per-account values (secure aggregation) | Strongest privacy story; most engineering; still needs a coordinator |

**Recommendation:** B, with the hosted aggregate store clearly separated from the
open-source local tool, opt-in, and publishing only its aggregation rules. The tool
stays downloadable and offline; pooling is an optional connected feature. Revisit C
if the pool grows.

---

## 9. Compliance (check, do not guess)

Primary sources quoted below; **this is not legal advice** and the splits are
explicit. Short quotes only.

**Meta.**
- Ad Library / transparency data is for public ad-transparency research under
  Meta's own terms; access is gated (e.g. "Authorized Access to Public
  Information" / Research Tools Terms, updated 2025-12-08). Using *public* ad
  creatives for **saturation volume** is plausibly in scope but terms-gated.
- Advertiser performance data is different. Meta policy has limited advertisers'
  use of Meta advertising data to **"aggregate and anonymous"** analysis, and
  Business Tools terms state other advertisers "may not target ads **solely on the
  basis of your Event Data**." The CMA accepted commitments that Meta not use
  advertiser data to compete against those advertisers. Whether a third party
  (us) may pool one advertiser's performance to inform another is **not clearly
  permitted**.
- **Allowed (likely):** read public Ad Library creatives for volume, under Ad
  Library terms. **Unclear:** pooling advertiser performance across accounts.
  **Needs a lawyer:** any use of Meta-derived performance data to benefit other
  advertisers.

**TikTok.**
- Commercial Content API lets the public/researchers search EU/UK ads in the
  Commercial Content Library; access needs an application and review. It carries
  **no engagement, spend or audience data**. A secondary source says commercial
  users may be ineligible.
- **Allowed (likely, with application):** volume/supply classification from the
  EU/UK library (Norway via EEA). **Unclear:** commercial eligibility. **Needs a
  lawyer:** commercial-use eligibility and any performance inference.

**Snap.** Transparency repository (Ads Gallery) exists; **advertiser-data and API
terms were not located in this pass. Needs checking — do not assume.**

**GDPR.**
- Aggregates above the min cell size, with no path to a person or a single
  advertiser, are the design's anchor. Advertiser identity is a business, but ad
  performance can be linked to an identifiable advertiser, so treat the pooled
  pipeline as processing that must be aggregated/anonymised before sharing.
- **Roles need confirmation:** whether we are controller or processor of the
  contributed aggregates, the lawful basis (likely consent via opt-in), and the
  anonymisation standard that takes the data out of GDPR scope. **Needs a lawyer.**

---

## 10. Other public, time-relevant sources

| Source | Signal | Freshness | Licence / terms |
|--------|--------|-----------|-----------------|
| **Meta Ad Library / EU DSA repositories** | Ad volume & content type (classified by us) | Days | Transparency terms; gated API |
| **TikTok Commercial Content Library** | Ad volume (EU/UK) | Days–weeks | Application + review; no performance |
| **Google Trends** | Category/interest demand over time | Daily/weekly | Free, non-commercial-ish terms; relative (not absolute) |
| **SSB (Statistics Norway)** | Retail/consumption, population, regional | Monthly/quarterly | Open data, attribution |
| **Norges Bank** | FX (already used) | Daily | Open data |
| **Our opportunity calendar** | Norwegian seasonal moments | Static/editable | Ours |

Each is a prior or a context layer, never a source of advertiser performance.

---

## 11. Phased build plan (smallest useful step first)

1. **Volume from one public library.** Meta Ad Library ingest for a couple of
   industry buckets, classified with the existing tagging module; show volume +
   direction + speed. No pooling, no performance. Serves saturation-volume and
   quote-check context immediately.
2. **Own-account response.** Let a single linked account compute its own
   per-content-type response (reuse the exhaustion/decay code); the `own_account`
   provenance tier.
3. **Aggregate store (opt-in), min cell size 5.** The `pooled` tier for the cells
   that clear the floor; coarsening and suppression built in from the start.
4. **Partial-pooling blend.** Wire the ladder (own → pooled → public → assumption)
   with N/recency/market/grade weighting into the planner's estimate.
5. **Evidence graph tables + "established" thresholds.** Persist aggregates and
   edges; surface provenance on every answer.
6. **Second and third public sources** (TikTok library, Google Trends/SSB context).
7. **Reflexivity + privacy hardening** (noise on small cells, widely-viewed note).

Each step is shippable and keeps the tool a sanity checker that describes and never
instructs.

---

Sources consulted for §9 (compliance), to be verified against the platforms' own
current terms before relying on them:
[Meta Research Tools Terms](https://transparency.meta.com/researchtools/product-terms-meta-research) ·
[Meta advertising data-use (aggregate/anonymous), via ConductAtlas](https://conductatlas.com/platform/meta-ads/meta-advertising-policies/provision/CA-P-053263/meta-advertising-data-use-limited-to-aggregate-anonymous-basis/) ·
[CMA decision on Meta ad-data commitments](https://assets.publishing.service.gov.uk/media/6543a5b7d36c910012935c7a/Meta_Final_Commitments_Decision_final.pdf) ·
[TikTok Commercial Content API](https://developers.tiktok.com/products/commercial-content-api) ·
[TikTok Research API & Commercial Content Library announcement](https://newsroom.tiktok.com/tiktoks-research-api-and-commercial-content-library?lang=en-GB)
