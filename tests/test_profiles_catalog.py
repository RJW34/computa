"""Tests for centralized profile catalog consistency."""

from __future__ import annotations

from abso.core.applier import ProfileApplier
from abso.profiles import get_all_profiles
from abso.profiles.catalog import PROFILE_CATALOG, get_profile_manifest


def test_catalog_matches_applier_registry() -> None:
    """ProfileApplier registry must mirror centralized catalog keys exactly."""
    assert set(ProfileApplier.PROFILES) == set(PROFILE_CATALOG)


def test_catalog_matches_get_all_profiles() -> None:
    """get_all_profiles() must mirror centralized catalog keys exactly."""
    assert set(get_all_profiles()) == set(PROFILE_CATALOG)


def test_catalog_keys_match_profile_id_property() -> None:
    """Catalog key must match each profile class profile_id."""
    for profile_id, entry in PROFILE_CATALOG.items():
        assert entry.profile_class().profile_id == profile_id


def test_profile_manifest_has_required_fields() -> None:
    """Manifest must include metadata required by tray and GUI surfaces."""
    manifest = get_profile_manifest()
    assert manifest, "Manifest should not be empty"
    for profile in manifest:
        assert profile["id"]
        assert profile["display_name"]
        assert "tray_category" in profile
        assert "tray_subtitle" in profile
        assert profile["sync_mode"] in {"on", "off", "agnostic"}
