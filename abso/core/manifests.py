"""Manifest loading utilities for configurable heuristics."""

from __future__ import annotations

import copy
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path(__file__).parent / "manifests"


def _load_manifest(name: str, fallback: dict[str, Any]) -> dict[str, Any]:
    path = MANIFESTS_DIR / name
    if not path.exists():
        return copy.deepcopy(fallback)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning(f"Failed to load manifest '{path}': {e}")

    return copy.deepcopy(fallback)


@lru_cache(maxsize=8)
def load_linter_rules(fallback_json: str) -> dict[str, Any]:
    """Load linter rule manifest with JSON fallback payload."""
    fallback = json.loads(fallback_json)
    return _load_manifest("linter_rules.json", fallback)


@lru_cache(maxsize=8)
def load_game_detection_manifest(fallback_json: str) -> dict[str, Any]:
    """Load game detection manifest with JSON fallback payload."""
    fallback = json.loads(fallback_json)
    return _load_manifest("game_detection.json", fallback)
