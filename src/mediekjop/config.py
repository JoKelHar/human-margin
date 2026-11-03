# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Loader for the single YAML configuration file.

The whole agent reads its configuration from one file (config/config.yaml by
default). Credentials are never read from here — only from environment
variables — so this loader deliberately has no notion of secrets.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Repo root is two parents up from this file: src/mediekjop/config.py -> repo/
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "config.yaml"


def repo_root() -> Path:
    """Absolute path to the repository root."""
    return _REPO_ROOT


def config_path() -> Path:
    """Resolve the config path, honouring the MEDIEKJOP_CONFIG env override."""
    override = os.environ.get("MEDIEKJOP_CONFIG")
    return Path(override).expanduser().resolve() if override else _DEFAULT_CONFIG_PATH


@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> dict[str, Any]:
    """Load and cache the YAML config as a plain dict."""
    p = Path(path).expanduser().resolve() if path else config_path()
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


# --- small typed accessors used across the codebase -------------------------

def enabled_channels(cfg: dict[str, Any] | None = None) -> list[str]:
    """Channel keys with enabled: true, in priority order."""
    cfg = cfg or load_config()
    chans = cfg.get("channels", {})
    enabled = [(k, v.get("priority", 99)) for k, v in chans.items() if v.get("enabled")]
    return [k for k, _ in sorted(enabled, key=lambda kv: kv[1])]


def reporting_currency(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    return cfg.get("currency", {}).get("reporting", "NOK")
