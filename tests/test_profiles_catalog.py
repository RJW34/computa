"""Tests for centralized profile catalog consistency."""

from __future__ import annotations

from collections import defaultdict

from abso.core.applier import ProfileApplier
from abso.profiles import get_all_profiles
from abso.profiles.catalog import (
    PROFILE_CATALOG,
    get_profile_manifest,
    get_profile_instances,
    resolve_profile_id,
)


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


def test_retired_rivals_aliases_resolve_to_offline_profile() -> None:
    """Retired generic Rivals ids should canonicalize to the consolidated offline lane."""
    assert "rivals2" not in PROFILE_CATALOG
    assert "rivals2-300hz-max" not in PROFILE_CATALOG
    assert resolve_profile_id("rivals2") == "rivals2-offline"
    assert resolve_profile_id("rivals2-300hz-max") == "rivals2-offline"


def test_rivals_manifest_contains_canonical_hdr_variants() -> None:
    """The live manifest should expose the consolidated Rivals SDR/HDR matrix."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    for profile_id in {
        "rivals2-offline",
        "rivals2-offline-hdr",
        "rivals2-online",
        "rivals2-online-hdr",
        "rivals2-gsync",
        "rivals2-gsync-hdr",
        "rivals2-online-gsync",
        "rivals2-online-gsync-hdr",
        "rivals2-streaming",
        "rivals2-streaming-hdr",
        "rivals2-tournament-sim-144hz",
    }:
        assert profile_id in manifest


def test_shooter_and_arpg_families_expose_canonical_hdr_sdr_pairs() -> None:
    """Families with explicit native HDR support should expose paired SDR/HDR lanes."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    for profile_id in {
        "cod-bo7",
        "cod-bo7-sdr",
        "diablo4",
        "diablo4-sdr",
        "fortnite",
        "fortnite-hdr",
        "fortnite-streaming",
        "fortnite-streaming-hdr",
        "overwatch2-gsync-streaming",
        "overwatch2-gsync-hdr-streaming",
    }:
        assert profile_id in manifest


def test_profile_manifest_has_required_fields() -> None:
    """Manifest must include metadata required by tray and GUI surfaces."""
    manifest = get_profile_manifest()
    assert manifest, "Manifest should not be empty"
    for profile in manifest:
        assert profile["id"]
        assert profile["display_name"]
        assert isinstance(profile["handlers"], list)
        assert isinstance(profile["has_in_game_settings"], bool)
        assert "tray_category" in profile
        assert "tray_subtitle" in profile
        assert profile["sync_mode"] in {"on", "off", "agnostic"}


def test_slippi_tray_metadata_matches_sync_behavior() -> None:
    """Slippi tray badges/descriptions should match the actual sync intent."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    assert manifest["slippi-melee"]["sync_mode"] == "off"
    assert manifest["slippi-melee-console-parity"]["sync_mode"] == "on"
    assert manifest["slippi-melee-universal"]["sync_mode"] == "off"
    assert manifest["slippi-melee-vrr-lab"]["sync_mode"] == "on"
    assert "sync-agnostic" not in manifest["slippi-melee-universal"]["tray_description"].lower()


def test_overlapping_nvidia_profile_families_have_stable_driver_identity() -> None:
    """Variant families sharing executable hints must declare explicit NVIDIA profile identity."""
    applier = ProfileApplier()
    groups: dict[tuple[str, ...], list[tuple[str, object]]] = defaultdict(list)

    for profile_id, profile in get_profile_instances().items():
        if not profile.executable_hints:
            continue
        key = tuple(sorted(profile.executable_hints))
        groups[key].append((profile_id, profile))

    failures: list[str] = []
    for family in groups.values():
        if len(family) < 2:
            continue

        for profile_id, profile in family:
            settings_map = applier._collect_settings(profile)
            final_settings = applier._finalize_handler_settings(
                profile,
                profile_id,
                settings_map,
                None,
            )
            nvidia_settings = final_settings.get("NvidiaSettingsHandler")
            if not nvidia_settings:
                continue

            if not nvidia_settings.get("profile_name"):
                failures.append(profile_id)

    assert not failures, (
        "Profiles sharing executable families must finalize explicit NVIDIA profile names: "
        + ", ".join(sorted(failures))
    )
