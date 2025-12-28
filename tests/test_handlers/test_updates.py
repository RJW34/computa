"""Tests for UpdatesSettingsHandler."""

from unittest.mock import patch

from abso.settings.updates import UpdatesSettingsHandler


class TestUpdatesDetect:
    """Tests for UpdatesSettingsHandler.detect()."""

    @patch.object(UpdatesSettingsHandler, "_get_delivery_optimization")
    @patch.object(UpdatesSettingsHandler, "_get_active_hours")
    @patch.object(UpdatesSettingsHandler, "_get_updates_paused")
    def test_detect_returns_update_settings(self, mock_paused, mock_hours, mock_do):
        """Test detect returns dictionary with update settings."""
        mock_do.return_value = {"download_mode": 1}
        mock_hours.return_value = {"start": 8, "end": 2}
        mock_paused.return_value = False

        handler = UpdatesSettingsHandler()
        result = handler.detect()

        assert "delivery_optimization" in result
        assert "active_hours" in result
        assert "updates_paused" in result

    @patch.object(UpdatesSettingsHandler, "_get_delivery_optimization")
    @patch.object(UpdatesSettingsHandler, "_get_active_hours")
    @patch.object(UpdatesSettingsHandler, "_get_updates_paused")
    def test_detect_handles_none_values(self, mock_paused, mock_hours, mock_do):
        """Test detect handles None values gracefully."""
        mock_do.return_value = None
        mock_hours.return_value = None
        mock_paused.return_value = None

        handler = UpdatesSettingsHandler()
        result = handler.detect()

        assert result is not None


class TestUpdatesAudit:
    """Tests for UpdatesSettingsHandler.audit()."""

    @patch.object(UpdatesSettingsHandler, "detect")
    def test_audit_p2p_enabled_creates_issue(self, mock_detect):
        """Test audit creates issue when P2P is enabled."""
        mock_detect.return_value = {
            "delivery_optimization": {"download_mode": 2},  # LAN + Internet
            "active_hours": {"start": 8, "end": 2},
            "updates_paused": False,
        }

        handler = UpdatesSettingsHandler()
        issues = handler.audit()

        p2p_issues = [i for i in issues if "P2P" in i.title or "Delivery" in i.title]
        assert len(p2p_issues) >= 1

    @patch.object(UpdatesSettingsHandler, "detect")
    def test_audit_p2p_disabled_no_issues(self, mock_detect):
        """Test audit returns no issues when P2P is disabled."""
        mock_detect.return_value = {
            "delivery_optimization": {"download_mode": 0},  # HTTP only
            "active_hours": {"start": 8, "end": 2},
            "updates_paused": False,
        }

        handler = UpdatesSettingsHandler()
        issues = handler.audit()

        p2p_issues = [i for i in issues if "P2P" in i.title or "Delivery" in i.title]
        assert len(p2p_issues) == 0

    @patch.object(UpdatesSettingsHandler, "detect")
    def test_audit_handles_missing_do_data(self, mock_detect):
        """Test audit handles missing delivery optimization data."""
        mock_detect.return_value = {
            "delivery_optimization": {},
            "active_hours": None,
            "updates_paused": None,
        }

        handler = UpdatesSettingsHandler()
        issues = handler.audit()

        # Should not crash
        assert issues is not None


class TestUpdatesApply:
    """Tests for UpdatesSettingsHandler.apply()."""

    @patch.object(UpdatesSettingsHandler, "_set_delivery_optimization_mode")
    def test_apply_disables_p2p(self, mock_set_do):
        """Test apply disables P2P updates."""
        handler = UpdatesSettingsHandler()
        result = handler.apply({"disable_p2p": True})

        assert result["success"] is True
        mock_set_do.assert_called_with(0)

    @patch.object(UpdatesSettingsHandler, "_set_active_hours")
    def test_apply_sets_active_hours(self, mock_set_hours):
        """Test apply sets active hours."""
        handler = UpdatesSettingsHandler()
        result = handler.apply({
            "active_hours": {"start": 9, "end": 3}
        })

        assert result["success"] is True
        mock_set_hours.assert_called_with(9, 3)

    @patch.object(UpdatesSettingsHandler, "_set_delivery_optimization_mode")
    def test_apply_handles_error(self, mock_set_do):
        """Test apply handles errors gracefully."""
        mock_set_do.side_effect = PermissionError("Access denied")

        handler = UpdatesSettingsHandler()
        result = handler.apply({"disable_p2p": True})

        assert result["success"] is False
        assert result["error"] is not None


class TestUpdatesBackupRestore:
    """Tests for UpdatesSettingsHandler backup/restore."""

    @patch.object(UpdatesSettingsHandler, "detect")
    def test_backup_returns_current_state(self, mock_detect):
        """Test backup returns current update settings."""
        expected = {
            "delivery_optimization": {"download_mode": 1},
            "active_hours": {"start": 8, "end": 2},
        }
        mock_detect.return_value = expected

        handler = UpdatesSettingsHandler()
        result = handler.backup()

        assert "delivery_optimization" in result

    @patch.object(UpdatesSettingsHandler, "_set_delivery_optimization_mode")
    def test_restore_applies_backed_up_state(self, mock_set_do):
        """Test restore applies backed up settings."""
        handler = UpdatesSettingsHandler()
        result = handler.restore({
            "delivery_optimization": {"download_mode": 1}
        })

        assert result is True
        mock_set_do.assert_called_with(1)

    def test_restore_handles_missing_data(self):
        """Test restore handles missing data gracefully."""
        handler = UpdatesSettingsHandler()
        result = handler.restore({})

        assert result is True
