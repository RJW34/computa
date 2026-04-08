"""Tests for MouseSettingsHandler."""

import winreg
from unittest.mock import MagicMock, patch

from abso.settings.mouse import MouseSettingsHandler


class TestMouseDetect:
    """Tests for MouseSettingsHandler.detect()."""

    @patch.object(MouseSettingsHandler, "_get_mouse_sensitivity")
    @patch.object(MouseSettingsHandler, "_get_mouse_speed")
    @patch.object(MouseSettingsHandler, "_get_mouse_threshold")
    @patch.object(MouseSettingsHandler, "_get_enhanced_pointer_precision")
    @patch.object(MouseSettingsHandler, "_get_smooth_curve")
    @patch.object(MouseSettingsHandler, "_is_acceleration_disabled")
    def test_detect_returns_expected_keys(self, mock_accel, mock_curve, mock_epp, mock_thresh, mock_speed, mock_sensitivity):
        """Test detect returns dictionary with all expected keys."""
        mock_sensitivity.return_value = 10
        mock_speed.return_value = 0
        mock_thresh.return_value = 0
        mock_epp.return_value = False
        mock_curve.return_value = None
        mock_accel.return_value = True

        handler = MouseSettingsHandler()
        result = handler.detect()

        assert "mouse_speed" in result
        assert "mouse_sensitivity" in result
        assert "mouse_threshold1" in result
        assert "mouse_threshold2" in result
        assert "enhanced_pointer_precision" in result
        assert "is_acceleration_disabled" in result

    @patch("abso.settings.mouse.winreg")
    def test_get_mouse_speed_returns_value(self, mock_winreg):
        """Test _get_mouse_speed reads registry value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = ("1", winreg.REG_SZ)
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = MouseSettingsHandler()
        result = handler._get_mouse_speed()

        assert result == 1

    @patch("abso.settings.mouse.winreg")
    def test_get_enhanced_pointer_precision(self, mock_winreg):
        """Test _get_enhanced_pointer_precision detects EPP setting."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = ("1", winreg.REG_SZ)
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = MouseSettingsHandler()
        result = handler._get_enhanced_pointer_precision()

        assert result is True


class TestMouseAudit:
    """Tests for MouseSettingsHandler.audit()."""

    @patch.object(MouseSettingsHandler, "detect")
    def test_audit_acceleration_enabled_creates_warning(self, mock_detect):
        """Test audit creates warning when acceleration is enabled."""
        mock_detect.return_value = {
            "mouse_speed": 1,
            "mouse_threshold1": 6,
            "mouse_threshold2": 10,
            "enhanced_pointer_precision": True,
            "smooth_mouse_x_curve": None,
            "smooth_mouse_y_curve": None,
            "is_acceleration_disabled": False,
        }

        handler = MouseSettingsHandler()
        issues = handler.audit()

        accel_issues = [i for i in issues if "acceleration" in i.title.lower()]
        assert len(accel_issues) >= 1
        assert any(i.severity == "warning" for i in accel_issues)

    @patch.object(MouseSettingsHandler, "detect")
    def test_audit_acceleration_disabled_no_warning(self, mock_detect):
        """Test audit doesn't create warning when acceleration is disabled."""
        mock_detect.return_value = {
            "mouse_speed": 0,
            "mouse_threshold1": 0,
            "mouse_threshold2": 0,
            "enhanced_pointer_precision": False,
            "smooth_mouse_x_curve": MouseSettingsHandler.LINEAR_X_CURVE,
            "smooth_mouse_y_curve": MouseSettingsHandler.LINEAR_Y_CURVE,
            "is_acceleration_disabled": True,
        }

        handler = MouseSettingsHandler()
        issues = handler.audit()

        accel_issues = [i for i in issues if "acceleration" in i.title.lower()]
        assert len(accel_issues) == 0

    @patch.object(MouseSettingsHandler, "detect")
    def test_audit_epp_enabled_mentioned(self, mock_detect):
        """Test audit mentions Enhanced Pointer Precision when enabled."""
        mock_detect.return_value = {
            "mouse_speed": 0,
            "mouse_threshold1": 0,
            "mouse_threshold2": 0,
            "enhanced_pointer_precision": True,
            "smooth_mouse_x_curve": None,
            "smooth_mouse_y_curve": None,
            "is_acceleration_disabled": False,
        }

        handler = MouseSettingsHandler()
        issues = handler.audit()

        # Should have an issue mentioning EPP
        assert any("Enhanced Pointer Precision" in str(i.current_value) for i in issues)


