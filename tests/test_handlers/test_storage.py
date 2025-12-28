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

    @patch.object(StorageSettingsHandler, "_set_last_access_disabled")
    def test_restore_handles_exception(self, mock_set):
        """Test restore handles exceptions gracefully."""
        mock_set.side_effect = Exception("Error")

        handler = StorageSettingsHandler()
        result = handler.restore({"last_access_disabled": True})

        assert result is False


class TestStoragePrivateMethods:
    """Tests for private helper methods."""

    @patch("subprocess.run")
    def test_get_last_access_disabled_true(self, mock_run):
        """Test _get_last_access_disabled returns True for value 1."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="DisableLastAccess = 1"
        )

        handler = StorageSettingsHandler()
        result = handler._get_last_access_disabled()

        assert result is True

    @patch("subprocess.run")
    def test_get_last_access_disabled_true_value_3(self, mock_run):
        """Test _get_last_access_disabled returns True for value 3."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="DisableLastAccess = 3"
        )

        handler = StorageSettingsHandler()
        result = handler._get_last_access_disabled()

        assert result is True

    @patch("subprocess.run")
    def test_get_last_access_disabled_false(self, mock_run):
        """Test _get_last_access_disabled returns False for value 0."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="DisableLastAccess = 0"
        )

        handler = StorageSettingsHandler()
        result = handler._get_last_access_disabled()

        assert result is False

    @patch("subprocess.run")
    def test_get_last_access_disabled_handles_set_to_format(self, mock_run):
        """Test _get_last_access_disabled handles 'set to' format."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="DisableLastAccess is set to 1"
        )

        handler = StorageSettingsHandler()
        result = handler._get_last_access_disabled()

        assert result is True

    @patch("subprocess.run")
    def test_get_last_access_disabled_handles_failure(self, mock_run):
        """Test _get_last_access_disabled returns None on failure."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=1)

        handler = StorageSettingsHandler()
        result = handler._get_last_access_disabled()

        assert result is None

    @patch("subprocess.run")
    def test_get_last_access_disabled_handles_timeout(self, mock_run):
        """Test _get_last_access_disabled handles timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

        handler = StorageSettingsHandler()
        result = handler._get_last_access_disabled()

        assert result is None

    @patch("subprocess.run")
    def test_set_last_access_disabled_success(self, mock_run):
        """Test _set_last_access_disabled succeeds."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        handler = StorageSettingsHandler()
        result = handler._set_last_access_disabled(True)

        assert result["success"] is True

    @patch("subprocess.run")
    def test_set_last_access_disabled_failure(self, mock_run):
        """Test _set_last_access_disabled handles failure."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Access denied",
            stdout=""
        )

        handler = StorageSettingsHandler()
        result = handler._set_last_access_disabled(True)

        assert result["success"] is False
        assert "Access denied" in result["error"]

    @patch("subprocess.run")
    def test_set_last_access_disabled_timeout(self, mock_run):
        """Test _set_last_access_disabled handles timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

        handler = StorageSettingsHandler()
        result = handler._set_last_access_disabled(True)

        assert result["success"] is False
        assert "Timeout" in result["error"]

    @patch("subprocess.run")
    def test_get_8dot3_disabled_true(self, mock_run):
        """Test _get_8dot3_disabled returns True."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Disable8dot3 = 1"
        )

        handler = StorageSettingsHandler()
        result = handler._get_8dot3_disabled()

        assert result is True

    @patch("subprocess.run")
    def test_get_8dot3_disabled_false(self, mock_run):
        """Test _get_8dot3_disabled returns False."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Disable8dot3 = 0"
        )

        handler = StorageSettingsHandler()
        result = handler._get_8dot3_disabled()

        assert result is False

    @patch("subprocess.run")
    def test_get_8dot3_disabled_handles_timeout(self, mock_run):
        """Test _get_8dot3_disabled handles timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

        handler = StorageSettingsHandler()
        result = handler._get_8dot3_disabled()

        assert result is None

    @patch("subprocess.run")
    def test_set_8dot3_disabled_success(self, mock_run):
        """Test _set_8dot3_disabled succeeds."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        handler = StorageSettingsHandler()
        result = handler._set_8dot3_disabled(True)

        assert result["success"] is True

    @patch("subprocess.run")
    def test_set_8dot3_disabled_timeout(self, mock_run):
        """Test _set_8dot3_disabled handles timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

        handler = StorageSettingsHandler()
        result = handler._set_8dot3_disabled(True)

        assert result["success"] is False
        assert "Timeout" in result["error"]

    @patch("subprocess.run")
    def test_get_trim_enabled_true(self, mock_run):
        """Test _get_trim_enabled returns True when TRIM is enabled."""
        from unittest.mock import MagicMock
        # disabledeletenotify = 0 means TRIM is ENABLED
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="DisableDeleteNotify = 0"
        )

        handler = StorageSettingsHandler()
        result = handler._get_trim_enabled()

        assert result is True

    @patch("subprocess.run")
    def test_get_trim_enabled_false(self, mock_run):
        """Test _get_trim_enabled returns False when TRIM is disabled."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="DisableDeleteNotify = 1"
        )

        handler = StorageSettingsHandler()
        result = handler._get_trim_enabled()

        assert result is False

    @patch("subprocess.run")
    def test_get_trim_enabled_handles_timeout(self, mock_run):
        """Test _get_trim_enabled handles timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

        handler = StorageSettingsHandler()
        result = handler._get_trim_enabled()

        assert result is None

    @patch("subprocess.run")
    def test_set_trim_enabled_success(self, mock_run):
        """Test _set_trim_enabled succeeds."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        handler = StorageSettingsHandler()
        result = handler._set_trim_enabled(True)

        assert result["success"] is True

    @patch("subprocess.run")
    def test_set_trim_enabled_timeout(self, mock_run):
        """Test _set_trim_enabled handles timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

        handler = StorageSettingsHandler()
        result = handler._set_trim_enabled(True)

        assert result["success"] is False
        assert "Timeout" in result["error"]

    @patch("subprocess.run")
    def test_set_trim_enabled_uses_correct_value(self, mock_run):
        """Test _set_trim_enabled uses correct value (0 for enabled)."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        handler = StorageSettingsHandler()
        handler._set_trim_enabled(True)

        # Enable TRIM means disabledeletenotify = 0
        call_args = mock_run.call_args[0][0]
        assert "0" in call_args

    @patch("subprocess.run")
    def test_set_last_access_uses_value_3(self, mock_run):
        """Test _set_last_access_disabled uses value 3 for disabled."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        handler = StorageSettingsHandler()
        handler._set_last_access_disabled(True)

        # Should use value "3" for disabled (both user and system)
        call_args = mock_run.call_args[0][0]
        assert "3" in call_args
