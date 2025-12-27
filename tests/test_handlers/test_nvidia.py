"""Tests for NvidiaSettingsHandler."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from gametune.settings.nvidia import NvidiaSettingsHandler, NvidiaSettingValues


class TestNvidiaSettingsHandler:
    """Tests for NvidiaSettingsHandler methods."""

    def test_parse_low_latency_value_off(self):
        """Test parsing low latency 'off' value."""
        handler = NvidiaSettingsHandler()
        assert handler._parse_low_latency_value("0x00000000") == "off"
        assert handler._parse_low_latency_value("0x0") == "off"

    def test_parse_low_latency_value_on(self):
        """Test parsing low latency 'on' value."""
        handler = NvidiaSettingsHandler()
        assert handler._parse_low_latency_value("0x00000001") == "on"
        assert handler._parse_low_latency_value("0x1") == "on"

    def test_parse_low_latency_value_ultra(self):
        """Test parsing low latency 'ultra' value."""
        handler = NvidiaSettingsHandler()
        assert handler._parse_low_latency_value("0x00000002") == "ultra"
        assert handler._parse_low_latency_value("0x2") == "ultra"

    def test_parse_low_latency_value_unknown(self):
        """Test parsing unknown low latency value."""
        handler = NvidiaSettingsHandler()
        assert handler._parse_low_latency_value("0x99999999") == "unknown"
        assert handler._parse_low_latency_value("invalid") == "unknown"

    def test_get_low_latency_hex_off(self):
        """Test getting hex value for 'off'."""
        handler = NvidiaSettingsHandler()
        # _get_low_latency_hex returns a hex string format
        assert handler._get_low_latency_hex("off") == "0x00000000"

    def test_get_low_latency_hex_on(self):
        """Test getting hex value for 'on'."""
        handler = NvidiaSettingsHandler()
        assert handler._get_low_latency_hex("on") == "0x00000001"

    def test_get_low_latency_hex_ultra(self):
        """Test getting hex value for 'ultra'."""
        handler = NvidiaSettingsHandler()
        assert handler._get_low_latency_hex("ultra") == "0x00000002"

    def test_get_low_latency_hex_invalid(self):
        """Test getting hex value for invalid input defaults to off."""
        handler = NvidiaSettingsHandler()
        assert handler._get_low_latency_hex("invalid") == "0x00000000"

    def test_presets_exist(self):
        """Test that all expected presets exist."""
        from gametune.settings.nvidia import NVIDIA_PRESETS

        assert "minimum_latency" in NVIDIA_PRESETS
        assert "low_latency_high_fps" in NVIDIA_PRESETS
        assert "balanced" in NVIDIA_PRESETS

    def test_preset_minimum_latency_settings(self):
        """Test minimum_latency preset has expected settings."""
        from gametune.settings.nvidia import NVIDIA_PRESETS

        preset = NVIDIA_PRESETS["minimum_latency"]
        settings = preset.get("settings", {})
        assert settings.get("low_latency_mode") == "ultra"
        assert settings.get("vsync") == "off"
        assert settings.get("power_management") == "prefer_max_performance"

    def test_preset_balanced_settings(self):
        """Test balanced preset has expected settings."""
        from gametune.settings.nvidia import NVIDIA_PRESETS

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

    @patch("gametune.settings.nvidia.subprocess.run")
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

    @patch("gametune.settings.nvidia.subprocess.run")
    def test_detect_gpu_info_handles_missing_nvidia_smi(self, mock_run):
        """Test _detect_gpu_info handles missing nvidia-smi."""
        mock_run.side_effect = FileNotFoundError("nvidia-smi not found")

        handler = NvidiaSettingsHandler()
        result = handler._detect_gpu_info()

        assert result.get("gpu_name") is None
        assert result.get("driver_version") is None
