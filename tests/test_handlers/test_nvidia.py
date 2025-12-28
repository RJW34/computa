"""Tests for NvidiaSettingsHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.settings.nvidia import NvidiaSettingsHandler
from abso.settings.nvidia.parsing import (
    parse_low_latency_value,
)
from abso.settings.nvidia.profiles import get_setting_value


class TestNvidiaParsing:
    """Tests for NIP file parsing functions."""

    def test_parse_low_latency_value_off(self):
        """Test parsing low latency 'off' value."""
        assert parse_low_latency_value("0x00000000") == "off"
        assert parse_low_latency_value("0x0") == "off"

    def test_parse_low_latency_value_on(self):
        """Test parsing low latency 'on' value."""
        assert parse_low_latency_value("0x00000001") == "on"
        assert parse_low_latency_value("0x1") == "on"

    def test_parse_low_latency_value_ultra(self):
        """Test parsing low latency 'ultra' value."""
        assert parse_low_latency_value("0x00000002") == "ultra"
        assert parse_low_latency_value("0x2") == "ultra"

    def test_parse_low_latency_value_unknown(self):
        """Test parsing unknown low latency value."""
        assert parse_low_latency_value("0x99999999") == "unknown"
        assert parse_low_latency_value("invalid") == "unknown"


class TestNvidiaProfiles:
    """Tests for profile generation functions."""

    def test_get_setting_value_low_latency_off(self):
        """Test getting decimal value for low latency 'off'."""
        assert get_setting_value("off", "low_latency") == 0

    def test_get_setting_value_low_latency_on(self):
        """Test getting decimal value for low latency 'on'."""
        assert get_setting_value("on", "low_latency") == 1

    def test_get_setting_value_low_latency_ultra(self):
        """Test getting decimal value for low latency 'ultra'."""
        assert get_setting_value("ultra", "low_latency") == 2

    def test_get_setting_value_low_latency_invalid(self):
        """Test getting decimal value for invalid input defaults to 0."""
        assert get_setting_value("invalid", "low_latency") == 0

    def test_get_setting_value_power_management(self):
        """Test getting decimal values for power management settings."""
        assert get_setting_value("adaptive", "power") == 0
        assert get_setting_value("prefer_max_performance", "power") == 1
        assert get_setting_value("optimal", "power") == 2

    def test_get_setting_value_vsync(self):
        """Test getting decimal values for vsync settings."""
        assert get_setting_value("off", "vsync") == 0
        assert get_setting_value("on", "vsync") == 1
        assert get_setting_value("adaptive", "vsync") == 2

    def test_get_setting_value_shader_cache(self):
        """Test getting decimal values for shader cache settings."""
        assert get_setting_value("off", "shader_cache") == 0
        assert get_setting_value("unlimited", "shader_cache") == 4294967295


class TestNvidiaPresets:
    """Tests for Nvidia preset configurations."""

    def test_presets_exist(self):
        """Test that all expected presets exist."""
        from abso.settings.nvidia import NVIDIA_PRESETS

        assert "minimum_latency" in NVIDIA_PRESETS
        assert "low_latency_high_fps" in NVIDIA_PRESETS
        assert "balanced" in NVIDIA_PRESETS

    def test_preset_minimum_latency_settings(self):
        """Test minimum_latency preset has expected settings."""
        from abso.settings.nvidia import NVIDIA_PRESETS

        preset = NVIDIA_PRESETS["minimum_latency"]
        settings = preset.get("settings", {})
        assert settings.get("low_latency_mode") == "ultra"
        assert settings.get("vsync") == "off"
        assert settings.get("power_management") == "prefer_max_performance"

    def test_preset_balanced_settings(self):
        """Test balanced preset has expected settings."""
        from abso.settings.nvidia import NVIDIA_PRESETS

        preset = NVIDIA_PRESETS["balanced"]
        settings = preset.get("settings", {})
        assert settings.get("low_latency_mode") == "on"
        # balanced typically uses adaptive vsync
        assert "vsync" in settings


class TestNvidiaDetect:
    """Tests for detect() method."""

    def test_detect_returns_expected_keys(self):
        """Test detect returns dict with expected keys."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler, "_detect_gpu_info", return_value={"gpu_name": None}):
            with patch.object(handler, "_check_npi_available", return_value=False):
                result = handler.detect()

        assert "driver_version" in result
        assert "gpu_name" in result
        assert "npi_available" in result
        assert "current_settings" in result

    @patch("abso.settings.nvidia.subprocess.run")
    def test_detect_gpu_info_parses_nvidia_smi(self, mock_run):
        """Test _detect_gpu_info parses nvidia-smi output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 4090, 536.23, 24564\n"
        )

        handler = NvidiaSettingsHandler()
        result = handler._detect_gpu_info()

        assert result.get("gpu_name") == "NVIDIA GeForce RTX 4090"
        assert result.get("driver_version") == "536.23"
        assert result.get("vram_total_mb") == 24564

    @patch("abso.settings.nvidia.subprocess.run")
    def test_detect_gpu_info_handles_missing_nvidia_smi(self, mock_run):
        """Test _detect_gpu_info handles missing nvidia-smi."""
        mock_run.side_effect = FileNotFoundError("nvidia-smi not found")

        handler = NvidiaSettingsHandler()
        result = handler._detect_gpu_info()

        assert result.get("gpu_name") is None
        assert result.get("driver_version") is None
