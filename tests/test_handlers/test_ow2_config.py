"""Tests for OW2ConfigHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from abso.settings.ow2_config import OW2ConfigHandler

# Sample Settings_v0.ini content mimicking OW2's real format
SAMPLE_INI = """\
[Render.13]
WindowMode = "1"
FullscreenWindow = "0"
FullscreenWindowEnabled = "0"
WindowedFullscreen = "1"
VerticalSyncEnabled = "1"
LimitToRefresh = "0"
CpuForceSyncEnabled = "0"
UseGPUScale = "1"
FrameRateCap = "60"
RenderScale = "0"
GFXPresetLevel = "3"
EffectsQuality = "3"
TextureDetail = "3"
ModelQuality = "3"
AADetail = "1"
HighQualityUpsample = "1"
TripleBufferingEnabled = "1"
ShowFPSCounter = "0"
ShowIND = "0"

[Sound.1]
MasterVolume = "50"
"""


def _write_settings_ini(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_apply_rejects_unsupported_keys() -> None:
    handler = OW2ConfigHandler()
    result = handler.apply({"crosshair_size": 5})
    assert result["success"] is False
    assert "Unsupported OW2 config keys" in (result.get("error") or "")


def test_apply_updates_allowed_keys(tmp_path: Path) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        result = handler.apply({
            "window_mode": 0,
            "fullscreen_window": False,
            "fullscreen_window_enabled": True,
            "windowed_fullscreen": False,
            "vsync": False,
            "reduce_buffering": True,
            "dynamic_render_scale": False,
            "frame_rate_cap": 400,
            "gfx_preset": 1,
            "effects_quality": 1,
            "texture_detail": 1,
            "model_quality": 1,
            "aa_detail": 0,
            "upscaling": False,
            "triple_buffering": False,
            "show_fps": True,
            "show_latency": True,
        })

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")

    # Verify key=value pairs use OW2's quoted format
    assert 'WindowMode = "0"' in content
    assert 'FullscreenWindow = "0"' in content
    assert 'FullscreenWindowEnabled = "1"' in content
    assert 'WindowedFullscreen = "0"' in content
    assert 'VerticalSyncEnabled = "0"' in content
    assert 'CpuForceSyncEnabled = "1"' in content
    assert 'UseGPUScale = "0"' in content
    assert 'FrameRateCap = "400"' in content
    assert 'GFXPresetLevel = "1"' in content
    assert 'EffectsQuality = "1"' in content
    assert 'TextureDetail = "1"' in content
    assert 'ModelQuality = "1"' in content
    assert 'AADetail = "0"' in content
    assert 'HighQualityUpsample = "0"' in content
    assert 'TripleBufferingEnabled = "0"' in content
    assert 'ShowFPSCounter = "1"' in content
    assert 'ShowIND = "1"' in content

    # Non-render section should be preserved
    assert 'MasterVolume = "50"' in content


def test_apply_appends_missing_keys(tmp_path: Path) -> None:
    # Minimal INI with only a few keys in the render section
    minimal_ini = """\
[Render.13]
WindowMode = "1"

[Sound.1]
MasterVolume = "50"
"""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, minimal_ini)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        result = handler.apply({
            "window_mode": 0,
            "vsync": False,
            "show_fps": True,
        })

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")

    # Updated existing key
    assert 'WindowMode = "0"' in content
    # Appended missing keys
    assert 'VerticalSyncEnabled = "0"' in content
    assert 'ShowFPSCounter = "1"' in content
    # Sound section preserved
    assert "[Sound.1]" in content


def test_apply_preserves_protected_keys(tmp_path: Path) -> None:
    """Protected keys should not be modifiable even if somehow requested."""
    ini_with_sensitivity = """\
[Render.13]
WindowMode = "1"
MouseSensitivity = "15.00"

