"""Tests for OW2ConfigHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from abso.settings.ow2_config import OW2ConfigHandler

# Sample Settings_v0.ini content mimicking OW2's real format
SAMPLE_INI = """\
[Render.13]
WindowMode = "1"
FullscreenWindow = "0"
FullscreenWindowEnabled = "0"
WindowedFullscreen = "1"
LimitToRefresh = "1"
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
    assert 'LimitToRefresh = "0"' in content
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
    assert 'LimitToRefresh = "0"' in content
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


def test_verify_active_expands_auto_vrr_fps_cap(tmp_path: Path) -> None:
    """auto_vrr_fps_cap must verify the concrete FrameRateCap OW2 sees."""
    ini = SAMPLE_INI.replace('FrameRateCap = "60"', 'FrameRateCap = "285"')
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
        "target": 285,
        "current": 285,
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
    assert verify["settings"]["frame_rate_cap"]["target"] == 285
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
    assert 'MasterVolume = "40"' in restored
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
    assert "OW2 VSync enabled in-game" in titles
    assert "OW2 Reduce Buffering disabled" in titles
    assert "OW2 Triple Buffering enabled" in titles
    assert "OW2 Dynamic Render Scale enabled" in titles


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


def test_apply_reports_no_drift_when_write_holds(tmp_path: Path) -> None:
    """Happy path: no sabotage, no drift notices."""
    ini_path = tmp_path / "Settings_v0.ini"
    _write_settings_ini(ini_path, SAMPLE_INI)

    with patch("abso.settings.ow2_config._get_ow2_settings_path", return_value=ini_path):
        handler = OW2ConfigHandler()
        result = handler.apply({"window_mode": 0})

    assert result["success"] is True
    assert "notices" not in result or not result["notices"]
