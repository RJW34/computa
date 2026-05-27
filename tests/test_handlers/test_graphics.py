"""Tests for GraphicsSettingsHandler."""

import winreg
from unittest.mock import MagicMock, patch

from abso.settings.graphics import GraphicsSettingsHandler


class TestGraphicsDetect:
    """Tests for GraphicsSettingsHandler.detect()."""

    @patch.object(GraphicsSettingsHandler, "_get_mpo_disabled")
    @patch.object(GraphicsSettingsHandler, "_get_global_fso_disabled")
    @patch.object(GraphicsSettingsHandler, "_get_game_dvr_behavior")
    @patch.object(GraphicsSettingsHandler, "_get_hardware_cursor")
    def test_detect_returns_expected_keys(self, mock_cursor, mock_dvr, mock_fso, mock_mpo):
        """Test detect returns dictionary with all expected keys."""
        mock_mpo.return_value = False
        mock_fso.return_value = False
        mock_dvr.return_value = 0
        mock_cursor.return_value = True

        handler = GraphicsSettingsHandler()
        result = handler.detect()

        assert "mpo_disabled" in result
        assert "global_fso_disabled" in result
        assert "game_dvr_behavior" in result
        assert "hardware_cursor" in result

    @patch("abso.settings.graphics.winreg")
    def test_get_mpo_disabled_when_disabled(self, mock_winreg):
        """Test _get_mpo_disabled returns True when MPO is disabled."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (5, winreg.REG_DWORD)
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = GraphicsSettingsHandler()
        result = handler._get_mpo_disabled()

        assert result is True

    @patch("abso.settings.graphics.winreg")
    def test_get_mpo_disabled_when_enabled(self, mock_winreg):
        """Test _get_mpo_disabled returns False when MPO is enabled."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = GraphicsSettingsHandler()
        result = handler._get_mpo_disabled()

        assert result is False

    @patch("abso.settings.graphics.winreg")
    def test_set_mpo_disabled_raises_when_authoritative_write_denied(self, mock_winreg):
        """Primary DisableOverlays write failure must fail the apply."""
        mock_winreg.OpenKey.side_effect = PermissionError("Access denied")
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS

        handler = GraphicsSettingsHandler()

        try:
            handler._set_mpo_disabled(True)
        except PermissionError as exc:
            assert "DisableOverlays" in str(exc)
        else:
            raise AssertionError("PermissionError was not raised")

    @patch("abso.settings.graphics.winreg")
    def test_set_mpo_disabled_raises_when_authoritative_write_fails(self, mock_winreg):
        """Primary DisableOverlays write errors are not best-effort."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.SetValueEx.side_effect = OSError("registry unavailable")
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS
        mock_winreg.REG_DWORD = winreg.REG_DWORD

        handler = GraphicsSettingsHandler()

        try:
            handler._set_mpo_disabled(True)
        except OSError as exc:
            assert "DisableOverlays" in str(exc)
        else:
            raise AssertionError("OSError was not raised")
        mock_winreg.CloseKey.assert_called_with(mock_key)

    @patch("abso.settings.graphics.winreg")
    def test_get_game_dvr_behavior_returns_value(self, mock_winreg):
        """Test _get_game_dvr_behavior returns registry value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (2, winreg.REG_DWORD)
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = GraphicsSettingsHandler()
        result = handler._get_game_dvr_behavior()

        assert result == 2


class TestGraphicsAudit:
    """Tests for GraphicsSettingsHandler.audit()."""

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_audit_mpo_enabled_creates_info(self, mock_detect):
        """Test audit creates info issue when MPO is enabled."""
        mock_detect.return_value = {
            "mpo_disabled": False,
            "global_fso_disabled": True,
            "game_dvr_behavior": 0,
            "hardware_cursor": True,
        }

        handler = GraphicsSettingsHandler()
        issues = handler.audit()

        mpo_issues = [i for i in issues if "MPO" in i.title]
        assert len(mpo_issues) == 1
        assert mpo_issues[0].severity == "info"

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_audit_global_fso_disabled_creates_info(self, mock_detect):
        """Test audit creates info issue when global FSO is forcibly disabled."""
        mock_detect.return_value = {
            "mpo_disabled": True,
            "global_fso_disabled": True,
            "game_dvr_behavior": 2,
            "hardware_cursor": True,
        }

        handler = GraphicsSettingsHandler()
        issues = handler.audit()

        fso_issues = [i for i in issues if "Fullscreen" in i.title]
        assert len(fso_issues) == 1
        assert fso_issues[0].severity == "info"
        assert fso_issues[0].optimal_value == "Profile-managed per-exe policy"

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_audit_profile_managed_settings_minimal_issues(self, mock_detect):
        """Test audit returns minimal issues for profile-managed graphics settings."""
        mock_detect.return_value = {
            "mpo_disabled": True,
            "global_fso_disabled": False,
            "game_dvr_behavior": 0,
            "hardware_cursor": True,
        }

        handler = GraphicsSettingsHandler()
        issues = handler.audit()

        # Should have no issues when global FSO remains profile-managed.
        assert len(issues) == 0


