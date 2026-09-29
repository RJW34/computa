"""Rivals 2 lane policy and native file boundaries; all probes are mocked."""

from unittest.mock import patch

import pytest

from abso.core.vrr import get_vrr_fps_cap_for_policy
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.rivals2_300hz_max import Rivals2_300HzMaxProfile
from abso.profiles.rivals2_gsync import (
    Rivals2GSyncCaptureProfile,
    Rivals2GSyncHDRCaptureProfile,
    Rivals2GSyncHDRProfile,
    Rivals2GSyncProfile,
)
from abso.profiles.rivals2_nosync import Rivals2NoSyncHDRProfile, Rivals2NoSyncProfile
from abso.settings.nvidia import NvidiaSettingsHandler
from abso.settings.rivals2_config import Rivals2ConfigHandler

FAMILIES = (
    Rivals2NoSyncProfile, Rivals2NoSyncHDRProfile,
    Rivals2GSyncProfile, Rivals2GSyncHDRProfile,
    Rivals2GSyncCaptureProfile, Rivals2GSyncHDRCaptureProfile,
    Rivals2Profile, Rivals2_300HzMaxProfile,
)


@pytest.fixture(params=FAMILIES, ids=lambda cls: cls().profile_id)
def profile(request):
    return request.param()


def test_rivals_preserves_baseline_system_policy_and_user_input(profile):
    assert profile.get_settings("PowerSettingsHandler") == {}
    registry = profile.get_settings("RegistrySettingsHandler")
    assert "win32_priority_separation" not in registry
    assert "game_priority" not in registry
    assert not profile.get_settings("NicDriverHandler").get("nic_tuning", False)
    assert not profile.get_settings("InterruptModeHandler").get("enable_msi", False)
    assert profile.get_settings("NetworkSettingsHandler") == {"disable_nagle": False, "preset": "default"}
    assert profile.get_settings("CpuAffinityHandler")["strategy"] is None
    assert profile.get_settings("ProcessPriorityHandler") == {"cpu_priority": 2, "io_priority": 2}
    assert "raw_input" not in profile.get_settings("Rivals2ConfigHandler")
    assert not any("reflex" in key.lower() for key in profile.get_settings("Rivals2ConfigHandler"))


def test_rivals_uses_one_native_limiter_and_no_forced_opengl_threading(profile):
    native = profile.get_settings("Rivals2ConfigHandler")
    driver = profile.get_settings("NvidiaSettingsHandler")
    resolved = NvidiaSettingsHandler.__new__(NvidiaSettingsHandler)._resolve_requested_nvidia_settings(driver)
    gsync = profile.requires_confirmed_vrr_support
    assert "preset" not in driver
    assert not driver.get("auto_vrr_fps_cap", False)
    assert resolved["max_frame_rate"] == "off"
    assert resolved["threaded_optimization"] == "auto"
    assert resolved["low_latency_mode"] == "on"
    assert resolved["shader_cache"] == "on"
    assert resolved["vsync"] == ("on" if gsync else "off")
    assert resolved["vrr_app_override"] == ("allow" if gsync else "force_off")
    assert not profile.allow_dual_limiter
    assert native["auto_vrr_fps_cap"] is True
    assert native["vrr_cap_policy"] == ("refresh_minus_3" if gsync else "fighting_60hz_nosync")
    assert get_vrr_fps_cap_for_policy(300, native["vrr_cap_policy"]) == (297 if gsync else 300)


def test_rivals_capture_sync_and_hdr_match_native_presentation_targets(profile):
    capture = profile.is_capture_safe
    gsync = profile.requires_confirmed_vrr_support
    hdr = not profile.is_sdr_only
    native = profile.get_settings("Rivals2ConfigHandler")
    driver = profile.get_settings("NvidiaSettingsHandler")
    windows = profile.get_settings("WindowsSettingsHandler")
    assert native["fullscreen_mode"] == (1 if capture else 0)
    assert native["vsync"] is capture
    assert native["hdr_output"] is False
    assert "hdr_nits" not in native
    assert windows["hdr"] is hdr
    assert windows["auto_hdr"] is False
    assert windows["max_refresh_rate"] is True
    assert windows["windowed_optimizations"] is capture
    assert windows["vrr_optimize"] is capture
    assert profile.get_settings("GraphicsSettingsHandler")["disable_global_fso"] is (not capture)
    assert all(disabled is (not capture) for disabled in profile.fullscreen_optimizations_per_exe.values())
    assert driver["global_vrr_mode"] == ("fullscreen_and_windowed" if capture else "fullscreen_only" if gsync else "off")
    assert profile.nvidia_profile_name == "Rivals 2"
    assert profile.nvidia_binding_executables == ["Rivals2-Win64-Shipping.exe"]
    if capture:
        rows = {row["setting"]: row for row in profile.get_in_game_settings()}
        assert rows["V-SYNC"]["value"] == "On"
        assert "windowed and fullscreen" in rows["Set up G-SYNC"]["reason"]
        assert "V-Sync On" in " ".join(profile.get_post_apply_notes())
        assert profile.overlay_compatible_fallback_profile_id is None


def test_each_rivals_lane_applies_only_managed_keys_and_is_idempotent(tmp_path, profile):
    path = tmp_path / "GameUserSettings.ini"
    unowned = ("bUseRawInput=False\nPreferredFullscreenMode=2\nHDRDisplayOutputNits=750\n"
               "CustomController=new-layout\n[ScalabilityGroups]\nsg.ResolutionQuality=100\n"
               "sg.TextureQuality=2\n[Other]\nFrameRateLimit=30\n")
    path.write_text("[/Script/Engine.GameUserSettings]\nFullscreenMode=2\nLastConfirmedFullscreenMode=2\n"
                    "bUseVSync=False\nFrameRateLimit=999\nbUseHDRDisplayOutput=True\n" + unowned)
    with (
        patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=300),
    ):
        handler = Rivals2ConfigHandler()
        settings = profile.get_settings("Rivals2ConfigHandler")
        assert handler.apply(settings)["success"]
        before = path.read_bytes()
        with patch("abso.settings.rivals2_config.atomic_write_text", side_effect=AssertionError("Unnecessary rewrite")):
            assert handler.apply(settings)["applied"] == []
        assert handler.verify_active(settings)["all_active"]
    assert path.read_bytes() == before
    assert path.read_text().endswith(unowned)
    cap = 297 if profile.requires_confirmed_vrr_support else 300
    assert f"FrameRateLimit={cap}\n" in path.read_text()


@pytest.mark.parametrize("profile_class", [Rivals2Profile, Rivals2_300HzMaxProfile])
def test_legacy_aliases_do_not_force_300_on_lower_refresh_displays(profile_class):
    native = profile_class().get_settings("Rivals2ConfigHandler")
    assert "frame_rate_limit" not in native
    assert get_vrr_fps_cap_for_policy(144, native["vrr_cap_policy"]) == 120
