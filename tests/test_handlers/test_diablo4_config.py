"""Tests for Diablo4ConfigHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from abso.settings.diablo4_config import Diablo4ConfigHandler


def _write_local_prefs(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_detect_reads_diablo4_local_prefs(tmp_path: Path) -> None:
    prefs_path = tmp_path / "Documents" / "Diablo IV" / "LocalPrefs.txt"
    _write_local_prefs(
        prefs_path,
        "\n".join(
            [
                'DisplayModeWindowMode "1"',
                'DisplayModeRefreshRate "300"',
                'DisplayModeColorSpace "1"',
                'HDRBlackPoint "0.000100"',
                'HDRWhitePoint "1000.000000"',
                'HDRBrightness "250.000000"',
                'Vsync "0"',
                'Reflex "1"',
                'LimitForegroundFPS "0"',
                'MaxForegroundFPS "0"',
                'LimitBackgroundFPS "1"',
                'MaxBackgroundFPS "60"',
            ]
        ) + "\n",
    )

    with patch("abso.settings.diablo4_config._get_diablo4_local_prefs_path", return_value=prefs_path):
        detected = Diablo4ConfigHandler().detect()

    assert detected["window_mode"] == 1
    assert detected["refresh_rate"] == 300
    assert detected["hdr_output"] is True
    assert detected["hdr_white_point"] == 1000.0
    assert detected["hdr_brightness"] == 250.0
    assert detected["vsync"] is False
    assert detected["reflex"] is True
    assert detected["limit_foreground_fps"] is False
    assert detected["background_fps_limit"] == 60


def test_apply_updates_diablo4_local_prefs(tmp_path: Path) -> None:
    prefs_path = tmp_path / "Documents" / "Diablo IV" / "LocalPrefs.txt"
    _write_local_prefs(
        prefs_path,
        "\n".join(
            [
                'DisplayModeWindowMode "0"',
                'DisplayModeRefreshRate "144"',
                'DisplayModeColorSpace "0"',
                'HDRWhitePoint "500.000000"',
                'HDRBrightness "150.000000"',
                'Vsync "1"',
                'Reflex "0"',
                'LimitForegroundFPS "1"',
                'MaxForegroundFPS "144"',
                'LimitBackgroundFPS "1"',
                'MaxBackgroundFPS "30"',
            ]
        ) + "\n",
    )

    with (
        patch("abso.settings.diablo4_config._get_diablo4_local_prefs_path", return_value=prefs_path),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=300),
    ):
        result = Diablo4ConfigHandler().apply(
            {
                "window_mode": 1,
                "auto_refresh_rate": True,
                "hdr_output": True,
                "hdr_white_point": 1000.0,
                "hdr_brightness": 250.0,
                "vsync": False,
                "reflex": True,
                "limit_foreground_fps": False,
                "foreground_fps_limit": 0,
                "limit_background_fps": True,
                "background_fps_limit": 60,
            }
        )

    assert result["success"] is True
    content = prefs_path.read_text(encoding="utf-8")
    assert 'DisplayModeWindowMode "1"' in content
    assert 'DisplayModeRefreshRate "300"' in content
    assert 'DisplayModeColorSpace "1"' in content
    assert 'HDRWhitePoint "1000.000000"' in content
    assert 'HDRBrightness "250.000000"' in content
    assert 'Vsync "0"' in content
    assert 'Reflex "1"' in content
    assert 'LimitForegroundFPS "0"' in content
    assert 'MaxForegroundFPS "0"' in content
    assert 'LimitBackgroundFPS "1"' in content
    assert 'MaxBackgroundFPS "60"' in content


def test_verify_active_reports_mismatch(tmp_path: Path) -> None:
    prefs_path = tmp_path / "Documents" / "Diablo IV" / "LocalPrefs.txt"
    _write_local_prefs(
        prefs_path,
        "\n".join(
            [
                'DisplayModeWindowMode "0"',
                'DisplayModeColorSpace "0"',
                'Vsync "1"',
                'Reflex "0"',
            ]
        ) + "\n",
    )

    with patch("abso.settings.diablo4_config._get_diablo4_local_prefs_path", return_value=prefs_path):
        verify = Diablo4ConfigHandler().verify_active(
            {
                "window_mode": 1,
                "hdr_output": True,
                "vsync": False,
                "reflex": True,
            }
        )

    assert verify["all_active"] is False
    assert verify["settings"]["window_mode"]["active"] is False
    assert verify["settings"]["hdr_output"]["active"] is False
    assert verify["settings"]["vsync"]["active"] is False
    assert verify["settings"]["reflex"]["active"] is False


def test_restore_rewrites_backed_up_file(tmp_path: Path) -> None:
    prefs_path = tmp_path / "Documents" / "Diablo IV" / "LocalPrefs.txt"
    _write_local_prefs(prefs_path, 'DisplayModeWindowMode "1"\n')

    handler = Diablo4ConfigHandler()
    restored = handler.restore(
        {
            "config_found": True,
            "config_path": str(prefs_path),
            "file_content": 'DisplayModeWindowMode "0"\n',
        }
    )

    assert restored is True
    assert prefs_path.read_text(encoding="utf-8") == 'DisplayModeWindowMode "0"\n'
