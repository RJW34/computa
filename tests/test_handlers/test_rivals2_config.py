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
            }
        )

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")
    assert "PlayerTag=goofy" in content
    assert "DefaultControlScheme=goofy" in content
    assert "FullscreenMode=0" in content
    assert "bUseVSync=False" in content
    assert "bUseRawInput=True" in content
    assert "FrameRateLimit=297" in content


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
