# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Synthetic Norwegian data generation (Phase 1 acceptance surface)."""

from .generator import GeneratorConfig, SyntheticDataset, generate, write_dataset  # noqa: F401

__all__ = ["GeneratorConfig", "SyntheticDataset", "generate", "write_dataset"]
