"""Tests for nvidia profiles module."""

import pytest

from abso.settings.nvidia.presets import NVIDIA_PRESETS
from abso.settings.nvidia.profiles import (
    _build_executables_xml,
    _build_settings_xml,
    _make_setting_xml,
    generate_custom_profile,
    generate_game_profile,
    generate_preset_profile,
    get_setting_value,
)


class TestGetSettingValue:
    """Tests for get_setting_value function."""

    def test_low_latency_off(self):
        """Test low latency 'off' returns 0."""
        assert get_setting_value("off", "low_latency") == 0

    def test_low_latency_on(self):
        """Test low latency 'on' returns 1."""
        assert get_setting_value("on", "low_latency") == 1

    def test_low_latency_ultra(self):
        """Test low latency 'ultra' returns 2."""
        assert get_setting_value("ultra", "low_latency") == 2

    def test_low_latency_case_insensitive(self):
        """Test low latency is case-insensitive."""
        assert get_setting_value("ULTRA", "low_latency") == 2
        assert get_setting_value("Ultra", "low_latency") == 2

    def test_low_latency_unknown_defaults_to_zero(self):
        """Test low latency unknown value defaults to 0."""
        assert get_setting_value("invalid", "low_latency") == 0

    def test_power_adaptive(self):
        """Test power 'adaptive' returns 0."""
        assert get_setting_value("adaptive", "power") == 0

    def test_power_prefer_max_performance(self):
        """Test power 'prefer_max_performance' returns 1."""
        assert get_setting_value("prefer_max_performance", "power") == 1

    def test_power_optimal(self):
        """Test power 'optimal' returns 2."""
        assert get_setting_value("optimal", "power") == 2

    def test_power_unknown_defaults_to_one(self):
        """Test power unknown value defaults to 1 (prefer_max_performance)."""
        assert get_setting_value("invalid", "power") == 1

    def test_vsync_off(self):
        """Test vsync 'off' returns 0."""
        assert get_setting_value("off", "vsync") == 0

    def test_vsync_on(self):
        """Test vsync 'on' returns 1."""
        assert get_setting_value("on", "vsync") == 1

    def test_vsync_adaptive(self):
        """Test vsync 'adaptive' returns 2."""
        assert get_setting_value("adaptive", "vsync") == 2

    def test_vsync_adaptive_half(self):
        """Test vsync 'adaptive_half' returns 3."""
        assert get_setting_value("adaptive_half", "vsync") == 3

    def test_vsync_unknown_defaults_to_zero(self):
        """Test vsync unknown value defaults to 0."""
        assert get_setting_value("invalid", "vsync") == 0

    def test_framerate_off(self):
        """Test framerate 'off' returns 0."""
        assert get_setting_value("off", "framerate") == 0

    def test_framerate_number(self):
        """Test framerate number returns integer."""
        assert get_setting_value("60", "framerate") == 60
        assert get_setting_value("144", "framerate") == 144
        assert get_setting_value("240", "framerate") == 240

    def test_framerate_invalid_returns_zero(self):
        """Test framerate invalid value returns 0."""
        assert get_setting_value("not_a_number", "framerate") == 0

    def test_shader_cache_off(self):
        """Test shader_cache 'off' returns 0."""
        assert get_setting_value("off", "shader_cache") == 0

    def test_shader_cache_on(self):
        assert get_setting_value("on", "shader_cache") == 1

    def test_shader_cache_default(self):
        """NIP defaults to the SDK's enabled value, never disabled size zero."""
        assert get_setting_value("default", "shader_cache") == 1

    @pytest.mark.parametrize("value", ["unlimited", "max", "1024", "invalid", "2"])
    def test_shader_cache_size_is_not_an_enabled_enum(self, value):
        with pytest.raises(ValueError, match="global settings"):
            get_setting_value(value, "shader_cache")

    def test_threaded_auto(self):
        """Test threaded 'auto' returns 0."""
        assert get_setting_value("auto", "threaded") == 0

    def test_threaded_on(self):
        """Test threaded 'on' returns 1."""
        assert get_setting_value("on", "threaded") == 1

    def test_threaded_off(self):
        """Test threaded 'off' returns 2."""
        assert get_setting_value("off", "threaded") == 2

    def test_unknown_type_returns_zero(self):
        """Test unknown setting type returns 0."""
        assert get_setting_value("anything", "unknown_type") == 0


class TestMakeSettingXml:
    """Tests for _make_setting_xml function."""

    def test_creates_valid_xml(self):
        """Test creates valid XML structure."""
        xml = _make_setting_xml(12345, 67890)
        assert "<ProfileSetting>" in xml
        assert "<SettingID>12345</SettingID>" in xml
        assert "<SettingValue>67890</SettingValue>" in xml
        assert "</ProfileSetting>" in xml

    def test_uses_decimal_format(self):
        """Test uses decimal format for IDs and values."""
        xml = _make_setting_xml(8102046, 2)
        assert "8102046" in xml
        assert "0x" not in xml


