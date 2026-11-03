# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Parse the ad-name naming convention into tag evidence.

The buyer encodes provenance and Norwegian-ness in the ad/post name using the
underscore-delimited tokens defined in ``config.tagging.naming_convention``
(e.g. ``Vinterkos_HL-UGC_NO-loc_NO-dia_lang-dia_v3``). This module turns such a
name into a :class:`TagEvidence` — never the other way round, and never using
any performance signal.

Only the tokens the convention defines are read; everything else in the name
(the concept, the ``v3`` version suffix) is ignored. A name that carries *no*
provenance token yields evidence with ``provenance=None`` — the creative is
untagged as far as naming is concerned, which the resolver treats as "no
opinion", not as a guess.
"""

from __future__ import annotations

from .evidence import TagEvidence
from ..schema.enums import TagSource

# config locality-token flag names -> TagEvidence boolean field
_LOCALITY_FIELD = {
    "norwegian_locations": "norwegian_locations",
    "norwegian_faces": "norwegian_faces",
    "norwegian_cultural_refs": "norwegian_cultural_refs",
    "dialect_present": "dialect_present",
}


def parse_name(raw_name: str, cfg: dict, confidence: float = 0.95) -> TagEvidence:
    """Parse ``raw_name`` into naming-convention evidence using ``cfg``.

    When a provenance token is found the creative is taken to *follow the
    convention*, so an absent locality token means the marker is absent
    (``False``), not unknown. When no provenance token is found nothing is
    asserted: all fields stay ``None`` so the resolver can fall back.
    """
    nc = cfg["tagging"]["naming_convention"]
    prov_tokens = nc["provenance_tokens"]
    loc_tokens = nc["locality_tokens"]
    lang_tokens = nc["language_tokens"]

    tokens = [t for t in str(raw_name).split("_") if t]

    provenance = sub_type = None
    for tok in tokens:
        if tok in prov_tokens:
            provenance = prov_tokens[tok]["provenance"]
            sub_type = prov_tokens[tok].get("sub_type")
            break

    if provenance is None:
        # Not in the convention — no opinion at all.
        return TagEvidence(source=TagSource.NAMING_CONVENTION)

    # Follows the convention: locality flags are complete (absent token => False).
    fields: dict[str, object] = {
        "norwegian_locations": False,
        "norwegian_faces": False,
        "norwegian_cultural_refs": False,
        "dialect_present": False,
    }
    language = None
    for tok in tokens:
        if tok in loc_tokens:
            field = _LOCALITY_FIELD.get(loc_tokens[tok])
            if field:
                fields[field] = True
        elif tok in lang_tokens:
            language = lang_tokens[tok]

    return TagEvidence(
        source=TagSource.NAMING_CONVENTION,
        provenance=provenance,
        sub_type=sub_type,
        language=language,
        confidence=confidence,
        **fields,
    )