class TestGraphicsApply:
    """Tests for GraphicsSettingsHandler.apply()."""

    @patch.object(GraphicsSettingsHandler, "detect")
    @patch.object(GraphicsSettingsHandler, "_set_mpo_disabled")
    def test_apply_disable_mpo(self, mock_set_mpo, mock_detect):
        """Test apply disables MPO."""
        # detect() returns mpo_disabled=False (different from target=True)
        mock_detect.return_value = {"mpo_disabled": False}

        handler = GraphicsSettingsHandler()
        result = handler.apply({"disable_mpo": True})

        assert result["success"] is True
        assert result["requires_reboot"] is True
        assert result["changed_keys"] == ["disable_mpo"]
        assert any("MPO registry state changed" in note for note in result["notices"])
        mock_set_mpo.assert_called_once_with(True)

    @patch.object(GraphicsSettingsHandler, "detect")
    @patch.object(GraphicsSettingsHandler, "_set_global_fso_disabled")
    def test_apply_disable_fso(self, mock_set_fso, mock_detect):
        """Test apply disables global FSO."""
        mock_detect.return_value = {"mpo_disabled": True}

        handler = GraphicsSettingsHandler()
        result = handler.apply({"disable_global_fso": True})

        assert result["success"] is True
        assert result["changed_keys"] == ["disable_global_fso"]
        mock_set_fso.assert_called_once_with(True)

    @patch.object(GraphicsSettingsHandler, "detect")
    @patch.object(GraphicsSettingsHandler, "_set_game_dvr_behavior")
    def test_apply_game_dvr_behavior(self, mock_set_dvr, mock_detect):
        """Test apply sets GameDVR behavior."""
        mock_detect.return_value = {"mpo_disabled": True}

        handler = GraphicsSettingsHandler()
        result = handler.apply({"game_dvr_behavior": 2})

        assert result["success"] is True
        assert result["changed_keys"] == ["game_dvr_behavior"]
        mock_set_dvr.assert_called_once_with(2)

    @patch.object(GraphicsSettingsHandler, "detect")
    @patch.object(GraphicsSettingsHandler, "_set_game_dvr_behavior")
    @patch.object(GraphicsSettingsHandler, "_set_global_fso_disabled")
    def test_apply_skips_matching_fso_and_game_dvr(
        self,
        mock_set_fso,
        mock_set_dvr,
        mock_detect,
    ):
        """Already-matching FSO/GameDVR registry state should not be rewritten."""
        mock_detect.return_value = {
            "mpo_disabled": True,
            "global_fso_disabled": False,
            "game_dvr_behavior": 0,
        }

        handler = GraphicsSettingsHandler()
        result = handler.apply(
            {
                "disable_global_fso": False,
                "game_dvr_behavior": 0,
            }
        )

        assert result["success"] is True
        assert result["changed"] is False
        assert result["changed_keys"] == []
        mock_set_fso.assert_not_called()
        mock_set_dvr.assert_not_called()

    @patch.object(GraphicsSettingsHandler, "detect")
    @patch.object(GraphicsSettingsHandler, "_set_mpo_disabled")
    def test_apply_handles_permission_error(self, mock_set_mpo, mock_detect):
        """Test apply handles permission errors."""
        mock_detect.return_value = {"mpo_disabled": False}
        mock_set_mpo.side_effect = PermissionError("Access denied")

        handler = GraphicsSettingsHandler()
        result = handler.apply({"disable_mpo": True})

        assert result["success"] is False
        assert "Permission" in result["error"]

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_verify_mpo_mismatch_marks_pending_apply(self, mock_detect):
        """MPO verify should distinguish unwritten registry target from reboot."""
        mock_detect.return_value = {"mpo_disabled": False}

        handler = GraphicsSettingsHandler()
        result = handler.verify_active({"disable_mpo": True})

        setting = result["settings"]["mpo_disabled"]
        assert result["all_active"] is False
        assert result["pending_apply_settings"] == ["mpo_disabled"]
        assert "pending_reboot_gated_settings" not in result
        assert setting["reboot_gated"] is True
        assert setting["activation"] == "after_reboot"
        assert setting["registry_target_written"] is False
        assert setting["next_action"] == "run_elevated_apply_to_write_registry"
        assert "elevated apply" in setting["note"]

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_verify_mpo_written_reports_reboot_commit_action(self, mock_detect):
        """A matching MPO registry target is written, but live DWM commit is boot-gated."""
        mock_detect.return_value = {"mpo_disabled": True}

        handler = GraphicsSettingsHandler()
        result = handler.verify_active({"disable_mpo": True})

        setting = result["settings"]["mpo_disabled"]
        assert result["all_active"] is True
        assert "pending_apply_settings" not in result
        assert setting["registry_target_written"] is True
        assert setting["live_activation_verifiable"] is False
        assert setting["next_action"] == "reboot_to_commit_live_compositor"
        assert "compositor path" in setting["note"]


class TestGraphicsBackupRestore:
    """Tests for GraphicsSettingsHandler backup/restore."""

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_backup_returns_detected_settings(self, mock_detect):
        """Test backup returns current detected settings."""
        expected = {
            "mpo_disabled": True,
            "global_fso_disabled": False,
            "game_dvr_behavior": 0,
            "hardware_cursor": True,
        }
        mock_detect.return_value = expected

        handler = GraphicsSettingsHandler()
        result = handler.backup()

        assert result == expected

    @patch.object(GraphicsSettingsHandler, "_set_mpo_disabled")
    @patch.object(GraphicsSettingsHandler, "_set_game_dvr_behavior")
    def test_restore_applies_settings(self, mock_set_dvr, mock_set_mpo):
        """Test restore applies backed up settings."""
        handler = GraphicsSettingsHandler()
        result = handler.restore(
            {
                "mpo_disabled": True,
                "game_dvr_behavior": 2,
            }
        )

        assert result is True
        mock_set_mpo.assert_called_once_with(True)
        mock_set_dvr.assert_called_once_with(2)

    @patch.object(GraphicsSettingsHandler, "_set_mpo_disabled")
    def test_restore_handles_error(self, mock_set_mpo):
        """Test restore handles errors gracefully."""
        mock_set_mpo.side_effect = PermissionError("Access denied")

        handler = GraphicsSettingsHandler()
        result = handler.restore({"mpo_disabled": True})

        assert result is False
