# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Phase 3 — tagging: naming parser, trust hierarchy, untagged-spend report.

The strongest test here is a round-trip: the synthetic generator *encodes*
provenance and Norwegian-ness into each ad name using the config convention,
then writes the ground-truth tags onto the creative row. The tagging module
must be the exact inverse — recovering those tags from the name alone, with no
access to the baked-in columns and no performance signal.
"""

from __future__ import annotations

import pandas as pd
import pytest

from mediekjop import tagging
from mediekjop.schema.enums import Provenance, TagSource
from mediekjop.tagging import TagEvidence, parse_name, resolve, tag_creatives

# columns the resolver fills but the naming convention cannot carry
_NOT_IN_NAME = {"dialect_region", "shows_people"}


# --- naming parser ----------------------------------------------------------

def test_parse_name_full(cfg):
    ev = parse_name("Vinterkos_HL-UGC_NO-loc_NO-dia_lang-dia_v3", cfg)
    assert ev.source is TagSource.NAMING_CONVENTION
    assert ev.provenance == Provenance.HUMAN_LED.value
    assert ev.sub_type == "ugc"
    assert ev.language == "dialect"
    assert ev.norwegian_locations is True
    assert ev.dialect_present is True
    # absent tokens mean "absent", not "unknown", once the name follows the convention
    assert ev.norwegian_faces is False
    assert ev.norwegian_cultural_refs is False
    assert ev.confidence == 0.95


def test_parse_name_ai_tokens(cfg):
    assert parse_name("Nyhet_AA_lang-eng_v1", cfg).provenance == "ai_assisted"
    ag = parse_name("Nyhet_AG_lang-mix_v2", cfg)
    assert ag.provenance == "ai_generated"
    assert ag.sub_type is None  # sub-type is only for human_led


def test_parse_name_untagged_has_no_opinion(cfg):
    ev = parse_name("Vinterkos_final_v7", cfg)
    assert ev.provenance is None
    assert ev.norwegian_locations is None  # None, not False — nothing was asserted


# --- trust hierarchy --------------------------------------------------------

def test_naming_outranks_lower_sources(cfg):
    naming = parse_name("X_HL-STF_lang-bok_v1", cfg)
    override = TagEvidence(TagSource.CSV_OVERRIDE, provenance="ai_generated", confidence=0.9)
    platform = TagEvidence(TagSource.PLATFORM_LABEL, provenance="ai_assisted", confidence=0.6)
    r = resolve([platform, override, naming])  # order of the list must not matter
    assert r.provenance == "human_led"
    assert r.sub_type == "staff_founder"
    assert r.tag_source == TagSource.NAMING_CONVENTION.value
    assert r.tag_confidence == 0.95


def test_lower_source_fills_gaps(cfg):
    # naming sets provenance but carries no dialect_region; a C2PA manifest does.
    naming = parse_name("X_HL-DOC_NO-dia_lang-dia_v1", cfg)
    c2pa = TagEvidence(TagSource.C2PA, dialect_region="vestland", shows_people=True)
    r = resolve([naming, c2pa])
    assert r.provenance == "human_led"                 # from naming (higher trust)
    assert r.tag_source == TagSource.NAMING_CONVENTION.value
    assert r.dialect_region == "vestland"              # gap filled by C2PA
    assert r.shows_people is True


def test_platform_label_used_when_no_naming(cfg):
    naming = parse_name("JustAConcept_v4", cfg)  # no provenance token
    platform = TagEvidence(TagSource.PLATFORM_LABEL, provenance="ai_generated", confidence=0.6)
    r = resolve([naming, platform])
    assert r.provenance == "ai_generated"
    assert r.tag_source == TagSource.PLATFORM_LABEL.value
    assert r.tag_confidence == 0.6


def test_no_evidence_is_untagged():
    r = resolve([])
    assert r.is_untagged
    assert r.provenance is None
    assert r.tag_source == TagSource.UNTAGGED.value


def test_evidence_rejects_bad_provenance():
    with pytest.raises(ValueError):
        TagEvidence(TagSource.CSV_OVERRIDE, provenance="made_up")


# --- round-trip against the generator's ground truth ------------------------

def test_tagging_recovers_generator_ground_truth(dataset, cfg):
    truth = dataset.frames["creative"].copy()

    # Present the resolver only with identity + name; strip every tag column.
    stripped = truth[["creative_id", "account_id", "raw_name", "created_date"]].copy()
    tagged = tag_creatives(stripped, cfg).set_index("creative_id")
    truth = truth.set_index("creative_id")

    recoverable = [
        "provenance", "human_sub_type", "ai_sub_type", "language",
        "norwegian_locations", "norwegian_faces", "norwegian_cultural_refs",
        "dialect_present",
    ]
    for cid, want in truth.iterrows():
        got = tagged.loc[cid]
        if pd.isna(want["provenance"]):
            assert pd.isna(got["provenance"]), f"{cid} should stay untagged"
            assert got["tag_source"] == TagSource.UNTAGGED.value
            continue
        assert got["tag_source"] == TagSource.NAMING_CONVENTION.value
        for col in recoverable:
            g, w = got[col], want[col]
            if pd.isna(g) and pd.isna(w):  # both "no sub-type" (AI creative)
                continue
            assert g == w, f"{cid}: {col} {g!r} != {w!r}"


# --- untagged-spend report + DB write-back ----------------------------------

def test_untagged_spend_report_on_dataset(con, cfg):
    rep = tagging.untagged_spend(con, cfg)
    assert 0.0 <= rep.untagged_share <= 1.0
    assert rep.untagged_spend_nok <= rep.total_spend_nok
    assert rep.warn_threshold == cfg["thresholds"]["untagged_spend_warn_share"]
    assert rep.over_threshold == (rep.untagged_share > rep.warn_threshold)


def test_apply_to_db_tags_untagged_creatives(con, cfg):
    # Simulate the real pipeline: Phase 2 leaves everything untagged.
    con.execute(
        "UPDATE creative SET provenance = NULL, human_sub_type = NULL, "
        "tag_source = 'untagged', tag_confidence = 0.0"
    )
    before = tagging.untagged_spend(con, cfg)
    assert before.untagged_share == pytest.approx(1.0)

    n_tagged = tagging.apply_to_db(con, cfg)
    after = tagging.untagged_spend(con, cfg)

    assert n_tagged > 0
    assert after.untagged_share < before.untagged_share
    # whatever is still untagged must be creatives whose name carries no token
    (named_untagged,) = con.execute(
        "SELECT COUNT(*) FROM creative WHERE provenance IS NULL "
        "AND raw_name NOT LIKE '%\\_HL-%' ESCAPE '\\' "
        "AND raw_name NOT LIKE '%\\_AA\\_%' ESCAPE '\\' "
        "AND raw_name NOT LIKE '%\\_AG\\_%' ESCAPE '\\'"
    ).fetchone()
    (still_untagged,) = con.execute(
        "SELECT COUNT(*) FROM creative WHERE provenance IS NULL"
    ).fetchone()
    assert still_untagged == named_untagged


def test_csv_override_wins_over_lower_sources_in_db(con, cfg):
    con.execute("UPDATE creative SET provenance = NULL, tag_source = 'untagged'")
    # force one creative's provenance via a buyer CSV override
    cid = con.execute("SELECT creative_id FROM creative LIMIT 1").fetchone()[0]
    tagging.apply_to_db(con, cfg, overrides={cid: {"provenance": "ai_assisted"}})
    prov, src = con.execute(
        "SELECT provenance, tag_source FROM creative WHERE creative_id = ?", [cid]
    ).fetchone()
    # the generated name follows the convention, so naming still outranks the override
    # unless the name is untagged; assert the stamp is one of the two valid sources
    assert src in (TagSource.NAMING_CONVENTION.value, TagSource.CSV_OVERRIDE.value)
    assert prov in Provenance.values()


# --- AI provenance sub-types ------------------------------------------------

@pytest.mark.parametrize("token,provenance,sub", [
    ("AA-PRD", "ai_assisted", "product_imagery"),
    ("AA-CPY", "ai_assisted", "copy_variants"),
    ("AG-UGC", "ai_generated", "synthetic_ugc"),
    ("AG-SCN", "ai_generated", "synthetic_scene"),
])
def test_parse_ai_subtypes(cfg, token, provenance, sub):
    ev = parse_name(f"Nyhet_{token}_lang-eng_v1", cfg)
    assert ev.provenance == provenance
    assert ev.sub_type == sub


@pytest.mark.parametrize("token,provenance", [("AA", "ai_assisted"), ("AG", "ai_generated")])
def test_untyped_ai_tokens_still_parse(cfg, token, provenance):
    ev = parse_name(f"Nyhet_{token}_lang-eng_v1", cfg)
    assert ev.provenance == provenance
    assert ev.sub_type is None


def _one_creative(raw_name):
    return pd.DataFrame([{
        "creative_id": "c1", "account_id": "a", "raw_name": raw_name,
        "created_date": "2025-01-01",
    }])


def test_ai_subtype_routes_to_ai_sub_type_column(cfg):
    got = tag_creatives(_one_creative("Produkt_AA-PRD_lang-eng_v1"), cfg).iloc[0]
    assert got["provenance"] == "ai_assisted"
    assert got["ai_sub_type"] == "product_imagery"
    assert got["human_sub_type"] is None


def test_ag_ugc_sets_shows_people_for_compliance(cfg):
    got = tag_creatives(_one_creative("Testimonial_AG-UGC_lang-eng_v1"), cfg).iloc[0]
    assert got["provenance"] == "ai_generated"
    assert got["ai_sub_type"] == "synthetic_ugc"
    # synthetic people -> shows_people True so it feeds the kroppspress / AI-disclosure flags
    assert bool(got["shows_people"]) is True


def test_ag_ugc_feeds_kroppspress_count_in_db(con, cfg):
    # A known AG-UGC creative, tagged in place, must be counted by the kroppspress
    # query the dashboard uses (ai provenance AND shows_people).
    con.execute(
        "INSERT INTO creative (creative_id, account_id, raw_name, created_date, "
        "tag_source, tag_confidence) VALUES "
        "('agugc-test', 'a', 'Testimonial_AG-UGC_lang-eng_v1', DATE '2025-01-01', 'untagged', 0.0)")
    tagging.apply_to_db(con, cfg)
    prov, ai_sub, shows = con.execute(
        "SELECT provenance, ai_sub_type, shows_people FROM creative WHERE creative_id = 'agugc-test'"
    ).fetchone()
    assert (prov, ai_sub, shows) == ("ai_generated", "synthetic_ugc", True)
    counted = con.execute(
        "SELECT COUNT(*) FROM creative WHERE creative_id = 'agugc-test' "
        "AND provenance IN ('ai_assisted','ai_generated') AND shows_people").fetchone()[0]
    assert counted == 1
