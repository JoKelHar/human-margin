"""CLI: generate a synthetic dataset into a DuckDB file.

Usage:
    uv run python scripts/generate.py --out data/synthetic.duckdb
    uv run python scripts/generate.py --accounts 2 --days 180 --seed 7
"""

from __future__ import annotations

import argparse
import datetime as dt

from mediekjop.config import load_config
from mediekjop.schema import database
from mediekjop.synthetic import GeneratorConfig, generate, write_dataset


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic Norwegian media-buying data.")
    ap.add_argument("--out", default="data/synthetic.duckdb", help="output DuckDB path")
    ap.add_argument("--accounts", type=int, default=1)
    ap.add_argument("--days", type=int, default=150)
    ap.add_argument("--start", default="2025-03-01", help="start date YYYY-MM-DD")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    gc = GeneratorConfig(
        seed=args.seed,
        n_accounts=args.accounts,
        start_date=dt.date.fromisoformat(args.start),
        days=args.days,
    )
    ds = generate(gc, load_config())
    counts = write_dataset(ds, args.out)

    print(f"Wrote {args.out}")
    for table, n in counts.items():
        print(f"  {table:22s} {n:>8,} rows")

    # quick sanity peek
    con = database.connect(args.out)
    try:
        untagged = con.execute(
            "SELECT ROUND(100.0 * SUM(CASE WHEN c.provenance IS NULL THEN a.spend_nok ELSE 0 END)"
            " / SUM(a.spend_nok), 1) FROM ad_performance a JOIN creative c USING (creative_id)"
        ).fetchone()[0]
        total_spend = con.execute("SELECT ROUND(SUM(spend_nok)) FROM ad_performance").fetchone()[0]
        currencies = con.execute(
            "SELECT currency, COUNT(*) FROM ad_performance GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    finally:
        con.close()
    print(f"\nTotal spend: {total_spend:,.0f} NOK (normalised)")
    print(f"Untagged spend share: {untagged}%")
    print(f"Currencies present: {currencies}")


if __name__ == "__main__":
    main()
