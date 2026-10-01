"""Rocket League lane contracts; all checks are pure or use mocked drivers."""

from unittest.mock import patch

import pytest

import abso.main  # noqa: F401 - establish the production import order
from abso.core.linter import ProfileLinter
from abso.core.process_janitor import CAPTURE_ALLOWED_IMAGES
from abso.core.rollback_guard import RollbackGuard
from abso.core.stability_gate import StabilityGate
from abso.core.vrr import get_vrr_fps_cap_for_policy
from abso.profiles.rocket_league import (
    RocketLeagueGSyncCaptureProfile,
    RocketLeagueGSyncHDRCaptureProfile,
    RocketLeagueGSyncHDRProfile,
    RocketLeagueGSyncProfile,
    RocketLeagueHDRProfile,
    RocketLeagueProfile,
)
from abso.settings.nvidia import NvidiaSettingsHandler
from abso.settings.nvidia.nvapi_drs import DRSProfileManager

ROCKET_LEAGUE_PROFILES = (
    RocketLeagueProfile,
    RocketLeagueHDRProfile,
    RocketLeagueGSyncProfile,
    RocketLeagueGSyncHDRProfile,
    RocketLeagueGSyncCaptureProfile,
    RocketLeagueGSyncHDRCaptureProfile,
)


@pytest.fixture(params=ROCKET_LEAGUE_PROFILES, ids=lambda cls: cls().profile_id)
def profile(request):
    return request.param()


def test_six_unique_rocket_league_lanes():
    assert {cls().profile_id for cls in ROCKET_LEAGUE_PROFILES} == {
        "rocket-league", "rocket-league-hdr", "rocket-league-gsync",
        "rocket-league-gsync-hdr", "rocket-league-gsync-capture",
        "rocket-league-gsync-hdr-capture",
    }


def test_native_settings_are_manual_and_launch_requires_platform_client(profile):
    assert profile.application_scope == "system_only"
    assert profile.executable_hints == ["RocketLeague.exe"]
    assert profile.nvidia_binding_executables == ["RocketLeague.exe"]
    assert profile.graphics_api == "dx11"
    assert profile.is_online_profile is True
    assert profile.requires_reflex is False
    handler_names = {type(handler).__name__ for handler in profile.get_handlers()}
    assert not any(name.endswith("ConfigHandler") for name in handler_names)
    assert "Epic Games Launcher or Steam" in profile.external_launch_required_reason
    assert "does not write or verify native settings" in " ".join(profile.get_post_apply_notes())


def test_preserves_unresearched_system_and_calibration_policy(profile):
    for handler in (
        "PowerSettingsHandler", "NetworkSettingsHandler", "NicDriverHandler",
        "InterruptModeHandler", "AudioEngineHandler", "MouseSettingsHandler",
        "ColorProfileSettingsHandler", "DisplayColorRangeHandler", "AmdSettingsHandler",
    ):
        assert profile.get_settings(handler) == {}, handler
    assert profile.get_settings("RegistrySettingsHandler") == {
        "fullscreen_optimizations": {"RocketLeague.exe": False},
    }
    assert profile.get_settings("GraphicsSettingsHandler") == {"disable_global_fso": False}
    assert profile.get_settings("ProcessPriorityHandler") == {"cpu_priority": 2, "io_priority": 2}
    assert profile.get_settings("CpuAffinityHandler") == {"strategy": None}
    windows = profile.get_settings("WindowsSettingsHandler")
    assert "hags" not in windows
    assert windows.get("sdr_white_level_nits") is None
    if not profile.is_sdr_only:
        assert windows["advanced_color"] is True
    assert windows["hdr"] is (not profile.is_sdr_only)
    assert windows["auto_hdr"] is False


def test_online_pipeline_preserves_requested_llm_on_and_native_queue_encoding(profile):
    """Online lanes must not silently downgrade a requested Ultra policy."""
    settings = {type(h).__name__: profile.get_settings(type(h).__name__) for h in profile.get_handlers()}
    lint = ProfileLinter().lint(profile)
    assert not lint.errors
    gated, gate_result = StabilityGate().process(profile, settings, lint_result=lint)
    guard = RollbackGuard(mode="block")
    guarded = guard.check(profile, gated)
    assert profile.optimization_target == "stable_online"
    assert gate_result.blocked_count == 0
    assert guarded.passed
    assert guarded.enforced_overrides == {}
    assert guard.apply_overrides(gated, guarded) == settings
    nvidia = settings["NvidiaSettingsHandler"]
    assert nvidia["low_latency_mode"] == "on"
    assert "preset" not in nvidia
    resolved = NvidiaSettingsHandler.__new__(NvidiaSettingsHandler)._resolve_requested_nvidia_settings(nvidia)
    assert DRSProfileManager.low_latency_native_settings(resolved["low_latency_mode"]) == {
        "ultra_low_latency": 0, "prerendered_frames": 1, "low_latency_mode": 1,
    }


