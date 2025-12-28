"""Tests for ServicesSettingsHandler."""

from unittest.mock import patch

from abso.settings.services import ServicesSettingsHandler


class TestServicesDetect:
    """Tests for ServicesSettingsHandler.detect()."""

    @patch.object(ServicesSettingsHandler, "_get_service_info")
    def test_detect_returns_services_dict(self, mock_get_info):
        """Test detect returns dictionary with services key."""
        mock_get_info.return_value = {
            "exists": True,
            "start_type": 2,
            "status": "running",
        }

        handler = ServicesSettingsHandler()
        result = handler.detect()

        assert "services" in result
        assert isinstance(result["services"], dict)

    @patch.object(ServicesSettingsHandler, "_get_service_info")
    def test_detect_queries_all_gaming_services(self, mock_get_info):
        """Test detect queries all configured gaming services."""
        mock_get_info.return_value = {"exists": True, "start_type": 2}

        handler = ServicesSettingsHandler()
        handler.detect()

        # Should have queried each service in GAMING_SERVICES
        assert mock_get_info.call_count == len(handler.GAMING_SERVICES)

    @patch.object(ServicesSettingsHandler, "_get_service_info")
    def test_detect_handles_missing_service(self, mock_get_info):
        """Test detect handles services that don't exist."""
        mock_get_info.return_value = {"exists": False}

        handler = ServicesSettingsHandler()
        result = handler.detect()

        # Should not crash, should return empty/false for missing services
        assert result is not None


class TestServicesAudit:
    """Tests for ServicesSettingsHandler.audit()."""

    @patch.object(ServicesSettingsHandler, "detect")
    def test_audit_sysmain_automatic_creates_warning(self, mock_detect):
        """Test audit creates warning when SysMain is Automatic."""
        mock_detect.return_value = {
            "services": {
                "SysMain": {"exists": True, "start_type": 2},  # Automatic
                "DiagTrack": {"exists": True, "start_type": 4},  # Disabled
                "WSearch": {"exists": True, "start_type": 4},
                "XblAuthManager": {"exists": False},
                "XblGameSave": {"exists": False},
                "XboxGipSvc": {"exists": False},
                "XboxNetApiSvc": {"exists": False},
            }
        }

        handler = ServicesSettingsHandler()
        issues = handler.audit()

        sysmain_issues = [i for i in issues if "SysMain" in i.title]
        assert len(sysmain_issues) == 1
        assert sysmain_issues[0].severity == "warning"

    @patch.object(ServicesSettingsHandler, "detect")
    def test_audit_diagtrack_automatic_creates_info(self, mock_detect):
        """Test audit creates info when DiagTrack is Automatic."""
        mock_detect.return_value = {
            "services": {
                "SysMain": {"exists": True, "start_type": 4},  # Disabled
                "DiagTrack": {"exists": True, "start_type": 2},  # Automatic
                "WSearch": {"exists": True, "start_type": 4},
                "XblAuthManager": {"exists": False},
                "XblGameSave": {"exists": False},
                "XboxGipSvc": {"exists": False},
                "XboxNetApiSvc": {"exists": False},
            }
        }

        handler = ServicesSettingsHandler()
        issues = handler.audit()

        diagtrack_issues = [i for i in issues if "Telemetry" in i.title]
        assert len(diagtrack_issues) == 1
        assert diagtrack_issues[0].severity == "info"

    @patch.object(ServicesSettingsHandler, "detect")
    def test_audit_all_disabled_no_issues(self, mock_detect):
        """Test audit returns no issues when services are optimally configured."""
        mock_detect.return_value = {
            "services": {
                "SysMain": {"exists": True, "start_type": 4},
                "DiagTrack": {"exists": True, "start_type": 4},
                "WSearch": {"exists": True, "start_type": 4},
                "XblAuthManager": {"exists": True, "start_type": 4},
                "XblGameSave": {"exists": True, "start_type": 4},
                "XboxGipSvc": {"exists": True, "start_type": 3},  # Manual is optimal
                "XboxNetApiSvc": {"exists": True, "start_type": 4},
            }
        }

        handler = ServicesSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0

    @patch.object(ServicesSettingsHandler, "detect")
    def test_audit_skips_nonexistent_services(self, mock_detect):
        """Test audit skips services that don't exist on the system."""
        mock_detect.return_value = {
            "services": {
                "SysMain": {"exists": False},
                "DiagTrack": {"exists": False},
                "WSearch": {"exists": False},
                "XblAuthManager": {"exists": False},
                "XblGameSave": {"exists": False},
                "XboxGipSvc": {"exists": False},
                "XboxNetApiSvc": {"exists": False},
            }
        }

        handler = ServicesSettingsHandler()
        issues = handler.audit()

        # No issues should be raised for nonexistent services
        assert len(issues) == 0


