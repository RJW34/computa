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

        with (patch.object(handler, "_detect_gpu_info", return_value={"gpu_name": None}),
              patch.object(handler, "_check_npi_available", return_value=False)):
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

    @patch("abso.settings.nvidia.subprocess.run")
    def test_detect_gpu_info_handles_timeout(self, mock_run):
        """Test _detect_gpu_info handles timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5)

        handler = NvidiaSettingsHandler()
        result = handler._detect_gpu_info()

        assert result.get("gpu_name") is None

    @patch("abso.settings.nvidia.subprocess.run")
    def test_detect_gpu_info_handles_empty_output(self, mock_run):
        """Test _detect_gpu_info handles empty output."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        handler = NvidiaSettingsHandler()
        result = handler._detect_gpu_info()

        assert result.get("gpu_name") is None


class TestNvidiaAudit:
    """Tests for audit() method."""

    def test_audit_returns_npi_not_found_issue(self):
        """Test audit returns issue when NPI not available."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler, "detect", return_value={"npi_available": False}):
            issues = handler.audit()

        npi_issues = [i for i in issues if "Profile Inspector not found" in i.title]
        assert len(npi_issues) == 1

    def test_audit_detects_non_max_power(self):
        """Test audit detects non-maximum power management."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler, "detect", return_value={
            "npi_available": True,
            "current_settings": {"power_management": "adaptive"}
        }):
            issues = handler.audit()

        power_issues = [i for i in issues if "Power Management" in i.title]
        assert len(power_issues) == 1
        assert power_issues[0].severity == "warning"

    def test_audit_detects_low_latency_off(self):
        """Test audit detects low latency mode off."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler, "detect", return_value={
            "npi_available": True,
            "current_settings": {"low_latency_mode": "off"}
        }):
            issues = handler.audit()

        latency_issues = [i for i in issues if "Low Latency" in i.title]
        assert len(latency_issues) == 1

    def test_audit_detects_vsync_on(self):
        """Test audit detects VSync enabled."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler, "detect", return_value={
            "npi_available": True,
            "current_settings": {"vsync": "on"}
        }):
            issues = handler.audit()

        vsync_issues = [i for i in issues if "VSync" in i.title]
        assert len(vsync_issues) == 1

    def test_audit_detects_limited_shader_cache(self):
        """Test audit detects limited shader cache."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler, "detect", return_value={
            "npi_available": True,
            "current_settings": {"shader_cache": "1024MB"}
        }):
            issues = handler.audit()

        cache_issues = [i for i in issues if "Shader Cache" in i.title]
        assert len(cache_issues) == 1

    def test_audit_no_issues_when_optimal(self):
        """Test audit returns no issues when settings are optimal."""
        handler = NvidiaSettingsHandler()

        # VRR-optimal settings: VSync ON is correct with G-SYNC (acts as safety net)
        # See: abso/core/vrr.py for VRR knowledge base
        with patch.object(handler, "detect", return_value={
            "npi_available": True,
            "current_settings": {
                "power_management": "prefer_max_performance",
                "low_latency_mode": "on",  # "on" not "ultra" - ultra overrides FPS caps
                "vsync": "on",  # VRR safety net - doesn't add latency with proper FPS cap
                "shader_cache": "unlimited"
            }
        }):
            issues = handler.audit()

        # VSync "on" still produces an info issue (reminder about FPS cap)
        # but no warnings/criticals - that's the expected optimal state
        warnings_or_higher = [i for i in issues if i.severity in ("warning", "critical")]
        assert len(warnings_or_higher) == 0


class TestNvidiaApply:
    """Tests for apply() method."""

    def test_apply_returns_error_when_npi_unavailable(self):
        """Test apply returns error when NPI is not available."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "is_available", return_value=False):
            result = handler.apply({"preset": "minimum_latency"})

        assert result["success"] is False
        assert "not configured" in result["error"]

    def test_apply_unknown_preset_returns_error(self):
        """Test apply returns error for unknown preset."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "is_available", return_value=True):
            result = handler.apply({"preset": "nonexistent_preset"})

        assert result["success"] is False
        assert "Unknown preset" in result["error"]

    def test_apply_preset_success(self):
        """Test apply preset succeeds."""
        handler = NvidiaSettingsHandler()

        with (patch.object(handler._npi, "is_available", return_value=True),
              patch.object(handler._npi, "import_profile")):
            result = handler.apply({"preset": "minimum_latency"})

        assert result["success"] is True
        assert "minimum_latency" in result["applied"][0]

    def test_apply_profile_path_success(self, tmp_path):
        """Test apply from profile path succeeds."""
        profile_file = tmp_path / "test.nip"
        profile_file.write_text("test", encoding="utf-8")

        handler = NvidiaSettingsHandler()

        with (patch.object(handler._npi, "is_available", return_value=True),
              patch.object(handler._npi, "import_profile")):
            result = handler.apply({"profile_path": str(profile_file)})

        assert result["success"] is True

    def test_apply_profile_path_not_found(self, tmp_path):
        """Test apply from missing profile path fails."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "is_available", return_value=True):
            result = handler.apply({"profile_path": str(tmp_path / "nonexistent.nip")})

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_apply_individual_settings(self):
        """Test apply individual settings."""
        handler = NvidiaSettingsHandler()

        with (patch.object(handler._npi, "is_available", return_value=True),
              patch.object(handler._npi, "import_profile")):
            result = handler.apply({"low_latency_mode": "ultra", "vsync": "off"})

        assert result["success"] is True

    def test_apply_handles_exception(self):
        """Test apply handles exceptions."""
        handler = NvidiaSettingsHandler()

        with (patch.object(handler._npi, "is_available", return_value=True),
              patch.object(handler._npi, "import_profile", side_effect=Exception("NPI error"))):
            result = handler.apply({"preset": "minimum_latency"})

        assert result["success"] is False
        assert "NPI error" in result["error"]