def test_sync_and_limiter_intent_survives_handler_request_normalization(profile):
    handler = NvidiaSettingsHandler.__new__(NvidiaSettingsHandler)
    requested = handler._extract_requested_settings(profile.get_settings("NvidiaSettingsHandler"))
    resolved = handler._resolve_requested_nvidia_settings(requested["settings"])
    gsync = profile.requires_confirmed_vrr_support
    assert requested["driver_profile_name"] == "Rocket League"
    assert resolved["vsync"] == ("on" if gsync else "off")
    assert resolved["vsync_tear_control"] == "disable"
    assert resolved["vrr_app_override"] == ("allow" if gsync else "force_off")
    assert requested["auto_vrr_fps_cap"] is gsync
    if gsync:
        assert get_vrr_fps_cap_for_policy(300, requested["vrr_cap_policy"]) == 297
        assert profile.requires_exact_nvidia_binding is True
        assert requested["global_settings"]["vrr_mode"] == (
            "fullscreen_and_windowed" if profile.is_capture_safe else "fullscreen_only"
        )
    else:
        # Explicitly clear a prior driver limiter/VRR policy when leaving G-SYNC.
        assert resolved["max_frame_rate"] == "off"
        assert requested["global_settings"]["vrr_mode"] == "off"


def test_native_guidance_matches_presentation_contract_and_caps(profile):
    rows = {row["setting"]: row for row in profile.get_in_game_settings()}
    capture = profile.is_capture_safe
    gsync = profile.requires_confirmed_vrr_support
    assert rows["Display Mode"]["value"] == ("Borderless" if capture else "Fullscreen")
    assert rows["Vertical Sync"]["value"] == ("On" if capture else "Off")
    assert rows["Frames Per Second"]["value"] == (
        "Unlimited (set manually)" if gsync else "Sustainable limit (set manually)"
    )
    assert "heuristic" in rows["Low Latency Mode"]["reason"]
    assert "No native Reflex is assumed" in rows["Low Latency Mode"]["reason"]
    assert rows["Graphics, controls, and Input Buffer"]["value"] == "Preserve your settings"
    if gsync:
        assert "does not promise 297 FPS" in rows["Frames Per Second"]["reason"]
    if not profile.is_sdr_only:
        assert "SDR game content in Windows HDR" in rows["HDR"]["value"]
        assert "does not configure native game HDR or RTX HDR" in rows["HDR"]["reason"]
    if capture:
        windows = profile.get_settings("WindowsSettingsHandler")
        assert windows["windowed_optimizations"] is True
        assert windows["vrr_optimize"] is True
        assert "encoder/output settings are unchanged" in " ".join(profile.get_post_apply_notes())
    assert profile.display_path_requirements.require_overlay_free_path is (gsync and not capture)


def test_fallbacks_terminate_and_preserve_windows_hdr_lane(profile):
    profiles = {cls().profile_id: cls() for cls in ROCKET_LEAGUE_PROFILES}
    if profile.requires_confirmed_vrr_support and not profile.is_capture_safe:
        capture = profiles[profile.overlay_compatible_fallback_profile_id]
        no_sync = profiles[profile.mixed_refresh_safe_fallback_profile_id]
        assert capture.is_capture_safe
        assert capture.is_sdr_only is profile.is_sdr_only
        assert no_sync.is_sdr_only is profile.is_sdr_only
        assert not no_sync.requires_confirmed_vrr_support
        assert capture.overlay_compatible_fallback_profile_id is None
    else:
        assert profile.overlay_compatible_fallback_profile_id is None
        assert profile.mixed_refresh_safe_fallback_profile_id is None


def test_shared_janitor_preserves_capture_stack_only_in_streaming_lanes(profile):
    with patch("abso.core.process_janitor._load_user_process_overrides", return_value=((), ())):
        killset = profile.launch_process_killset()
    images = {image.lower() for image in (*killset.always_safe, *killset.opt_in)}
    assert "rocketleague.exe" not in images
    if profile.is_capture_safe:
        assert not images & CAPTURE_ALLOWED_IMAGES
    else:
        assert "obs64.exe" in images
    assert profile.cpu_partition_policy == "full"
    assert "rocketleague.exe" not in {image.lower() for image in profile.background_steer_images}
