# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Brief: turn a scenario and Decide's Position into a creative brief and a test
hypothesis, then stop for a human decision.

The LLM (the brief skill) drafts; Python validates (:mod:`brief.checks`) and records; the
human gate (:mod:`brief.approve`) is the only thing that can approve. The agent never
approves its own output. Stance thresholds live in :mod:`brief.config`.
"""

from __future__ import annotations