class TestNvidiaBackupRestore:
    """Tests for backup() and restore() methods."""

    def test_backup_when_npi_unavailable(self):
        """Test backup succeeds with note when NPI unavailable."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "is_available", return_value=False):
            result = handler.backup()

        # Backup always succeeds - NPI unavailable just means nothing to backup
        assert result["success"] is True
        assert result["profile_path"] is None
        assert "not available" in result["note"]

    def test_backup_creates_file(self, tmp_path):
        """Test backup creates .nip file."""
        handler = NvidiaSettingsHandler()
        handler.BACKUP_DIR = tmp_path

        with (patch.object(handler._npi, "is_available", return_value=True),
              patch.object(handler._npi, "export_profile"),
              patch.object(handler._npi, "read_current_settings", return_value={})):
            result = handler.backup()

        assert result["success"] is True
        assert result["profile_path"] is not None
        assert "nvidia_backup_" in result["profile_path"]

    def test_backup_handles_exception(self):
        """Test backup succeeds with note when export fails (NPI doesn't support headless export)."""
        handler = NvidiaSettingsHandler()

        with (patch.object(handler._npi, "is_available", return_value=True),
              patch.object(handler._npi, "export_profile", side_effect=Exception("Export failed"))):
            result = handler.backup()

        # Backup always succeeds - export failure just means we note it
        # Nvidia settings can be restored by re-applying the game profile
        assert result["success"] is True
        assert result["profile_path"] is None
        assert result["note"] is not None

    def test_restore_without_profile_path(self):
        """Test restore with no profile_path returns True."""
        handler = NvidiaSettingsHandler()
        result = handler.restore({})

        assert result is True

    def test_restore_missing_file_returns_false(self, tmp_path):
        """Test restore with missing file returns False."""
        handler = NvidiaSettingsHandler()
        result = handler.restore({"profile_path": str(tmp_path / "nonexistent.nip")})

        assert result is False

    def test_restore_applies_profile(self, tmp_path):
        """Test restore applies backup profile."""
        profile_file = tmp_path / "backup.nip"
        profile_file.write_text("test", encoding="utf-8")

        handler = NvidiaSettingsHandler()

        with (patch.object(handler._npi, "is_available", return_value=True),
              patch.object(handler._npi, "import_profile")):
            result = handler.restore({"profile_path": str(profile_file)})

        assert result is True


class TestNvidiaBackwardsCompatibility:
    """Tests for backwards compatibility methods."""

    def test_npi_path_property(self):
        """Test NPI_PATH property returns path."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "get_path", return_value=None):
            assert handler.NPI_PATH is None

    def test_check_npi_available(self):
        """Test _check_npi_available returns boolean."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "is_available", return_value=True):
            assert handler._check_npi_available() is True

    def test_get_setting_value_method(self):
        """Test _get_setting_value method works."""
        handler = NvidiaSettingsHandler()
        assert handler._get_setting_value("ultra", "low_latency") == 2

    def test_import_profile_method(self):
        """Test _import_profile method works."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "import_profile") as mock:
            from pathlib import Path
            handler._import_profile(Path("test.nip"))
            mock.assert_called_once()

    def test_export_profile_method(self):
        """Test _export_profile method works."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "export_profile") as mock:
            from pathlib import Path
            handler._export_profile(Path("test.nip"))
            mock.assert_called_once()
