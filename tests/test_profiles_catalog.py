"""Tests for centralized profile catalog consistency."""

from __future__ import annotations

from collections import defaultdict

from abso.core.applier import ProfileApplier
from abso.profiles import get_all_profiles
from abso.profiles.catalog import (
    PROFILE_ALIASES,
    PROFILE_CATALOG,
    get_profile_instances,
    get_profile_manifest,
    is_valid_sync_mode,
    is_valid_tray_category,
    profile_id_conflict_kind,
    resolve_profile_id,
    sync_mode_choices,
    tray_category_choices,
)
from abso.profiles.yaml_loader import YAMLProfileLoader


def _write_yaml_profile(directory, profile_id: str) -> None:
    (directory / f"{profile_id}.yaml").write_text(
        f"""
profile_id: {profile_id}
display_name: {profile_id}
description: Test user profile
optimization_target: stable_online
executable_hints:
  - CustomGame.exe
""".lstrip(),
        encoding="utf-8",
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


def test_profile_aliases_target_canonical_catalog_ids_directly() -> None:
    """Alias resolution is one-hop, so aliases must never point at aliases."""
    assert set(PROFILE_ALIASES.values()) <= set(PROFILE_CATALOG)


def test_retired_rivals_aliases_resolve_to_nosync_profile() -> None:
    """Retired generic Rivals ids should canonicalize to the merged no-sync lane."""
    assert "rivals2" not in PROFILE_CATALOG
    assert "rivals2-300hz-max" not in PROFILE_CATALOG
    assert resolve_profile_id("rivals2") == "rivals2-nosync"
    assert resolve_profile_id("rivals2-300hz-max") == "rivals2-nosync"


def test_retired_offline_online_split_ids_resolve_to_merged_lanes() -> None:
    """2026-07 consolidation: every pre-merge lane ID redirects to its successor."""
    retired_to_canonical = {
        "rivals2-offline": "rivals2-nosync",
        "rivals2-offline-hdr": "rivals2-nosync-hdr",
        "rivals2-online": "rivals2-nosync",
        "rivals2-online-hdr": "rivals2-nosync-hdr",
        "rivals2-online-gsync": "rivals2-gsync",
        "rivals2-online-gsync-hdr": "rivals2-gsync-hdr",
        "rivals2-online-gsync-hdr-capture": "rivals2-gsync-hdr-capture",
    }
    for retired, canonical in retired_to_canonical.items():
        assert retired not in PROFILE_CATALOG, retired
        assert resolve_profile_id(retired) == canonical, retired


def test_profile_id_conflict_kind_distinguishes_reserved_ids() -> None:
    assert profile_id_conflict_kind("overwatch2") == "built-in profile"
    assert profile_id_conflict_kind("rivals2") == "profile alias"
    assert profile_id_conflict_kind("custom-rivals2") is None


def test_tray_category_validation_accepts_current_and_legacy_categories() -> None:
    assert is_valid_tray_category("Shooters")
    assert is_valid_tray_category("Shooter")
    assert is_valid_tray_category("Other")
    assert not is_valid_tray_category("FPS")
    assert "Shooters" in tray_category_choices()
    assert "Shooter" in tray_category_choices()


def test_sync_mode_validation_accepts_catalog_modes() -> None:
    assert is_valid_sync_mode("on")
    assert is_valid_sync_mode("off")
    assert is_valid_sync_mode("agnostic")
    assert not is_valid_sync_mode("adaptive")
    assert sync_mode_choices() == ("on", "off", "agnostic")


def test_user_profiles_cannot_shadow_retired_aliases(tmp_path, monkeypatch) -> None:
    """User YAML IDs that resolve elsewhere must not appear as selectable profiles."""
    _write_yaml_profile(tmp_path, "rivals2")
    _write_yaml_profile(tmp_path, "custom-rivals2")
    monkeypatch.setattr(YAMLProfileLoader, "USER_PROFILES_DIR", tmp_path)

    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    assert "custom-rivals2" in manifest
    assert "rivals2" not in manifest
    assert resolve_profile_id("rivals2") == "rivals2-nosync"


def test_streaming_aliases_resolve_directly_to_capture_safe_lanes() -> None:
    """Every requested game name must route streaming input to a real capture lane."""
    assert "rivals2-nosync-hdr" in PROFILE_CATALOG
    assert "rivals2-gsync-hdr" in PROFILE_CATALOG
    assert "rivals2-tournament-sim-144hz" not in PROFILE_CATALOG

    aliases = {
        "slippi-melee-streaming": "slippi-melee-capture",
        "slippi-melee-streaming-hdr": "slippi-melee-hdr-capture",
        "ssbm-streaming": "slippi-melee-capture",
        "ssbm-streaming-hdr": "slippi-melee-hdr-capture",
        "rivals2-streaming": "rivals2-gsync-capture",
        "rivals2-streaming-hdr": "rivals2-gsync-hdr-capture",
        "roa2-streaming": "rivals2-gsync-capture",
        "roa2-streaming-hdr": "rivals2-gsync-hdr-capture",
        "fortnite-streaming": "fortnite-gsync-capture",
        "fortnite-streaming-hdr": "fortnite-gsync-hdr-capture",
        "overwatch2-streaming": "overwatch2-gsync-capture",
        "overwatch2-streaming-hdr": "overwatch2-gsync-hdr-capture",
        "overwatch2-gsync-streaming": "overwatch2-gsync-capture",
        "overwatch2-gsync-hdr-streaming": "overwatch2-gsync-hdr-capture",
        "cs2-streaming": "counter-strike-2-gsync-capture",
        "cs2-streaming-hdr": "counter-strike-2-gsync-hdr-capture",
        "counter-strike-2-streaming": "counter-strike-2-gsync-capture",
        "counter-strike-2-streaming-hdr": "counter-strike-2-gsync-hdr-capture",
    }
    profiles = get_profile_instances()
    for alias, canonical in aliases.items():
        assert alias not in PROFILE_CATALOG, alias
        assert resolve_profile_id(alias) == canonical, alias
        assert profiles[canonical].is_capture_safe is True, alias

    assert resolve_profile_id("rivals2-tournament-sim-144hz") == "rivals2-nosync"
    assert resolve_profile_id("pacdeluxe-streaming") == "pacdeluxe"
    assert resolve_profile_id("ryujinx-ssbu-streaming") == "ryujinx-ssbu"
    assert resolve_profile_id("slippi-melee-vrr-lab") == "slippi-melee"


def test_requested_families_expose_visible_streaming_lanes() -> None:
    """Tray metadata should make both SDR and HDR streaming choices explicit."""
    expected_by_group = {
        "slippi-melee": {"slippi-melee-capture", "slippi-melee-hdr-capture"},
        "rivals2": {"rivals2-gsync-capture", "rivals2-gsync-hdr-capture"},
        "fortnite": {"fortnite-gsync-capture", "fortnite-gsync-hdr-capture"},
        "overwatch2": {
            "overwatch2-gsync-capture",
            "overwatch2-gsync-hdr-capture",
        },
        "counter-strike-2": {
            "counter-strike-2-gsync-capture",
            "counter-strike-2-gsync-hdr-capture",
        },
    }
    manifest = get_profile_manifest()
    for group, expected_ids in expected_by_group.items():
        entries = {
            row["id"]: row
            for row in manifest
            if row["tray_group"] == group and "streaming" in row["tray_variant"].lower()
        }
        assert set(entries) == expected_ids, group
        assert all(row["tray_visible"] is True for row in entries.values()), group


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
        assert "tray_group" in profile
        assert "tray_group_name" in profile
        assert "tray_variant" in profile
        assert "tray_rank" in profile
        assert "tray_visible" in profile
        assert profile["tray_group"]
        assert profile["tray_group_name"]
        assert profile["tray_variant"]
        assert isinstance(profile["tray_rank"], int)
        assert isinstance(profile["tray_visible"], bool)
        assert profile["sync_mode"] in {"on", "off", "agnostic"}


def test_slippi_tray_metadata_matches_sync_behavior() -> None:
    """Slippi tray badges/descriptions should match the actual sync intent."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    assert manifest["slippi-melee"]["sync_mode"] == "off"
    assert manifest["slippi-melee-console-parity"]["sync_mode"] == "on"
    assert manifest["slippi-melee-universal"]["sync_mode"] == "off"
    assert "sync-agnostic" not in manifest["slippi-melee-universal"]["tray_description"].lower()


def test_tray_manifest_groups_variants_by_game_once() -> None:
    """Tray grouping metadata should group variants under one game label."""
    manifest = get_profile_manifest()
    groups: dict[str, list[str]] = defaultdict(list)
    group_names: dict[str, set[str]] = defaultdict(set)

    legacy_categories = {"Productivity", "Shooter", "ARPG", "Streaming"}
    for profile in manifest:
        assert profile["tray_category"] not in legacy_categories
        groups[profile["tray_group"]].append(profile["id"])
        group_names[profile["tray_group"]].add(profile["tray_group_name"])

    for names in group_names.values():
        assert len(names) == 1

    assert set(groups["rivals2"]) == {
        "rivals2-nosync",
        "rivals2-nosync-hdr",
        "rivals2-gsync",
        "rivals2-gsync-capture",
        "rivals2-gsync-hdr",
        "rivals2-gsync-hdr-capture",
    }
    assert set(groups["slippi-melee"]) == {
        "slippi-melee",
        "slippi-melee-hdr",
        "slippi-melee-capture",
        "slippi-melee-hdr-capture",
        "slippi-melee-console-parity",
        "slippi-melee-console-parity-hdr",
        "slippi-melee-universal",
        "slippi-melee-universal-hdr",
    }
    assert set(groups["overwatch2"]) == {
        "overwatch2",
        "overwatch2-hdr",
        "overwatch2-gsync",
        "overwatch2-gsync-hdr",
        "overwatch2-gsync-capture",
        "overwatch2-gsync-hdr-capture",
    }
    assert set(groups["fortnite"]) == {
        "fortnite",
        "fortnite-hdr",
        "fortnite-gsync-hdr",
        "fortnite-gsync-capture",
        "fortnite-gsync-hdr-capture",
    }
    assert set(groups["counter-strike-2"]) == {
        "counter-strike-2",
        "counter-strike-2-hdr",
        "counter-strike-2-gsync",
        "counter-strike-2-gsync-hdr",
        "counter-strike-2-gsync-capture",
        "counter-strike-2-gsync-hdr-capture",
    }


def test_tray_rank_orders_rivals2_variants_for_users() -> None:
    """Rivals 2 tray variants should pair strict and streaming HDR/SDR lanes."""
    profiles = [profile for profile in get_profile_manifest() if profile["tray_group"] == "rivals2"]

    assert [profile["id"] for profile in sorted(profiles, key=lambda item: item["tray_rank"])] == [
        "rivals2-gsync-hdr",
        "rivals2-gsync-hdr-capture",
        "rivals2-gsync",
        "rivals2-gsync-capture",
        "rivals2-nosync-hdr",
        "rivals2-nosync",
    ]


def test_no_sync_tray_labels_match_sync_mode() -> None:
    """Profiles advertised as no-sync must not carry agnostic sync badges."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    for profile_id in ("fortnite", "fortnite-hdr"):
        assert manifest[profile_id]["sync_mode"] == "off"


def test_manifest_exposes_honest_application_scope_for_incomplete_families() -> None:
    """Families without native handlers should surface system-only scope in the manifest."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    assert manifest["diablo4"]["application_scope"] == "system_plus_native_config"
    assert manifest["fortnite"]["application_scope"] == "system_plus_native_config"
    assert manifest["marvel-rivals-sdr"]["application_scope"] == "system_plus_native_config"
    assert manifest["ryujinx-ssbu"]["application_scope"] == "system_only"


def test_deadlock_hdr_catalog_does_not_claim_native_hdr() -> None:
    """Deadlock HDR lanes are Windows HDR composition, not native game HDR."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    for profile_id in ("deadlock-hdr", "deadlock-gsync-hdr"):
        text = " ".join(
            str(manifest[profile_id].get(key, ""))
            for key in ("description", "tray_subtitle", "tray_description")
        ).lower()
        assert "native hdr" not in text
        assert "windows hdr" in text
        assert "renders sdr" in text


def test_cs2_hdr_catalog_does_not_claim_native_hdr() -> None:
    """CS2 HDR lanes are Windows HDR composition, not native game HDR."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    for profile_id in ("counter-strike-2-hdr", "counter-strike-2-gsync-hdr"):
        text = " ".join(
            str(manifest[profile_id].get(key, ""))
            for key in ("description", "tray_subtitle", "tray_description")
        ).lower()
        assert "native hdr" in text
        assert "not configured" in text or "does not establish" in text
        assert "windows hdr" in text
        assert "composition" in text


def test_rivals2_hdr_catalog_reports_windows_hdr_composition() -> None:
    """Rivals 2 HDR lanes must not claim native HDR support."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}

    for profile_id in (
        "rivals2-nosync-hdr",
        "rivals2-gsync-hdr",
        "rivals2-gsync-hdr-capture",
    ):
        text = " ".join(
            str(manifest[profile_id].get(key, ""))
            for key in ("description", "tray_subtitle", "tray_description")
        ).lower()
        assert "windows hdr composition" in text
        assert "native" in text and "hdr" in text
        assert "native game hdr stays off" in text or "native hdr remains off" in text


def test_productivity_catalog_reports_sdr_hdr_off_lane() -> None:
    """Productivity default turns HDR off; the tray must not claim it leaves HDR alone."""
    manifest = {profile["id"]: profile for profile in get_profile_manifest()}
    profile = get_profile_instances()["productivity"]
    windows_settings = profile.get_settings("WindowsSettingsHandler")

    assert windows_settings["hdr"] is False
    assert windows_settings["auto_hdr"] is False

    text = " ".join(
        str(manifest["productivity"].get(key, ""))
        for key in ("description", "tray_subtitle", "tray_description")
    ).lower()
    assert "hdr off" in text or "turns windows hdr off" in text
    assert "does not touch hdr" not in text
    assert "does not change hdr" not in text


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

        if (
            settings.get("disable_nagle")
            or settings.get("preset") == "gaming"
            or "tcp_global" in settings
            or settings.get("tcp_nodelay")
            or settings.get("tcp_ack_frequency")
        ):
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
