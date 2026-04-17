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


def test_future_dated_cod_profiles_are_not_registered() -> None:
    """BO7 profiles were not specable as of the April 16, 2025 audit date."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    assert "cod-bo7" not in PROFILE_CATALOG
    assert "cod-bo7-sdr" not in PROFILE_CATALOG
    assert "cod-bo7" not in manifest
    assert "cod-bo7-sdr" not in manifest


def test_profile_manifest_has_required_fields() -> None:
    """Manifest must include metadata required by tray and GUI surfaces."""
    manifest = get_profile_manifest()
    assert manifest, "Manifest should not be empty"
    for profile in manifest:
        assert profile["id"]
        assert profile["display_name"]
        assert profile["application_scope"] in {"system_only", "system_plus_native_config"}
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


def test_manifest_exposes_honest_application_scope_for_incomplete_families() -> None:
    """Families without native handlers should surface system-only scope in the manifest."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    assert manifest["diablo4"]["application_scope"] == "system_plus_native_config"
    assert manifest["fortnite"]["application_scope"] == "system_plus_native_config"
    assert manifest["marvel-rivals-sdr"]["application_scope"] == "system_plus_native_config"
    assert manifest["ryujinx-ssbu"]["application_scope"] == "system_only"


def test_builtin_profiles_do_not_use_optional_service_cnm_or_memory_tweaks() -> None:
    """Built-ins should avoid broad local/service/memory side effects by default."""
    prohibited = {
        "CNMSettingsHandler",
        "ServicesSettingsHandler",
        "MemorySettingsHandler",
    }

    offenders: list[str] = []
    for profile_id, profile in get_profile_instances().items():
        handler_names = {handler.__class__.__name__ for handler in profile.get_handlers()}
        if handler_names & prohibited:
            offenders.append(profile_id)

    assert not offenders


def test_builtin_profiles_use_os_default_networking_without_explicit_scope() -> None:
    """Profiles that do not opt into network tuning should not request TCP writes."""
    offenders: list[str] = []
    for profile_id, profile in get_profile_instances().items():
        if profile.network_scope != "none":
            continue

        settings = profile.get_settings("NetworkSettingsHandler")
        if not settings:
            continue

        if settings.get("disable_nagle") or settings.get("preset") == "gaming" or "tcp_global" in settings:
            offenders.append(profile_id)

    assert not offenders


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