[Sound.1]
MasterVolume = "50"
"""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, ini_with_sensitivity)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        # Normal apply should not touch protected keys
        result = handler.apply({"window_mode": 0})

    assert result["success"] is True
    content = ini_path.read_text(encoding="utf-8")
    assert 'MouseSensitivity = "15.00"' in content


def test_apply_skips_when_game_not_installed() -> None:
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=None):
        handler = OW2ConfigHandler()
        result = handler.apply({"window_mode": 0})

    assert result["success"] is True
    assert "skipped" in result


def test_detect_parses_quoted_values(tmp_path: Path) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        detected = handler.detect()

    assert detected["config_found"] is True
    assert detected["window_mode"] == 1
    assert detected["fullscreen_window"] == 0
    assert detected["fullscreen_window_enabled"] == 0
    assert detected["windowed_fullscreen"] == 1
    assert detected["vsync"] == 1
    assert detected["reduce_buffering"] == 0
    assert detected["dynamic_render_scale"] == 1
    assert detected["frame_rate_cap"] == 60
    assert detected["gfx_preset"] == 3
    assert detected["aa_detail"] == 1
    assert detected["triple_buffering"] == 1
    assert detected["show_fps"] == 0
    assert detected["show_latency"] == 0


def test_verify_active_reports_mismatch(tmp_path: Path) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        verify = handler.verify_active({
            "window_mode": 0,
            "vsync": False,
            "reduce_buffering": True,
        })

    assert verify["all_active"] is False
    assert verify["settings"]["window_mode"]["active"] is False
    assert verify["settings"]["vsync"]["active"] is False
    assert verify["settings"]["reduce_buffering"]["active"] is False


def test_verify_active_all_match(tmp_path: Path) -> None:
    """When current values match targets, all_active should be True."""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        verify = handler.verify_active({
            "window_mode": 1,  # matches SAMPLE_INI
            "vsync": True,     # "1" == True -> "1"
        })

    # window_mode=1 matches, vsync True -> "1" matches "1"
    assert verify["all_active"] is True


@pytest.mark.parametrize("native_vsync", [0, 1])
def test_vsync_readback_uses_native_key_despite_opposite_legacy_value(
    tmp_path: Path, native_vsync: int,
) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(
        ini_path,
        '[Render.13]\n'
        f'VerticalSyncEnabled = "{native_vsync}"\n'
        f'LimitToRefresh = "{1 - native_vsync}"\n',
    )
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        assert handler.detect()["vsync"] == native_vsync
        assert handler.verify_active({"vsync": bool(native_vsync)})["all_active"] is True
        mismatch = handler.verify_active({"vsync": not native_vsync})
    assert mismatch["all_active"] is False
    assert mismatch["settings"]["vsync"]["current"] == native_vsync


@pytest.mark.parametrize("target", [False, True])
@pytest.mark.parametrize("file_exists", [False, True])
def test_missing_native_vsync_never_verifies_from_legacy_key(
    tmp_path: Path, target: bool, file_exists: bool,
) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    if file_exists:
        _write_settings_ini(ini_path, f'[Render.13]\nLimitToRefresh = "{int(target)}"\n')
    with patch(
        "abso.settings.ow2_config._get_ow2_settings_path",
        return_value=ini_path if file_exists else None,
    ):
        result = OW2ConfigHandler().verify_active({"vsync": target})
    assert result["all_active"] is False
    assert result["settings"]["vsync"] == {
        "current": None, "target": int(target), "active": False,
    }


@pytest.mark.parametrize("target", [False, True])
def test_vsync_apply_preserves_unowned_limit_to_refresh(tmp_path: Path, target: bool) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    legacy_value = 1 - int(target)
    _write_settings_ini(ini_path, f'[Render.13]\nLimitToRefresh = "{legacy_value}"\n')
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        result = handler.apply({"vsync": target})
        assert handler.verify_active({"vsync": target})["all_active"] is True
    assert result["success"] is True
    assert result["applied"] == ["VerticalSyncEnabled"]
    content = ini_path.read_text(encoding="utf-8")
    assert f'VerticalSyncEnabled = "{int(target)}"' in content
    assert f'LimitToRefresh = "{legacy_value}"' in content


def test_restore_native_vsync_preserves_live_legacy_key(tmp_path: Path) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(
        ini_path, '[Render.13]\nVerticalSyncEnabled = "1"\nLimitToRefresh = "1"\n',
    )
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        assert OW2ConfigHandler().restore({
            "config_found": True,
            "file_content": '[Render.13]\nVerticalSyncEnabled = "0"\nLimitToRefresh = "0"\n',
        })
    assert ini_path.read_text(encoding="utf-8") == (
        '[Render.13]\nVerticalSyncEnabled = "0"\nLimitToRefresh = "1"\n'
    )


def test_verify_active_expands_auto_vrr_fps_cap(tmp_path: Path) -> None:
    """auto_vrr_fps_cap must verify the concrete FrameRateCap OW2 sees.

    At 300 Hz the cap is refresh - 3 = 297 (Blur Busters G-SYNC 101).
    """
    ini = SAMPLE_INI.replace('FrameRateCap = "60"', 'FrameRateCap = "297"')
    ini = ini.replace('UseCustomFrameRates = "0"\n', "")
    ini = ini.replace('ShowFPSCounter = "0"', 'UseCustomFrameRates = "1"\nShowFPSCounter = "0"')
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, ini)

    with (
        patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path),
        patch(
            "abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate",
            return_value=300,
        ),
    ):
        verify = OW2ConfigHandler().verify_active({"auto_vrr_fps_cap": True})

    assert verify["all_active"] is True
    assert verify["settings"]["frame_rate_cap"] == {
        "target": 297,
        "current": 297,
        "active": True,
    }
    assert verify["settings"]["use_custom_frame_rates"]["active"] is True


def test_verify_active_preserves_legacy_ow2_reflex_gsync_cap_policy(tmp_path: Path) -> None:
    """Legacy explicit policy retains its old cap; shipped OW2 lanes use refresh_minus_3."""
    ini = SAMPLE_INI.replace('FrameRateCap = "60"', 'FrameRateCap = "276"')
    ini = ini.replace('UseCustomFrameRates = "0"\n', "")
    ini = ini.replace('ShowFPSCounter = "0"', 'UseCustomFrameRates = "1"\nShowFPSCounter = "0"')
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, ini)

    with (
        patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path),
        patch(
            "abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate",
            return_value=300,
        ),
    ):
        verify = OW2ConfigHandler().verify_active({
            "auto_vrr_fps_cap": True,
            "vrr_cap_policy": "ow2_reflex_gsync",
        })

    assert verify["all_active"] is True
    assert verify["settings"]["frame_rate_cap"] == {
        "target": 276,
        "current": 276,
        "active": True,
    }
    assert verify["settings"]["use_custom_frame_rates"]["active"] is True


def test_verify_active_reports_auto_vrr_fps_cap_drift(tmp_path: Path) -> None:
    """A drifted OW2 cap should make state/health verification fail."""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with (
        patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path),
        patch(
            "abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate",
            return_value=300,
        ),
    ):
        verify = OW2ConfigHandler().verify_active({"auto_vrr_fps_cap": True})

    assert verify["all_active"] is False
    assert verify["settings"]["frame_rate_cap"]["target"] == 297
    assert verify["settings"]["frame_rate_cap"]["current"] == 60
    assert verify["settings"]["frame_rate_cap"]["active"] is False


def test_backup_restore_round_trip(tmp_path: Path) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()

        # Backup
        backup_data = handler.backup()
        assert backup_data["config_found"] is True
        assert backup_data["file_content"] == SAMPLE_INI

        # Mutate
        handler.apply({"window_mode": 0, "vsync": False})
        mutated = ini_path.read_text(encoding="utf-8")
        assert 'WindowMode = "0"' in mutated

        # Restore
        ok = handler.restore(backup_data)
        assert ok is True
        restored = ini_path.read_text(encoding="utf-8")
        assert restored == SAMPLE_INI


def test_restore_preserves_current_keybinds_from_stale_backup(tmp_path: Path) -> None:
    """Baseline restores must not revert user keybinds from an older backup."""
    backup_ini = """\