class TestGenerateCustomProfile:
    """Tests for generate_custom_profile function."""

    def test_generates_file(self):
        """Test generates a .nip file."""
        path = generate_custom_profile({"low_latency_mode": "ultra"}, "test_profile")
        assert path.exists()
        assert path.suffix == ".nip"
        assert "test_profile" in path.name

    def test_file_contains_xml(self):
        """Test generated file contains valid XML."""
        path = generate_custom_profile({"vsync": "off"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "<?xml version=" in content
        assert "<ArrayOfProfile>" in content
        assert "</ArrayOfProfile>" in content

    def test_includes_low_latency_setting(self):
        """Test includes low latency setting in output."""
        path = generate_custom_profile({"low_latency_mode": "ultra"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "8102046" in content  # LOW_LATENCY_MODE decimal ID (0x007BA09E)
        assert "<SettingValue>2</SettingValue>" in content

    def test_includes_power_management_setting(self):
        """Test includes power management setting."""
        path = generate_custom_profile({"power_management": "prefer_max_performance"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "274197361" in content  # POWER_MANAGEMENT decimal ID (0x1057EB71)

    def test_includes_vsync_setting(self):
        """Test includes vsync setting."""
        path = generate_custom_profile({"vsync": "adaptive"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "11041231" in content  # VSYNC decimal ID (0x00A879CF)
        assert "<SettingValue>2</SettingValue>" in content

    def test_includes_max_frame_rate_setting(self):
        """Test includes max frame rate setting."""
        path = generate_custom_profile({"max_frame_rate": "144"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "277041154" in content  # MAX_FRAME_RATE decimal ID (0x10835002)
        assert "<SettingValue>144</SettingValue>" in content

    def test_includes_shader_cache_setting(self):
        """Test includes shader cache setting."""
        path = generate_custom_profile({"shader_cache": "on"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "1675263" in content  # PS_SHADERDISKCACHE_ID (0x00198FFF)
        assert "<SettingValue>1</SettingValue>" in content
        assert "4294967295" not in content

    def test_includes_threaded_optimization_setting(self):
        """Test includes threaded optimization setting."""
        path = generate_custom_profile({"threaded_optimization": "on"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "549528094" in content  # THREADED_OPTIMIZATION decimal ID (0x20C1221E)
        assert "<SettingValue>1</SettingValue>" in content

    def test_includes_multiple_settings(self):
        """Test includes multiple settings."""
        settings = {
            "low_latency_mode": "ultra",
            "vsync": "off",
            "power_management": "prefer_max_performance",
        }
        path = generate_custom_profile(settings, "test")
        content = path.read_text(encoding="utf-16")
        assert "8102046" in content  # LOW_LATENCY_MODE (0x007BA09E)
        assert "11041231" in content  # VSYNC (0x00A879CF)
        assert "274197361" in content  # POWER_MANAGEMENT (0x1057EB71)

    def test_empty_settings(self):
        """Test handles empty settings."""
        path = generate_custom_profile({}, "empty")
        content = path.read_text(encoding="utf-16")
        assert "<ArrayOfProfile>" in content
        assert "<Settings>" in content

    def test_creates_temp_directory(self):
        """Test creates temp directory if needed."""
        path = generate_custom_profile({"vsync": "off"}, "test")
        assert path.parent.exists()
        assert path.parent.name == "abso_nvidia"


class TestGeneratePresetProfile:
    """Tests for generate_preset_profile function."""

    def test_generates_minimum_latency_preset(self):
        """Test generates minimum_latency preset."""
        path = generate_preset_profile("minimum_latency")
        assert path.exists()
        content = path.read_text(encoding="utf-16")
        # Should have low latency ultra (2)
        assert "<SettingValue>2</SettingValue>" in content

    def test_generates_balanced_preset(self):
        """Test generates balanced preset."""
        path = generate_preset_profile("balanced")
        assert path.exists()
        assert "abso_balanced" in path.name

    def test_uses_preset_from_dict(self):
        """Test uses preset from NVIDIA_PRESETS dict."""
        for preset_name in NVIDIA_PRESETS:
            path = generate_preset_profile(preset_name)
            assert path.exists()

    def test_unknown_preset_returns_empty_profile(self):
        """Test unknown preset returns profile with no settings."""
        path = generate_preset_profile("nonexistent_preset")
        content = path.read_text(encoding="utf-16")
        # Should still create valid XML, just with empty settings
        assert "<ArrayOfProfile>" in content

    def test_custom_preset_dict(self):
        """Test accepts custom preset dict."""
        custom_preset = {
            "settings": {
                "vsync": "on",
                "low_latency_mode": "off",
            }
        }
        path = generate_preset_profile("custom", preset=custom_preset)
        content = path.read_text(encoding="utf-16")
        assert "abso_custom" in path.name
        # vsync on = 1
        assert "11041231" in content  # VSYNC ID


class TestBuildExecutablesXml:
    """Tests for _build_executables_xml function."""

    def test_single_executable(self):
        """Test single executable generates correct XML."""
        xml = _build_executables_xml(["Game.exe"])
        assert "<string>Game.exe</string>" in xml

    def test_multiple_executables(self):
        """Test multiple executables generates correct XML."""
        xml = _build_executables_xml(["Game.exe", "Game-Shipping.exe", "launcher.exe"])
        assert "<string>Game.exe</string>" in xml
        assert "<string>Game-Shipping.exe</string>" in xml
        assert "<string>launcher.exe</string>" in xml

    def test_empty_list_returns_empty_string(self):
        """Test empty list returns empty string."""
        xml = _build_executables_xml([])
        assert xml == ""

    def test_executables_on_separate_lines(self):
        """Test executables are on separate lines."""
        xml = _build_executables_xml(["a.exe", "b.exe"])
        # Should have newlines between entries
        assert "\n" in xml


class TestBuildSettingsXml:
    """Tests for _build_settings_xml function."""

    def test_single_setting(self):
        """Test single setting generates correct XML."""
        xml = _build_settings_xml({"low_latency_mode": "ultra"})
        assert "8102046" in xml  # LOW_LATENCY_MODE decimal ID
        assert "<SettingValue>2</SettingValue>" in xml

    def test_multiple_settings(self):
        """Test multiple settings generates correct XML."""
        xml = _build_settings_xml({
            "low_latency_mode": "ultra",
            "vsync": "off",
            "power_management": "prefer_max_performance",
        })
        assert "8102046" in xml  # LOW_LATENCY_MODE
        assert "11041231" in xml  # VSYNC
        assert "274197361" in xml  # POWER_MANAGEMENT

    def test_empty_settings_returns_empty_string(self):
        """Test empty settings returns empty string."""
        xml = _build_settings_xml({})
        assert xml == ""


class TestGenerateGameProfile:
    """Tests for generate_game_profile function."""

    def test_generates_file(self):
        """Test generates a .nip file."""
        path = generate_game_profile(
            {"low_latency_mode": "ultra"},
            ["Game.exe"],
            "Test Game"
        )
        assert path.exists()
        assert path.suffix == ".nip"
        assert "abso_game_" in path.name

    def test_includes_game_name_in_profile(self):
        """Test includes game name in profile name."""
        path = generate_game_profile(
            {"vsync": "off"},
            ["Game.exe"],
            "Rivals of Aether 2"
        )
        content = path.read_text(encoding="utf-16")
        assert "<ProfileName>ABSO - Rivals of Aether 2</ProfileName>" in content

    def test_includes_executables(self):
        """Test includes executables in XML."""
        path = generate_game_profile(
            {"vsync": "off"},
            ["RivalsofAether2.exe", "RivalsOfAether2-Win64-Shipping.exe"],
            "Rivals 2"
        )
        content = path.read_text(encoding="utf-16")
        assert "<string>RivalsofAether2.exe</string>" in content
        assert "<string>RivalsOfAether2-Win64-Shipping.exe</string>" in content

    def test_includes_settings(self):
        """Test includes settings in XML."""
        path = generate_game_profile(
            {"low_latency_mode": "ultra", "vsync": "off"},
            ["Game.exe"],
            "Test"
        )
        content = path.read_text(encoding="utf-16")
        assert "8102046" in content  # LOW_LATENCY_MODE
        assert "11041231" in content  # VSYNC

    def test_file_is_utf16_encoded(self):
        """Test file is UTF-16 encoded."""
        path = generate_game_profile(
            {"vsync": "off"},
            ["Game.exe"],
            "Test"
        )
        # Should be able to read as UTF-16
        content = path.read_text(encoding="utf-16")
        assert "<?xml version=" in content

    def test_safe_filename_generation(self):
        """Test creates safe filename from game name."""
        path = generate_game_profile(
            {"vsync": "off"},
            ["Game.exe"],
            "Marvel Rivals: HDR"
        )
        assert "marvel_rivals_hdr" in path.name.lower()
        assert ":" not in path.name

    def test_multiple_executables_in_file(self):
        """Test multiple executables are all included."""
        executables = [
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "brave.exe",
        ]
        path = generate_game_profile(
            {"vsync": "adaptive"},
            executables,
            "Browser Game"
        )
        content = path.read_text(encoding="utf-16")
        for exe in executables:
            assert f"<string>{exe}</string>" in content

    def test_executeables_element_present(self):
        """Test Executeables element is present (NPI spelling)."""
        path = generate_game_profile(
            {"vsync": "off"},
            ["Game.exe"],
            "Test"
        )
        content = path.read_text(encoding="utf-16")
        assert "<Executeables>" in content
        assert "</Executeables>" in content

    def test_not_base_profile(self):
        """Test does not use Base Profile name."""
        path = generate_game_profile(
            {"vsync": "off"},
            ["Game.exe"],
            "My Game"
        )
        content = path.read_text(encoding="utf-16")
        assert "Base Profile" not in content
        assert "ABSO - My Game" in content