class TestServicesApply:
    """Tests for ServicesSettingsHandler.apply()."""

    @patch.object(ServicesSettingsHandler, "_set_service_start_type")
    @patch.object(ServicesSettingsHandler, "_stop_service")
    def test_apply_disables_service(self, mock_stop, mock_set_type):
        """Test apply can disable a service."""
        handler = ServicesSettingsHandler()
        result = handler.apply({
            "services": {
                "SysMain": {"start_type": 4}  # Disabled
            }
        })

        assert result["success"] is True
        mock_set_type.assert_called()

    @patch.object(ServicesSettingsHandler, "_set_service_start_type")
    def test_apply_handles_error(self, mock_set_type):
        """Test apply handles errors gracefully."""
        mock_set_type.side_effect = RuntimeError("Failed to change service")

        handler = ServicesSettingsHandler()
        result = handler.apply({
            "services": {
                "SysMain": {"start_type": 4}
            }
        })

        assert result["success"] is False
        assert result["error"] is not None


class TestServicesBackupRestore:
    """Tests for ServicesSettingsHandler backup/restore."""

    @patch.object(ServicesSettingsHandler, "detect")
    def test_backup_returns_service_states(self, mock_detect):
        """Test backup returns current service states."""
        expected = {
            "services": {
                "SysMain": {"exists": True, "start_type": 2},
                "DiagTrack": {"exists": True, "start_type": 4},
            }
        }
        mock_detect.return_value = expected

        handler = ServicesSettingsHandler()
        result = handler.backup()

        assert "services" in result

    @patch.object(ServicesSettingsHandler, "_set_service_start_type")
    def test_restore_applies_backed_up_states(self, mock_set_type):
        """Test restore applies backed up service states."""
        backup_data = {
            "services": {
                "SysMain": {"exists": True, "start_type": 2},
            }
        }

        handler = ServicesSettingsHandler()
        result = handler.restore(backup_data)

        assert result is True
        mock_set_type.assert_called()

    def test_restore_handles_empty_data(self):
        """Test restore handles empty backup data."""
        handler = ServicesSettingsHandler()
        result = handler.restore({})

        assert result is True

    @patch.object(ServicesSettingsHandler, "_set_service_start_type")
    def test_restore_handles_exception(self, mock_set_type):
        """Test restore handles exceptions gracefully."""
        mock_set_type.side_effect = Exception("Failed")

        handler = ServicesSettingsHandler()
        result = handler.restore({
            "services": {"SysMain": {"exists": True, "start_type": 2}}
        })

        assert result is False


class TestServicesConstants:
    """Tests for service configuration constants."""

    def test_gaming_services_defined(self):
        """Test GAMING_SERVICES dict is defined."""
        handler = ServicesSettingsHandler()
        assert hasattr(handler, "GAMING_SERVICES")
        assert len(handler.GAMING_SERVICES) > 0

    def test_sysmain_config(self):
        """Test SysMain service configuration."""
        handler = ServicesSettingsHandler()
        assert "SysMain" in handler.GAMING_SERVICES
        config = handler.GAMING_SERVICES["SysMain"]
        assert "display_name" in config
        assert "optimal_start_type" in config
        assert "severity" in config

    def test_start_type_constants(self):
        """Test start type constants are correct."""
        handler = ServicesSettingsHandler()
        assert handler.START_AUTOMATIC == 2
        assert handler.START_MANUAL == 3
        assert handler.START_DISABLED == 4


class TestServicesPrivateMethods:
    """Tests for private service methods."""

    @patch("subprocess.run")
    def test_get_service_info_success(self, mock_run):
        """Test _get_service_info returns service info."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="SERVICE_NAME: SysMain\nSTART_TYPE: 2 AUTO_START\nSTATE: 4 RUNNING\n"
        )

        handler = ServicesSettingsHandler()
        result = handler._get_service_info("SysMain")

        assert result is not None
        assert isinstance(result, dict)

    @patch("subprocess.run")
    def test_get_service_info_not_found(self, mock_run):
        """Test _get_service_info handles missing service."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")

        handler = ServicesSettingsHandler()
        result = handler._get_service_info("NonExistentService")

        assert result is not None
        assert result.get("exists") is False

    @patch("subprocess.run")
    def test_stop_service_success(self, mock_run):
        """Test _stop_service stops a service."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        handler = ServicesSettingsHandler()
        result = handler._stop_service("SysMain")

        assert result is True
        mock_run.assert_called()

    @patch("subprocess.run")
    def test_stop_service_failure(self, mock_run):
        """Test _stop_service handles failure."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=1)

        handler = ServicesSettingsHandler()
        result = handler._stop_service("SysMain")

        assert result is False

    @patch("subprocess.run")
    def test_set_service_start_type_success(self, mock_run):
        """Test _set_service_start_type succeeds."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        handler = ServicesSettingsHandler()
        handler._set_service_start_type("SysMain", 4)

        mock_run.assert_called()

    @patch("subprocess.run")
    def test_set_service_start_type_failure_returns_error(self, mock_run):
        """Test _set_service_start_type returns error on failure."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=1, stderr="Access denied", stdout="")

        handler = ServicesSettingsHandler()
        result = handler._set_service_start_type("SysMain", 4)

        assert result["success"] is False
        assert "Access denied" in result["error"]

    def test_set_service_start_type_invalid_type(self):
        """Test _set_service_start_type handles invalid start type."""
        handler = ServicesSettingsHandler()
        result = handler._set_service_start_type("SysMain", 999)

        assert result["success"] is False
        assert "Invalid start type" in result["error"]
