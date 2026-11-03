# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Creative tagging [Phase 3].

Resolves provenance, human sub-type and Norwegian-ness using the trust
hierarchy: naming_convention -> csv_override -> platform_label -> c2pa.
Provenance is NEVER inferred from performance. Untagged spend is reported as a
share of total.

Public surface:
    parse_name                 — ad name -> naming-convention evidence
    TagEvidence, ResolvedTag   — the evidence/result value objects
    resolve, tag_creatives     — merge evidence; tag a creative frame
    untagged_spend             — untagged-spend report against the threshold
    apply_to_db                — the ingest -> tagging write-back step
"""

from __future__ import annotations

from .evidence import DEFAULT_CONFIDENCE, TRUST_ORDER, ResolvedTag, TagEvidence
from .naming import parse_name
from .report import UntaggedSpendReport, apply_to_db, untagged_spend
from .resolver import RESOLVED_COLUMNS, resolve, tag_creatives

__all__ = [
    "parse_name",
    "TagEvidence",
    "ResolvedTag",
    "resolve",
    "tag_creatives",
    "untagged_spend",
    "UntaggedSpendReport",
    "apply_to_db",
    "RESOLVED_COLUMNS",
    "TRUST_ORDER",
    "DEFAULT_CONFIDENCE",
]
