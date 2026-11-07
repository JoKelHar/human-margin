<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright 2026 João Harrison
-->
# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the project is pre-1.0, the public interfaces may still change between
minor versions.

## [Unreleased]

Work in progress toward the Creative Approach Planner (AI vs hybrid vs human)
and the AI-exhaustion statistical engine. Not yet released.

## [0.1.0] - 2026-11-03

First tagged release. Covers the data foundation of the agent on synthetic data.

### Added

- **Unified placement-grain schema** defined once as `TableSpec` objects, with
  DuckDB DDL and loader column order derived from it so they cannot drift.
  Dual-currency money (original + NOK-normalised) via a dated FX layer.
- **Synthetic data generator** encoding ground truth (faster AI fatigue,
  cohort sensitivity, placement affinity, engagement-quality contrast,
  Norwegian seasonality, organic posts and AI-callout comments); ground truth
  is written separately and never into the performance tables.
- **CSV ingestion** for Meta, Snapchat, TikTok and YouTube: one declarative
  `MappingSpec` per platform consumed by a generic `CsvMapper`, behind a
  `DataSource` protocol so API connectors can swap in later.
- **Creative tagging** (provenance, human sub-type, Norwegian-ness) via a trust
  hierarchy — naming convention → CSV override → platform label → C2PA —
  merged field by field, with untagged spend reported as a share of total.
  Provenance is never inferred from performance.
- **Demo dashboard** (theme-aware) and a weekly Markdown report,
  both built from the synthetic data.
- Test suite (40 tests) including a round-trip proving the tagger recovers the
  generator's ground-truth tags from ad names alone.

### Licensing and open-source readiness

- Dual licensing: Apache-2.0 for code, CC BY 4.0 for the benchmark library and
  documentation.
- `NOTICE`, `CITATION.cff`, `CONTRIBUTING.md` (DCO), `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, `DATA_SOURCES.md`, `THIRD_PARTY_LICENSES.md`, GitHub issue and
  pull-request templates, and SPDX headers across the source tree.

[Unreleased]: https://github.com/JoKelHar/mediekjop-signal/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/JoKelHar/mediekjop-signal/releases/tag/v0.1.0
