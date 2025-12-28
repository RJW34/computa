"""Tests for StorageSettingsHandler."""

from unittest.mock import patch

from abso.settings.storage import StorageSettingsHandler


class TestStorageDetect:
    """Tests for StorageSettingsHandler.detect()."""

    @patch.object(StorageSettingsHandler, "_get_last_access_disabled")
    @patch.object(StorageSettingsHandler, "_get_8dot3_disabled")
    @patch.object(StorageSettingsHandler, "_get_trim_enabled")
    def test_detect_returns_storage_settings(self, mock_trim, mock_8dot3, mock_last):
        """Test detect returns dictionary with storage settings."""
        mock_last.return_value = True
        mock_8dot3.return_value = True
        mock_trim.return_value = True

        handler = StorageSettingsHandler()
        result = handler.detect()

        assert "last_access_disabled" in result
        assert "short_names_disabled" in result
        assert "trim_enabled" in result

    @patch.object(StorageSettingsHandler, "_get_last_access_disabled")
    @patch.object(StorageSettingsHandler, "_get_8dot3_disabled")
    @patch.object(StorageSettingsHandler, "_get_trim_enabled")
    def test_detect_handles_none_values(self, mock_trim, mock_8dot3, mock_last):
        """Test detect handles None values gracefully."""
        mock_last.return_value = None
        mock_8dot3.return_value = None
        mock_trim.return_value = None

        handler = StorageSettingsHandler()
        result = handler.detect()

        assert result is not None


class TestStorageAudit:
    """Tests for StorageSettingsHandler.audit()."""

    @patch.object(StorageSettingsHandler, "detect")
    def test_audit_last_access_enabled_creates_issue(self, mock_detect):
        """Test audit creates issue when last access time is enabled."""
        mock_detect.return_value = {
            "last_access_disabled": False,
            "short_names_disabled": True,
            "trim_enabled": True,
        }

        handler = StorageSettingsHandler()
        issues = handler.audit()

        last_access_issues = [i for i in issues if "Last Access" in i.title]
        assert len(last_access_issues) >= 1

    @patch.object(StorageSettingsHandler, "detect")
    def test_audit_trim_disabled_creates_warning(self, mock_detect):
        """Test audit creates warning when TRIM is disabled."""
        mock_detect.return_value = {
            "last_access_disabled": True,
            "short_names_disabled": True,
            "trim_enabled": False,
        }

        handler = StorageSettingsHandler()
        issues = handler.audit()

        trim_issues = [i for i in issues if "TRIM" in i.title]
        assert len(trim_issues) >= 1
        assert any(i.severity == "warning" for i in trim_issues)

    @patch.object(StorageSettingsHandler, "detect")
    def test_audit_all_optimized_no_issues(self, mock_detect):
        """Test audit returns no issues when all settings are optimal."""
        mock_detect.return_value = {
            "last_access_disabled": True,
            "short_names_disabled": True,
            "trim_enabled": True,
        }

        handler = StorageSettingsHandler()
        issues = handler.audit()

        # Should have no last access or trim issues
        assert len([i for i in issues if "Last Access" in i.title or "TRIM" in i.title]) == 0


class TestStorageApply:
    """Tests for StorageSettingsHandler.apply()."""

    @patch.object(StorageSettingsHandler, "_set_last_access_disabled")
    def test_apply_disables_last_access(self, mock_set_last):
        """Test apply disables last access time."""
        mock_set_last.return_value = {"success": True}

        handler = StorageSettingsHandler()
        result = handler.apply({"disable_last_access": True})

        assert result["success"] is True
        mock_set_last.assert_called_with(True)

    @patch.object(StorageSettingsHandler, "_set_last_access_disabled")
    @patch.object(StorageSettingsHandler, "_set_8dot3_disabled")
    @patch.object(StorageSettingsHandler, "_set_trim_enabled")
    def test_apply_preset_gaming(self, mock_trim, mock_8dot3, mock_last):
        """Test apply with gaming preset applies all optimizations."""
        mock_last.return_value = {"success": True}
        mock_8dot3.return_value = {"success": True}
        mock_trim.return_value = {"success": True}

        handler = StorageSettingsHandler()
        result = handler.apply({"preset": "gaming"})

        assert result["success"] is True
        mock_last.assert_called()

    @patch.object(StorageSettingsHandler, "_set_last_access_disabled")
    def test_apply_handles_error(self, mock_set_last):
        """Test apply handles errors gracefully."""
        mock_set_last.return_value = {"success": False, "error": "Failed"}

        handler = StorageSettingsHandler()
        result = handler.apply({"disable_last_access": True})

        assert result["success"] is False


class TestStorageBackupRestore:
    """Tests for StorageSettingsHandler backup/restore."""

    @patch.object(StorageSettingsHandler, "detect")
    def test_backup_returns_current_state(self, mock_detect):
        """Test backup returns current storage settings."""
        expected = {
            "last_access_disabled": True,
            "short_names_disabled": True,
            "trim_enabled": True,
        }
        mock_detect.return_value = expected

        handler = StorageSettingsHandler()
        result = handler.backup()

        assert "last_access_disabled" in result
        assert "trim_enabled" in result

    @patch.object(StorageSettingsHandler, "_set_last_access_disabled")
    @patch.object(StorageSettingsHandler, "_set_trim_enabled")
    def test_restore_applies_backed_up_state(self, mock_trim, mock_last):
        """Test restore applies backed up settings."""
        mock_last.return_value = {"success": True}
        mock_trim.return_value = {"success": True}

        handler = StorageSettingsHandler()
        result = handler.restore({
            "last_access_disabled": True,
            "trim_enabled": True,
        })

        assert result is True
