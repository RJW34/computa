"""Fortnite's synchronization policy and manual-setting boundaries."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from abso.profiles.fortnite import (
    FortniteGSyncCaptureProfile,
    FortniteGSyncHDRCaptureProfile,
    FortniteGSyncHDRProfile,
    FortniteHDRProfile,
    FortniteProfile,
)
from abso.settings.fortnite_config import FortniteConfigHandler
from abso.settings.nvidia.presets import NVIDIA_PRESETS

FAMILIES = (FortniteProfile, FortniteHDRProfile, FortniteGSyncHDRProfile,
            FortniteGSyncCaptureProfile, FortniteGSyncHDRCaptureProfile)


@pytest.mark.parametrize("profile_class", FAMILIES)
def test_fortnite_preserves_baseline_system_policy_and_manual_native_settings(profile_class):
    profile = profile_class()
    assert profile.get_settings("PowerSettingsHandler") == {}
    registry = profile.get_settings("RegistrySettingsHandler")
    assert "win32_priority_separation" not in registry
    assert "game_priority" not in registry
    assert profile.get_settings("NicDriverHandler")["nic_tuning"] is False
    assert profile.get_settings("InterruptModeHandler")["enable_msi"] is False
    assert profile.get_settings("GraphicsSettingsHandler")["disable_global_fso"] is False
    assert not any(profile.fullscreen_optimizations_per_exe.values())
    native = profile.get_settings("FortniteConfigHandler")
    assert native["require_reflex"] is True
    assert "hdr_output" not in native and "hdr_nits" not in native
    assert native["frame_rate_limit"] == 0
    assert native.get("auto_vrr_fps_cap", False) is False
    assert set(native) <= {"fullscreen_mode", "vsync", "frame_rate_limit", "auto_vrr_fps_cap", "require_reflex"}


@pytest.mark.parametrize(("profile_class", "capture", "gsync", "hdr"), [
    (FortniteProfile, False, False, False),
    (FortniteHDRProfile, False, False, True),
    (FortniteGSyncHDRProfile, False, True, True),
    (FortniteGSyncCaptureProfile, True, True, False),
    (FortniteGSyncHDRCaptureProfile, True, True, True),
])
def test_fortnite_lanes_have_one_explicit_limiter_and_distinct_presentation(profile_class, capture, gsync, hdr):
    profile = profile_class()
    native = profile.get_settings("FortniteConfigHandler")
    driver = profile.get_settings("NvidiaSettingsHandler")
    preset = NVIDIA_PRESETS[driver["preset"]]["settings"]
    assert native["fullscreen_mode"] == (1 if capture else 0)
    assert native["vsync"] is capture
    assert driver.get("auto_vrr_fps_cap", False) is gsync
    assert preset["low_latency_mode"] == "off"
    assert preset["vsync"] == ("on" if gsync else "off")
    assert profile.allow_dual_limiter is False
    assert profile.get_settings("WindowsSettingsHandler")["hdr"] is hdr
    if capture:
        assert profile.is_capture_safe is True
        assert driver["global_vrr_mode"] == "fullscreen_and_windowed"
        assert profile.get_settings("ProcessPriorityHandler") == {"cpu_priority": 2, "io_priority": 2}
    elif gsync:
        assert driver["global_vrr_mode"] == "fullscreen_only"


@pytest.mark.parametrize("profile_class", FAMILIES)
def test_every_fortnite_apply_preserves_user_options_and_never_forces_native297(tmp_path, profile_class):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "GameUserSettings.ini"
    user_lines = ["LatencyTweak2=1", "bUseHDRDisplayOutput=False", "HDRDisplayOutputNits=750",
                  "FortAntiAliasingMethod=DLSS", "DLSSQuality=3", "bUseNanite=False",
                  "bRayTracing=False", "CustomControl=Keep", "[ScalabilityGroups]",
                  "sg.ResolutionQuality=67", "sg.TextureQuality=1", "[D3DRHIPreference]",
                  "PreferredRHI=dx12", "PreferredFeatureLevel=sm6"]
    path.write_text("[/Script/FortniteGame.FortGameUserSettings]\n"
                    "PreferredFullscreenMode=2\nLastConfirmedFullscreenMode=2\n"
                    "bUseVSync=False\nFrameRateLimit=240\n" + "\n".join(user_lines) + "\n")
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        settings = profile_class().get_settings("FortniteConfigHandler")
        assert handler.apply(settings)["success"]
        first = path.read_bytes()
        assert handler.apply(settings)["applied"] == []
        assert path.read_bytes() == first
        verified = handler.verify_active(settings)
    assert verified["all_active"]
    assert verified["manual_steps"][0]["satisfied"] is True
    assert "FrameRateLimit=0\n" in path.read_text()
    assert "FrameRateLimit=297" not in path.read_text()
    assert path.read_text().endswith("\n".join(user_lines) + "\n")


@pytest.mark.parametrize("profile_class", FAMILIES)
def test_fortnite_guidance_keeps_renderer_and_reflex_manual_and_hdr_unverified(profile_class):
    profile = profile_class()
    rows = {row["setting"]: row for row in profile.get_in_game_settings()}
    assert "On or On + Boost" in rows["NVIDIA Reflex Low Latency"]["value"]
    assert "Performance (DX12)" in rows["Rendering Mode"]["value"]
    assert "manually" in rows["Rendering Mode"]["value"].lower()
    if not profile.is_sdr_only:
        assert "native game HDR unverified" in rows["HDR"]["value"]
        assert "HDR Peak Brightness / Nits" not in rows