[Render.13]
WindowMode = "0"
KeyBinds = "old-bindings"
KeyBindsV2 = "old-bindings-v2"
MouseSensitivity = "10.00"

[Sound.1]
MasterVolume = "40"
"""
    current_ini = """\
[Render.13]
WindowMode = "1"
KeyBinds = "current-bindings"
KeyBindsV2 = "current-bindings-v2"
MouseSensitivity = "7.50"

[Sound.1]
MasterVolume = "20"
"""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, current_ini)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        ok = handler.restore({
            "config_found": True,
            "config_path": str(ini_path),
            "file_content": backup_ini,
        })

    assert ok is True
    restored = ini_path.read_text(encoding="utf-8")
    assert 'WindowMode = "0"' in restored  # backup restore still restores render baseline
    assert 'MasterVolume = "20"' in restored
    assert 'KeyBinds = "current-bindings"' in restored
    assert 'KeyBindsV2 = "current-bindings-v2"' in restored
    assert 'MouseSensitivity = "7.50"' in restored
    assert "old-bindings" not in restored
    assert 'MouseSensitivity = "10.00"' not in restored


def test_restore_adds_current_keybind_when_backup_lacks_new_key(tmp_path: Path) -> None:
    """If OW2 adds a protected key after the backup, keep the live value."""
    backup_ini = """\
