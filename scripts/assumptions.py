# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Assumptions register: list every assumption in use, and what real data replaces it.

The tidy-up checklist. Covers the benchmark library, the industry price bands, the
market-similarity config and the synthetic demo data. Nothing here is real-world
measured data; each line says what would replace it.

    uv run python scripts/assumptions.py
"""

from __future__ import annotations

from mediekjop.planner.benchmarks import load_benchmarks, load_weights, provenance
from mediekjop.planner.formats import (
    drafted_cost_slots,
    load_formats,
    unfilled_cost_slots,
)
from mediekjop.planner.schema import load_industries
from mediekjop.planner.snapshot import load_snapshots


def _line(where: str, key: str, value: str, replace_with: str) -> None:
    print(f"  - {key}")
    print(f"      file:    {where}")
    print(f"      value:   {value}")
    print(f"      replace: {replace_with}")


def main() -> None:
    print("ASSUMPTIONS REGISTER - what still needs real-world data\n")

    print("## Benchmark library  (data/benchmarks/benchmarks.yaml)")
    rows = load_benchmarks()
    for e in rows:
        if provenance(e) == "assumption":
            _line("data/benchmarks/benchmarks.yaml",
                  f"{e['metric']}/{e['industry']}/{e['channel']} (assumption)",
                  f"{e['value']} {e['unit']}",
                  "a sourced NO/Nordic figure, or pooled linked-account data")
    print("  - perf_multiplier (response, memory_brand)")
    print("      file:    data/benchmarks/benchmarks.yaml")
    print("      value:   response ~1.0 (parity), memory ~1.18 (human); cited but global/native-ads")
    print("      replace: pooled Norwegian human-vs-AI response and brand-lift data")

    print("\n## Industry price bands  (config/planner/industries.yaml)")
    cfg = load_industries()
    for row in cfg["industries"]:
        if row.get("bands_tier") == "assumption":
            _line("config/planner/industries.yaml",
                  f"price band / {row['key']} (assumption)",
                  f"low_max {row['low_max']} / high_min {row['high_min']} NOK",
                  "real per-industry Norwegian price distributions (sourced or pooled)")

    print("\n## Expert-estimate slots to fill  (named, dated; never invented)")
    slots = [r for r in cfg["industries"]
             if r.get("bands_tier") == "expert_estimate" and not r.get("bands_filled")]
    for row in slots:
        _line("config/planner/industries.yaml",
              f"price band / {row['key']} (expert_estimate, unfilled)",
              f"low_max {row['low_max']} / high_min {row['high_min']} NOK  [bands_expert: '']",
              "set bands_expert to '<name>, <YYYY-MM>', adjust thresholds, bands_filled: true")
    for e in rows:
        if provenance(e) == "expert_estimate":
            _line("data/benchmarks/benchmarks.yaml",
                  f"{e['metric']}/{e['industry']}/{e['channel']} (expert_estimate)",
                  f"{e['value']} {e['unit']} - {e.get('source_name', '')}",
                  "confirm or adjust; replace with a public figure or pooled data when available")
    if not slots:
        print("  (none unfilled in industries.yaml)")

    print("\n## Content-format priors  (config/planner/formats.yaml)")
    for key, f in load_formats().items():
        if f.priors_tier == "assumption":
            _line("config/planner/formats.yaml",
                  f"format priors / {key} (assumption)",
                  f"ctr_mult {f.ctr_mult.point} / cvr_mult {f.cvr_mult.point}",
                  "a sourced or pooled per-format response figure for Norway")

    print("\n## Production-cost drafts awaiting promotion  (config/planner/formats.yaml)")
    print("  (owner-adjusted bands, still tier assumption; promote to expert_estimate when settled)")
    drafts = drafted_cost_slots()
    for c in drafts:
        _line("config/planner/formats.yaml",
              f"production cost / {c.fmt} x {c.approach} (assumption, draft — pending promotion)",
              f"{c.nok.low:.0f}-{c.nok.point:.0f}-{c.nok.high:.0f} NOK  [source: '{c.source}']",
              "promote when settled: set tier: expert_estimate, filled: true, "
              "source: '<name>, <YYYY-MM>'")
    if not drafts:
        print("  (no drafts pending in formats.yaml)")

    print("\n## Production-cost expert slots still empty  (config/planner/formats.yaml)")
    slots = unfilled_cost_slots()
    for c in slots:
        _line("config/planner/formats.yaml",
              f"production cost / {c.fmt} x {c.approach} (expert_estimate, unfilled)",
              f"{c.nok.low:.0f}-{c.nok.point:.0f}-{c.nok.high:.0f} NOK  [source: '']",
              "set a realistic commercial band from experience and add source: '<name>, <YYYY-MM>'")
    if not slots:
        print("  (none empty in formats.yaml)")

    print("\n## Market-similarity config  (config/planner/weights.yaml)")
    w = load_weights()
    gw = {k: v.get("weight") for k, v in (w.get("geography_weight") or {}).items()}
    _line("config/planner/weights.yaml", "geography_weight", str(gw),
          "calibrate from pooled cross-market account data")
    _line("config/planner/weights.yaml", "price_level_vs_norway",
          str(w.get("price_level_vs_norway")),
          "a sourced purchasing-power-parity table")

    print("\n## Public ad-volume snapshots  (data/snapshots/)")
    print("  (context layer, no performance data; provenance public_snapshot. A manual")
    print("   sample is a hand-coded public-library sweep; ai_read is coder judgement.)")
    snaps = load_snapshots()
    if not snaps:
        print("  (no snapshots populated)")
    for ind, s in sorted(snaps.items()):
        if not s.populated:
            _line(f"data/snapshots/{ind}.yaml", f"{ind} (awaiting_fetch)",
                  "no sample yet (planner says 'No market snapshot yet.')",
                  "fetch via the API or hand-code a manual sample")
            continue
        run = (f"median {s.median_run_days:g} days live so far (lower bound; all active)"
               if s.all_active else f"median run {s.median_run_days} days")
        _line(f"data/snapshots/{ind}.yaml",
              f"{ind} ({s.method}, N={s.n})",
              f"{s.market}, as_of {s.as_of}; {run}; ai_read is coder judgement",
              "a larger / API-pulled sample, and pooled linked-account performance for the "
              "approach-vs-outcome question (the snapshot carries no performance data)")

    print("\n## Synthetic demo data  (src/mediekjop/synthetic/, config/config.yaml)")
    _line("src/mediekjop/synthetic/generator.py",
          "planted multipliers: _BASE_CTR / _SAVE_RATE / _LIKE_RATE, _AI_SUBTYPE_*, _conv_mult",
          "illustrative constants written to ground_truth.json",
          "nothing - the whole synthetic dataset is a demo; replace by ingesting real ad exports")
    _line("src/mediekjop/synthetic/fatigue.py", "BASE_DECAY_K (per-provenance half-lives)",
          "illustrative decay rates", "measured fatigue curves from real account data")
    _line("config/config.yaml", "base_cpm_nok (per channel)",
          "generator priors only", "real CPMs by channel and market")

    print("\nEvery line above is an assumption or illustrative constant, not measured data.")


if __name__ == "__main__":
    main()
