# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Fetch a public ad-volume snapshot from the Meta Ad Library API (official only).

This is the day-one public-context puller. It uses the Meta Ad Library Graph API
``ads_archive`` endpoint, within Meta's terms, with NO scraping. It writes a
dated, versioned ``data/snapshots/<industry>.yaml`` carrying the sample size, a
run-length longevity proxy, and the source/terms - never any performance data.

ADVERTISER (PAGE-ID) SWEEP, not keyword search: a keyword search misses most
Norwegian nightlife ads (venues rarely put the search terms in the ad text, and
EU commercial-ad coverage is partial). So this puller takes a list of advertiser
**page IDs** and samples each page's live ads, capped at ``--per-page`` (default
4) per advertiser - the same max-per-advertiser rule as the manual sweep. Pages
that return no live ads are reported (a 0-live-ad log, which is signal, not an
error). Build the page-ID list once from the advertisers you care about; it also
makes the venue / 0-ad method log fall out automatically.

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
            --market "Norwegian nightlife" \\
            --pages 1112223334,9998887776 --per-page 4
        # or: --pages-file data/snapshots/uteliv_pages.txt  (one page ID per line)

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


def fetch_page(token: str, page_id: str, country: str, cap: int) -> list[dict]:
    """Live ads for one advertiser page, capped at `cap` (max per advertiser)."""
    params = {
        "access_token": token, "ad_type": "ALL", "ad_reached_countries": f"['{country}']",
        "search_page_ids": f"[{page_id}]", "ad_active_status": "ACTIVE",
        "fields": "id,page_id,page_name,ad_delivery_start_time,ad_delivery_stop_time,"
                  "ad_creative_bodies,publisher_platforms",
        "limit": str(min(cap, 100)),
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    got: list[dict] = []
    while url and len(got) < cap:
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 (official API host)
            import json
            payload = json.load(resp)
        if "error" in payload:
            raise SystemExit(f"Ad Library API error (page {page_id}): {payload['error'].get('message')}")
        got.extend(payload.get("data", []))
        url = (payload.get("paging") or {}).get("next")
    return got[:cap]


def _page_ids(args) -> list[str]:
    ids: list[str] = []
    if args.pages_file:
        ids += [ln.strip() for ln in Path(args.pages_file).read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    if args.pages:
        ids += [p.strip() for p in args.pages.split(",") if p.strip()]
    # de-duplicate, preserve order
    seen: set[str] = set()
    return [p for p in ids if not (p in seen or seen.add(p))]


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch a Meta Ad Library snapshot (official API).")
    ap.add_argument("--industry", required=True, help="planner industry key (e.g. uteliv)")
    ap.add_argument("--market", required=True, help="human label, e.g. 'Norwegian nightlife'")
    ap.add_argument("--pages", default=None, help="comma-separated advertiser page IDs")
    ap.add_argument("--pages-file", default=None, help="file with one advertiser page ID per line")
    ap.add_argument("--per-page", type=int, default=4, help="max ads sampled per advertiser (cap)")
    ap.add_argument("--country", default="NO")
    args = ap.parse_args()

    token = os.environ.get("META_AD_LIBRARY_TOKEN")
    if not token:
        print("META_AD_LIBRARY_TOKEN is not set.\n\n"
              "This puller needs an identity-verified Meta Ad Library API token (see the module\n"
              "docstring). Without it, no snapshot can be fetched. Per the project's compliance\n"
              "stance, we do not scrape or work around this - set the token or leave the snapshot\n"
              "in its 'awaiting_fetch' state.", file=sys.stderr)
        raise SystemExit(2)

    pages = _page_ids(args)
    if not pages:
        print("No advertiser page IDs given. Pass --pages or --pages-file (keyword search is\n"
              "not used: it misses most Norwegian nightlife ads).", file=sys.stderr)
        raise SystemExit(2)

    ads: list[dict] = []
    empty_pages: list[str] = []
    for pid in pages:
        page_ads = fetch_page(token, pid, args.country, args.per_page)
        if page_ads:
            ads.extend(page_ads)
        else:
            empty_pages.append(pid)
    today = dt.date.today()
    runs = [d for d in (_run_days(a.get("ad_delivery_start_time"),
                                  a.get("ad_delivery_stop_time"), today) for a in ads) if d is not None]
    median_run = float(statistics.median(runs)) if runs else None

    # Write creative snippets for a manual/semi-automatic content-type + ai_read pass.
    review = ROOT / "data" / "snapshots" / f"{args.industry}_review.csv"
    review.parent.mkdir(parents=True, exist_ok=True)
    with review.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ad_id", "page_id", "advertiser", "start", "stop", "platforms",
                    "creative_body", "content_type (fill in)", "ai_read (fill in)"])
        for a in ads:
            body = " ".join(a.get("ad_creative_bodies") or [])[:300].replace("\n", " ")
            w.writerow([a.get("id"), a.get("page_id"), a.get("page_name"),
                        a.get("ad_delivery_start_time"), a.get("ad_delivery_stop_time"),
                        ",".join(a.get("publisher_platforms") or []), body, "", ""])

    snap = {
        "industry": args.industry, "market": args.market, "as_of": today.isoformat(),
        "n": len(ads), "status": "sampled" if ads else "awaiting_fetch",
        "provenance": "public_snapshot",
        "source": f"Meta Ad Library API (ads_archive, ad_type=ALL, country={args.country}); "
                  f"advertiser page-ID sweep of {len(pages)} pages, max {args.per_page}/page; "
                  "official API, within terms, no scraping.",
        "method": f"API sample, {len(pages)} advertiser page IDs, cap {args.per_page}/page.",
        "median_run_days": median_run, "all_active": True,   # queried ACTIVE only
        "content_type_share": {},   # fill from the manual review CSV, then re-save
        "ai_read_share": {},        # fill from the manual review CSV, then re-save
    }
    out = ROOT / "data" / "snapshots" / f"{args.industry}.yaml"
    out.write_text(yaml.safe_dump(snap, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Wrote {out} (N={len(ads)} from {len(pages)} pages, median run {median_run} days).")
    if empty_pages:
        print(f"0-live-ad pages ({len(empty_pages)}): {', '.join(empty_pages)} "
              "(signal, not an error - record in the method log).")
    print(f"Now tag content_type and ai_read in {review} and copy the shares into the snapshot.")


if __name__ == "__main__":
    main()