[Render.13]
WindowMode = "0"

[Sound.1]
MasterVolume = "40"
"""
    current_ini = """\
[Render.13]
WindowMode = "1"
KeyBindsV2 = "current-new-format"

[Sound.1]
MasterVolume = "20"
"""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, current_ini)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        ok = handler.restore({
            "config_found": True,
            "config_path": str(ini_path),
            "file_content": backup_ini,
        })

    assert ok is True
    restored = ini_path.read_text(encoding="utf-8")
    assert 'WindowMode = "0"' in restored
    assert 'KeyBindsV2 = "current-new-format"' in restored


@pytest.mark.parametrize("current_mode, backup_mode", [(2, 0), (0, 2), (1, 0), (2, None)])
def test_restore_preserves_manual_reflex_choice(
    tmp_path: Path, current_mode: int, backup_mode: int | None,
) -> None:
    """A stale baseline must not undo a manual Reflex change in either direction."""
    backup_ini = '[Render.13]\nWindowMode = "0"\n'
    if backup_mode is not None:
        backup_ini += f'ReflexMode = "{backup_mode}"\n'
    current_ini = f'[Render.13]\nWindowMode = "1"\nReflexMode = "{current_mode}"\n'
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, current_ini)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        assert OW2ConfigHandler().restore({
            "config_found": True,
            "config_path": str(ini_path),
            "file_content": backup_ini,
        }) is True

    restored = ini_path.read_text(encoding="utf-8")
    assert 'WindowMode = "0"' in restored  # Managed baseline still restores.
    assert f'ReflexMode = "{current_mode}"' in restored
    assert restored.count("ReflexMode") == 1


@pytest.mark.parametrize("live_file_exists", [True, False])
def test_restore_does_not_introduce_reflex_absent_from_live_config(
    tmp_path: Path, live_file_exists: bool,
) -> None:
    """An absent manual setting stays absent, including whole-file recovery."""
    backup_ini = (
        '[Render.13]\nWindowMode = "0"\nReflexMode = "2"\n'
        'KeyBindsV2 = "backup-controls"\n'
    )
    ini_path = tmp_path / "Settings_v0.ini"
    if live_file_exists:
        _write_settings_ini(
            ini_path, '[Render.13]\nWindowMode = "1"\nKeyBindsV2 = "live-controls"\n'
        )

    with patch(
        "abso.settings.ow2_config._get_ow2_settings_path",
        return_value=ini_path if live_file_exists else None,
    ):
        assert OW2ConfigHandler().restore({
            "config_found": True,
            "config_path": str(ini_path),
            "file_content": backup_ini,
        }) is True

    restored = ini_path.read_text(encoding="utf-8")
    assert 'WindowMode = "0"' in restored
    assert "ReflexMode" not in restored
    expected_controls = "live-controls" if live_file_exists else "backup-controls"
    assert f'KeyBindsV2 = "{expected_controls}"' in restored


def test_restore_preserves_all_unmanaged_graphics_calibration_and_sections(tmp_path: Path) -> None:
    """Switching profiles must not undo settings the user changed in the game."""
    baseline = (
        '[Render.13]\nWindowMode = "0"\nFrameRateCap = "60"\n'
        'ReflexMode = "0"\nLocalReflections = "1"\nSimpleDirectionalShadows = "1"\n'
        'MaxTonemapLuminance = "200.0"\nMinTonemapLuminance = "0.0"\n'
        'ObsoleteGameOption = "old"\n[Sound.1]\nMasterVolume = "40"\n'
    )
    current = (
        '[Input.1]\nHighTickInput = "-1"\n\n'
        '[Render.14]\nWindowMode = "1"\nFrameRateCap = "297"\n'
        'ReflexMode = "2"\nLocalReflections = "0"\nSimpleDirectionalShadows = "0"\n'
        'MaxTonemapLuminance = "388.0"\nMinTonemapLuminance = "0.16"\n'
        '; Preserve this comment and future settings\nNewGameOption = "live"\n'
        '[Sound.2]\nMasterVolume = "20"\n'
    )
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, current)
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        assert OW2ConfigHandler().restore({"config_found": True, "file_content": baseline})

    assert ini_path.read_text(encoding="utf-8") == current.replace(
        'WindowMode = "1"', 'WindowMode = "0"'
    ).replace('FrameRateCap = "297"', 'FrameRateCap = "60"')


def test_restore_removes_owned_keys_absent_from_baseline_only_in_render(tmp_path: Path) -> None:
    """An introduced owned key is undone without erasing same-named unrelated data."""
    baseline = '[Render.13]\nWindowMode = "0"\n'
    current = (
        '[Render.13]\nWindowMode = "1"\nFrameRateCap = "297"\n'
        'UseCustomFrameRates = "1"\nLocalReflections = "0"\n'
        '[Unrelated.1]\nFrameRateCap = "20"\n'
    )
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, current)
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        assert OW2ConfigHandler().restore({"config_found": True, "file_content": baseline})

    assert ini_path.read_text(encoding="utf-8") == (
        '[Render.13]\nWindowMode = "0"\nLocalReflections = "0"\n'
        '[Unrelated.1]\nFrameRateCap = "20"\n'
    )


def test_restore_adds_missing_managed_values_without_importing_manual_baseline(tmp_path: Path) -> None:
    baseline = (
        '[Render.13]\nWindowMode = "0"\nFrameRateCap = "60"\n'
        'ReflexMode = "2"\nLocalReflections = "1"\n'
    )
    current = '[Input.1]\nHighTickInput = "-1"\n[Sound.2]\nMasterVolume = "20"\n'
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, current)
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        assert OW2ConfigHandler().restore({"config_found": True, "file_content": baseline})

    restored = ini_path.read_text(encoding="utf-8")
    assert restored.startswith(current)
    assert 'WindowMode = "0"' in restored
    assert 'FrameRateCap = "60"' in restored
    assert "ReflexMode" not in restored
    assert "LocalReflections" not in restored


@pytest.mark.parametrize("baseline", [
    None,
    "",
    '[Sound.1]\nMasterVolume = "40"\n',
    '[Render.13]\nFrameRateCap = 60\n',
    '[Render.13]\nFrameRateCap = "60"\nFrameRateCap = "120"\n',
])
def test_restore_rejects_unusable_baseline_before_writing(tmp_path: Path, baseline: str | None) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)
    with (
        patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path),
        patch.object(Path, "write_text") as write,
    ):
        assert OW2ConfigHandler().restore({"config_found": True, "file_content": baseline}) is False
        write.assert_not_called()
    assert ini_path.read_text(encoding="utf-8") == SAMPLE_INI


def test_restore_does_not_rewrite_unchanged_file(tmp_path: Path) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)
    with (
        patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path),
        patch.object(Path, "write_text") as write,
    ):
        assert OW2ConfigHandler().restore({"config_found": True, "file_content": SAMPLE_INI})
        write.assert_not_called()


def test_apply_idempotent(tmp_path: Path) -> None:
    """Applying the same settings twice should be safe and report no changes."""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()

        # First apply
        result1 = handler.apply({"window_mode": 0})
        assert result1["success"] is True
        assert "WindowMode" in result1["applied"]

        # Second apply — same value, should be no-op
        result2 = handler.apply({"window_mode": 0})
        assert result2["success"] is True
        assert result2.get("applied", []) == []


def test_detect_when_not_installed() -> None:
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=None):
        handler = OW2ConfigHandler()
        detected = handler.detect()

    assert detected["config_found"] is False


def test_audit_flags_suboptimal_settings(tmp_path: Path) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        issues = handler.audit()

    # SAMPLE_INI has vsync=1, reduce_buffering=0, triple_buffering=1, dynamic_render_scale=1
    titles = [i.title for i in issues]
    assert "OW2 VSync enabled in-game" not in titles
    assert "OW2 Reduce Buffering disabled" not in titles
    assert "OW2 Triple Buffering enabled" in titles
    assert "OW2 Dynamic Render Scale enabled" in titles


@pytest.mark.parametrize("reflex_mode", [None, 0, 1, 2])
def test_audit_does_not_treat_reduce_buffering_off_as_universally_wrong(
    tmp_path: Path, reflex_mode: int | None,
) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    content = '[Render.13]\nCpuForceSyncEnabled = "0"\n'
    if reflex_mode is not None:
        content += f'ReflexMode = "{reflex_mode}"\n'
    _write_settings_ini(ini_path, content)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        assert handler.audit() == []
        assert handler.verify_active({"reduce_buffering": False})["all_active"] is True
        assert handler.verify_active({"reduce_buffering": True})["all_active"] is False


def test_apply_native_vsync_on_buffering_off_preserves_other_choices_and_is_idempotent(
    tmp_path: Path,
) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    original = (
        '[Render.13]\nVerticalSyncEnabled = "0"\nCpuForceSyncEnabled = "1"\n'
        'LimitToRefresh = "0"\nReflexMode = "2"\nFrameRateCap = "297"\nHDR = "1"\n'
        'HDRPaperWhite = "203"\nLocalReflections = "0"\n'
        '[Controls.1]\nMouseSensitivity = "7.50"\n'
        '[Sound.1]\nMasterVolume = "50"\n'
    )
    _write_settings_ini(ini_path, original)
    settings = {"vsync": True, "reduce_buffering": False}

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        assert handler.verify_active(settings)["all_active"] is False
        first = handler.apply(settings)
        assert first["success"] is True
        assert first["applied"] == ["CpuForceSyncEnabled", "VerticalSyncEnabled"]
        assert handler.verify_active(settings)["all_active"] is True
        with patch.object(Path, "write_text") as write:
            second = handler.apply(settings)
            assert second["success"] is True
            assert second["applied"] == []
            write.assert_not_called()
        assert handler.verify_active(settings)["all_active"] is True

    expected = original.replace('VerticalSyncEnabled = "0"', 'VerticalSyncEnabled = "1"').replace(
        'CpuForceSyncEnabled = "1"', 'CpuForceSyncEnabled = "0"',
    )
    assert ini_path.read_text(encoding="utf-8") == expected


def test_apply_surfaces_post_write_window_mode_drift(tmp_path: Path) -> None:
    """If OW2 overwrites WindowMode after ABSO writes, apply must surface it.

    Simulates the real failure mode: ABSO writes the INI, then something
    (OW2 itself, or the user in-game) rewrites WindowMode back to 1. The
    handler should report the drift via notices so the caller can flag it
    instead of silently accepting a profile that won't actually engage the
    exclusive-fullscreen path.
    """
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    real_write_text = Path.write_text

    def sabotage_write_text(self, content, *args, **kwargs):
        # Let the handler's write land, then simulate OW2 flipping WindowMode
        # back to borderless before the post-apply drift check runs.
        result = real_write_text(self, content, *args, **kwargs)
        if self == ini_path:
            mutated = self.read_text(encoding="utf-8").replace(
                'WindowMode = "0"',
                'WindowMode = "1"',
            )
            real_write_text(self, mutated, encoding="utf-8")
        return result

    with (
        patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path),
        patch.object(Path, "write_text", sabotage_write_text),
    ):
        handler = OW2ConfigHandler()
        result = handler.apply({"window_mode": 0})

    assert result["success"] is True
    notices = result.get("notices") or []
    assert any("window_mode" in n and "drifted" in n for n in notices), notices


REFLEX_INI = """\
[Render.13]
WindowMode = "1"
VerticalSyncEnabled = "0"
ReflexMode = "2"

