"""Tests for PowerSettingsHandler."""

import pytest
from unittest.mock import patch, MagicMock

from abso.settings.power import PowerSettingsHandler
from abso.core.models import Issue


class TestPowerDetect:
    """Tests for PowerSettingsHandler.detect()."""

    @patch.object(PowerSettingsHandler, "_get_active_plan")
    @patch.object(PowerSettingsHandler, "_list_plans")
    @patch.object(PowerSettingsHandler, "_has_ultimate_performance")
    def test_detect_returns_expected_keys(self, mock_has_up, mock_list, mock_active):
        """Test detect returns dictionary with all expected keys."""
        mock_active.return_value = {"guid": "test-guid", "name": "Balanced"}
        mock_list.return_value = [{"guid": "test-guid", "name": "Balanced"}]
        mock_has_up.return_value = False

        handler = PowerSettingsHandler()
        result = handler.detect()

        assert "active_plan" in result
        assert "available_plans" in result
        assert "has_ultimate_performance" in result

    @patch.object(PowerSettingsHandler, "_run_powercfg")
    def test_get_active_plan_parses_output(self, mock_run):
        """Test _get_active_plan parses powercfg output correctly."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)"
        )

        handler = PowerSettingsHandler()
        result = handler._get_active_plan()

        assert result["guid"] == "381b4222-f694-41f0-9685-ff5bb260df2e"
        assert result["name"] == "Balanced"

    @patch.object(PowerSettingsHandler, "_run_powercfg")
    def test_list_plans_parses_multiple(self, mock_run):
        """Test _list_plans parses multiple plans."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""Existing Power Schemes (* Active)
-----------------------------------
Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *
Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)
"""
        )

        handler = PowerSettingsHandler()
        result = handler._list_plans()

        assert len(result) == 2
        assert result[0]["name"] == "Balanced"
        assert result[1]["name"] == "High performance"

    @patch.object(PowerSettingsHandler, "_run_powercfg")
    def test_get_active_plan_handles_error(self, mock_run):
        """Test _get_active_plan handles powercfg errors."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")

        handler = PowerSettingsHandler()
        result = handler._get_active_plan()

        assert result == {}


class TestPowerAudit:
    """Tests for PowerSettingsHandler.audit()."""

    @patch.object(PowerSettingsHandler, "detect")
    def test_audit_balanced_plan_creates_warning(self, mock_detect):
        """Test audit creates warning when using Balanced plan."""
        mock_detect.return_value = {
            "active_plan": {
                "guid": "381b4222-f694-41f0-9685-ff5bb260df2e",
                "name": "Balanced",
            },
            "available_plans": [],
            "has_ultimate_performance": False,
        }

        handler = PowerSettingsHandler()
        issues = handler.audit()

        power_issues = [i for i in issues if "power plan" in i.title.lower()]
        assert len(power_issues) == 1
        assert power_issues[0].severity == "warning"

    @patch.object(PowerSettingsHandler, "detect")
    def test_audit_high_performance_no_warning(self, mock_detect):
        """Test audit doesn't warn when using High Performance."""
        mock_detect.return_value = {
            "active_plan": {
                "guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
                "name": "High performance",
            },
            "available_plans": [],
            "has_ultimate_performance": True,
        }

        handler = PowerSettingsHandler()
        issues = handler.audit()

        power_issues = [i for i in issues if "power plan" in i.title.lower()]
        assert len(power_issues) == 0

    @patch.object(PowerSettingsHandler, "detect")
    def test_audit_ultimate_performance_no_warning(self, mock_detect):
        """Test audit doesn't warn when using Ultimate Performance."""
        mock_detect.return_value = {
            "active_plan": {
                "guid": "e9a42b02-d5df-448d-aa00-03f14749eb61",
                "name": "Ultimate Performance",
            },
            "available_plans": [],
            "has_ultimate_performance": True,
        }

        handler = PowerSettingsHandler()
        issues = handler.audit()

        power_issues = [i for i in issues if "power plan" in i.title.lower()]
        assert len(power_issues) == 0

    @patch.object(PowerSettingsHandler, "detect")
    def test_audit_missing_ultimate_performance_info(self, mock_detect):
        """Test audit creates info when Ultimate Performance not available."""
        mock_detect.return_value = {
            "active_plan": {
                "guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
                "name": "High performance",
            },
            "available_plans": [],
            "has_ultimate_performance": False,
        }

        handler = PowerSettingsHandler()
        issues = handler.audit()

        up_issues = [i for i in issues if "Ultimate Performance" in i.title]
        assert len(up_issues) == 1
        assert up_issues[0].severity == "info"


