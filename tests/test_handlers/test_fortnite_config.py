"""Tests for FortniteConfigHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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
                "hdr_output": True,
                "hdr_nits": 800,
            }
        )

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")
    assert "PreferredFullscreenMode=0" in content
    assert "LastConfirmedFullscreenMode=0" in content
    assert "bUseVSync=False" in content
    assert "FrameRateLimit=0" in content
    assert "bUseHDRDisplayOutput=True" in content
    assert "HDRDisplayOutputNits=800" in content


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
                "hdr_output": True,
                "hdr_nits": 1000,
            }
        )

    assert detected["fullscreen_mode"] == 0
    assert detected["vsync"] is False
    assert detected["frame_rate_limit"] == 0
    assert detected["hdr_output"] is True
    assert detected["hdr_nits"] == 1000
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
                "hdr_output": True,
                "hdr_nits": 1000,
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
        result = handler.apply({"fullscreen_mode": 0, "hdr_output": True})

        assert backup["config_found"] is True
        assert result["success"] is True

        restored = handler.restore(backup)

    assert restored is True
    assert ini_path.read_text(encoding="utf-8") == original


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
