# Mediekjøp Signal

A **recommend-only** media-buying analysis agent for Norwegian B2C advertisers,
whose distinguishing feature is **AI-exhaustion detection**: spotting where
audiences tire of, distrust, or ignore AI-generated creative. It ingests paid and
organic social data, keeps everything at **placement grain**, and answers two
questions with evidence, never opinion:

1. Where does human-led content earn its higher cost, and where are AI-generated
   iterations winning on efficiency? *(retrospective)*
2. Where are the next opportunities for distinctly human-led content cycles and
   placements? *(forward-looking, flagged before spend)*

The agent **never** changes budgets, bids or ad status, and never launches
experiments on any platform. It recommends; a human acts.

> **Live demo dashboard** → https://jokelhar.github.io/mediekjop-signal/
> A Smartly-style console rendering the human-vs-AI decision matrix, exhaustion
> and opportunity alerts, built on **synthetic** Norwegian data. Prototype view —
> the descriptive aggregates behind it are not yet the full statistical engine.

## Status

| Phase | Scope | State |
|---|---|---|
| **1** | Unified placement-grain schema + synthetic data generator | ✅ complete |
| **2** | CSV mappers (Meta, Snapchat, TikTok, YouTube) behind a `DataSource` interface | ✅ complete |
| **3** | Tagging: provenance, sub-types, Norwegian-ness (trust hierarchy) + untagged-spend reporting | ✅ complete |
| 4 | Exhaustion module, mixed-effects stats, breakdowns | ◻ next |
| 5 | Norwegian sentiment / AI-callout detection | ◻ |
| 6–10 | Decision matrix, opportunity, halo, recommendations, API connectors | ◻ |

Every remaining module exists as a documented stub (`src/mediekjop/*/__init__.py`).

## Scope: Norwegian *consumer*, not Norwegian *locality*

The unit of relevance is the **Norwegian consumer**. A Norwegian buying in
EUR/USD/GBP from a foreign advertiser is in scope. Therefore:

- **Currency is multi-currency**, normalised to **NOK** for reporting via a dated
  FX layer (`fx_rate`). Original transaction currency is preserved.
- **Creative language is not a filter.** English-language ads reaching Norwegian
  consumers are first-class.
- **"Norwegian-ness"** (language, dialect, locations, faces, cultural refs) is a
  **descriptive analytical dimension** — something tested as an explanatory
  variable — never an inclusion filter.

## Quickstart

Requires Python 3.11+. Uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # venv + Phase 1–2 deps
uv run pytest -q        # 28 tests
```

End-to-end on synthetic data (generate → analyse → dashboard → report):

```bash
uv run python scripts/generate.py --out data/synthetic.duckdb --accounts 1 --days 180
uv run python scripts/demo_insights.py          # -> out/insights.json
uv run python scripts/build_dashboard.py        # -> docs/index.html (the live demo)
uv run python scripts/weekly_report.py          # Markdown weekly brief to stdout
```

A rendered example brief lives at [`samples/weekly_report_sample.md`](samples/weekly_report_sample.md).

Ingest real platform exports (the Phase 2 path), using the included samples:

```python
from mediekjop.ingest import SPECS, CsvDataSource, ingest_into_db, const_fx
from mediekjop.schema import database

con = database.connect("data/account.duckdb")
sources = [CsvDataSource(SPECS[p], f"samples/exports/{f}") for p, f in {
    "meta": "meta_ads_export.csv", "snapchat": "snapchat_ads_export.csv",
    "tiktok": "tiktok_ads_export.csv", "youtube": "google_ads_youtube_export.csv",
}.items()]
account = {"account_id": "acc1", "account_name": "Demo", "brand": "demo", "home_currency": "NOK"}
ingest_into_db(con, sources, account, fx_lookup=const_fx({"EUR": 11.5}))
```

## Architecture

```
ingest (DataSource: CSV now, API later) → unified placement-grain schema → DuckDB
   → tagging → exhaustion / sentiment / opportunity / measurement → recommend → report + dashboard
