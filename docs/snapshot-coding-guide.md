<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright 2026 João Harrison
-->
# Market-snapshot coding guide (manual sample)

A **snapshot** is a dated, aggregate count of *public ad volume* for a planner
industry in Norway. It carries **no performance data** — only how many ads were
sampled, what content types they are, and how long they have been running. It is
shown in the planner as context (a position), never as advice, and always with
its sample size.

There are two ways to build one:

1. **API** — `scripts/fetch_ad_library.py`, which needs an identity-verified Meta
   Ad Library API token. Preferred when a token is available.
2. **Manual sample** (this guide) — tag 30–50 ads per industry by hand from the
   **public** [Meta Ad Library website](https://www.facebook.com/ads/library/)
   into a CSV. No token, no API, no scraping: you are reading the same public
   transparency product a person would, and recording an aggregate count.

The snapshot is **maintainer-built**: you fetch or code it, commit it as a dated
versioned file under `data/snapshots/`, and users get it bundled. Trying the
planner never requires any of this — with no snapshot it just says
"No market snapshot yet."

## How to sample

1. Open the [Ad Library](https://www.facebook.com/ads/library/), set **Country =
   Norway** and **Ad category = All ads**, and search terms for the industry
   (e.g. nightlife: `nattklubb`, `utested`, `bar oslo`).
2. Take ads **in the order they appear** (don't cherry-pick) until you have
   30–50 for that industry. A consistent, unbiased sweep matters more than size.
3. For each ad, fill one row of the CSV (template:
   [`data/snapshots/manual_sample_template.csv`](../data/snapshots/manual_sample_template.csv)).

## Columns

| Column | What to record |
|--------|----------------|
| `ad_url` | The ad's permalink in the Ad Library (the `?id=…` URL). |
| `advertiser` | *(optional)* The advertiser / page name, for the next round's page-ID sweep. Leave blank if not recorded. |
| `industry` | The planner industry **key** from `config/planner/industries.yaml` (e.g. `uteliv`, `fitness_wellness`, `beauty_skincare`, `events_concerts`). One CSV may hold several industries; rows are aggregated per key. |
| `content_type` | The ad's **format** — one of the coding formats below (or `other`). |
| `ai_read` | *(optional)* How artificial the ad **reads** to you: `none` / `some` / `heavy` / `unsure`. A blank is read as `unsure`. |
| `start_date` | The ad's "Started running on" date, `YYYY-MM-DD`. |
| `still_active` | `y` if the library shows it active, else `n`. |
| `coder` | Your initials/name (who coded the row). |
| `date_coded` | The date you coded it, `YYYY-MM-DD`. |

Case is normalised on load, and a `start_date` later than its `date_coded` is
rejected (not clamped). Run length is a **lower bound**: it is computed as
`date_coded − start_date` (days **live so far**), because Norway ads leave the Ad
Library once they stop, so every sampled ad is still running. The snapshot reports
the **median** across the sample as "days live so far", never as a total run length.

## `content_type` — the format (match `config/planner/formats.yaml`)

`content_type` records **format only**. Use exactly these keys so shares line up
with the format priors:

- **`static_image`** — a single still image (photo or graphic), no motion.
- **`short_video`** — any short edited video (Reels/Shorts/in-feed) that is *not*
  primarily a creator talking to camera: b-roll, product motion, montage.
- **`ugc_talking_head`** — a creator/person talking to camera, lo-fi
  "user-generated" style (testimonial, piece-to-camera, unboxing).
- **`studio_shoot`** — visibly polished, produced studio photography or film
  (crew, lighting, set).
- **`other`** — fits none of the above. Kept in the count, never dropped; if
  `other` is large, the format list probably needs a new entry.

`ai_mockup` is a planner format but is **not** a coding option here — you cannot
reliably tell a mock-up from the public library, so artificiality is captured
separately by `ai_read` (below). A row tagged `ai_mockup` is rejected.

When a single ad mixes types, record the **dominant** one (what most of the
creative is). If you genuinely cannot tell, use `other` rather than guessing.

## `ai_read` — perceived artificiality (coder judgement, not provenance)

`ai_read` is **how artificial the ad reads to an experienced coder** — a
perception, *not* a claim about how the ad was actually made (which the library
does not disclose). It is always tagged "coder judgement" and never reported as
"AI-generated".

- **`none`** — reads as a real photo/video.
- **`some`** — real material visibly AI-edited, composited or partly generated.
- **`heavy`** — the scene itself reads as generated.
- **`unsure`** — you cannot call it (counted, never dropped). A blank cell is
  treated as `unsure`.

We code perception, not provenance, because provenance is not knowable from the
public library; what an audience *reads* as artificial is observable and is the
thing the planner's AI-vs-human question is actually about.

## Building the snapshot file

```bash
uv run python scripts/build_snapshot.py path/to/coded_sample.csv \
    --market "Norwegian nightlife" \
    --source "Best-effort sweep …; 35 live ads; max 4 per venue. …"
```

This aggregates per industry and writes a dated, versioned
`data/snapshots/<industry>.yaml` (provenance `public_snapshot`, `method:
manual_sample`, with `n`, `as_of`, format share, `ai_read` share and the
format × ai_read cross-tab). It also prints those three tables, each with N.
`--source` is written **verbatim** to the snapshot's `source` field — put the
method note (below) there. Review the file, then commit it.

## Method log (record this per round)

Alongside the CSV, record how the sweep was done so the sample can be judged:

- **Venues / advertisers searched** — the list of pages swept (and the per-venue
  cap, e.g. max 4 ads per venue).
- **Keywords used** — the search terms, if a keyword sweep was used.
- **Venues with 0 live ads** — pages checked that had no live ads (this is signal,
  not an error: Norwegian nightlife runs light on paid Meta ads).

If any of these were not kept for a round, write **"not recorded"** — do not
back-fill or guess.

### 2026-11 uteliv round (`data/snapshots/uteliv.yaml`)

- Venues searched: ~50 across Norway — **per-venue list not recorded this round**.
- Keywords used: ~25 nightlife terms — **individual terms not recorded**.
- Venues with 0 live ads: **not recorded** (the sweep was exhaustive; 35 live ads
  found in total, max 4 per venue).
- Note: November sweep, julebord-heavy and seasonal; live ads only.

Next round: use the optional `advertiser` column and a fixed page-ID list (see
`scripts/fetch_ad_library.py`) so the venue/0-ad log falls out automatically.
