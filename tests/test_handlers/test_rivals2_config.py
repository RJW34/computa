"""Tests for Rivals2ConfigHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from abso.settings.rivals2_config import Rivals2ConfigHandler


def _write_game_user_settings(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_apply_rejects_unsupported_keys(tmp_path: Path) -> None:
    handler = Rivals2ConfigHandler()
    result = handler.apply({"player_tag": "goofy"})
    assert result["success"] is False
    assert "Unsupported Rivals 2 config keys" in (result.get("error") or "")


def test_apply_updates_allowed_keys_and_preserves_protected_keys(tmp_path: Path) -> None:
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "PlayerTag=goofy",
                "DefaultControlScheme=goofy",
                "FullscreenMode=1",
                "bUseVSync=True",
                "bUseRawInput=False",
            ]
        )
        + "\n",
    )

    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir):
        handler = Rivals2ConfigHandler()
        result = handler.apply(
            {
                "fullscreen_mode": 0,
                "vsync": False,
                "raw_input": True,
                "frame_rate_limit": 297,
                "hdr_output": True,
                "hdr_nits": 1000,
            }
        )

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")
    assert "PlayerTag=goofy" in content
    assert "DefaultControlScheme=goofy" in content
    assert "FullscreenMode=0" in content
    assert "LastConfirmedFullscreenMode=0" in content
    assert "bUseVSync=False" in content
    assert "bUseRawInput=True" in content
    assert "FrameRateLimit=297" in content
    assert "bUseHDRDisplayOutput=True" in content
    assert "HDRDisplayOutputNits=1000" in content


def test_apply_updates_only_engine_settings_section_when_present(tmp_path: Path) -> None:
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "[/Script/Rivals2.PlayerSettings]",
                "PlayerTag=goofy",
                "FullscreenMode=2",
                "[/Script/Engine.GameUserSettings]",
                "FullscreenMode=1",
                "bUseVSync=True",
                "bUseRawInput=False",
                "[/Script/Another.Settings]",
                "FullscreenMode=2",
            ]
        )
        + "\n",
    )

    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir):
        handler = Rivals2ConfigHandler()
        result = handler.apply({"fullscreen_mode": 0, "vsync": False, "raw_input": True})

    assert result["success"] is True
    assert ini_path.read_text(encoding="utf-8").splitlines() == [
        "[/Script/Rivals2.PlayerSettings]",
        "PlayerTag=goofy",
        "FullscreenMode=2",
        "[/Script/Engine.GameUserSettings]",
        "FullscreenMode=0",
        "bUseVSync=False",
        "bUseRawInput=True",
        "LastConfirmedFullscreenMode=0",
        "[/Script/Another.Settings]",
        "FullscreenMode=2",
    ]


def test_verify_active_reports_mismatch(tmp_path: Path) -> None:
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "FullscreenMode=1",
                "bUseVSync=True",
                "bUseRawInput=False",
            ]
        )
        + "\n",
    )

    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir):
        handler = Rivals2ConfigHandler()
        verify = handler.verify_active({"fullscreen_mode": 0, "vsync": False, "raw_input": True})

    assert verify["all_active"] is False
    assert verify["settings"]["fullscreen_mode"]["active"] is False
    assert verify["settings"]["vsync"]["active"] is False
    assert verify["settings"]["raw_input"]["active"] is False


def test_apply_auto_vrr_fps_cap_uses_detected_refresh(tmp_path: Path) -> None:
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "FullscreenMode=1",
                "bUseVSync=True",
                "bUseRawInput=False",
                "FrameRateLimit=999",
            ]
        )
        + "\n",
    )

    with (
        patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=300),
    ):
        handler = Rivals2ConfigHandler()
        result = handler.apply({"auto_vrr_fps_cap": True})

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")
    # 300Hz cap = refresh - 3 = 297 (Blur Busters G-SYNC 101 convention).
    assert "FrameRateLimit=297" in content


def test_apply_auto_vrr_fps_cap_honors_fighting_60hz_policy(tmp_path: Path) -> None:
    """Rivals lanes snap the cap to the 60 Hz sim grid (240 @ 300 Hz)."""
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "FullscreenMode=0",
                "bUseVSync=False",
                "FrameRateLimit=999",
            ]
        )
        + "\n",
    )

    with (
        patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=300),
    ):
        handler = Rivals2ConfigHandler()
        result = handler.apply(
            {"auto_vrr_fps_cap": True, "vrr_cap_policy": "fighting_60hz_vrr"}
        )

    assert result["success"] is True
    assert "FrameRateLimit=240" in ini_path.read_text(encoding="utf-8")


def test_apply_nosync_policy_caps_at_refresh_multiple(tmp_path: Path) -> None:
    """The online no-sync lane caps at the largest multiple of 60 <= refresh."""
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(ini_path, "FullscreenMode=0\nFrameRateLimit=0\n")

    with (
        patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=300),
    ):
        handler = Rivals2ConfigHandler()
        result = handler.apply(
            {"auto_vrr_fps_cap": True, "vrr_cap_policy": "fighting_60hz_nosync"}
        )

    assert result["success"] is True
    assert "FrameRateLimit=300" in ini_path.read_text(encoding="utf-8")


def test_verify_treats_0_and_999_frame_rate_as_equivalent_uncapped(tmp_path: Path) -> None:
    """The game's UI writes 999 for uncapped; UE treats 0 the same. No drift."""
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(ini_path, "FrameRateLimit=999\n")

    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir):
        handler = Rivals2ConfigHandler()
        verify_zero_target = handler.verify_active({"frame_rate_limit": 0})
        verify_native_target = handler.verify_active({"frame_rate_limit": 999})

    assert verify_zero_target["settings"]["frame_rate_limit"]["active"] is True
    assert verify_zero_target["all_active"] is True
    assert verify_native_target["settings"]["frame_rate_limit"]["active"] is True


