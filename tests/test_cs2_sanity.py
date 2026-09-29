"""Evidence-review boundaries for all CS2 lanes; no live machine operations."""

from unittest.mock import patch

import pytest

from abso.profiles.counter_strike_2 import (
    CounterStrike2GSyncCaptureProfile,
    CounterStrike2GSyncHDRCaptureProfile,
    CounterStrike2GSyncHDRProfile,
    CounterStrike2GSyncProfile,
    CounterStrike2HDRProfile,
    CounterStrike2Profile,
)
from abso.settings.nvidia import NvidiaSettingsHandler

CS2_PROFILES = (
    CounterStrike2Profile,
    CounterStrike2HDRProfile,
    CounterStrike2GSyncProfile,
    CounterStrike2GSyncHDRProfile,
    CounterStrike2GSyncCaptureProfile,
    CounterStrike2GSyncHDRCaptureProfile,
)


@pytest.fixture(params=CS2_PROFILES, ids=lambda cls: cls().profile_id)
def profile(request):
    return request.param()


def test_cs2_preserves_system_baseline_but_clears_stale_fso_disable(profile):
    """Removing speculative policy must retain an explicit FSO-clear request."""
    assert profile.get_settings("PowerSettingsHandler") == {}
    registry = profile.get_settings("RegistrySettingsHandler")
    assert "win32_priority_separation" not in registry
    assert "game_priority" not in registry
    assert registry["fullscreen_optimizations"] == {"cs2.exe": False}
    assert profile.get_settings("GraphicsSettingsHandler")["disable_global_fso"] is False
    assert profile.get_settings("InterruptModeHandler") == {"enable_msi": False}
    assert profile.get_settings("NicDriverHandler") == {"nic_tuning": False}
    assert profile.get_settings("CpuAffinityHandler")["strategy"] is None


def test_cs2_disabled_nic_and_msi_requests_do_not_probe_or_write_devices(profile):
    """False is a no-op, not a request to force the inverse driver policy."""
    from abso.settings.interrupt_mode import InterruptModeHandler
    from abso.settings.nic_driver import NicDriverHandler

    with (
        patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", side_effect=AssertionError("GPU probe")),
        patch.object(NicDriverHandler, "_active_adapter", side_effect=AssertionError("NIC probe")),
    ):
        for handler in (InterruptModeHandler(), NicDriverHandler()):
            result = handler.apply(profile.get_settings(type(handler).__name__))
            assert result["success"] is True
            assert result["changed"] is False
            assert result["requires_reboot"] is False


def test_cs2_native_sync_guidance_matches_driver_lane_without_claiming_verification(profile):
    """Four VRR lanes follow Valve's combination; no-sync still permits tearing."""
    nvidia = profile.get_settings("NvidiaSettingsHandler")
    rows = {row["setting"]: row for row in profile.get_in_game_settings()}
    notes = " ".join(profile.get_post_apply_notes())
    resolved = NvidiaSettingsHandler.__new__(NvidiaSettingsHandler)._resolve_requested_nvidia_settings(
        nvidia
    )
    gsync = profile.requires_confirmed_vrr_support

    assert resolved["low_latency_mode"] == "off"
    assert resolved["vsync"] == ("on" if gsync else "off")
    assert rows["Wait for Vertical Sync"]["value"] == (
        "Enabled (in-game)" if gsync else "Disabled"
    )
    assert "optional" in rows["NVIDIA Reflex"]["value"]
    assert "Enabled" in rows["NVIDIA Reflex"]["value"]
    assert "optional" in notes
    assert "does not write or verify" in notes

    if gsync:
        assert nvidia["auto_vrr_fps_cap"] is True
        cap = rows["Maximum FPS in game (fps_max)"]
        assert cap["value"].startswith("0 (manual;")
        assert "driver" in cap["value"]
        assert "Reflex may pace FPS lower" in cap["reason"]
        assert "does not promise 297 FPS" in cap["reason"]
        assert "NVIDIA G-Sync status" in rows
    else:
        # A switch out of a VRR lane requests Off rather than retaining 297.
        assert not nvidia.get("auto_vrr_fps_cap", False)
        assert resolved["max_frame_rate"] == "off"
        assert resolved["vrr_app_override"] == "force_off"
        assert nvidia["global_vrr_mode"] == "off"


def test_cs2_keeps_fullscreen_and_capture_display_contracts_distinct(profile):
    nvidia = profile.get_settings("NvidiaSettingsHandler")
    windows = profile.get_settings("WindowsSettingsHandler")
    rows = {row["setting"]: row for row in profile.get_in_game_settings()}
    if profile.is_capture_safe:
        assert rows["Display Mode"]["value"] == "Fullscreen Windowed (borderless)"
        assert nvidia["global_vrr_mode"] == "fullscreen_and_windowed"
        assert windows["windowed_optimizations"] is True
        assert windows["vrr_optimize"] is True
        assert profile.get_settings("ProcessPriorityHandler") == {"cpu_priority": 2, "io_priority": 2}
        assert profile.mixed_refresh_safe_fallback_profile_id is None
        assert profile.overlay_compatible_fallback_profile_id is None
    else:
        assert rows["Display Mode"]["value"] == "Fullscreen"
        if profile.requires_confirmed_vrr_support:
            assert nvidia["global_vrr_mode"] == "fullscreen_only"
    assert windows["hdr"] is (not profile.is_sdr_only)
    assert windows["auto_hdr"] is False


def test_cs2_graphics_guidance_separates_cost_preferences_and_unknown_hdr_output(profile):
    rows = {row["setting"]: row for row in profile.get_in_game_settings()}
    assert "Shader Detail" in rows
    assert "Particle Detail" in rows
    assert "Shader / Particle / Effect Detail" not in rows
    assert "can degrade graphics performance" in rows["Boost Player Contrast"]["reason"]
    if profile.is_sdr_only:
        assert "not an sRGB clamp" in rows["Color Space"]["reason"]
    else:
        assert "game HDR output unverified" in rows["HDR"]["value"]
        assert "rendering-quality choice" in rows["HDR"]["reason"]
        assert "not panel calibration" in rows["SDR content brightness"]["reason"]


def test_cs2_stays_system_only_without_native_writes(profile):
    """A recommendation is not an automatic in-game setting or readback."""
    handler_names = {type(handler).__name__ for handler in profile.get_handlers()}
    assert not any("ConfigHandler" in name for name in handler_names)
    assert {"PowerSettingsHandler", "InterruptModeHandler", "NicDriverHandler"} <= handler_names
