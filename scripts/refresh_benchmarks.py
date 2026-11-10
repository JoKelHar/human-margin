# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Flag stale benchmark-library entries (older than 18 months).

A research helper, not a scraper: it never fetches paywalled content and never
rewrites figures. It lists entries due for a refresh so a human can update them
from a public source, following the citation policy in DATA_SOURCES.md.

    uv run python scripts/refresh_benchmarks.py
"""

from __future__ import annotations

import datetime as dt

from mediekjop.planner.benchmarks import STALE_MONTHS, load_benchmarks, stale_entries

def main() -> None:
    rows = load_benchmarks()
    today = dt.date.today()
    stale = stale_entries(rows, today)
    print(f"Benchmark library: {len(rows)} entries, {len(stale)} stale "
          f"(older than {STALE_MONTHS} months as of {today}).")
    for e in sorted(stale, key=lambda x: x["published"]):
        who = f"{e['metric']}/{e['industry']}/{e['channel']}"
        print(f"  [{e['published']}] {who:32} {e['source_name']}")
    if not stale:
        print("  Nothing stale.")
    else:
        print("\nUpdate these from a public source (see DATA_SOURCES.md); never scrape paywalled data.")


if __name__ == "__main__":
    main()
