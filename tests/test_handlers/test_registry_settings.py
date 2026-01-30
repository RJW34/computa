"""Tests for registry settings handler."""

from unittest.mock import patch

import pytest

from abso.core.exceptions import RegistryWriteError
from abso.settings.registry import RegistrySettingsHandler


class TestRegistrySettingsHandlerConstants:
    """Tests for RegistrySettingsHandler constants."""

    def test_win32_priority_constants(self):
        """Test Win32PrioritySeparation constants are defined."""
        assert RegistrySettingsHandler.WIN32_PRIORITY_DEFAULT == 0x26
        assert RegistrySettingsHandler.WIN32_PRIORITY_GAMING == 0x2A

    def test_registry_paths_are_strings(self):
        """Test registry paths are defined."""
        assert isinstance(RegistrySettingsHandler.MULTIMEDIA_KEY, str)
        assert isinstance(RegistrySettingsHandler.GAMES_TASK_KEY, str)
        assert isinstance(RegistrySettingsHandler.APPCOMPAT_KEY, str)
        assert isinstance(RegistrySettingsHandler.PRIORITY_CONTROL_KEY, str)


class TestRegistrySettingsHandlerDetect:
    """Tests for detect method."""

    @patch.object(RegistrySettingsHandler, "_get_win32_priority_separation", return_value=0x26)
    @patch.object(RegistrySettingsHandler, "_get_game_priority", return_value={"priority": 6})
    @patch.object(RegistrySettingsHandler, "_get_network_throttling", return_value=0xFFFFFFFF)
    @patch.object(RegistrySettingsHandler, "_get_system_responsiveness", return_value=0)
    def test_detect_returns_expected_keys(self, *mocks):
        """Test detect returns dictionary with expected keys."""
        handler = RegistrySettingsHandler()
        result = handler.detect()

        assert "system_responsiveness" in result
        assert "network_throttling" in result
        assert "game_priority" in result
        assert "win32_priority_separation" in result

    @patch.object(RegistrySettingsHandler, "_get_win32_priority_separation", return_value=0x2A)
    @patch.object(RegistrySettingsHandler, "_get_game_priority", return_value={"priority": 6, "gpu_priority": 8})
    @patch.object(RegistrySettingsHandler, "_get_network_throttling", return_value=0xFFFFFFFF)
    @patch.object(RegistrySettingsHandler, "_get_system_responsiveness", return_value=0)
    def test_detect_optimal_settings(self, *mocks):
        """Test detect with optimal settings."""
        handler = RegistrySettingsHandler()
        result = handler.detect()

        assert result["system_responsiveness"] == 0
        assert result["network_throttling"] == 0xFFFFFFFF
        assert result["game_priority"]["priority"] == 6
        assert result["win32_priority_separation"] == 0x2A


