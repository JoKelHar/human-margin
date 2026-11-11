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
| `industry` | The planner industry **key** from `config/planner/industries.yaml` (e.g. `uteliv`, `fitness_wellness`, `beauty_skincare`, `events_concerts`). One CSV may hold several industries; rows are aggregated per key. |
| `content_type` | One of the format keys below (or `other`). |
| `start_date` | The ad's "Started running on" date, `YYYY-MM-DD`. |
| `still_active` | `y` if the library shows it active, else `n`. |
| `coder` | Your initials/name (who coded the row). |
| `date_coded` | The date you coded it, `YYYY-MM-DD`. |

Run length (the longevity proxy) is computed as `date_coded − start_date` in
days; the snapshot reports the **median** across the sample.

## Content-type definitions (match `config/planner/formats.yaml`)

Use exactly these keys so shares line up with the format priors:

- **`static_image`** — a single still image (photo or graphic), no motion.
- **`short_video`** — any short edited video (Reels/Shorts/in-feed) that is *not*
  primarily a creator talking to camera: b-roll, product motion, montage.
- **`ugc_talking_head`** — a creator/person talking to camera, lo-fi
  "user-generated" style (testimonial, piece-to-camera, unboxing).
- **`studio_shoot`** — visibly polished, produced studio photography or film
  (crew, lighting, set).
- **`ai_mockup`** — obviously AI-generated or AI-composited product/scene imagery.
- **`other`** — fits none of the above. Kept in the count, never dropped; if
  `other` is large, the format list probably needs a new entry.

When a single ad mixes types, record the **dominant** one (what most of the
creative is). If you genuinely cannot tell, use `other` rather than guessing.

## Building the snapshot file

```bash
uv run python scripts/build_snapshot.py path/to/coded_sample.csv \
    --market "Oslo nightlife"
```

This aggregates per industry and writes a dated, versioned
`data/snapshots/<industry>.yaml` (provenance `public_snapshot`, `method:
manual_sample`, with `n` and `as_of`). Review the file, then commit it.
