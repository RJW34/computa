"""Tests for MemorySettingsHandler."""

import winreg
from unittest.mock import MagicMock, patch

from abso.settings.memory import MemorySettingsHandler


class TestMemoryDetect:
    """Tests for MemorySettingsHandler.detect()."""

    @patch.object(MemorySettingsHandler, "_get_large_system_cache")
    @patch.object(MemorySettingsHandler, "_get_disable_paging_executive")
    @patch.object(MemorySettingsHandler, "_get_clear_page_file_at_shutdown")
    def test_detect_returns_expected_keys(self, mock_clear, mock_paging, mock_cache):
        """Test detect returns dictionary with all expected keys."""
        mock_cache.return_value = 0
        mock_paging.return_value = 1
        mock_clear.return_value = 0

        handler = MemorySettingsHandler()
        result = handler.detect()

        assert "large_system_cache" in result
        assert "disable_paging_executive" in result
        assert "clear_page_file_at_shutdown" in result

    @patch("abso.settings.memory.winreg")
    def test_get_large_system_cache(self, mock_winreg):
        """Test _get_large_system_cache reads registry value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (0, winreg.REG_DWORD)
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = MemorySettingsHandler()
        result = handler._get_large_system_cache()

        assert result == 0


class TestMemoryAudit:
    """Tests for MemorySettingsHandler.audit()."""

    @patch.object(MemorySettingsHandler, "detect")
    def test_audit_large_cache_enabled_creates_info(self, mock_detect):
        """Test audit creates info when Large System Cache is enabled."""
        mock_detect.return_value = {
            "large_system_cache": 1,
            "disable_paging_executive": 1,
            "clear_page_file_at_shutdown": 0,
        }

        handler = MemorySettingsHandler()
        issues = handler.audit()

        cache_issues = [i for i in issues if "Large System Cache" in i.title]
        assert len(cache_issues) == 1
        assert cache_issues[0].severity == "info"

    @patch.object(MemorySettingsHandler, "detect")
    def test_audit_legacy_kernel_residency_missing_creates_info(self, mock_detect):
        """Test audit creates info when legacy kernel-residency tweak is absent."""
        mock_detect.return_value = {
            "large_system_cache": 0,
            "disable_paging_executive": 0,  # Paging allowed
            "clear_page_file_at_shutdown": 0,
        }

        handler = MemorySettingsHandler()
        issues = handler.audit()

        paging_issues = [i for i in issues if "kernel-residency" in i.title.lower()]
        assert len(paging_issues) == 1
        assert paging_issues[0].severity == "info"
        assert paging_issues[0].optimal_value == "Leave default unless explicitly testing legacy tweak"

    @patch.object(MemorySettingsHandler, "detect")
    def test_audit_profile_target_settings_minimal_issues(self, mock_detect):
        """Test audit returns minimal issues when settings match the profile target."""
        mock_detect.return_value = {
            "large_system_cache": 0,
            "disable_paging_executive": 1,
            "clear_page_file_at_shutdown": 0,
        }

        handler = MemorySettingsHandler()
        issues = handler.audit()

        # Should have no issues when values match the explicit profile target.
        assert len(issues) == 0


class TestMemoryApply:
    """Tests for MemorySettingsHandler.apply()."""

    @patch.object(MemorySettingsHandler, "detect")
    @patch.object(MemorySettingsHandler, "_set_large_system_cache")
    def test_apply_disables_large_cache(self, mock_set_cache, mock_detect):
        """Test apply can disable Large System Cache."""
        # detect() returns different value so setter is called
        mock_detect.return_value = {"large_system_cache": 1, "disable_paging_executive": 1}

        handler = MemorySettingsHandler()
        result = handler.apply({"large_system_cache": 0})

        assert result["success"] is True
        mock_set_cache.assert_called_once_with(0)

    @patch.object(MemorySettingsHandler, "detect")
    @patch.object(MemorySettingsHandler, "_set_disable_paging_executive")
    def test_apply_disables_paging(self, mock_set_paging, mock_detect):
        """Test apply can disable kernel paging."""
        # detect() returns different value so setter is called
        mock_detect.return_value = {"large_system_cache": 0, "disable_paging_executive": 0}

        handler = MemorySettingsHandler()
        result = handler.apply({"disable_paging_executive": 1})

        assert result["success"] is True
        mock_set_paging.assert_called_once_with(1)

    @patch.object(MemorySettingsHandler, "detect")
    @patch.object(MemorySettingsHandler, "_set_large_system_cache")
    def test_apply_handles_permission_error(self, mock_set_cache, mock_detect):
        """Test apply handles permission errors."""
        mock_detect.return_value = {"large_system_cache": 1, "disable_paging_executive": 1}
        mock_set_cache.side_effect = PermissionError("Access denied")

        handler = MemorySettingsHandler()
        result = handler.apply({"large_system_cache": 0})

        assert result["success"] is False
        assert "Permission" in result["error"]

    @patch.object(MemorySettingsHandler, "detect")
    @patch.object(MemorySettingsHandler, "_set_large_system_cache")
    def test_apply_requires_reboot(self, mock_set_cache, mock_detect):
        """Test apply indicates reboot is required."""
        # detect() returns different value so reboot is required
        mock_detect.return_value = {"large_system_cache": 1, "disable_paging_executive": 1}

        handler = MemorySettingsHandler()
        result = handler.apply({"large_system_cache": 0})

        assert result["requires_reboot"] is True


class TestMemoryBackupRestore:
    """Tests for MemorySettingsHandler backup/restore."""

    @patch.object(MemorySettingsHandler, "detect")
    def test_backup_returns_current_settings(self, mock_detect):
        """Test backup returns current memory settings."""
        expected = {
            "large_system_cache": 1,
            "disable_paging_executive": 0,
            "clear_page_file_at_shutdown": 0,
        }
        mock_detect.return_value = expected

        handler = MemorySettingsHandler()
        result = handler.backup()

        assert result == expected

    @patch.object(MemorySettingsHandler, "_set_large_system_cache")
    @patch.object(MemorySettingsHandler, "_set_disable_paging_executive")
    def test_restore_applies_settings(self, mock_paging, mock_cache):
        """Test restore applies backed up settings."""
        handler = MemorySettingsHandler()
        result = handler.restore({
            "large_system_cache": 1,
            "disable_paging_executive": 0,
        })

        assert result is True
        mock_cache.assert_called_once_with(1)
        mock_paging.assert_called_once_with(0)

    @patch.object(MemorySettingsHandler, "_set_large_system_cache")
    def test_restore_handles_error(self, mock_set_cache):
        """Test restore handles errors gracefully."""
        mock_set_cache.side_effect = PermissionError("Access denied")

        handler = MemorySettingsHandler()
        result = handler.restore({"large_system_cache": 0})

        assert result is False
