# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""One tag claim from one source, and the resolved tag that wins the hierarchy.

Every tagging source (the ad-name convention, a buyer-supplied CSV override, a
platform's self-declared AI label, a C2PA content-credential manifest) speaks
the same language: a :class:`TagEvidence`. Each field is optional — a source
asserts only what it knows (``None`` means "no opinion", which is distinct from
``False``). The resolver merges several evidences field-by-field by trust.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from ..schema.enums import Provenance, TagSource

# Highest trust first. Source of truth for the order is config.tagging
# (naming_convention -> csv_override -> platform_label -> c2pa); kept in sync here.
TRUST_ORDER: tuple[TagSource, ...] = (
    TagSource.NAMING_CONVENTION,
    TagSource.CSV_OVERRIDE,
    TagSource.PLATFORM_LABEL,
    TagSource.C2PA,
)

# Default per-source confidence (0..1). Trust order decides *who wins*;
# confidence records *how reliable the winning signal is*.
DEFAULT_CONFIDENCE: dict[TagSource, float] = {
    TagSource.NAMING_CONVENTION: 0.95,
    TagSource.CSV_OVERRIDE: 0.90,
    TagSource.PLATFORM_LABEL: 0.60,  # platforms over- and under-label
    TagSource.C2PA: 0.80,
}

# Fields a source may assert, grouped by what they describe.
_PROVENANCE_FIELDS = ("provenance", "sub_type")
_NORWEGIANNESS_FIELDS = (
    "language", "dialect_present", "dialect_region",
    "norwegian_locations", "norwegian_faces", "norwegian_cultural_refs",
)
_OTHER_FIELDS = ("shows_people",)
ASSERTABLE_FIELDS = _PROVENANCE_FIELDS + _NORWEGIANNESS_FIELDS + _OTHER_FIELDS


@dataclass
class TagEvidence:
    """A single source's claims about one creative. Unset fields are ``None``."""

    source: TagSource
    provenance: str | None = None          # human_led | ai_assisted | ai_generated
    sub_type: str | None = None            # human sub-type, only when human_led
    language: str | None = None
    dialect_present: bool | None = None
    dialect_region: str | None = None
    norwegian_locations: bool | None = None
    norwegian_faces: bool | None = None
    norwegian_cultural_refs: bool | None = None
    shows_people: bool | None = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.provenance is not None and self.provenance not in Provenance.values():
            raise ValueError(f"unknown provenance {self.provenance!r} from {self.source}")
        # sub_type only makes sense for human_led; drop a stray one rather than lie.
        if self.sub_type is not None and self.provenance != Provenance.HUMAN_LED.value:
            self.sub_type = None

    def has_provenance(self) -> bool:
        return self.provenance is not None


@dataclass
class ResolvedTag:
    """The outcome of merging evidence: what goes onto the creative row."""

    provenance: str | None = None
    sub_type: str | None = None
    tag_source: str = TagSource.UNTAGGED.value
    tag_confidence: float = 0.0
    language: str | None = None
    dialect_present: bool | None = None
    dialect_region: str | None = None
    norwegian_locations: bool | None = None
    norwegian_faces: bool | None = None
    norwegian_cultural_refs: bool | None = None
    shows_people: bool | None = None

    @property
    def is_untagged(self) -> bool:
        return self.provenance is None

    def as_creative_columns(self) -> dict:
        """Emit using the ``creative`` table's own column names.

        The only rename is ``sub_type`` -> ``human_sub_type`` (the schema scopes
        the sub-type to human-led creative); every other field name matches.
        """
        out = {f.name: getattr(self, f.name) for f in fields(self)}
        out["human_sub_type"] = out.pop("sub_type")
        return out
