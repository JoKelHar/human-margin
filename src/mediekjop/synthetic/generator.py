"""Synthetic Norwegian media-buying data generator.

Produces a realistic, fully-tagged dataset at placement grain for developing and
validating every downstream module before real exports exist:

  * NOK plus foreign-currency campaigns (Norwegian consumers buying from abroad),
    with a dated FX layer and NOK-normalised money columns.
  * All provenance types and human sub-types, with a configurable share left
    deliberately untagged so the untagged-spend report has something to flag.
  * Norwegian-ness markers (language, dialect, locations, faces, cultural refs).
  * Fatigue curves: AI creative decays faster at equal frequency, faster still
    in younger cohorts, with some segments set to a *widening* gap over time.
  * Placement affinity: UGC/lo-fi wins in Stories/Spotlight/Reels; studio-polished
    wins in Feed/in-stream.
  * Engagement-quality contrast: AI wins clicks/likes but loses saves/shares.
  * Seasonality around Norwegian calendar moments, and organic posts + comments.

The *intended* effects (e.g. decay half-lives per provenance) are written to
ground_truth.json so later phases can be checked for recovering them. The
performance tables themselves never contain ground-truth labels, so no analysis
can "cheat".
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import load_config
from ..schema import database
from ..schema.enums import (
    AudienceType,
    FunnelStage,
    Language,
    Provenance,
    RefType,
    TagSource,
)
from . import fatigue
from .calendar_effects import demand_multiplier, windows_for_years

# --- fixed modelling constants ----------------------------------------------

# Approximate FX: 1 unit of currency = N NOK (daily random walk added).
_FX_BASE = {"NOK": 1.0, "EUR": 11.7, "USD": 10.8, "GBP": 13.6, "SEK": 1.02, "DKK": 1.57}

_COHORT_SHARE = {
    "age_13_17": 0.07, "age_18_24": 0.12, "age_25_34": 0.19,
    "age_35_44": 0.18, "age_45_54": 0.17, "age_55_plus": 0.27,
}

# Which channels skew to which cohorts (affects how segments are built, and is a
# realistic prior — younger audiences heavier on Snap/TikTok).
_CHANNEL_COHORT_SKEW = {
    "snapchat": ["age_13_17", "age_18_24", "age_25_34"],
    "tiktok": ["age_18_24", "age_25_34", "age_35_44"],
    "meta": ["age_25_34", "age_35_44", "age_45_54", "age_55_plus"],
    "youtube": ["age_18_24", "age_25_34", "age_35_44", "age_45_54"],
}

_AUDIENCE_TYPE_FACTOR = {
    "prospecting": 1.0, "lookalike": 0.5, "retargeting": 0.15, "broad": 1.2,
}

# Base click-through rate by provenance (AI higher early; it decays faster).
_BASE_CTR = {"human_led": 0.0120, "ai_assisted": 0.0135, "ai_generated": 0.0165}

# Base thumb-stop (3s view / impression) for video, by provenance.
_BASE_THUMBSTOP = {"human_led": 0.42, "ai_assisted": 0.40, "ai_generated": 0.38}

# Engagement-quality rates per impression (saves/shares favour human).
_SAVE_RATE = {"human_led": 0.0032, "ai_assisted": 0.0022, "ai_generated": 0.0014}
_SHARE_RATE = {"human_led": 0.0024, "ai_assisted": 0.0017, "ai_generated": 0.0011}
_LIKE_RATE = {"human_led": 0.0090, "ai_assisted": 0.0105, "ai_generated": 0.0125}
_COMMENT_RATE = {"human_led": 0.00070, "ai_assisted": 0.00075, "ai_generated": 0.00095}
# Negative feedback (hides etc.) base rate; scaled up with frequency and for AI.
_HIDE_RATE = {"human_led": 0.00018, "ai_assisted": 0.00028, "ai_generated": 0.00048}

# Human sub-type affinities: multiplier on thumb-stop by placement family.
_SUBTYPE_PLACEMENT_THUMBSTOP = {
    ("ugc", "vertical"): 1.25, ("ugc", "feed"): 0.95,
    ("creator", "vertical"): 1.18, ("creator", "feed"): 1.02,
    ("staff_founder", "vertical"): 1.10, ("staff_founder", "feed"): 1.00,
    ("documentary", "vertical"): 1.05, ("documentary", "feed"): 1.08,
    ("studio_polished", "vertical"): 0.98, ("studio_polished", "feed"): 1.15,
}

# Funnel-stage conversion rates (per link click) and average order value (NOK).
# Tuned so blended ROAS lands in a believable range for Norwegian activewear.
_FUNNEL_CVR = {"awareness": 0.006, "consideration": 0.022, "conversion": 0.055}
_AOV_NOK = 1750.0

_HASH_SALT = "mediekjop-synthetic-v1"  # synthetic only; real ingest uses a secret salt

_COMMENT_POOL_NEUTRAL = [
    "Så fin reklame!", "Hvor kan jeg kjøpe dette?", "Elsker dette produktet",
    "Kjempebra 👏", "Dette må jeg prøve", "Fin musikk i videoen",
    "Looks great", "Where can I buy this?", "Love it",
]
_COMMENT_POOL_CALLOUT = [
    "Dette er jo KI-generert...", "Helt tydelig laget med AI",
    "AI-søppel, ikke ekte", "Er dette KI? Ser fake ut",
    "This is clearly AI-generated", "fake, laga med KI",
]


@dataclass
class GeneratorConfig:
    seed: int = 42
    n_accounts: int = 1
    start_date: dt.date = dt.date(2025, 3, 1)
    days: int = 150
    n_campaigns_per_account: int = 5
    n_creatives_per_account: int = 18
    untagged_share: float = 0.12
    foreign_currency_share: float = 0.25  # share of campaigns billed in a non-NOK currency
    comment_sample_creatives: int = 10


@dataclass
class SyntheticDataset:
    frames: dict[str, pd.DataFrame]
    ground_truth: dict = field(default_factory=dict)

    def row_counts(self) -> dict[str, int]:
        return {name: len(df) for name, df in self.frames.items()}


# --- helpers -----------------------------------------------------------------

def _placement_family(placement_name: str, fmt: str) -> str:
    """Group placements into 'vertical' (stories/reels/spotlight/shorts) vs 'feed'."""
    vertical = {"stories", "reels", "spotlight", "shorts"}
    return "vertical" if placement_name in vertical else "feed"


def _author_hash(raw_author: str) -> str:
    return hashlib.sha256(f"{_HASH_SALT}:{raw_author}".encode()).hexdigest()[:16]


def _build_placements(cfg: dict) -> pd.DataFrame:
    rows = []
    for p in cfg["placements"]:
        channel, publisher, name, fmt = p["channel"], p["publisher"], p["name"], p["format"]
        rows.append({
            "placement_id": f"{channel}:{publisher}:{name}",
            "channel": channel,
            "publisher": publisher,
            "placement_name": name,
            "format": fmt,
            "is_video": fmt == "video",
        })
    return pd.DataFrame(rows)


def _build_date_dim(start: dt.date, days: int) -> pd.DataFrame:
    rows = []
    for i in range(days):
        d = start + dt.timedelta(days=i)
        iso = d.isocalendar()
        rows.append({
            "date": d, "year": d.year, "quarter": (d.month - 1) // 3 + 1,
            "month": d.month, "day": d.day, "iso_year": iso.year,
            "iso_week": iso.week, "weekday": d.isoweekday(),
        })
    return pd.DataFrame(rows)


def _build_fx(start: dt.date, days: int, currencies: list[str], rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    # per-currency slow random walk around the base rate
    state = {c: _FX_BASE.get(c, 1.0) for c in currencies}
    for i in range(days):
        d = start + dt.timedelta(days=i)
        for c in currencies:
            if c == "NOK":
                rows.append({"date": d, "currency": c, "nok_per_unit": 1.0})
                continue
            base = _FX_BASE.get(c, 1.0)
            state[c] += rng.normal(0, base * 0.002)
            state[c] = float(np.clip(state[c], base * 0.9, base * 1.1))
            rows.append({"date": d, "currency": c, "nok_per_unit": round(state[c], 4)})
    return pd.DataFrame(rows)


def _make_creatives(account_id: str, gc: GeneratorConfig, cfg: dict, rng: np.random.Generator):
    """Create the creative pool with provenance + Norwegian-ness + raw names."""
    prov_choices = ["human_led", "human_led", "ai_assisted", "ai_generated"]
    sub_types = cfg["tagging"]["human_sub_types"]
    prov_token = {
        ("human_led", "ugc"): "HL-UGC", ("human_led", "creator"): "HL-CRE",
        ("human_led", "staff_founder"): "HL-STF", ("human_led", "documentary"): "HL-DOC",
        ("human_led", "studio_polished"): "HL-STU",
        ("ai_assisted", None): "AA", ("ai_generated", None): "AG",
    }
    lang_token = {"bokmal": "lang-bok", "nynorsk": "lang-nyn", "dialect": "lang-dia",
                  "english": "lang-eng", "mixed": "lang-mix"}
    concepts = ["Vinterkos", "Fjelltur", "Fredagstaco", "Hyttetur", "Sommerkveld",
                "Bylivet", "Kaffepause", "Treningsrutine", "Familietid", "Nyhet"]

    rows = []
    for n in range(gc.n_creatives_per_account):
        cid = f"{account_id}-cr{n:03d}"
        provenance = rng.choice(prov_choices)
        sub_type = rng.choice(sub_types) if provenance == "human_led" else None
        untagged = rng.random() < gc.untagged_share

        # Norwegian-ness (human content more often carries locality markers)
        human = provenance == "human_led"
        language = rng.choice(
            ["bokmal", "bokmal", "nynorsk", "dialect", "english", "mixed"]
            if human else ["bokmal", "english", "english", "mixed"]
        )
        dialect_present = language == "dialect" or (human and rng.random() < 0.25)
        dialect_region = rng.choice([r["key"] for r in cfg["regions"]]) if dialect_present else None
        no_loc = rng.random() < (0.55 if human else 0.15)
        no_face = rng.random() < (0.50 if human else 0.12)
        no_cult = rng.random() < (0.45 if human else 0.10)
        shows_people = rng.random() < 0.7

        concept = rng.choice(concepts)
        if untagged:
            raw_name = f"{concept}_final_v{n}"
            prov_out = None
            sub_out = None
            tag_source = TagSource.UNTAGGED.value
            tag_conf = 0.0
        else:
            tok = prov_token[(provenance, sub_type if human else None)]
            loc_tokens = []
            if no_loc:
                loc_tokens.append("NO-loc")
            if no_face:
                loc_tokens.append("NO-face")
            if no_cult:
                loc_tokens.append("NO-cult")
            if dialect_present:
                loc_tokens.append("NO-dia")
            parts = [concept, tok] + loc_tokens + [lang_token[language], f"v{n}"]
            raw_name = "_".join(parts)
            prov_out = provenance
            sub_out = sub_type
            tag_source = TagSource.NAMING_CONVENTION.value
            tag_conf = 0.95

        rows.append({
            "creative_id": cid,
            "account_id": account_id,
            "raw_name": raw_name,
            "created_date": gc.start_date,
            "provenance": prov_out,
            "human_sub_type": sub_out,
            "tag_source": tag_source,
            "tag_confidence": tag_conf,
            "language": language,
            "dialect_present": bool(dialect_present),
            "dialect_region": dialect_region,
            "norwegian_locations": bool(no_loc),
            "norwegian_faces": bool(no_face),
            "norwegian_cultural_refs": bool(no_cult),
            "shows_people": bool(shows_people),
            # kept out of the DB table; used internally for metric generation:
            "_true_provenance": provenance,
            "_true_sub_type": sub_type,
        })
    return pd.DataFrame(rows)


def _make_segments(account_id: str, cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    regions = cfg["regions"]
    rows = []
    # a spread of cohort x region x audience_type, all market NO
    picks = [
        ("age_18_24", AudienceType.PROSPECTING), ("age_25_34", AudienceType.PROSPECTING),
        ("age_25_34", AudienceType.RETARGETING), ("age_35_44", AudienceType.PROSPECTING),
        ("age_45_54", AudienceType.PROSPECTING), ("age_55_plus", AudienceType.BROAD),
        ("age_18_24", AudienceType.LOOKALIKE), ("age_35_44", AudienceType.RETARGETING),
    ]
    for i, (cohort, atype) in enumerate(picks):
        region = rng.choice([r["key"] for r in regions], p=_region_probs(regions))
        rows.append({
            "segment_id": f"{account_id}-seg{i:02d}",
            "account_id": account_id,
            "age_cohort": cohort,
            "gender": "all",
            "region": region,
            "audience_type": atype.value,
            "market": "NO",
        })
    return pd.DataFrame(rows)


def _region_probs(regions: list[dict]) -> np.ndarray:
    w = np.array([r["pop_weight"] for r in regions], dtype=float)
    return w / w.sum()


def _segment_audience(cohort: str, region_weight: float, atype: str) -> int:
    base = region_weight * 2_000_000 * _COHORT_SHARE.get(cohort, 0.15)
    base *= _AUDIENCE_TYPE_FACTOR.get(atype, 1.0)
    return int(np.clip(base, 20_000, 600_000))


# --- main generation ---------------------------------------------------------

def generate(gc: GeneratorConfig | None = None, cfg: dict | None = None) -> SyntheticDataset:
    gc = gc or GeneratorConfig()
    cfg = cfg or load_config()
    rng = np.random.default_rng(gc.seed)

    years = sorted({(gc.start_date + dt.timedelta(days=i)).year for i in range(gc.days)})
    windows = windows_for_years(cfg, years)
    currencies = cfg["currency"]["known"]
    base_cpm = cfg["base_cpm_nok"]
    region_weight = {r["key"]: r["pop_weight"] for r in cfg["regions"]}

    placements = _build_placements(cfg)
    date_dim = _build_date_dim(gc.start_date, gc.days)
    fx = _build_fx(gc.start_date, gc.days, currencies, rng)
    fx_lookup = {(r.date, r.currency): r.nok_per_unit for r in fx.itertuples()}

    accounts, campaigns, creatives, segments = [], [], [], []
    ad_rows, organic_rows, comment_rows = [], [], []

    for a in range(gc.n_accounts):
        account_id = f"acc{a:02d}"
        accounts.append({
            "account_id": account_id,
            "account_name": f"Synthetic Brand {a}",
            "brand": f"brand_{a}",
            "home_currency": "NOK",
        })
        cre_df = _make_creatives(account_id, gc, cfg, rng)
        seg_df = _make_segments(account_id, cfg, rng)
        creatives.append(cre_df.drop(columns=["_true_provenance", "_true_sub_type"]))
        segments.append(seg_df)

        # map creative_id -> true provenance/sub_type for metric generation
        true_prov = dict(zip(cre_df.creative_id, cre_df._true_provenance))
        true_sub = dict(zip(cre_df.creative_id, cre_df._true_sub_type))
        creative_ids = list(cre_df.creative_id)
        # group creatives by provenance so every campaign can span all three
        prov_groups: dict[str, list[str]] = defaultdict(list)
        for cid in creative_ids:
            prov_groups[true_prov[cid]].append(cid)

        for c in range(gc.n_campaigns_per_account):
            campaign_id = f"{account_id}-camp{c:02d}"
            funnel = str(rng.choice([FunnelStage.AWARENESS.value,
                                      FunnelStage.CONSIDERATION.value,
                                      FunnelStage.CONVERSION.value]))
            channel = rng.choice(list(_CHANNEL_COHORT_SKEW.keys()))
            flight_offset = int(rng.integers(0, max(1, gc.days - 60)))
            flight_len = int(rng.integers(45, min(75, gc.days - flight_offset) + 1))
            flight_start = gc.start_date + dt.timedelta(days=flight_offset)
            flight_end = flight_start + dt.timedelta(days=flight_len - 1)
            currency = (rng.choice([x for x in currencies if x != "NOK"])
                        if rng.random() < gc.foreign_currency_share else "NOK")
            daily_budget_nok = float(rng.integers(3000, 15000))

            campaigns.append({
                "campaign_id": campaign_id, "account_id": account_id,
                "name": f"{channel}_{funnel}_{c}", "objective": funnel,
                "funnel_stage": funnel, "flight_start": flight_start, "flight_end": flight_end,
            })

            # pick this campaign's placements (channel-appropriate), creatives, segments
            camp_placements = placements[placements.channel == channel]
            if camp_placements.empty:
                camp_placements = placements
            # stratified pick: up to 2 creatives from each provenance group, so a
            # conversion campaign is never missing a provenance (keeps per-group
            # ROAS/conversions meaningful rather than a small-sample accident)
            camp_creatives = []
            for grp in prov_groups.values():
                take = min(2, len(grp))
                camp_creatives += list(rng.choice(grp, size=take, replace=False))
            cohort_pref = _CHANNEL_COHORT_SKEW.get(channel, [])
            seg_pool = seg_df[seg_df.age_cohort.isin(cohort_pref)]
            if len(seg_pool) < 2:
                seg_pool = seg_df
            n_seg = int(rng.integers(2, min(4, len(seg_pool)) + 1))
            camp_segments = seg_pool.sample(n=n_seg, random_state=int(rng.integers(0, 1_000_000)))

            _generate_campaign_rows(
                ad_rows=ad_rows,
                campaign_id=campaign_id, account_id=account_id, funnel=funnel,
                channel=channel, currency=currency, daily_budget_nok=daily_budget_nok,
                flight_start=flight_start, flight_len=flight_len,
                placements=camp_placements, creative_ids=camp_creatives,
                segments=camp_segments, true_prov=true_prov, true_sub=true_sub,
                base_cpm=base_cpm, region_weight=region_weight, windows=windows,
                fx_lookup=fx_lookup, rng=rng,
            )

        # organic posts + comments for this account
        _generate_organic_and_comments(
            organic_rows, comment_rows, account_id, cre_df, placements,
            gc, windows, rng,
        )

    frames = {
        "account": pd.DataFrame(accounts),
        "campaign": pd.DataFrame(campaigns),
        "placement": placements,
        "audience_segment": pd.concat(segments, ignore_index=True),
        "creative": pd.concat(creatives, ignore_index=True),
        "date_dim": date_dim,
        "fx_rate": fx,
        "ad_performance": pd.DataFrame(ad_rows),
        "organic_performance": pd.DataFrame(organic_rows),
        "comment": pd.DataFrame(comment_rows),
    }

    ground_truth = {
        "decay_k_by_provenance": fatigue.BASE_DECAY_K,
        "half_life_by_provenance": {p: fatigue.half_life(k) for p, k in fatigue.BASE_DECAY_K.items()},
        "cohort_ai_sensitivity": fatigue.COHORT_AI_SENSITIVITY,
        "save_rate_by_provenance": _SAVE_RATE,
        "share_rate_by_provenance": _SHARE_RATE,
        "like_rate_by_provenance": _LIKE_RATE,
        "note": (
            "AI creative is built to decay faster (shorter half-life) and to win "
            "likes/clicks while losing saves/shares. Phase 4 must recover these "
            "from the performance tables, which contain no provenance-truth labels."
        ),
    }
    return SyntheticDataset(frames=frames, ground_truth=ground_truth)


def _generate_campaign_rows(
    *, ad_rows, campaign_id, account_id, funnel, channel, currency, daily_budget_nok,
    flight_start, flight_len, placements, creative_ids, segments, true_prov, true_sub,
    base_cpm, region_weight, windows, fx_lookup, rng,
):
    # stable per-cell weights so the daily budget splits deterministically
    cre_w = {cid: rng.uniform(0.6, 1.4) for cid in creative_ids}
    plc_w = {p.placement_id: rng.uniform(0.6, 1.4) for p in placements.itertuples()}
    seg_w = {s.segment_id: rng.uniform(0.6, 1.4) for s in segments.itertuples()}
    total_w = sum(cre_w.values()) * sum(plc_w.values()) * sum(seg_w.values())

    # per (creative, segment) frequency state
    freq_state: dict[tuple[str, str], dict] = {}
    seg_info = {s.segment_id: s for s in segments.itertuples()}

    # some segments get a widening (worsening) exhaustion trend
    widening = {s.segment_id: (rng.random() < 0.4) for s in segments.itertuples()}

    for day_i in range(flight_len):
        day = flight_start + dt.timedelta(days=day_i)
        season = demand_multiplier(day, windows)
        nok_per_unit = fx_lookup.get((day, currency), _FX_BASE.get(currency, 1.0))
        day_frac = day_i / max(flight_len - 1, 1)

        # pass 1: impressions per cell + aggregate per (creative, segment)
        cells = []
        impr_by_cs: dict[tuple[str, str], float] = defaultdict(float)
        for cid in creative_ids:
            for p in placements.itertuples():
                for s in segments.itertuples():
                    cpm_nok = base_cpm.get(channel, 60) * _cpm_place_mult(p.placement_name) * season
                    cpm_nok *= rng.uniform(0.9, 1.1)
                    weight = cre_w[cid] * plc_w[p.placement_id] * seg_w[s.segment_id]
                    cell_budget = daily_budget_nok * season * weight / total_w
                    impressions = max(0.0, cell_budget / cpm_nok * 1000.0)
                    cells.append((cid, p, s, impressions, cpm_nok))
                    impr_by_cs[(cid, s.segment_id)] += impressions

        # update frequency state
        for (cid, seg_id), impr in impr_by_cs.items():
            st = freq_state.get((cid, seg_id))
            if st is None:
                s = seg_info[seg_id]
                aud = _segment_audience(s.age_cohort, region_weight.get(s.region, 0.05), s.audience_type)
                st = {"cum_impr": 0.0, "cum_reach": 1.0, "audience": aud}
                freq_state[(cid, seg_id)] = st
            st["cum_impr"] += impr
            remaining = max(0.0, st["audience"] - st["cum_reach"])
            st["cum_reach"] = min(st["audience"], st["cum_reach"] + remaining * 0.10)

        # pass 2: emit rows
        for cid, p, s, impressions, cpm_nok in cells:
            if impressions < 1:
                continue
            provenance = true_prov[cid]
            sub_type = true_sub[cid]
            st = freq_state[(cid, s.segment_id)]
            frequency = st["cum_impr"] / st["cum_reach"]
            impr = int(round(impressions))
            reach = max(1, int(round(impr / max(frequency, 1.0))))

            k = fatigue.decay_k(provenance, s.age_cohort)
            trend = 0.6 * day_frac if widening[s.segment_id] and provenance != "human_led" else 0.0
            ctr = fatigue.decayed_rate(_BASE_CTR[provenance], k, frequency, trend)
            ctr = float(np.clip(ctr * rng.uniform(0.85, 1.15), 0.0005, 0.08))
            clicks = int(round(impr * ctr))
            link_clicks = int(round(clicks * rng.uniform(0.7, 0.95)))

            fam = _placement_family(p.placement_name, p.format)
            if p.is_video:
                ts_base = _BASE_THUMBSTOP[provenance]
                if provenance == "human_led" and sub_type:
                    ts_base *= _SUBTYPE_PLACEMENT_THUMBSTOP.get((sub_type, fam), 1.0)
                thumbstop = float(np.clip(ts_base * np.exp(-0.5 * k * frequency) * rng.uniform(0.9, 1.1), 0.05, 0.9))
                three_sec = int(round(impr * thumbstop))
                video_plays = three_sec
                completion = float(np.clip(0.28 * (1.1 if fam == "feed" else 0.95), 0.05, 0.8))
                video_completions = int(round(video_plays * completion))
                avg_watch = round(float(np.clip(rng.normal(6.5, 1.5), 1.0, 20.0)), 2)
            else:
                three_sec = video_plays = video_completions = 0
                avg_watch = 0.0

            likes = int(round(impr * _LIKE_RATE[provenance] * rng.uniform(0.8, 1.2)))
            comments = int(round(impr * _COMMENT_RATE[provenance] * rng.uniform(0.7, 1.3)))
            shares = int(round(impr * _SHARE_RATE[provenance] * rng.uniform(0.8, 1.2)))
            saves = int(round(impr * _SAVE_RATE[provenance] * rng.uniform(0.8, 1.2)))
            hide_scale = 1.0 + 0.15 * frequency
            hides = int(round(impr * _HIDE_RATE[provenance] * hide_scale * rng.uniform(0.7, 1.3)))
            not_interested = int(round(hides * rng.uniform(0.4, 0.8)))
            negative_feedback = hides + not_interested
            unfollows = int(round(negative_feedback * rng.uniform(0.0, 0.2)))

            cvr = _FUNNEL_CVR[funnel] * (1.05 if provenance == "human_led" else 1.0)
            conversions = int(round(link_clicks * cvr * rng.uniform(0.7, 1.3)))
            spend_nok = impr / 1000.0 * cpm_nok
            conv_value_nok = conversions * _AOV_NOK * rng.uniform(0.8, 1.2)
            spend = spend_nok / nok_per_unit
            conv_value = conv_value_nok / nok_per_unit

            ad_rows.append({
                "account_id": account_id, "campaign_id": campaign_id,
                "creative_id": cid, "placement_id": p.placement_id,
                "segment_id": s.segment_id, "date": day,
                "impressions": impr, "reach": reach, "frequency": round(frequency, 3),
                "clicks": clicks, "link_clicks": link_clicks,
                "three_sec_views": three_sec, "video_plays": video_plays,
                "video_completions": video_completions, "avg_watch_time_sec": avg_watch,
                "likes": likes, "comments_count": comments, "shares": shares, "saves": saves,
                "hides": hides, "not_interested": not_interested,
                "negative_feedback": negative_feedback, "unfollows": unfollows,
                "conversions": conversions, "currency": currency,
                "spend": round(spend, 2), "conversion_value": round(conv_value, 2),
                "spend_nok": round(spend_nok, 2), "conversion_value_nok": round(conv_value_nok, 2),
            })


def _cpm_place_mult(placement_name: str) -> float:
    return {
        "feed": 1.1, "feed_video": 1.05, "stories": 0.9, "reels": 0.95,
        "spotlight": 0.85, "shorts": 0.8, "in_stream": 1.25,
    }.get(placement_name, 1.0)


def _generate_organic_and_comments(organic_rows, comment_rows, account_id, cre_df,
                                    placements, gc, windows, rng):
    organic_placements = placements[placements.placement_name.isin(
        ["feed", "reels", "stories", "spotlight", "shorts"])]
    n_posts = max(8, gc.n_creatives_per_account // 2)
    post_creatives = cre_df.sample(n=min(n_posts, len(cre_df)),
                                   random_state=gc.seed).reset_index(drop=True)
    for i, cr in post_creatives.iterrows():
        post_id = f"{account_id}-post{i:03d}"
        p = organic_placements.sample(n=1, random_state=int(rng.integers(0, 1_000_000))).iloc[0]
        post_day = gc.start_date + dt.timedelta(days=int(rng.integers(0, gc.days - 7)))
        provenance = cr["_true_provenance"]
        # human-led organic tends to over-index on saves/shares/watch time
        quality = 1.4 if provenance == "human_led" else 0.9
        is_boosted = rng.random() < 0.3
        for d_off in range(7):  # 7-day post life
            day = post_day + dt.timedelta(days=d_off)
            decay = np.exp(-0.5 * d_off)
            impr = int(max(50, rng.normal(9000, 2500) * decay))
            reach = int(impr / rng.uniform(1.05, 1.4))
            organic_rows.append({
                "account_id": account_id, "post_id": post_id, "creative_id": cr["creative_id"],
                "placement_id": p.placement_id, "date": day,
                "impressions": impr, "reach": reach,
                "likes": int(impr * 0.011 * rng.uniform(0.8, 1.2)),
                "comments_count": int(impr * 0.0009 * rng.uniform(0.7, 1.3)),
                "shares": int(impr * 0.002 * quality * rng.uniform(0.8, 1.2)),
                "saves": int(impr * 0.003 * quality * rng.uniform(0.8, 1.2)),
                "video_plays": int(impr * 0.4) if p.is_video else 0,
                "video_completions": int(impr * 0.12) if p.is_video else 0,
                "avg_watch_time_sec": round(float(np.clip(rng.normal(7, 1.5), 1, 20)), 2) if p.is_video else 0.0,
                "is_boosted": bool(is_boosted),
                "boosted_date": (post_day + dt.timedelta(days=2)) if is_boosted else None,
            })

    # comments on a sample of creatives; AI-generated draws more callouts
    sample = cre_df.sample(n=min(gc.comment_sample_creatives, len(cre_df)),
                           random_state=gc.seed + 1)
    cidx = 0
    for _, cr in sample.iterrows():
        provenance = cr["_true_provenance"]
        n_comments = int(rng.integers(3, 9))
        callout_prob = {"human_led": 0.05, "ai_assisted": 0.12, "ai_generated": 0.30}[provenance]
        for _ in range(n_comments):
            is_callout = rng.random() < callout_prob
            pool = _COMMENT_POOL_CALLOUT if is_callout else _COMMENT_POOL_NEUTRAL
            text = str(rng.choice(pool))
            comment_rows.append({
                "comment_id": f"{account_id}-cmt{cidx:04d}",
                "account_id": account_id, "ref_type": RefType.AD.value,
                "ref_id": cr["creative_id"], "channel": "meta",
                "date": gc.start_date + dt.timedelta(days=int(rng.integers(0, gc.days))),
                "author_hash": _author_hash(f"user{int(rng.integers(0, 100000))}"),
                "language": cr["language"] if cr["language"] != "english" else "english",
                "text": text,
            })
            cidx += 1


def write_dataset(dataset: SyntheticDataset, db_path: str | Path,
                  ground_truth_path: str | Path | None = None) -> dict[str, int]:
    """Create the schema in a DuckDB file and load the dataset; write ground truth."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = database.connect(db_path)
    try:
        database.create_schema(con)
        counts = database.load_all(con, dataset.frames)
    finally:
        con.close()
    gt_path = Path(ground_truth_path) if ground_truth_path else db_path.with_name("ground_truth.json")
    gt_path.write_text(json.dumps(dataset.ground_truth, indent=2, default=str), encoding="utf-8")
    return counts
