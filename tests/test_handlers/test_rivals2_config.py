"""Tests for Rivals2ConfigHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

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
    assert "bUseRawInput=False" in content
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
        result = handler.apply({"fullscreen_mode": 0, "vsync": False})

    assert result["success"] is True
    assert ini_path.read_text(encoding="utf-8").splitlines() == [
        "[/Script/Rivals2.PlayerSettings]",
        "PlayerTag=goofy",
        "FullscreenMode=2",
        "[/Script/Engine.GameUserSettings]",
        "FullscreenMode=0",
        "bUseVSync=False",
        "bUseRawInput=False",
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
        verify = handler.verify_active({"fullscreen_mode": 0, "vsync": False})

    assert verify["all_active"] is False
    assert verify["settings"]["fullscreen_mode"]["active"] is False
    assert verify["settings"]["vsync"]["active"] is False


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
    """Explicit legacy custom policy remains available (240 at 300 Hz)."""
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


@pytest.mark.parametrize("finite_cap", [999, 1000, 1200])
def test_verify_distinguishes_uncapped_from_finite_caps(tmp_path: Path, finite_cap: int) -> None:
    """UE documents only zero as disabled; high numeric caps remain finite."""
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(ini_path, f"FrameRateLimit={finite_cap}\n")

    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=config_dir):
        handler = Rivals2ConfigHandler()
        verify_zero_target = handler.verify_active({"frame_rate_limit": 0})
        verify_native_target = handler.verify_active({"frame_rate_limit": finite_cap})

    assert verify_zero_target["settings"]["frame_rate_limit"]["active"] is False
    assert verify_zero_target["all_active"] is False
    assert verify_native_target["settings"]["frame_rate_limit"]["active"] is True


def test_verify_real_cap_mismatch_still_reports_drift(tmp_path: Path) -> None:
    """Saved cap readback must expose a different finite target."""
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
                "bUseRawInput=False",
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
        result = handler.apply({"fullscreen_mode": 0, "vsync": False})

        assert backup["config_found"] is True
        assert result["success"] is True

        restored = handler.restore(backup)

    assert restored is True
    assert ini_path.read_text(encoding="utf-8") == original


def test_restore_preserves_current_unmanaged_rivals_values(tmp_path: Path) -> None:
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    backup = (
        "[ScalabilityGroups]\n"
        "sg.TextureQuality=1\n"
        "[/Script/Engine.GameUserSettings]\n"
        "FullscreenMode=0\n"
        "LastConfirmedFullscreenMode=0\n"
        "bUseVSync=False\n"
        "PlayerPreference=old\n"
    )
    current = (
        "[ScalabilityGroups]\n"
        "sg.TextureQuality=3\n"
        "[/Script/Engine.GameUserSettings]\n"
        "FullscreenMode=1\n"
        "LastConfirmedFullscreenMode=1\n"
        "bUseVSync=True\n"
        "FrameRateLimit=240\n"
        "PlayerPreference=current\n"
    )
    _write_game_user_settings(ini_path, current)

    with patch(
        "abso.settings.rivals2_config._get_rivals2_config_dir",
        return_value=config_dir,
    ):
        restored = Rivals2ConfigHandler().restore(
            {
                "config_found": True,
                "config_path": str(ini_path),
                "file_content": backup,
            }
        )

    assert restored is True
    content = ini_path.read_text(encoding="utf-8")
    assert "FullscreenMode=0" in content
    assert "bUseVSync=False" in content
    assert "FrameRateLimit" not in content
    assert "sg.TextureQuality=3" in content
    assert "PlayerPreference=current" in content


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
    assert "bUseRawInput=False" in content
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


def test_missing_target_section_never_reads_or_changes_another_section(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    original = "[Other.Settings]\nFullscreenMode=0\nbUseVSync=False\nFrameRateLimit=297\n"
    _write_game_user_settings(path, original)
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        handler = Rivals2ConfigHandler()
        detected = handler.detect()
        result = handler.apply({"fullscreen_mode": 1, "vsync": True})
        verified = handler.verify_active({"fullscreen_mode": 0, "frame_rate_limit": 297})
    assert detected["config_section_found"] is False
    assert "fullscreen_mode" not in detected
    assert result["success"] is False
    assert "section not found" in result["error"]
    assert verified["all_active"] is False
    assert path.read_text() == original


def test_missing_config_apply_reports_failure(tmp_path: Path) -> None:
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        handler = Rivals2ConfigHandler()
        assert handler.apply({"vsync": True})["success"] is False
        assert handler.apply({})["success"] is True


@pytest.mark.parametrize(("refresh", "policy"), [(None, "refresh_minus_3"), (0, "refresh_minus_3"), (300, "not_a_policy")])
def test_unresolved_auto_cap_does_not_partially_apply_other_settings(tmp_path: Path, refresh, policy) -> None:
    path = tmp_path / "GameUserSettings.ini"
    _write_game_user_settings(path, "bUseVSync=False\nFrameRateLimit=999\n")
    before = path.read_bytes()
    settings = {"vsync": True, "auto_vrr_fps_cap": True, "vrr_cap_policy": policy}
    with (
        patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=refresh),
    ):
        handler = Rivals2ConfigHandler()
        result = handler.apply(settings)
        verified = handler.verify_active(settings)
    assert result["success"] is False
    assert "no settings were written" in result["error"]
    assert path.read_bytes() == before
    assert verified["settings"]["auto_vrr_fps_cap"]["status"] == "unverifiable"
    assert verified["all_active"] is False


def test_refresh_probe_exception_does_not_write_config(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    _write_game_user_settings(path, "bUseVSync=False\n")
    before = path.read_bytes()
    with (
        patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", side_effect=RuntimeError("probe failed")),
    ):
        result = Rivals2ConfigHandler().apply({"vsync": True, "auto_vrr_fps_cap": True})
    assert result["success"] is False
    assert path.read_bytes() == before


def test_restore_preserves_new_controls_graphics_raw_input_and_other_sections(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    original = (
        "[/Script/Engine.GameUserSettings]\nFullscreenMode=1\nbUseVSync=True\n"
        "FrameRateLimit=999\nbUseRawInput=False\nHDRDisplayOutputNits=750\nCustomGraphics=old\n"
        "[Controls]\nPlayerTag=original\nFrameRateLimit=12\n"
    )
    _write_game_user_settings(path, original)
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        handler = Rivals2ConfigHandler()
        backup = handler.backup()
        assert handler.apply({"fullscreen_mode": 0, "vsync": False, "frame_rate_limit": 297, "hdr_output": False})["success"]
        newer = path.read_text().replace("CustomGraphics=old", "CustomGraphics=new").replace("PlayerTag=original", "PlayerTag=new").replace("bUseRawInput=False", "bUseRawInput=True")
        path.write_text(newer)
        assert handler.restore(backup)
        restored = path.read_text()
        assert handler.restore(backup)
        assert path.read_text() == restored
    assert "FullscreenMode=1\n" in restored
    assert "bUseVSync=True\n" in restored
    assert "FrameRateLimit=999\n" in restored
    assert "bUseRawInput=True\n" in restored
    assert "HDRDisplayOutputNits=750\n" in restored
    assert "CustomGraphics=new\n" in restored
    assert "[Controls]\nPlayerTag=new\nFrameRateLimit=12\n" in restored
    # Added managed keys disappear when absent from the baseline.
    assert "LastConfirmedFullscreenMode=" not in restored
    assert "bUseHDRDisplayOutput=" not in restored


def test_restore_with_missing_original_section_does_not_copy_other_section_keys(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    original = "[Other]\nFrameRateLimit=30\n"
    _write_game_user_settings(path, original)
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        handler = Rivals2ConfigHandler()
        backup = handler.backup()
        path.write_text(original + "[/Script/Engine.GameUserSettings]\nFrameRateLimit=297\nbUseRawInput=True\nCustomGraphics=new\n")
        assert handler.restore(backup)
    assert path.read_text() == original + "[/Script/Engine.GameUserSettings]\nbUseRawInput=True\nCustomGraphics=new\n"


def test_restore_recovers_full_file_only_when_current_file_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    original = "[/Script/Engine.GameUserSettings]\nFrameRateLimit=999\nbUseRawInput=False\nCustomGraphics=saved\n"
    handler = Rivals2ConfigHandler()
    assert handler.restore({"config_found": True, "config_path": str(path), "file_content": original})
    assert path.read_text() == original


def test_profile_specific_audit_does_not_warn_for_borderless_or_vsync_on(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    _write_game_user_settings(path, "FullscreenMode=1\nbUseVSync=True\n")
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        handler = Rivals2ConfigHandler()
        assert handler.audit() == []
        assert handler.verify_active({"fullscreen_mode": 1, "vsync": True})["all_active"]


@pytest.mark.parametrize("key", ["raw_input", "undocumented_key"])
def test_unsupported_requests_fail_apply_and_verify_without_writes(tmp_path: Path, key: str) -> None:
    path = tmp_path / "GameUserSettings.ini"
    _write_game_user_settings(path, "bUseRawInput=True\nbUseVSync=False\n")
    before = path.read_bytes()
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        handler = Rivals2ConfigHandler()
        assert handler.apply({key: True, "vsync": True})["success"] is False
        verified = handler.verify_active({key: True})
    assert path.read_bytes() == before
    assert verified["all_active"] is False
    assert verified["settings"][key]["status"] == "unsupported"


@pytest.mark.parametrize("cap", [True, False, -1, 297.5, "nan", "inf", "-inf", None])
def test_invalid_cap_rejects_entire_apply_and_verify(tmp_path: Path, cap) -> None:
    path = tmp_path / "GameUserSettings.ini"
    _write_game_user_settings(path, "FrameRateLimit=0\nbUseVSync=False\n")
    before = path.read_bytes()
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        handler = Rivals2ConfigHandler()
        result = handler.apply({"frame_rate_limit": cap, "vsync": True})
        verified = handler.verify_active({"frame_rate_limit": cap})
    assert result["success"] is False
    assert path.read_bytes() == before
    assert verified["all_active"] is False
    assert verified["settings"]["frame_rate_limit"]["status"] == "invalid"


@pytest.mark.parametrize("saved_cap", ["297.5", "nan", "inf", "-1"])
def test_cap_readback_never_truncates_to_a_matching_integer(tmp_path: Path, saved_cap: str) -> None:
    path = tmp_path / "GameUserSettings.ini"
    _write_game_user_settings(path, f"FrameRateLimit={saved_cap}\n")
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        assert not Rivals2ConfigHandler().verify_active({"frame_rate_limit": 297})["all_active"]


@pytest.mark.parametrize("mode", [True, 3, -1, 1.5, "nan", "inf"])
def test_invalid_fullscreen_mode_does_not_write(tmp_path: Path, mode) -> None:
    path = tmp_path / "GameUserSettings.ini"
    _write_game_user_settings(path, "FullscreenMode=1\n")
    before = path.read_bytes()
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        handler = Rivals2ConfigHandler()
        assert handler.apply({"fullscreen_mode": mode})["success"] is False
        assert not handler.verify_active({"fullscreen_mode": mode})["all_active"]
    assert path.read_bytes() == before


def test_framework_reboot_metadata_is_not_a_native_setting(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    _write_game_user_settings(path, "bUseVSync=True\n")
    before = path.read_bytes()
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        handler = Rivals2ConfigHandler()
        settings = {"vsync": True, "_reboot_pending": True}
        assert handler.apply(settings)["success"]
        verified = handler.verify_active(settings)
    assert verified["all_active"]
    assert "_reboot_pending" not in verified["settings"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("saved_mode", ["1.5", "3", "-1", "nan", "inf"])
def test_invalid_saved_fullscreen_mode_cannot_match_valid_target(tmp_path: Path, saved_mode: str) -> None:
    path = tmp_path / "GameUserSettings.ini"
    _write_game_user_settings(path, f"FullscreenMode={saved_mode}\nbUseVSync=True\n")
    with patch("abso.settings.rivals2_config._get_rivals2_config_dir", return_value=tmp_path):
        verified = Rivals2ConfigHandler().verify_active({"fullscreen_mode": 1, "vsync": True})
    assert verified["all_active"] is False
    assert verified["settings"]["fullscreen_mode"]["status"] == "unverifiable"
    assert verified["settings"]["vsync"]["active"] is True
def test_restore_partial_legacy_payload_preserves_unrecorded_managed_keys(
    tmp_path: Path,
) -> None:
    """Old sparse payloads own only the keys they actually recorded."""
    config_dir = tmp_path / "Rivals2" / "Saved" / "Config" / "Windows"
    ini_path = config_dir / "GameUserSettings.ini"
    _write_game_user_settings(
        ini_path,
        "\n".join(
            [
                "[/Script/Engine.GameUserSettings]",
                "FullscreenMode=1",
                "LastConfirmedFullscreenMode=1",
                "bUseVSync=True",
                "bUseRawInput=True",
                "FrameRateLimit=240.000000",
                "bUseHDRDisplayOutput=True",
                "HDRDisplayOutputNits=800",
                "UnmanagedFutureSetting=keep",
            ]
        )
        + "\n",
    )
    legacy_payload = {
        "config_found": True,
        "config_path": str(ini_path),
        "fullscreen_mode": 0,
        "vsync": False,
    }

    with patch(
        "abso.settings.rivals2_config._get_rivals2_config_dir",
        return_value=config_dir,
    ):
        restored = Rivals2ConfigHandler().restore(legacy_payload)

    assert restored is True
    content = ini_path.read_text(encoding="utf-8")
    assert "FullscreenMode=0" in content
    assert "LastConfirmedFullscreenMode=0" in content
    assert "bUseVSync=False" in content
    assert "bUseRawInput=True" in content
    assert "FrameRateLimit=240.000000" in content
    assert "bUseHDRDisplayOutput=True" in content
    assert "HDRDisplayOutputNits=800" in content
    assert "UnmanagedFutureSetting=keep" in content


