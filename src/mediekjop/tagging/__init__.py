"""Creative tagging [Phase 3].

Resolves provenance, human sub-type and Norwegian-ness using the trust
hierarchy: naming_convention -> csv_override -> platform_label -> c2pa.
Provenance is NEVER inferred from performance. Untagged spend is reported as a
share of total.
"""
