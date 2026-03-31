"""Tests for the committed tray profile catalog cache."""

from __future__ import annotations

import json
from pathlib import Path

from abso.profiles.catalog import get_profile_manifest


def test_tray_profile_catalog_cache_matches_live_manifest() -> None:
    """Committed tray cache should mirror the live Python profile manifest."""
    cache_path = Path(__file__).resolve().parents[1] / "abso" / "tray" / "profile-catalog-cache.json"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))

    assert payload["profiles"] == get_profile_manifest()