class TestRegistrySettingsHandlerAudit:
    """Tests for audit method."""

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_no_issues_when_optimal(self, mock_detect):
        """Test audit returns no issues when all settings are optimal."""
        mock_detect.return_value = {
            "system_responsiveness": 10,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x2A,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_detects_non_zero_responsiveness(self, mock_detect):
        """Test audit detects non-zero system responsiveness."""
        mock_detect.return_value = {
            "system_responsiveness": 20,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x2A,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        responsiveness_issues = [i for i in issues if "Responsiveness" in i.title]
        assert len(responsiveness_issues) == 1
        assert responsiveness_issues[0].severity == "warning"

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_detects_network_throttling(self, mock_detect):
        """Test audit detects enabled network throttling."""
        mock_detect.return_value = {
            "system_responsiveness": 0,
            "network_throttling": 10,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x2A,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        throttling_issues = [i for i in issues if "throttling" in i.title.lower()]
        assert len(throttling_issues) == 1

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_detects_low_game_priority(self, mock_detect):
        """Test audit detects sub-optimal game priority."""
        mock_detect.return_value = {
            "system_responsiveness": 0,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 2},
            "win32_priority_separation": 0x2A,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        priority_issues = [i for i in issues if "priority" in i.title.lower()]
        assert len(priority_issues) == 1

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_detects_non_gaming_scheduler(self, mock_detect):
        """Test audit detects non-gaming scheduler setting."""
        mock_detect.return_value = {
            "system_responsiveness": 0,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x26,  # Default, not gaming
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        scheduler_issues = [i for i in issues if "scheduler" in i.title.lower()]
        assert len(scheduler_issues) == 1

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_handles_none_values(self, mock_detect):
        """Test audit handles None values gracefully."""
        mock_detect.return_value = {
            "system_responsiveness": None,
            "network_throttling": None,
            "game_priority": {},
            "win32_priority_separation": None,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()
        # Should not raise, may return issues for missing priority
        assert isinstance(issues, list)


class TestRegistrySettingsHandlerApply:
    """Tests for apply method."""

    @patch.object(RegistrySettingsHandler, "_set_win32_priority_separation")
    @patch.object(RegistrySettingsHandler, "_set_fullscreen_optimization")
    @patch.object(RegistrySettingsHandler, "_set_game_priority")
    @patch.object(RegistrySettingsHandler, "_set_network_throttling")
    @patch.object(RegistrySettingsHandler, "_set_system_responsiveness")
    def test_apply_all_settings(self, mock_resp, mock_throttle, mock_priority, mock_fs, mock_sched):
        """Test apply calls all setters."""
        handler = RegistrySettingsHandler()
        result = handler.apply({
            "system_responsiveness": 0,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x2A,
        })

        assert result["success"] is True
        mock_resp.assert_called_once_with(0)
        mock_throttle.assert_called_once_with(0xFFFFFFFF)
        mock_priority.assert_called_once()
        mock_sched.assert_called_once_with(0x2A)

    @patch.object(RegistrySettingsHandler, "_set_system_responsiveness")
    def test_apply_handles_exception(self, mock_set):
        """Test apply handles exceptions gracefully."""
        mock_set.side_effect = Exception("Registry error")

        handler = RegistrySettingsHandler()
        result = handler.apply({"system_responsiveness": 0})

        assert result["success"] is False
        assert "Registry error" in result["error"]

    @patch.object(RegistrySettingsHandler, "_set_fullscreen_optimization")
    def test_apply_fullscreen_optimizations(self, mock_set):
        """Test apply handles fullscreen optimization settings."""
        handler = RegistrySettingsHandler()
        result = handler.apply({
            "fullscreen_optimizations": {
                "C:\\Games\\game.exe": True,
            }
        })

        mock_set.assert_called_once_with("C:\\Games\\game.exe", True)
        assert result["success"] is True


class TestRegistrySettingsHandlerBackupRestore:
    """Tests for backup and restore methods."""

    @patch.object(RegistrySettingsHandler, "detect")
    def test_backup_returns_current_settings(self, mock_detect):
        """Test backup returns current settings."""
        mock_detect.return_value = {
            "system_responsiveness": 20,
            "network_throttling": 10,
            "game_priority": {"priority": 2},
            "win32_priority_separation": 0x26,
        }

        handler = RegistrySettingsHandler()
        backup = handler.backup()

        assert backup == mock_detect.return_value

    @patch.object(RegistrySettingsHandler, "_set_win32_priority_separation")
    @patch.object(RegistrySettingsHandler, "_set_game_priority")
    @patch.object(RegistrySettingsHandler, "_set_network_throttling")
    @patch.object(RegistrySettingsHandler, "_set_system_responsiveness")
    def test_restore_applies_backup_data(self, mock_resp, mock_throttle, mock_priority, mock_sched):
        """Test restore applies backup data."""
        handler = RegistrySettingsHandler()
        result = handler.restore({
            "system_responsiveness": 20,
            "network_throttling": 10,
            "game_priority": {"priority": 2},
            "win32_priority_separation": 0x26,
        })

        assert result is True
        mock_resp.assert_called_once_with(20)
        mock_throttle.assert_called_once_with(10)
        mock_priority.assert_called_once()
        mock_sched.assert_called_once_with(0x26)

    @patch.object(RegistrySettingsHandler, "_set_system_responsiveness")
    def test_restore_handles_exception(self, mock_set):
        """Test restore handles exceptions gracefully."""
        mock_set.side_effect = Exception("Registry error")

        handler = RegistrySettingsHandler()
        result = handler.restore({"system_responsiveness": 20})

        assert result is False


class TestRegistrySettingsHandlerPrivateMethods:
    """Tests for private helper methods."""

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_system_responsiveness_handles_missing_key(self, mock_open):
        """Test _get_system_responsiveness handles missing registry key."""
        mock_open.side_effect = Exception("Key not found")

        handler = RegistrySettingsHandler()
        result = handler._get_system_responsiveness()

        assert result is None

    @patch("abso.settings.registry.winreg.CloseKey")
    @patch("abso.settings.registry.winreg.QueryValueEx")
    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_system_responsiveness_returns_value(self, mock_open, mock_query, mock_close):
        """Test _get_system_responsiveness returns registry value."""
        mock_query.return_value = (20, 1)

        handler = RegistrySettingsHandler()
        result = handler._get_system_responsiveness()

        assert result == 20

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_network_throttling_handles_missing_key(self, mock_open):
        """Test _get_network_throttling handles missing registry key."""
        mock_open.side_effect = Exception("Key not found")

        handler = RegistrySettingsHandler()
        result = handler._get_network_throttling()

        assert result is None

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_game_priority_handles_missing_key(self, mock_open):
        """Test _get_game_priority handles missing registry key."""
        mock_open.side_effect = Exception("Key not found")

        handler = RegistrySettingsHandler()
        result = handler._get_game_priority()

        assert result == {}

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_win32_priority_separation_handles_missing_key(self, mock_open):
        """Test _get_win32_priority_separation handles missing registry key."""
        mock_open.side_effect = Exception("Key not found")

        handler = RegistrySettingsHandler()
        result = handler._get_win32_priority_separation()

        assert result is None

    @patch("abso.settings.registry.winreg.SetValueEx")
    @patch("abso.settings.registry.winreg.CloseKey")
    @patch("abso.settings.registry.winreg.OpenKey")
    def test_set_system_responsiveness_writes_value(self, mock_open, mock_close, mock_set):
        """Test _set_system_responsiveness writes to registry."""
        handler = RegistrySettingsHandler()
        handler._set_system_responsiveness(0)

        mock_set.assert_called_once()

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_set_system_responsiveness_handles_permission_error(self, mock_open):
        """Test _set_system_responsiveness raises on permission error."""
        mock_open.side_effect = PermissionError("Access denied")

        handler = RegistrySettingsHandler()

        with pytest.raises(RegistryWriteError):
            handler._set_system_responsiveness(0)

    @patch("abso.settings.registry.validate_dword_value")
    @patch("abso.settings.registry.winreg.SetValueEx")
    @patch("abso.settings.registry.winreg.CloseKey")
    @patch("abso.settings.registry.winreg.OpenKey")
    def test_set_win32_priority_separation_validates_value(self, mock_open, mock_close, mock_set, mock_validate):
        """Test _set_win32_priority_separation validates the value."""
        handler = RegistrySettingsHandler()
        handler._set_win32_priority_separation(0x2A)

        mock_validate.assert_called_once()