class TestMouseApply:
    """Tests for MouseSettingsHandler.apply()."""

    @patch.object(MouseSettingsHandler, "_disable_acceleration")
    def test_apply_disables_acceleration(self, mock_disable_accel):
        """Test apply can disable all acceleration."""
        handler = MouseSettingsHandler()
        result = handler.apply({
            "disable_acceleration": True,
        })

        assert result["success"] is True
        mock_disable_accel.assert_called_once()

    @patch.object(MouseSettingsHandler, "_set_mouse_speed")
    def test_apply_sets_mouse_speed(self, mock_set_speed):
        """Test apply sets mouse speed."""
        handler = MouseSettingsHandler()
        result = handler.apply({"mouse_speed": 0})

        assert result["success"] is True
        mock_set_speed.assert_called_once_with(0)

    @patch.object(MouseSettingsHandler, "_set_mouse_speed")
    def test_apply_handles_permission_error(self, mock_set_speed):
        """Test apply handles permission errors."""
        mock_set_speed.side_effect = PermissionError("Access denied")

        handler = MouseSettingsHandler()
        result = handler.apply({"mouse_speed": 0})

        assert result["success"] is False
        assert "Permission" in result["error"]


class TestMouseBackupRestore:
    """Tests for MouseSettingsHandler backup/restore."""

    @patch.object(MouseSettingsHandler, "detect")
    def test_backup_returns_current_settings(self, mock_detect):
        """Test backup returns current mouse settings."""
        expected = {
            "mouse_speed": 1,
            "mouse_sensitivity": 10,
            "mouse_threshold1": 6,
            "mouse_threshold2": 10,
            "enhanced_pointer_precision": True,
            "smooth_mouse_x_curve": b"\x00" * 40,
            "smooth_mouse_y_curve": b"\x00" * 40,
            "is_acceleration_disabled": False,
        }
        mock_detect.return_value = expected

        handler = MouseSettingsHandler()
        result = handler.backup()

        assert result == expected

    @patch("abso.settings.mouse.winreg")
    @patch.object(MouseSettingsHandler, "_notify_settings_change")
    def test_restore_applies_settings(self, mock_notify, mock_winreg):
        """Test restore applies backed up settings via registry."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS
        mock_winreg.REG_SZ = winreg.REG_SZ

        backup_data = {
            "mouse_speed": 0,
            "mouse_threshold1": 0,
            "mouse_threshold2": 0,
        }

        handler = MouseSettingsHandler()
        result = handler.restore(backup_data)

        assert result is True
        mock_winreg.SetValueEx.assert_called()
        mock_notify.assert_called_once()

    @patch("abso.settings.mouse.winreg")
    def test_restore_returns_false_on_failure(self, mock_winreg):
        """Test restore returns False when registry access fails."""
        mock_winreg.OpenKey.side_effect = PermissionError("Access denied")
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS

        handler = MouseSettingsHandler()
        result = handler.restore({"mouse_speed": 0})

        assert result is False


class TestMouseVerify:
    """Tests for verify_active()."""

    @patch.object(MouseSettingsHandler, "detect")
    @patch.object(MouseSettingsHandler, "_is_curve_linear")
    def test_verify_active_reports_success(self, mock_is_curve_linear, mock_detect):
        mock_detect.return_value = {
            "mouse_speed": 0,
            "mouse_sensitivity": 10,
            "mouse_threshold1": 0,
            "mouse_threshold2": 0,
            "enhanced_pointer_precision": False,
            "smooth_mouse_x_curve": [0] * 40,
            "smooth_mouse_y_curve": [0] * 40,
            "is_acceleration_disabled": True,
        }
        mock_is_curve_linear.return_value = True

        handler = MouseSettingsHandler()
        result = handler.verify_active(
            {
                "disable_acceleration": True,
                "set_linear_curve": True,
                "mouse_speed": 0,
                "mouse_sensitivity": 10,
            }
        )

        assert result["all_active"] is True
        assert result["settings"]["set_linear_curve"]["active"] is True

    @patch.object(MouseSettingsHandler, "detect")
    @patch.object(MouseSettingsHandler, "_is_curve_linear")
    def test_verify_active_reports_mismatch(self, mock_is_curve_linear, mock_detect):
        mock_detect.return_value = {
            "mouse_speed": 1,
            "mouse_sensitivity": 6,
            "mouse_threshold1": 6,
            "mouse_threshold2": 10,
            "enhanced_pointer_precision": True,
            "smooth_mouse_x_curve": [0] * 40,
            "smooth_mouse_y_curve": [0] * 40,
            "is_acceleration_disabled": False,
        }
        mock_is_curve_linear.return_value = False

        handler = MouseSettingsHandler()
        result = handler.verify_active(
            {
                "disable_acceleration": True,
                "set_linear_curve": True,
                "mouse_speed": 0,
                "mouse_sensitivity": 10,
            }
        )

        assert result["all_active"] is False
        assert result["settings"]["disable_acceleration"]["active"] is False
        assert result["settings"]["mouse_sensitivity"]["active"] is False