```

- **One schema, defined once** in [`schema/ddl.py`](src/mediekjop/schema/ddl.py) as
  `TableSpec` objects; DuckDB DDL and the loaders' column order are both derived
  from it, so they cannot drift.
- **Ingestion is declarative.** A platform is a `MappingSpec`
  ([`ingest/specs.py`](src/mediekjop/ingest/specs.py)) — column map + placement map —
  consumed by one generic `CsvMapper`. Adding a platform is a spec, not new code.
  The `DataSource` protocol is the seam that lets API connectors (Phase 10) swap in.
- **Recommend-only** is structural: no module can call a platform write API.

### Platform mapping coverage (Phase 2)

| Platform | Export | Click metric | Placements mapped | Currency |
|---|---|---|---|---|
| Meta | Ads Manager (Placement × Age) | Link clicks | FB/IG feed, reels, stories | spend column (NOK) |
| Snapchat | Ads Manager | Swipes | Snap Stories, Spotlight | Currency column |
| TikTok | Ads Manager | Clicks | TikTok feed | constant (NOK) |
| YouTube | Google Ads report | Clicks | Shorts, in-stream | Currency column (e.g. EUR → NOK) |

## The tagging naming convention

Provenance is tagged at source via tokens in the ad/post name (never inferred from
performance). Tokens are underscore-delimited, e.g.:

```
Vinterkos_HL-UGC_NO-loc_NO-dia_lang-dia_v3
```

| Token | Meaning |
|---|---|
| `HL-UGC` `HL-CRE` `HL-STF` `HL-DOC` `HL-STU` | human-led + sub-type (ugc / creator / staff_founder / documentary / studio_polished) |
| `AA` | ai_assisted (human concept, AI in production) |
| `AG` | ai_generated (concept/core visuals by AI) |
| `NO-loc` `NO-face` `NO-cult` `NO-dia` | recognisable Norwegian locations / faces / cultural refs / dialect present |
| `lang-bok` `lang-nyn` `lang-dia` `lang-eng` `lang-mix` | language of the creative |

**Trust hierarchy (Phase 3, implemented).** Several sources may have an opinion
about one creative — the ad name, a buyer-supplied CSV override, a platform's
self-declared AI label, a C2PA content-credential manifest. Each speaks a common
`TagEvidence`, and the resolver merges them **field by field** in trust order
`naming_convention → csv_override → platform_label → c2pa`: the highest-trust
source with an opinion on a field wins it, so a disciplined ad name can set
provenance while a lower source still fills a gap (e.g. `dialect_region`) the
name left blank. `tag_source` and `tag_confidence` record which source decided
the headline provenance. Anything no source speaks to stays **untagged** and is
reported as a **share of total NOK spend** against
`thresholds.untagged_spend_warn_share` — never guessed from performance.

```python
from mediekjop import tagging
# run the ingest -> tagging step in place, then report untagged spend
tagging.apply_to_db(con)                 # naming convention + optional overrides
rep = tagging.untagged_spend(con)
print(rep.untagged_share, rep.over_threshold)
```

The tagging module is the exact inverse of the naming convention the synthetic
generator uses to *encode* provenance into ad names — a round-trip test recovers
the generator's ground-truth tags from the names alone, with no access to the
performance tables.

## Data model (placement grain)

Dimensions: `account`, `campaign`, `placement`, `audience_segment`, `creative`
(carries provenance + Norwegian-ness), `date_dim`, `fx_rate`. Facts:
`ad_performance`, `organic_performance` (both placement grain), `comment` (author
identity stored only as a salted hash — GDPR).

## What the synthetic generator encodes

So later phases have real signal to recover (ground truth is written to
`ground_truth.json`, never into the performance tables):

- Fatigue curves where **AI creative decays faster** at equal frequency, faster
  still in **younger cohorts**; some segments have a *widening* gap over time
  (true exhaustion) vs others a *stable* gap (quality difference).
- **Placement affinity**: UGC/lo-fi wins in Stories/Spotlight/Reels;
  studio-polished wins in Feed/in-stream.
- **Engagement-quality contrast**: AI wins clicks/likes, loses saves/shares.
- Multi-currency campaigns, seasonality around Norwegian calendar moments,
  organic posts, and comments (some carrying AI-callout language).

## Known limitations

- **Ad-library coverage (verified Nov 2026):** TikTok's Commercial Content Library
  covers Norway via the EEA; Meta's full *commercial* ad archive likely does
  **not** (Norway is EEA but not EU) — expect manual export for Meta
  category-saturation. Confirm against each platform's own docs.
- The demo dashboard uses **descriptive aggregates** and simple log-linear decay
  fits, not the Phase-4 hierarchical/Bayesian engine. It is labelled a prototype.
- Halo measurement (Phase 8) cannot use user-level paths (privacy); it relies on
  geo holdouts, sequencing and time-series, reported with uncertainty.
- The saturation index is a **directional estimate** only, shown with its
  estimated classifier accuracy, never as a competitor league table.

## Compliance surfaced in reports

- **Markedsføringsloven**: advertising labelling, especially creator/influencer
  and boosted organic content.
- **Kroppspress-merking**: `ai_assisted`/`ai_generated` creatives showing people
  are flagged for retouch-labelling review (`shows_people` on `creative`).
- **Platform AI-disclosure** (Meta, TikTok).
- **GDPR**: aggregated performance only; commenter identities hashed before
  storage; competitor data limited to what public ad libraries expose.

## Tech

Python 3.11+ · pandas · DuckDB · (statsmodels/PyMC from Phase 4) · pytest · uv.
Config is one file: [`config/config.yaml`](config/config.yaml). Credentials come
only from environment variables — never logged, never committed.