def test_verify_real_cap_mismatch_still_reports_drift(tmp_path: Path) -> None:
    """Uncapped equivalence must not swallow genuine cap drift."""
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(ini_path, "FrameRateLimit=999\n")

    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir):
        handler = Rivals2ConfigHandler()
        verify = handler.verify_active({"frame_rate_limit": 240})

    assert verify["settings"]["frame_rate_limit"]["active"] is False
    assert verify["all_active"] is False


def test_detect_reads_hdr_settings(tmp_path: Path) -> None:
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "FullscreenMode=0",
                "bUseVSync=False",
                "bUseRawInput=True",
                "FrameRateLimit=297",
                "bUseHDRDisplayOutput=True",
                "HDRDisplayOutputNits=1000",
            ]
        )
        + "\n",
    )

    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir):
        handler = Rivals2ConfigHandler()
        detected = handler.detect()

    assert detected["hdr_output"] is True
    assert detected["hdr_nits"] == 1000


def test_backup_restore_round_trip_preserves_unknown_control_keys(tmp_path: Path) -> None:
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    original = "\n".join(
        [
            "[/Script/Rivals2.PlayerSettings]",
            "PlayerTag=goofy",
            "DefaultControlScheme=custom-layout",
            "UnknownControllerBinding=abc123",
            "[/Script/Engine.GameUserSettings]",
            "FullscreenMode=1",
            "bUseVSync=True",
            "bUseRawInput=False",
        ]
    ) + "\n"
    _write_game_user_settings(ini_path, original)

    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir):
        handler = Rivals2ConfigHandler()
        backup = handler.backup()
        result = handler.apply({"fullscreen_mode": 0, "vsync": False, "raw_input": True})

        assert backup["config_found"] is True
        assert result["success"] is True

        restored = handler.restore(backup)

    assert restored is True
    assert ini_path.read_text(encoding="utf-8") == original


def test_restore_falls_back_to_legacy_detect_payload(tmp_path: Path) -> None:
    """Older baseline backups stored detected fields without ``file_content``.

    Those payloads must still restore successfully so that a baseline
    restore (Phase 0 of a profile-switch transaction) does not abort with
    "Handler returned False" against pre-existing user backups.
    """
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "[/Script/Engine.GameUserSettings]",
                "FullscreenMode=1",
                "bUseVSync=True",
                "bUseRawInput=False",
                "FrameRateLimit=240.000000",
            ]
        )
        + "\n",
    )

    legacy_payload = {
        "config_found": True,
        "config_path": str(ini_path),
        "fullscreen_mode": 0,
        "vsync": False,
        "raw_input": True,
        "frame_rate_limit": 999,
        "hdr_output": False,
        "hdr_nits": 1000,
    }

    with patch(
        "abso.settings.rivals2_config._get_rivals2_config_dir",
        return_value=config_dir,
    ):
        handler = Rivals2ConfigHandler()
        restored = handler.restore(legacy_payload)

    assert restored is True
    content = ini_path.read_text(encoding="utf-8")
    assert "FullscreenMode=0" in content
    assert "bUseVSync=False" in content
    assert "bUseRawInput=True" in content
    assert "FrameRateLimit=999" in content


def test_restore_legacy_payload_when_game_uninstalled_is_noop(tmp_path: Path) -> None:
    """A legacy payload must not fail when the live config no longer exists."""
    config_dir = tmp_path / "missing"
    legacy_payload = {
        "config_found": True,
        "config_path": str(config_dir / "GameUserSettings.ini"),
        "fullscreen_mode": 0,
        "vsync": False,
    }

    with patch(
        "abso.settings.rivals2_config._get_rivals2_config_dir",
        return_value=None,
    ):
        handler = Rivals2ConfigHandler()
        restored = handler.restore(legacy_payload)

    assert restored is True
