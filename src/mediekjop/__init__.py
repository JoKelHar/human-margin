# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""mediekjop — Norwegian B2C media-buying analysis agent with AI-exhaustion detection.

Recommend-only. The agent never changes budgets, bids or ad status and never
launches experiments on any platform. Every conclusion is evidence-backed and
carries uncertainty; where data is insufficient it says so rather than guessing.

Module layout (built phase by phase):
    schema/       unified placement-grain data model + DuckDB storage  [Phase 1]
    synthetic/    realistic Norwegian synthetic-data generator         [Phase 1]
    ingest/       CSV/XLSX mappers, later API connectors                [Phase 2/10]
    tagging/      provenance, sub-types, Norwegian-ness resolver        [Phase 3]
    exhaustion/   decay curves, attention, breakdowns                   [Phase 4]
    sentiment/    Norwegian-aware comment / AI-callout detection        [Phase 5]
    opportunity/  cultural calendar, organic early-warning, saturation  [Phase 7]
    measurement/  halo & sequencing, experiment designer                [Phase 6/8]
    recommend/    budget reallocation recommendations                   [Phase 9]
    report/       weekly Markdown report + dashboard                    [Phase 9]
"""

__version__ = "0.1.0"
