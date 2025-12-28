"""Tests for nvidia profiles module."""

from pathlib import Path

from abso.settings.nvidia.presets import NVIDIA_PRESETS
from abso.settings.nvidia.profiles import (
    _make_setting_xml,
    generate_custom_profile,
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

    def test_shader_cache_unlimited(self):
        """Test shader_cache 'unlimited' returns max uint32."""
        assert get_setting_value("unlimited", "shader_cache") == 4294967295

    def test_shader_cache_max(self):
        """Test shader_cache 'max' returns max uint32."""
        assert get_setting_value("max", "shader_cache") == 4294967295

    def test_shader_cache_default(self):
        """Test shader_cache 'default' returns 0."""
        assert get_setting_value("default", "shader_cache") == 0

    def test_shader_cache_number(self):
        """Test shader_cache number returns integer."""
        assert get_setting_value("1024", "shader_cache") == 1024

    def test_shader_cache_invalid_returns_zero(self):
        """Test shader_cache invalid value returns 0."""
        assert get_setting_value("invalid", "shader_cache") == 0

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
        xml = _make_setting_xml(17322171, 2)
        assert "17322171" in xml
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
        assert "17322171" in content  # LOW_LATENCY_MODE decimal ID
        assert "<SettingValue>2</SettingValue>" in content

    def test_includes_power_management_setting(self):
        """Test includes power management setting."""
        path = generate_custom_profile({"power_management": "prefer_max_performance"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "17322212" in content  # POWER_MANAGEMENT decimal ID

    def test_includes_vsync_setting(self):
        """Test includes vsync setting."""
        path = generate_custom_profile({"vsync": "adaptive"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "17322232" in content  # VSYNC decimal ID
        assert "<SettingValue>2</SettingValue>" in content

    def test_includes_max_frame_rate_setting(self):
        """Test includes max frame rate setting."""
        path = generate_custom_profile({"max_frame_rate": "144"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "17322487" in content  # MAX_FRAME_RATE decimal ID
        assert "<SettingValue>144</SettingValue>" in content

    def test_includes_shader_cache_setting(self):
        """Test includes shader cache setting."""
        path = generate_custom_profile({"shader_cache": "unlimited"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "17322494" in content  # SHADER_CACHE_SIZE decimal ID
        assert "<SettingValue>4294967295</SettingValue>" in content

    def test_includes_threaded_optimization_setting(self):
        """Test includes threaded optimization setting."""
        path = generate_custom_profile({"threaded_optimization": "on"}, "test")
        content = path.read_text(encoding="utf-16")
        assert "17322472" in content  # THREADED_OPTIMIZATION decimal ID
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
        assert "17322171" in content  # LOW_LATENCY_MODE
        assert "17322232" in content  # VSYNC
        assert "17322212" in content  # POWER_MANAGEMENT

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
        content = path.read_text(encoding="utf-16")
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
        assert "17322232" in content  # VSYNC ID
