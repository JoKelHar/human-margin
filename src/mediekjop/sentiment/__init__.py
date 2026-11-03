# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Norwegian-aware comment sentiment and AI-callout detection [Phase 5].

Classifies comments in bokmål, nynorsk, dialect and English, and detects
AI-callout language (KI, KI-generert, laget med AI, ...) from an editable term
list in config. Commenter identities are hashed before storage (GDPR).
"""
