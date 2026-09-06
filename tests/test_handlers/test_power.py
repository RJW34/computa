"""Tests for PowerSettingsHandler."""

from unittest.mock import MagicMock, patch

from abso.settings.power import PowerSettingsHandler


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
            stdout="Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)",
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
""",
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
    @patch.object(PowerSettingsHandler, "_get_active_plan")
    @patch.object(PowerSettingsHandler, "_has_ultimate_performance")
    def test_apply_sets_active_plan(self, mock_has_up, mock_get_active, mock_set_active):
        """Test apply sets the active power plan."""
        mock_has_up.return_value = True
        mock_get_active.return_value = {"guid": "guid-bal", "name": "Balanced"}

        handler = PowerSettingsHandler()
        result = handler.apply({"active_plan": "high_performance"})

        assert result["success"] is True
        mock_set_active.assert_called_once_with(handler.HIGH_PERFORMANCE_GUID)

    @patch.object(PowerSettingsHandler, "_set_active_plan")
    @patch.object(PowerSettingsHandler, "_get_active_plan")
    def test_apply_skips_already_active_plan(self, mock_get_active, mock_set_active):
        """Already-active plans should not churn powercfg /setactive."""
        mock_get_active.return_value = {
            "guid": PowerSettingsHandler.HIGH_PERFORMANCE_GUID,
            "name": "High performance",
        }

        handler = PowerSettingsHandler()
        result = handler.apply({"active_plan": "high_performance"})

        assert result["success"] is True
        mock_set_active.assert_not_called()
        assert "Power plan already active: high_performance" in result["skipped"]

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

    @patch.object(PowerSettingsHandler, "_apply_current_scheme")
    @patch.object(PowerSettingsHandler, "_get_power_setting")
    @patch.object(PowerSettingsHandler, "_set_power_setting")
    @patch.object(PowerSettingsHandler, "_has_ultimate_performance")
    def test_apply_disables_usb_suspend(
        self, mock_has_up, mock_set_power, mock_get_power, mock_apply_scheme
    ):
        """Test apply disables USB selective suspend."""
        mock_has_up.return_value = True
        mock_get_power.return_value = 1

        handler = PowerSettingsHandler()
        result = handler.apply({"disable_usb_suspend": True})

        assert result["success"] is True
        mock_set_power.assert_called_once_with(
            handler.USB_SUBGROUP,
            handler.USB_SELECTIVE_SUSPEND,
            0,
            apply_changes=False,
        )
        mock_apply_scheme.assert_called_once()

    @patch.object(PowerSettingsHandler, "_apply_current_scheme")
    @patch.object(PowerSettingsHandler, "_get_power_setting")
    @patch.object(PowerSettingsHandler, "_set_power_setting")
    def test_apply_skips_matching_power_subsettings(
        self, mock_set_power, mock_get_power, mock_apply_scheme
    ):
        """Matching sub-settings should not rewrite or re-apply the scheme."""
        mock_get_power.return_value = 0

        handler = PowerSettingsHandler()
        result = handler.apply(
            {
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
            }
        )

        assert result["success"] is True
        mock_set_power.assert_not_called()
        mock_apply_scheme.assert_not_called()
        assert "USB selective suspend: already 0" in result["skipped"]
        assert "PCIe link state power management: already 0" in result["skipped"]

    @patch.object(PowerSettingsHandler, "_set_active_plan")
    @patch.object(PowerSettingsHandler, "_get_active_plan")
    def test_apply_handles_error(self, mock_get_active, mock_set_active):
        """Test apply handles errors gracefully."""
        mock_get_active.return_value = {"guid": "guid-bal", "name": "Balanced"}
        mock_set_active.side_effect = RuntimeError("Failed to set plan")

        handler = PowerSettingsHandler()
        result = handler.apply({"active_plan": "invalid-guid"})

        assert result["success"] is False
        assert result["error"] is not None


class TestPowerDetectPlanReuse:
    """detect() derives Ultimate Performance presence from one /list result."""

    @patch.object(PowerSettingsHandler, "_get_active_plan")
    @patch.object(PowerSettingsHandler, "_run_powercfg")
    def test_detect_spawns_one_list_query(self, mock_run, mock_active):
        """has_ultimate_performance reuses the /list output (no second spawn)."""
        mock_active.return_value = {"guid": "g", "name": "Balanced"}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "Power Scheme GUID: 11111111-2222-3333-4444-555555555555  (Balanced)\n"
                "Power Scheme GUID: 22222222-3333-4444-5555-666666666666  "
                "(Ultimate Performance)\n"
            ),
        )

        handler = PowerSettingsHandler()
        result = handler.detect()

        assert result["has_ultimate_performance"] is True
        list_calls = [c for c in mock_run.call_args_list if c.args and c.args[0] == "/list"]
        assert len(list_calls) == 1

    @patch.object(PowerSettingsHandler, "_get_active_plan")
    @patch.object(PowerSettingsHandler, "_list_plans")
    def test_detect_reports_missing_ultimate_performance(self, mock_list, mock_active):
        mock_active.return_value = {"guid": "g", "name": "Balanced"}
        mock_list.return_value = [{"guid": "g", "name": "Balanced"}]

        handler = PowerSettingsHandler()
        assert handler.detect()["has_ultimate_performance"] is False


class TestPowerBackupRestore:
    """Tests for PowerSettingsHandler backup/restore."""

    @patch.object(PowerSettingsHandler, "_get_power_setting", return_value=None)
    @patch.object(PowerSettingsHandler, "detect")
    def test_backup_returns_active_plan(self, mock_detect, mock_single):
        """Test backup returns active plan GUID via per-setting reads."""
        mock_detect.return_value = {
            "active_plan": {"guid": "test-guid-123", "name": "Test Plan"},
        }

        handler = PowerSettingsHandler()
        result = handler.backup()

        assert result["active_plan"] == "test-guid-123"
        # The five sub-settings are read with targeted queries (measured
        # faster than a full /qh dump on real hardware).
        assert mock_single.call_count == 5

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

    @patch.object(PowerSettingsHandler, "_set_power_setting")
    @patch.object(PowerSettingsHandler, "_restore_active_plan", return_value=False)
    def test_failed_plan_restore_never_writes_other_scheme(self, restore_plan, setter):
        handler = PowerSettingsHandler()
        result = handler.restore({"active_plan": "missing-guid", "processor_min_state": 5})
        assert result is False
        setter.assert_not_called()

    @patch.object(PowerSettingsHandler, "_list_plans")
    @patch.object(PowerSettingsHandler, "_set_active_plan")
    def test_restore_falls_back_to_plan_name_when_guid_gone(self, mock_set_active, mock_list):
        """If the backed-up GUID was deleted, restore the same-named plan."""
        # First call (stale GUID) fails; second call (resolved by name) succeeds.
        mock_set_active.side_effect = [RuntimeError("invalid GUID"), None]
        mock_list.return_value = [
            {"guid": "fresh-guid-999", "name": "Ultimate Performance"},
            {"guid": "balanced-guid", "name": "Balanced"},
        ]

        handler = PowerSettingsHandler()
        result = handler.restore(
            {"active_plan": "stale-guid-000", "active_plan_name": "Ultimate Performance"}
        )

        assert result is True
        assert mock_set_active.call_args_list[0].args[0] == "stale-guid-000"
        assert mock_set_active.call_args_list[1].args[0] == "fresh-guid-999"

    def test_restore_empty_data(self):
        """Test restore handles empty backup data."""
        handler = PowerSettingsHandler()
        result = handler.restore({})

        assert result is True


class TestPowerVerify:
    """Tests for PowerSettingsHandler.verify_active()."""

    @patch.object(PowerSettingsHandler, "detect")
    @patch.object(PowerSettingsHandler, "_get_power_setting")
    def test_verify_active_reports_expected_power_state(self, mock_get_power_setting, mock_detect):
        mock_detect.return_value = {
            "active_plan": {"guid": "guid-up", "name": "Ultimate Performance"},
            "available_plans": [],
            "has_ultimate_performance": True,
        }
        mock_get_power_setting.side_effect = [0, 0, 5, 100]

        handler = PowerSettingsHandler()
        result = handler.verify_active(
            {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
            }
        )

        assert result["all_active"] is True
        assert result["settings"]["active_plan"]["active"] is True
        assert result["settings"]["processor_max_state"]["active"] is True

    @patch.object(PowerSettingsHandler, "detect")
    @patch.object(PowerSettingsHandler, "_get_power_setting")
    def test_verify_active_reports_mismatch(self, mock_get_power_setting, mock_detect):
        mock_detect.return_value = {
            "active_plan": {"guid": "guid-bal", "name": "Balanced"},
            "available_plans": [],
            "has_ultimate_performance": False,
        }
        mock_get_power_setting.side_effect = [1, 1, 0, 99]

        handler = PowerSettingsHandler()
        result = handler.verify_active(
            {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
            }
        )

        assert result["all_active"] is False
        assert result["settings"]["ensure_ultimate_performance"]["active"] is False
        assert result["settings"]["disable_usb_suspend"]["active"] is False
        assert result["settings"]["processor_max_state"]["active"] is False


class TestPowerCoreParking:
    """Tests for the disable_core_parking knob (Bitsum Highest Performance)."""

    @patch.object(PowerSettingsHandler, "_apply_current_scheme")
    @patch.object(PowerSettingsHandler, "_get_power_setting")
    @patch.object(PowerSettingsHandler, "_set_power_setting")
    def test_apply_disables_core_parking(self, mock_set, mock_get, mock_apply_scheme):
        """A parked-cores plan (min < 100) is rewritten to 100 (fully unparked)."""
        mock_get.return_value = 5

        handler = PowerSettingsHandler()
        result = handler.apply({"disable_core_parking": True})

        assert result["success"] is True
        mock_set.assert_called_once_with(
            handler.PROCESSOR_SUBGROUP,
            handler.PROCESSOR_CORE_PARKING_MIN,
            100,
            apply_changes=False,
        )
        mock_apply_scheme.assert_called_once()

    @patch.object(PowerSettingsHandler, "_apply_current_scheme")
    @patch.object(PowerSettingsHandler, "_get_power_setting")
    @patch.object(PowerSettingsHandler, "_set_power_setting")
    def test_apply_skips_core_parking_already_unparked(
        self, mock_set, mock_get, mock_apply_scheme
    ):
        """Already-unparked (100) must not rewrite or re-apply the scheme."""
        mock_get.return_value = 100

        handler = PowerSettingsHandler()
        result = handler.apply({"disable_core_parking": True})

        assert result["success"] is True
        mock_set.assert_not_called()
        mock_apply_scheme.assert_not_called()
        assert "CPU core parking (min cores unparked): already 100" in result["skipped"]

    @patch.object(PowerSettingsHandler, "detect")
    @patch.object(PowerSettingsHandler, "_get_power_setting")
    def test_verify_core_parking_active(self, mock_get, mock_detect):
        mock_detect.return_value = {
            "active_plan": {"guid": "g", "name": "Ultimate Performance"},
            "available_plans": [],
            "has_ultimate_performance": True,
        }
        mock_get.return_value = 100

        handler = PowerSettingsHandler()
        result = handler.verify_active({"disable_core_parking": True})

        assert result["settings"]["disable_core_parking"]["active"] is True
        assert result["all_active"] is True

    @patch.object(PowerSettingsHandler, "detect")
    @patch.object(PowerSettingsHandler, "_get_power_setting")
    def test_verify_core_parking_mismatch(self, mock_get, mock_detect):
        mock_detect.return_value = {
            "active_plan": {"guid": "g", "name": "Ultimate Performance"},
            "available_plans": [],
            "has_ultimate_performance": True,
        }
        mock_get.return_value = 5  # parking still enabled

        handler = PowerSettingsHandler()
        result = handler.verify_active({"disable_core_parking": True})

        assert result["settings"]["disable_core_parking"]["active"] is False
        assert result["all_active"] is False

    @patch.object(PowerSettingsHandler, "detect")
    @patch.object(PowerSettingsHandler, "_get_power_setting")
    def test_backup_includes_core_parking(self, mock_get, mock_detect):
        mock_get.return_value = 100
        mock_detect.return_value = {"active_plan": {"guid": "g", "name": "n"}}

        handler = PowerSettingsHandler()
        backup = handler.backup()

        assert backup["core_parking_min"] == 100

    @patch.object(PowerSettingsHandler, "_set_power_setting")
    def test_restore_core_parking(self, mock_set):
        handler = PowerSettingsHandler()
        result = handler.restore({"core_parking_min": 100})

        assert result is True
        mock_set.assert_called_once_with(
            handler.PROCESSOR_SUBGROUP, handler.PROCESSOR_CORE_PARKING_MIN, 100
        )

    @patch.object(PowerSettingsHandler, "_run_powercfg")
    def test_get_power_setting_includes_hidden(self, mock_run):
        """Reads must use /qh — hidden settings (core parking) emit nothing under /query."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Current AC Power Setting Index: 0x00000064"
        )

        handler = PowerSettingsHandler()
        value = handler._get_power_setting("sub-guid", "setting-guid")

        assert value == 100
        assert mock_run.call_args[0][0] == "/qh"