class TestPowerApply:
    """Tests for PowerSettingsHandler.apply()."""

    @patch.object(PowerSettingsHandler, "_set_active_plan")
    @patch.object(PowerSettingsHandler, "_has_ultimate_performance")
    def test_apply_sets_active_plan(self, mock_has_up, mock_set_active):
        """Test apply sets the active power plan."""
        mock_has_up.return_value = True

        handler = PowerSettingsHandler()
        result = handler.apply({"active_plan": "high_performance"})

        assert result["success"] is True
        mock_set_active.assert_called_once_with(handler.HIGH_PERFORMANCE_GUID)

    @patch.object(PowerSettingsHandler, "_set_active_plan")
    @patch.object(PowerSettingsHandler, "_has_ultimate_performance")
    @patch.object(PowerSettingsHandler, "_create_ultimate_performance")
    def test_apply_creates_ultimate_performance(self, mock_create, mock_has_up, mock_set):
        """Test apply creates Ultimate Performance when requested."""
        mock_has_up.return_value = False

        handler = PowerSettingsHandler()
        result = handler.apply({"ensure_ultimate_performance": True})

        assert result["success"] is True
        mock_create.assert_called_once()

    @patch.object(PowerSettingsHandler, "_set_power_setting")
    @patch.object(PowerSettingsHandler, "_has_ultimate_performance")
    def test_apply_disables_usb_suspend(self, mock_has_up, mock_set_power):
        """Test apply disables USB selective suspend."""
        mock_has_up.return_value = True

        handler = PowerSettingsHandler()
        result = handler.apply({"disable_usb_suspend": True})

        assert result["success"] is True
        mock_set_power.assert_called_with(
            handler.USB_SUBGROUP,
            handler.USB_SELECTIVE_SUSPEND,
            0
        )

    @patch.object(PowerSettingsHandler, "_set_active_plan")
    def test_apply_handles_error(self, mock_set_active):
        """Test apply handles errors gracefully."""
        mock_set_active.side_effect = RuntimeError("Failed to set plan")

        handler = PowerSettingsHandler()
        result = handler.apply({"active_plan": "invalid-guid"})

        assert result["success"] is False
        assert result["error"] is not None


class TestPowerBackupRestore:
    """Tests for PowerSettingsHandler backup/restore."""

    @patch.object(PowerSettingsHandler, "detect")
    def test_backup_returns_active_plan(self, mock_detect):
        """Test backup returns active plan GUID."""
        mock_detect.return_value = {
            "active_plan": {"guid": "test-guid-123", "name": "Test Plan"},
        }

        handler = PowerSettingsHandler()
        result = handler.backup()

        assert result["active_plan"] == "test-guid-123"

    @patch.object(PowerSettingsHandler, "_set_active_plan")
    def test_restore_sets_active_plan(self, mock_set_active):
        """Test restore sets the backed up plan."""
        handler = PowerSettingsHandler()
        result = handler.restore({"active_plan": "test-guid-123"})

        assert result is True
        mock_set_active.assert_called_once_with("test-guid-123")

    @patch.object(PowerSettingsHandler, "_set_active_plan")
    def test_restore_handles_error(self, mock_set_active):
        """Test restore handles errors gracefully."""
        mock_set_active.side_effect = RuntimeError("Failed")

        handler = PowerSettingsHandler()
        result = handler.restore({"active_plan": "test-guid"})

        assert result is False

    def test_restore_empty_data(self):
        """Test restore handles empty backup data."""
        handler = PowerSettingsHandler()
        result = handler.restore({})

        assert result is True
