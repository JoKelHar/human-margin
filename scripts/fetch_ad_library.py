# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Fetch a public ad-volume snapshot from the Meta Ad Library API (official only).

This is the day-one public-context puller. It uses the Meta Ad Library Graph API
``ads_archive`` endpoint, within Meta's terms, with NO scraping. It writes a
dated, versioned ``data/snapshots/<industry>.yaml`` carrying the sample size, a
run-length longevity proxy, and the source/terms - never any performance data.

ACCESS (verified Nov 2026, confirm against Meta's current docs):
  - Needs a Meta Ad Library API access token from a PERSONAL account that has
    completed identity verification (government ID at facebook.com/ID). Until
    verification is approved, every query returns "Identity verification
    required". Business accounts cannot call this API.
  - In the EU/EEA (Norway qualifies), commercial ads are returned with
    ``ad_type=ALL``; coverage of non-issue commercial ads is reported as
    incomplete, so treat the sample as indicative and always record N.
  - Set the token in the environment; it is never logged or committed:

        export META_AD_LIBRARY_TOKEN=...
        uv run python scripts/fetch_ad_library.py --industry uteliv \\
            --market "Oslo nightlife" --terms "nattklubb,utested,bar oslo" --limit 200

CONTENT-TYPE TAGGING: the Ad Library exposes creative bodies/images, not our
naming-convention tokens, so automatic provenance tagging does not apply. v1
records volume + run length automatically and writes the creative snippets to a
``*_review.csv`` for a manual/semi-automatic content-type pass; the resulting
shares go into the snapshot's ``content_type_share``. Nothing is invented.

If you cannot get a token or the terms block this, stop and say so rather than
working around it (e.g. scraping) - that is the project's compliance stance.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import statistics
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
API = "https://graph.facebook.com/v21.0/ads_archive"


def _run_days(start: str | None, stop: str | None, today: dt.date) -> float | None:
    if not start:
        return None
    try:
        s = dt.date.fromisoformat(start[:10])
    except ValueError:
        return None
    e = today
    if stop:
        try:
            e = dt.date.fromisoformat(stop[:10])
        except ValueError:
            pass
    return max((e - s).days, 0)


def fetch(token: str, terms: str, country: str, limit: int) -> list[dict]:
    params = {
        "access_token": token, "ad_type": "ALL", "ad_reached_countries": f"['{country}']",
        "search_terms": terms, "ad_active_status": "ALL",
        "fields": "id,ad_delivery_start_time,ad_delivery_stop_time,ad_creative_bodies,publisher_platforms",
        "limit": str(min(limit, 100)),
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    got: list[dict] = []
    while url and len(got) < limit:
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 (official API host)
            import json
            payload = json.load(resp)
        if "error" in payload:
            raise SystemExit(f"Ad Library API error: {payload['error'].get('message')}")
        got.extend(payload.get("data", []))
        url = (payload.get("paging") or {}).get("next")
    return got[:limit]


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch a Meta Ad Library snapshot (official API).")
    ap.add_argument("--industry", required=True, help="planner industry key (e.g. uteliv)")
    ap.add_argument("--market", required=True, help="human label, e.g. 'Oslo nightlife'")
    ap.add_argument("--terms", required=True, help="comma-separated search terms")
    ap.add_argument("--country", default="NO")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    token = os.environ.get("META_AD_LIBRARY_TOKEN")
    if not token:
        print("META_AD_LIBRARY_TOKEN is not set.\n\n"
              "This puller needs an identity-verified Meta Ad Library API token (see the module\n"
              "docstring). Without it, no snapshot can be fetched. Per the project's compliance\n"
              "stance, we do not scrape or work around this - set the token or leave the snapshot\n"
              "in its 'awaiting_fetch' state.", file=sys.stderr)
        raise SystemExit(2)

    ads = fetch(token, args.terms, args.country, args.limit)
    today = dt.date.today()
    runs = [d for d in (_run_days(a.get("ad_delivery_start_time"),
                                  a.get("ad_delivery_stop_time"), today) for a in ads) if d is not None]
    median_run = float(statistics.median(runs)) if runs else None

    # Write creative snippets for a manual/semi-automatic content-type pass.
    review = ROOT / "data" / "snapshots" / f"{args.industry}_review.csv"
    review.parent.mkdir(parents=True, exist_ok=True)
    with review.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ad_id", "start", "stop", "platforms", "creative_body", "content_type (fill in)"])
        for a in ads:
            body = " ".join(a.get("ad_creative_bodies") or [])[:300].replace("\n", " ")
            w.writerow([a.get("id"), a.get("ad_delivery_start_time"), a.get("ad_delivery_stop_time"),
                        ",".join(a.get("publisher_platforms") or []), body, ""])

    snap = {
        "industry": args.industry, "market": args.market, "as_of": today.isoformat(),
        "n": len(ads), "status": "sampled" if ads else "awaiting_fetch",
        "provenance": "public_snapshot",
        "source": f"Meta Ad Library API (ads_archive, ad_type=ALL, country={args.country}); "
                  "official API, within terms, no scraping.",
        "method": f"API sample, terms={args.terms!r}, limit={args.limit}.",
        "median_run_days": median_run,
        "content_type_share": {},   # fill from the manual review CSV, then re-save
    }
    out = ROOT / "data" / "snapshots" / f"{args.industry}.yaml"
    out.write_text(yaml.safe_dump(snap, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Wrote {out} (N={len(ads)}, median run {median_run} days).")
    print(f"Now tag content types in {review} and copy the shares into content_type_share.")


if __name__ == "__main__":
    main()