[Sound.1]
MasterVolume = "50"
"""


def test_detect_reads_reflex_mode(tmp_path: Path) -> None:
    """ReflexMode is read-only but surfaced so the manual step can be confirmed."""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, REFLEX_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        detected = OW2ConfigHandler().detect()

    assert detected["reflex_mode"] == 2


def test_apply_ignores_expected_reflex_mode(tmp_path: Path) -> None:
    """expected_reflex_mode is advisory: accepted but never written to the INI."""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        result = OW2ConfigHandler().apply({"window_mode": 0, "expected_reflex_mode": 2})

    assert result["success"] is True  # not rejected as an unsupported key
    content = ini_path.read_text(encoding="utf-8")
    assert 'WindowMode = "0"' in content
    assert "ReflexMode" not in content  # ABSO must never write Reflex


def test_verify_reflex_manual_step_satisfied(tmp_path: Path) -> None:
    """A matching ReflexMode is reported satisfied without affecting all_active."""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, REFLEX_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        verify = OW2ConfigHandler().verify_active(
            {"window_mode": 1, "expected_reflex_mode": 2}
        )

    assert verify["all_active"] is True
    steps = verify["manual_steps"]
    assert len(steps) == 1
    assert steps[0]["key"] == "reflex_mode"
    assert steps[0]["satisfied"] is True
    assert steps[0]["current"] == 2
    assert steps[0]["expected_label"] == "Enabled + Boost"
    assert "Options > Video > General > NVIDIA Reflex" in steps[0]["instruction"]
    assert "choose Enabled + Boost" in steps[0]["instruction"]
    assert "does not change" in steps[0]["instruction"]


def test_verify_reflex_manual_step_unsatisfied_is_non_blocking(tmp_path: Path) -> None:
    """An unset Reflex is flagged but must NOT flip the profile to inactive."""
    ini = REFLEX_INI.replace('ReflexMode = "2"', 'ReflexMode = "0"')
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, ini)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        verify = OW2ConfigHandler().verify_active(
            {"window_mode": 1, "expected_reflex_mode": 2}
        )

    # window_mode matches, so the profile is still "active"; Reflex is advisory.
    assert verify["all_active"] is True
    assert verify["manual_steps"][0]["satisfied"] is False
    assert verify["manual_steps"][0]["current_label"] == "Disabled"


@pytest.mark.parametrize("saved_mode,satisfied", [(0, False), (1, True), (2, True), (7, False)])
def test_reflex_enabled_alternatives_preserve_user_choice(
    tmp_path: Path, saved_mode: int, satisfied: bool
) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    content = REFLEX_INI.replace('ReflexMode = "2"', f'ReflexMode = "{saved_mode}"')
    _write_settings_ini(ini_path, content)
    before = ini_path.read_bytes()
    guidance = {"expected_reflex_mode": 1, "accepted_reflex_modes": [1, 2]}
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        applied = handler.apply(guidance)
        verified = handler.verify_active(guidance)
    assert applied["success"] is True
    assert ini_path.read_bytes() == before
    step = verified["manual_steps"][0]
    assert step["satisfied"] is satisfied
    assert step["accepted"] == [1, 2]
    assert step["expected_label"] == "Enabled or Enabled + Boost"
    assert verified["all_active"] is True


@pytest.mark.parametrize("alternatives", [[], "1,2", [True, 2], [1, "2"], [1, 9], None])
def test_invalid_reflex_alternatives_keep_exact_custom_target(
    tmp_path: Path, alternatives: object
) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, REFLEX_INI.replace('ReflexMode = "2"', 'ReflexMode = "1"'))
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        verified = OW2ConfigHandler().verify_active({
            "expected_reflex_mode": 2, "accepted_reflex_modes": alternatives,
        })
    step = verified["manual_steps"][0]
    assert step["accepted"] == [2]
    assert step["satisfied"] is False


def test_reflex_alternatives_do_not_confirm_missing_saved_choice(tmp_path: Path) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)
    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        verified = OW2ConfigHandler().verify_active({
            "expected_reflex_mode": 1, "accepted_reflex_modes": [1, 2],
        })
    assert verified["manual_steps"][0]["satisfied"] is False
    assert verified["manual_steps"][0]["current_label"] == "unknown"


@pytest.mark.parametrize("config_state", ["missing_file", "missing_key", "unreadable"])
def test_verify_reflex_unknown_remains_actionable(tmp_path: Path, config_state: str) -> None:
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)
    if config_state == "unreadable":
        ini_path = tmp_path  # Reading a directory fails, without touching real settings.
    with patch(
        "abso.settings.ow2_config._get_ow2_settings_path",
        return_value=None if config_state == "missing_file" else ini_path,
    ):
        verify = OW2ConfigHandler().verify_active({"expected_reflex_mode": 2})

    step = verify["manual_steps"][0]
    assert step["satisfied"] is False
    assert step["current"] is None
    assert step["current_label"] == "unknown"
    assert "choose Enabled + Boost" in step["instruction"]
    assert verify["all_active"] is True  # Manual guidance remains non-blocking.


def test_apply_reports_no_drift_when_write_holds(tmp_path: Path) -> None:
    """Happy path: no sabotage, no drift notices."""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        result = handler.apply({"window_mode": 0})

    assert result["success"] is True
    assert "notices" not in result or not result["notices"]
