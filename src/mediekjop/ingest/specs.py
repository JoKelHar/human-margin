"""Declarative mapping specs, one per platform.

Each spec says how that platform's standard ads export maps into the unified
placement-grain schema. Verified against the documented export column names;
real exports drift, so these are the single place to adjust per account.
"""

from __future__ import annotations

from .base import MappingSpec

# --- Meta (Facebook + Instagram) --------------------------------------------
# Ads Manager export with a Placement + Age breakdown; spend column names the
# currency, e.g. "Amount spent (NOK)".
META_SPEC = MappingSpec(
    platform="meta",
    channel="meta",
    col_campaign="Campaign name",
    col_adset="Ad set name",
    col_ad="Ad name",
    col_date="Day",
    col_placement="Placement",
    col_age="Age",
    col_spend="Amount spent (NOK)",
    currency_const="NOK",
    metric_map={
        "impressions": "Impressions",
        "reach": "Reach",
        "frequency": "Frequency",
        "clicks": "Clicks (all)",
        "link_clicks": "Link clicks",
        "three_sec_views": "3-second video plays",
        "video_completions": "Video plays at 100%",
        "likes": "Post reactions",
        "comments_count": "Comments",
        "shares": "Post shares",
        "saves": "Post saves",
        "conversions": "Purchases",
        "conversion_value": "Purchases conversion value",
    },
    placement_map={
        "facebook feed": ("facebook", "feed"),
        "instagram feed": ("instagram", "feed"),
        "instagram reels": ("instagram", "reels"),
        "instagram stories": ("instagram", "stories"),
        "facebook stories": ("facebook", "stories"),
        "facebook reels": ("facebook", "reels"),
    },
)

# --- Snapchat ---------------------------------------------------------------
# Ads Manager export. Swipes are the click equivalent. Explicit Currency column.
SNAPCHAT_SPEC = MappingSpec(
    platform="snapchat",
    channel="snapchat",
    col_campaign="Campaign",
    col_adset="Ad Squad",
    col_ad="Ad",
    col_date="Day",
    col_placement="Placement",
    col_age="Age",
    col_spend="Spend",
    col_currency="Currency",
    metric_map={
        "impressions": "Impressions",
        "clicks": "Swipes",
        "link_clicks": "Swipes",
        "video_plays": "Video Views",
        "shares": "Shares",
        "saves": "Saves",
    },
    placement_map={
        "snap stories": ("snapchat", "stories"),
        "stories": ("snapchat", "stories"),
        "spotlight": ("snapchat", "spotlight"),
    },
)

# --- TikTok -----------------------------------------------------------------
TIKTOK_SPEC = MappingSpec(
    platform="tiktok",
    channel="tiktok",
    col_campaign="Campaign name",
    col_adset="Ad group name",
    col_ad="Ad name",
    col_date="Date",
    col_placement="Placement",
    col_age="Age",
    col_spend="Cost",
    currency_const="NOK",
    metric_map={
        "impressions": "Impressions",
        "clicks": "Clicks",
        "link_clicks": "Clicks",
        "video_plays": "Video Views",
        "three_sec_views": "2-second video views",
        "likes": "Likes",
        "comments_count": "Comments",
        "shares": "Shares",
        "conversions": "Conversions",
        "conversion_value": "Conversion value",
    },
    placement_map={
        "tiktok feed": ("tiktok", "feed"),
        "for you feed": ("tiktok", "feed"),
        "tiktok": ("tiktok", "feed"),
    },
)

# --- YouTube (via Google Ads) -----------------------------------------------
# Google Ads report with an explicit Currency column (often the account's, e.g.
# EUR) to exercise FX normalisation to NOK.
YOUTUBE_SPEC = MappingSpec(
    platform="youtube",
    channel="youtube",
    col_campaign="Campaign",
    col_adset="Ad group",
    col_ad="Ad group",  # Google reports often have no ad-name column at this grain
    col_date="Day",
    col_placement="Placement",
    col_age="Age",
    col_spend="Cost",
    col_currency="Currency",
    metric_map={
        "impressions": "Impressions",
        "clicks": "Clicks",
        "link_clicks": "Clicks",
        "video_plays": "Views",
        "video_completions": "Video played to 100%",
        "conversions": "Conversions",
        "conversion_value": "Conv. value",
    },
    placement_map={
        "youtube shorts": ("youtube", "shorts"),
        "shorts": ("youtube", "shorts"),
        "youtube in-stream": ("youtube", "in_stream"),
        "in-stream": ("youtube", "in_stream"),
    },
)

SPECS: dict[str, MappingSpec] = {
    "meta": META_SPEC,
    "snapchat": SNAPCHAT_SPEC,
    "tiktok": TIKTOK_SPEC,
    "youtube": YOUTUBE_SPEC,
}
