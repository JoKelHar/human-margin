# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Merge tag evidence by trust, then apply the result to creatives.

The trust hierarchy is ``naming_convention -> csv_override -> platform_label ->
c2pa`` (config ``tagging``). Resolution is field-by-field: for each field, the
value is taken from the highest-trust source that has an opinion on it. So a
disciplined ad name can set provenance while a C2PA manifest, lower in the
order, still fills a field the name left blank — rather than the whole creative
taking one source wholesale.

``tag_source`` and ``tag_confidence`` record *which* source decided the
provenance (the headline tag) and how reliable that signal is. A creative no
source has an opinion on stays ``untagged`` — never guessed from performance.
"""

from __future__ import annotations

import pandas as pd

from .evidence import (
    ASSERTABLE_FIELDS,
    DEFAULT_CONFIDENCE,
    TRUST_ORDER,
    ResolvedTag,
    TagEvidence,
)
from .naming import parse_name
from ..schema.enums import TagSource

# Which creative columns the resolver owns, in the `creative` table's own
# naming. Everything else on the row is left untouched (creative_id,
# account_id, raw_name, created_date).
RESOLVED_COLUMNS = list(ResolvedTag().as_creative_columns().keys())


def resolve(evidence: list[TagEvidence]) -> ResolvedTag:
    """Merge evidence into one :class:`ResolvedTag` by the trust hierarchy."""
    by_source = {e.source: e for e in evidence}
    ordered = [by_source[s] for s in TRUST_ORDER if s in by_source]

    out = ResolvedTag()

    # Headline provenance: first source in trust order that has one wins, and it
    # also decides sub_type and stamps tag_source / tag_confidence.
    for ev in ordered:
        if ev.has_provenance():
            out.provenance = ev.provenance
            out.sub_type = ev.sub_type
            out.tag_source = ev.source.value
            out.tag_confidence = ev.confidence
            break

    # Descriptive fields: highest-trust non-None for each, independent of who
    # won provenance (a lower source may still fill a gap).
    for field in ASSERTABLE_FIELDS:
        if field in ("provenance", "sub_type"):
            continue
        for ev in ordered:
            val = getattr(ev, field)
            if val is not None:
                setattr(out, field, val)
                break

    return out


def _evidence_for(creative_id: str, raw_name: str, cfg: dict,
                  overrides: dict | None, platform_labels: dict | None,
                  c2pa: dict | None) -> list[TagEvidence]:
    conf = {**DEFAULT_CONFIDENCE, **(cfg.get("tagging", {}).get("source_confidence", {}) or {})}
    ev: list[TagEvidence] = [
        parse_name(raw_name, cfg, confidence=conf[TagSource.NAMING_CONVENTION])
    ]
    if overrides and creative_id in overrides:
        ev.append(_dict_to_evidence(TagSource.CSV_OVERRIDE, overrides[creative_id],
                                    conf[TagSource.CSV_OVERRIDE]))
    if platform_labels and creative_id in platform_labels:
        ev.append(_dict_to_evidence(TagSource.PLATFORM_LABEL, platform_labels[creative_id],
                                    conf[TagSource.PLATFORM_LABEL]))
    if c2pa and creative_id in c2pa:
        ev.append(_dict_to_evidence(TagSource.C2PA, c2pa[creative_id],
                                    conf[TagSource.C2PA]))
    return ev


def _dict_to_evidence(source: TagSource, payload, default_conf: float) -> TagEvidence:
    """Accept either a bare provenance string or a dict of asserted fields."""
    if isinstance(payload, str):
        payload = {"provenance": payload}
    allowed = {k: v for k, v in payload.items() if k in ASSERTABLE_FIELDS}
    conf = payload.get("confidence", default_conf)
    return TagEvidence(source=source, confidence=conf, **allowed)


def tag_creatives(creatives: pd.DataFrame, cfg: dict, *,
                  overrides: dict | None = None,
                  platform_labels: dict | None = None,
                  c2pa: dict | None = None) -> pd.DataFrame:
    """Return a copy of a ``creative`` frame with resolved tag columns filled.

    ``overrides`` / ``platform_labels`` / ``c2pa`` map ``creative_id`` to either
    a provenance string or a dict of asserted :class:`TagEvidence` fields.
    """
    out = creatives.copy()
    resolved_rows = []
    for row in creatives.itertuples(index=False):
        ev = _evidence_for(row.creative_id, row.raw_name, cfg,
                           overrides, platform_labels, c2pa)
        resolved_rows.append(resolve(ev).as_creative_columns())

    resolved = pd.DataFrame(resolved_rows, index=out.index)
    for col in RESOLVED_COLUMNS:
        out[col] = resolved[col]
    return out
