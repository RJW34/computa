"""Tests for the committed tray profile catalog cache."""

from __future__ import annotations

import json
from pathlib import Path

from abso.profiles.catalog import get_profile_aliases, get_profile_manifest

CACHE_PATH = Path(__file__).resolve().parents[1] / "abso" / "tray" / "profile-catalog-cache.json"


def test_tray_profile_catalog_cache_matches_live_manifest() -> None:
    """Committed tray cache should mirror the live Python profile manifest."""
    payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    assert payload["profiles"] == get_profile_manifest()


def test_tray_profile_catalog_cache_includes_alias_map() -> None:
    """Cache must ship the retired-id alias map so the tray can normalize tray-config.json."""
    payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    assert "aliases" in payload, "Cache must expose an 'aliases' map for tray normalization"
    assert payload["aliases"] == get_profile_aliases()
