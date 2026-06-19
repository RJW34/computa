"""Tests for MarvelRivalsConfigHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from abso.settings.marvel_rivals_config import MarvelRivalsConfigHandler


def _write_game_user_settings(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_apply_updates_allowed_keys_and_reflex(tmp_path: Path) -> None:
    config_dir = tmp_path / "Marvel" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "FullscreenMode=1",
                "LastConfirmedFullscreenMode=1",
                "PreferredFullscreenMode=1",
                "bUseVSync=True",
                "FrameRateLimit=120.000000",
                "bUseHDRDisplayOutput=False",
                "HDRDisplayOutputNits=1000",
                "bNvidiaReflex=False",
                "bUseDynamicResolution=True",
                "bDlssFrameGeneration=True",
                "bFSRFrameGeneration=True",
                "bXeFrameGeneration=True",
            ]
        )
        + "\n",
    )

    with patch.object(MarvelRivalsConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = MarvelRivalsConfigHandler()
        result = handler.apply(
            {
                "fullscreen_mode": 0,
                "vsync": False,
                "frame_rate_limit": 297,
                "hdr_output": True,
                "hdr_nits": 1000,
                "nvidia_reflex": True,
                "dynamic_resolution": False,
                "dlss_frame_generation": False,
                "fsr_frame_generation": False,
                "xe_frame_generation": False,
            }
        )

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")
    assert "FullscreenMode=0" in content
    assert "LastConfirmedFullscreenMode=0" in content
    assert "PreferredFullscreenMode=0" in content
    assert "bUseVSync=False" in content
    assert "FrameRateLimit=297" in content
    assert "bUseHDRDisplayOutput=True" in content
    assert "HDRDisplayOutputNits=1000" in content
    assert "bNvidiaReflex=True" in content
    assert "bUseDynamicResolution=False" in content
    assert "bDlssFrameGeneration=False" in content
    assert "bFSRFrameGeneration=False" in content
    assert "bXeFrameGeneration=False" in content


def test_apply_updates_only_marvel_settings_section_when_present(tmp_path: Path) -> None:
    config_dir = tmp_path / "Marvel" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "[/Script/Other.Settings]",
                "FullscreenMode=2",
                "bDlssFrameGeneration=True",
                "[/Script/Marvel.MarvelGameUserSettings]",
                "FullscreenMode=1",
                "bDlssFrameGeneration=True",
                "bUseDynamicResolution=True",
                "[/Script/Another.Settings]",
                "FullscreenMode=2",
                "bDlssFrameGeneration=True",
            ]
        )
        + "\n",
    )

    with patch.object(MarvelRivalsConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = MarvelRivalsConfigHandler()
        result = handler.apply(
            {
                "fullscreen_mode": 0,
                "dlss_frame_generation": False,
                "dynamic_resolution": False,
            }
        )

    assert result["success"] is True
    assert ini_path.read_text(encoding="utf-8").splitlines() == [
        "[/Script/Other.Settings]",
        "FullscreenMode=2",
        "bDlssFrameGeneration=True",
        "[/Script/Marvel.MarvelGameUserSettings]",
        "FullscreenMode=0",
        "bDlssFrameGeneration=False",
        "bUseDynamicResolution=False",
        "LastConfirmedFullscreenMode=0",
        "PreferredFullscreenMode=0",
        "[/Script/Another.Settings]",
        "FullscreenMode=2",
        "bDlssFrameGeneration=True",
    ]


def test_apply_auto_vrr_fps_cap_uses_detected_refresh(tmp_path: Path) -> None:
    config_dir = tmp_path / "Marvel" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "FullscreenMode=0",
                "FrameRateLimit=999",
                "bNvidiaReflex=False",
            ]
        )
        + "\n",
    )

    with (
        patch.object(MarvelRivalsConfigHandler, "_get_config_dir", return_value=config_dir),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=300),
    ):
        handler = MarvelRivalsConfigHandler()
        result = handler.apply({"auto_vrr_fps_cap": True, "nvidia_reflex": True})

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")
    # 300Hz cap = refresh - 3 = 297 (Blur Busters G-SYNC 101 convention).
    assert "FrameRateLimit=297" in content
    assert "bNvidiaReflex=True" in content


def test_apply_auto_vrr_fps_cap_surfaces_notice_when_refresh_unknown(tmp_path: Path) -> None:
    """If refresh detection fails, the in-game cap is skipped WITH a notice.

    The old behavior silently wrote no FrameRateLimit and surfaced nothing, so
    a user could not tell their authoritative in-game cap never landed.
    """
    config_dir = tmp_path / "Marvel" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(ini_path, "FullscreenMode=0\nFrameRateLimit=120\n")

    with (
        patch.object(MarvelRivalsConfigHandler, "_get_config_dir", return_value=config_dir),
        patch(
            "abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate",
            return_value=None,
        ),
    ):
        handler = MarvelRivalsConfigHandler()
        result = handler.apply({"auto_vrr_fps_cap": True})

    assert result["success"] is True
    notices = " ".join(result.get("notices", []))
    assert "auto_vrr_fps_cap" in notices
    # The in-game limiter must be left untouched (no silent 0/garbage cap).
    assert "FrameRateLimit=120" in ini_path.read_text(encoding="utf-8")


def test_detect_and_verify_active_read_current_values(tmp_path: Path) -> None:
    config_dir = tmp_path / "Marvel" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "FullscreenMode=0",
                "LastConfirmedFullscreenMode=0",
                "PreferredFullscreenMode=0",
                "bUseVSync=False",
                "FrameRateLimit=297",
                "bUseHDRDisplayOutput=True",
                "HDRDisplayOutputNits=1000",
                "bNvidiaReflex=True",
                "bUseDynamicResolution=False",
                "bDlssFrameGeneration=False",
                "bFSRFrameGeneration=False",
                "bXeFrameGeneration=False",
            ]
        )
        + "\n",
    )

    with patch.object(MarvelRivalsConfigHandler, "_get_config_dir", return_value=config_dir):
        handler = MarvelRivalsConfigHandler()
        detected = handler.detect()
        verify = handler.verify_active(
            {
                "fullscreen_mode": 0,
                "vsync": False,
                "frame_rate_limit": 297,
                "hdr_output": True,
                "hdr_nits": 1000,
                "nvidia_reflex": True,
                "dynamic_resolution": False,
                "dlss_frame_generation": False,
                "fsr_frame_generation": False,
                "xe_frame_generation": False,
            }
        )

    assert detected["fullscreen_mode"] == 0
    assert detected["vsync"] is False
    assert detected["frame_rate_limit"] == 297
    assert detected["hdr_output"] is True
    assert detected["hdr_nits"] == 1000
    assert detected["nvidia_reflex"] is True
    assert detected["dynamic_resolution"] is False
    assert detected["dlss_frame_generation"] is False
    assert detected["fsr_frame_generation"] is False
    assert detected["xe_frame_generation"] is False
    assert verify["all_active"] is True
