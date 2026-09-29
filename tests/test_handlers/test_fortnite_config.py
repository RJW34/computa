"""Tests for FortniteConfigHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from abso.profiles.fortnite import FortniteGSyncHDRCaptureProfile
from abso.settings.fortnite_config import FortniteConfigHandler


def _write_game_user_settings(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_apply_updates_allowed_keys(tmp_path: Path) -> None:
    config_dir = tmp_path / "FortniteGame" / "Saved" / "Config" / "WindowsClient"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "PreferredFullscreenMode=1",
                "LastConfirmedFullscreenMode=1",
                "bUseVSync=True",
                "FrameRateLimit=120.000000",
                "bUseHDRDisplayOutput=False",
                "HDRDisplayOutputNits=1000",
            ]
        )
        + "\n",
    )

    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        result = handler.apply(
            {
                "fullscreen_mode": 0,
                "vsync": False,
                "frame_rate_limit": 0,
            }
        )

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")
    assert "PreferredFullscreenMode=0" in content
    assert "LastConfirmedFullscreenMode=0" in content
    assert "bUseVSync=False" in content
    assert "FrameRateLimit=0" in content
    assert "bUseHDRDisplayOutput=False" in content
    assert "HDRDisplayOutputNits=1000" in content


def test_apply_updates_only_fortnite_settings_section_when_present(tmp_path: Path) -> None:
    config_dir = tmp_path / "FortniteGame" / "Saved" / "Config" / "WindowsClient"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "[/Script/Other.Settings]",
                "PreferredFullscreenMode=2",
                "bUseVSync=True",
                "[/Script/FortniteGame.FortGameUserSettings]",
                "PreferredFullscreenMode=1",
                "LastConfirmedFullscreenMode=1",
                "bUseVSync=True",
                "[/Script/Another.Settings]",
                "PreferredFullscreenMode=2",
            ]
        )
        + "\n",
    )

    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        result = handler.apply({"fullscreen_mode": 0, "vsync": False})

    assert result["success"] is True
    assert ini_path.read_text(encoding="utf-8").splitlines() == [
        "[/Script/Other.Settings]",
        "PreferredFullscreenMode=2",
        "bUseVSync=True",
        "[/Script/FortniteGame.FortGameUserSettings]",
        "PreferredFullscreenMode=0",
        "LastConfirmedFullscreenMode=0",
        "bUseVSync=False",
        "[/Script/Another.Settings]",
        "PreferredFullscreenMode=2",
    ]


def test_detect_and_verify_active_read_current_values(tmp_path: Path) -> None:
    config_dir = tmp_path / "FortniteGame" / "Saved" / "Config" / "WindowsClient"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "PreferredFullscreenMode=0",
                "LastConfirmedFullscreenMode=0",
                "bUseVSync=False",
                "FrameRateLimit=0",
                "bUseHDRDisplayOutput=True",
                "HDRDisplayOutputNits=1000",
            ]
        )
        + "\n",
    )

    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        detected = handler.detect()
        verify = handler.verify_active(
            {
                "fullscreen_mode": 0,
                "vsync": False,
                "frame_rate_limit": 0,
            }
        )

    assert detected["fullscreen_mode"] == 0
    assert detected["vsync"] is False
    assert detected["frame_rate_limit"] == 0
    assert detected["hdr_output_saved"] is True
    assert detected["hdr_nits_saved"] == 1000
    assert "hdr_output" not in detected
    assert verify["all_active"] is True


def test_verify_active_ignores_framework_reboot_pending_key(tmp_path: Path) -> None:
    """The applier threads a synthetic ``_reboot_pending`` key into every
    handler's verify settings. It is not a GameUserSettings.ini key, so the UE
    handler must ignore it; otherwise a critical-verify config handler
    (FortniteConfigHandler.is_critical_verify=True) would falsely roll back a
    correct apply on every profile switch.
    """
    config_dir = tmp_path / "FortniteGame" / "Saved" / "Config" / "WindowsClient"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "PreferredFullscreenMode=0",
                "LastConfirmedFullscreenMode=0",
                "bUseVSync=False",
                "FrameRateLimit=297",
                "bUseHDRDisplayOutput=True",
                "HDRDisplayOutputNits=1000",
            ]
        )
        + "\n",
    )

    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        verify = handler.verify_active(
            {
                "fullscreen_mode": 0,
                "vsync": False,
                "frame_rate_limit": 297,
                # Injected by ProfileApplier._verify_settings for reboot-gated
                # handlers; must not be verified against the INI.
                "_reboot_pending": False,
            }
        )

    assert verify["all_active"] is True
    assert "_reboot_pending" not in verify["settings"]


def test_backup_restore_round_trip(tmp_path: Path) -> None:
    config_dir = tmp_path / "FortniteGame" / "Saved" / "Config" / "WindowsClient"
    ini_path = config_dir / "GameUserSettings.ini"
    original = "\n".join(
        [
            "PreferredFullscreenMode=1",
            "LastConfirmedFullscreenMode=1",
            "bUseVSync=True",
            "FrameRateLimit=240.000000",
            "bUseHDRDisplayOutput=False",
            "HDRDisplayOutputNits=1000",
        ]
    ) + "\n"
    _write_game_user_settings(ini_path, original)

    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        backup = handler.backup()
        result = handler.apply({"fullscreen_mode": 0})

        assert backup["config_found"] is True
        assert result["success"] is True

        restored = handler.restore(backup)

    assert restored is True
    assert ini_path.read_text(encoding="utf-8") == original


def test_restore_preserves_later_user_settings_and_other_sections(tmp_path):
    config_dir = tmp_path / "config"
    ini_path = config_dir / "GameUserSettings.ini"
    original = (
        "[/Script/FortniteGame.FortGameUserSettings]\n"
        "PreferredFullscreenMode=1\n"
        "FrameRateLimit=240.000000\n"
        "DLSSQuality=0\n"
        "bLatencyTweak2=False\n"
        "[Other]\nFrameRateLimit=60\n"
    )
    _write_game_user_settings(ini_path, original)
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        backup = handler.backup()
        assert handler.apply({"fullscreen_mode": 0, "frame_rate_limit": 0})["success"]
        updated = ini_path.read_text().replace("DLSSQuality=0", "DLSSQuality=2")
        updated = updated.replace("bLatencyTweak2=False", "bLatencyTweak2=True")
        updated = updated.replace("[Other]", "NewUserPreference=True\n[Other]")
        ini_path.write_text(updated)
        assert handler.restore(backup)
    restored = ini_path.read_text()
    assert "PreferredFullscreenMode=1" in restored
    assert "FrameRateLimit=240.000000" in restored
    assert "LastConfirmedFullscreenMode" not in restored
    assert "DLSSQuality=2" in restored
    assert "bLatencyTweak2=True" in restored
    assert "NewUserPreference=True" in restored
    assert "[Other]\nFrameRateLimit=60\n" in restored


def test_missing_game_config_cannot_verify_requested_settings():
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=None):
        result = FortniteConfigHandler().verify_active({"vsync": False})
    assert result["all_active"] is False
    assert result["settings"]["vsync"]["current"] is None


def test_unresolved_auto_cap_cannot_verify_active(tmp_path):
    config_dir = tmp_path / "config"
    _write_game_user_settings(config_dir / "GameUserSettings.ini", "FrameRateLimit=0\n")
    with (
        patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir),
        patch.object(FortniteConfigHandler, "_apply_auto_vrr_cap", return_value="No refresh readback"),
    ):
        result = FortniteConfigHandler().verify_active({"auto_vrr_fps_cap": True})
    assert result["all_active"] is False
    assert "No refresh" in result["error"]


def test_streaming_apply_preserves_user_graphics_and_hdr_and_restores(tmp_path: Path) -> None:
    """A future sync repair must preserve graphics choices made in Fortnite."""
    config_dir = tmp_path / "WindowsClient"
    ini_path = config_dir / "GameUserSettings.ini"
    user_owned = [
        "ResolutionSizeX=1920",
        "ResolutionSizeY=1080",
        "bUseHDRDisplayOutput=False",
        "HDRDisplayOutputNits=800",
        "bUseNanite=False",
        "bMotionBlur=False",
        "bUseDynamicResolution=False",
        "LatencyTweak2=2",
        "DLSSQuality=2",
        "bRayTracing=False",
        "[ScalabilityGroups]",
        "sg.ViewDistanceQuality=1",
        "sg.TextureQuality=1",
        "sg.ShadowQuality=0",
        "sg.GlobalIlluminationQuality=0",
        "sg.ReflectionQuality=0",
        "sg.EffectsQuality=0",
        "sg.PostProcessQuality=0",
        "[D3DRHIPreference]",
        "PreferredRHI=dx12",
    ]
    original_lines = [
        "[/Script/FortniteGame.FortGameUserSettings]",
        "PreferredFullscreenMode=0",
        "LastConfirmedFullscreenMode=0",
        "bUseVSync=False",
        "FrameRateLimit=60.000000",
        *user_owned,
    ]
    original = "\n".join(original_lines) + "\n"
    _write_game_user_settings(ini_path, original)
    settings = FortniteGSyncHDRCaptureProfile().get_settings("FortniteConfigHandler")

    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        backup = handler.backup()
        result = handler.apply(settings)
        assert result["success"] is True
        assert ini_path.read_text(encoding="utf-8").splitlines() == [
            "[/Script/FortniteGame.FortGameUserSettings]",
            "PreferredFullscreenMode=1",
            "LastConfirmedFullscreenMode=1",
            "bUseVSync=True",
            "FrameRateLimit=0",
            *user_owned,
        ]
        assert handler.verify_active(settings)["all_active"] is True
        assert handler.apply(settings)["applied"] == []
        assert handler.restore(backup) is True

    assert ini_path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(("raw", "mode", "satisfied"), [
    ("0", 0, False), ("1", 1, True), ("2", 2, True),
    (None, None, None), ("True", None, None), ("3", None, None), ("2.5", None, None),
])
def test_reflex_is_a_saved_manual_check_not_an_apply_target(tmp_path, raw, mode, satisfied):
    config_dir = tmp_path / "config"
    ini_path = config_dir / "GameUserSettings.ini"
    content = "[/Script/FortniteGame.FortGameUserSettings]\nbUseVSync=True\n"
    if raw is not None:
        content += f"LatencyTweak2={raw}\n"
    # Legacy booleans are not evidence for the current three-state setting.
    content += "bLatencyTweak1=True\nbLatencyTweak2=True\n"
    _write_game_user_settings(ini_path, content)
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        verification = handler.verify_active({"vsync": True, "require_reflex": True})
        applied = handler.apply({"vsync": True, "require_reflex": True})
    assert verification["all_active"] is True
    assert "require_reflex" not in verification["settings"]
    step = verification["manual_steps"][0]
    assert step["current"] == mode
    assert step["satisfied"] is satisfied
    assert step["accepted"] == [1, 2]
    assert step["expected_label"] == "On or On + Boost"
    assert "Settings > Video" in step["instruction"]
    assert applied["success"] is True
    assert applied["applied"] == []
    assert applied["manual_steps"] == verification["manual_steps"]
    assert ini_path.read_text() == content


def test_missing_config_reports_unknown_manual_reflex_without_claiming_native_success():
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=None):
        result = FortniteConfigHandler().verify_active({"vsync": True, "require_reflex": True})
    assert result["all_active"] is False
    assert result["manual_steps"][0]["satisfied"] is None
    assert result["manual_steps"][0]["current"] is None


@pytest.mark.parametrize("settings", [
    {"hdr_output": True}, {"hdr_output": False}, {"hdr_nits": 1000},
    {"reflex_mode": 2}, {"LatencyTweak2": 2},
])
def test_unsupported_hdr_or_reflex_requests_fail_before_any_write(tmp_path, settings):
    config_dir = tmp_path / "config"
    ini_path = config_dir / "GameUserSettings.ini"
    original = "bUseVSync=False\nbUseHDRDisplayOutput=False\nHDRDisplayOutputNits=800\nLatencyTweak2=1\n"
    _write_game_user_settings(ini_path, original)
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        result = handler.apply({"vsync": True, **settings})
        verified = handler.verify_active(settings)
    assert result["success"] is False
    assert "Unsupported" in result["error"]
    assert verified["all_active"] is False
    assert ini_path.read_text() == original


def test_old_backup_restore_preserves_newer_hdr_calibration_reflex_and_renderer(tmp_path):
    config_dir = tmp_path / "config"
    ini_path = config_dir / "GameUserSettings.ini"
    original = (
        "[/Script/FortniteGame.FortGameUserSettings]\nPreferredFullscreenMode=0\n"
        "bUseVSync=False\nFrameRateLimit=297\nbUseHDRDisplayOutput=True\n"
        "HDRDisplayOutputNits=1000\nbUseHDRDisplayCalibration=False\nLatencyTweak2=0\n"
        "[D3DRHIPreference]\nPreferredRHI=dx11\nPreferredFeatureLevel=es31\n"
    )
    _write_game_user_settings(ini_path, original)
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        backup = handler.backup()
        assert handler.apply({"fullscreen_mode": 1, "vsync": True, "frame_rate_limit": 0})["success"]
        edited = ini_path.read_text().replace("bUseHDRDisplayOutput=True", "bUseHDRDisplayOutput=False")
        edited = edited.replace("HDRDisplayOutputNits=1000", "HDRDisplayOutputNits=750")
        edited = edited.replace("bUseHDRDisplayCalibration=False", "bUseHDRDisplayCalibration=True")
        edited = edited.replace("LatencyTweak2=0", "LatencyTweak2=1")
        edited = edited.replace("PreferredRHI=dx11", "PreferredRHI=dx12")
        edited = edited.replace("PreferredFeatureLevel=es31", "PreferredFeatureLevel=sm6")
        ini_path.write_text(edited)
        assert handler.restore(backup)
    restored = ini_path.read_text()
    assert "PreferredFullscreenMode=0" in restored and "FrameRateLimit=297" in restored
    assert "bUseVSync=False" in restored
    for line in ("bUseHDRDisplayOutput=False", "HDRDisplayOutputNits=750",
                 "bUseHDRDisplayCalibration=True", "LatencyTweak2=1",
                 "PreferredRHI=dx12", "PreferredFeatureLevel=sm6"):
        assert line in restored


def test_sectioned_file_without_fortnite_section_is_never_used_as_its_settings(tmp_path):
    config_dir = tmp_path / "config"
    ini_path = config_dir / "GameUserSettings.ini"
    original = "[OtherGame]\nbUseVSync=True\nLatencyTweak2=2\n"
    _write_game_user_settings(ini_path, original)
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        verified = handler.verify_active({"vsync": True, "require_reflex": True})
        applied = handler.apply({"vsync": False, "require_reflex": True})
    assert not verified["all_active"]
    assert verified["manual_steps"][0]["satisfied"] is None
    assert not applied["success"]
    assert ini_path.read_text() == original


@pytest.mark.parametrize("mode", [-1, 3, 1.5, True, "fullscreen"])
def test_invalid_fullscreen_enum_cannot_be_written(tmp_path, mode):
    config_dir = tmp_path / "config"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(ini_path, "PreferredFullscreenMode=1\n")
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        result = handler.apply({"fullscreen_mode": mode})
        verified = handler.verify_active({"fullscreen_mode": mode})
    assert not result["success"]
    assert not verified["all_active"]
    assert ini_path.read_text() == "PreferredFullscreenMode=1\n"


@pytest.mark.parametrize("cap", [-1, 0.5, float("nan"), float("inf"), True, "invalid"])
def test_invalid_cap_fails_apply_and_verification_without_writes(tmp_path, cap):
    config_dir = tmp_path / "config"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(ini_path, "FrameRateLimit=1\nbUseVSync=False\n")
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = FortniteConfigHandler()
        result = handler.apply({"frame_rate_limit": cap, "vsync": True})
        verified = handler.verify_active({"frame_rate_limit": cap})
    assert not result["success"]
    assert not verified["all_active"]
    assert verified["settings"]["frame_rate_limit"]["status"] == "invalid_target"
    assert ini_path.read_text() == "FrameRateLimit=1\nbUseVSync=False\n"


@pytest.mark.parametrize(("key", "line", "target"), [
    ("frame_rate_limit", "FrameRateLimit=0.5", 0),
    ("frame_rate_limit", "FrameRateLimit=297.5", 297),
    ("frame_rate_limit", "FrameRateLimit=nan", 0),
    ("fullscreen_mode", "PreferredFullscreenMode=1.5", 1),
])
def test_numeric_readback_never_rounds_into_a_false_match(tmp_path, key, line, target):
    config_dir = tmp_path / "config"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(ini_path, line + "\n")
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=config_dir):
        verified = FortniteConfigHandler().verify_active({key: target})
    assert not verified["all_active"]
    assert not verified["settings"][key]["active"]
