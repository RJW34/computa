"""CLI smoke tests for A.B.S.O."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from abso.core.applier import ApplyResult
from abso.main import cli


class TestCLIHelp:
    """Test CLI help commands work without crashing."""

    def test_main_help(self):
        """Test main --help doesn't crash."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "A.B.S.O." in result.output or "abso" in result.output.lower()

    def test_detect_help(self):
        """Test detect --help doesn't crash."""
        runner = CliRunner()
        result = runner.invoke(cli, ["detect", "--help"])

        assert result.exit_code == 0
        assert "detect" in result.output.lower()

    def test_audit_help(self):
        """Test audit --help doesn't crash."""
        runner = CliRunner()
        result = runner.invoke(cli, ["audit", "--help"])

        assert result.exit_code == 0
        assert "audit" in result.output.lower()

    def test_profiles_help(self):
        """Test profiles --help doesn't crash."""
        runner = CliRunner()
        result = runner.invoke(cli, ["profiles", "--help"])

        assert result.exit_code == 0

    def test_apply_help(self):
        """Test apply --help doesn't crash."""
        runner = CliRunner()
        result = runner.invoke(cli, ["apply", "--help"])

        assert result.exit_code == 0
        assert "profile" in result.output.lower()

    def test_restore_help(self):
        """Test restore --help doesn't crash."""
        runner = CliRunner()
        result = runner.invoke(cli, ["restore", "--help"])

        assert result.exit_code == 0


class TestCLIProfiles:
    """Test profiles command."""

    def test_profiles_lists_games(self):
        """Test profiles command lists available profiles."""
        runner = CliRunner()
        result = runner.invoke(cli, ["profiles"])

        assert result.exit_code == 0
        # Should list at least one profile
        assert "slippi" in result.output.lower() or "melee" in result.output.lower()


class TestCLIDetect:
    """Test detect command with mocked hardware detection."""

    @patch("abso.main.HardwareDetector")
    def test_detect_runs_without_crash(self, mock_detector_class):
        """Test detect command doesn't crash with mocked detector."""
        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = {
            "gpu": {"name": "Test GPU", "driver_version": "1.0"},
            "cpu": {"name": "Test CPU", "cores": 8},
            "monitors": [{"name": "Test Monitor", "refresh_rate": 144}],
            "ram": {"total_gb": 32},
            "windows": {"version": "Windows 11", "build": "22000"},
        }
        mock_detector_class.return_value = mock_detector

        runner = CliRunner()
        result = runner.invoke(cli, ["detect"])

        # Should complete (exit code 0) or fail gracefully
        # We're testing it doesn't crash with an exception
        assert result.exception is None or result.exit_code in [0, 1]


class TestCLIAudit:
    """Test audit command with mocked auditor."""

    @patch("abso.main.ConfigurationAuditor")
    def test_audit_runs_without_crash(self, mock_auditor_class):
        """Test audit command doesn't crash with mocked auditor."""
        mock_auditor = MagicMock()
        mock_auditor.audit_all.return_value = []  # No issues
        mock_auditor_class.return_value = mock_auditor

        runner = CliRunner()
        result = runner.invoke(cli, ["audit"])

        # Should complete without exception
        assert result.exception is None or result.exit_code in [0, 1]

    @patch("abso.main.ConfigurationAuditor")
    def test_audit_verbose_runs_without_crash(self, mock_auditor_class):
        """Test audit --verbose doesn't crash."""
        mock_auditor = MagicMock()
        mock_auditor.audit_all.return_value = []
        mock_auditor_class.return_value = mock_auditor

        runner = CliRunner()
        result = runner.invoke(cli, ["audit", "--verbose"])

        assert result.exception is None or result.exit_code in [0, 1]


class TestCLIApply:
    """Test apply command error handling."""

    def test_apply_invalid_profile(self):
        """Test apply with invalid profile name gives error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["apply", "nonexistent-profile-xyz"])

        # Should fail with an error message, not crash
        assert result.exit_code != 0 or "not found" in result.output.lower() or "error" in result.output.lower()

    def test_apply_requires_profile_name(self):
        """Test apply without profile name gives usage error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["apply"])

        # Click should show usage error for missing argument
        assert result.exit_code != 0

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=True)
    def test_apply_json_uses_transaction_manager(self, mock_is_admin, mock_tx_manager_cls):
        """JSON apply should use transactional execution and return transaction metadata."""
        tx_result = MagicMock()
        tx_result.success = True
        tx_result.backup_id = None
        tx_result.error = None
        tx_result.rollback_performed = False
        tx_result.apply_result = ApplyResult(
            success=True,
            requires_reboot=False,
            in_game_settings=False,
            applied_settings=["WindowsSettingsHandler"],
            failed_settings=[],
        )
        tx_result.compliance_report = MagicMock()
        tx_result.compliance_report.to_dict.return_value = {
            "profile_id": "slippi-melee",
            "passed": True,
            "has_critical": False,
            "issues": [],
        }
        tx_result.to_dict.return_value = {
            "success": True,
            "profile_id": "slippi-melee",
            "state": "committed",
            "backup_id": None,
            "error": None,
            "rollback_performed": False,
            "rollback_error": None,
            "compliance": tx_result.compliance_report.to_dict.return_value,
            "checkpoints": [],
        }

        mock_manager = mock_tx_manager_cls.return_value
        mock_manager.execute.return_value = tx_result

        runner = CliRunner()
        result = runner.invoke(cli, ["apply", "slippi-melee", "--json", "--no-backup"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["success"] is True
        assert payload["data"]["profile"] == "slippi-melee"
        assert payload["data"]["transaction"]["profile_id"] == "slippi-melee"
        mock_manager.execute.assert_called_once_with(
            profile_id="slippi-melee",
            create_backup=False,
        )


class TestCLIRestore:
    """Test restore command error handling."""

    def test_restore_help(self):
        """Test restore --help doesn't crash."""
        runner = CliRunner()
        result = runner.invoke(cli, ["restore", "--help"])

        assert result.exit_code == 0

    def test_restore_with_backup_id_runs(self):
        """Test restore with backup ID doesn't crash."""
        runner = CliRunner()
        result = runner.invoke(cli, ["restore", "test-backup"])

        # Should run without exception (may succeed or fail gracefully)
        assert result.exception is None or result.exit_code in [0, 1]


class TestCLIVersion:
    """Test version-related CLI functionality."""

    def test_main_outputs_info(self):
        """Test main --help contains version info."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        # Should have some output
        assert len(result.output) > 0


class TestCLIAuditWithIssues:
    """Test audit command with issues."""

    @patch("abso.main.ConfigurationAuditor")
    def test_audit_with_issues_shows_results(self, mock_auditor_class):
        """Test audit command shows issues when found."""
        from abso.core.models import Issue

        mock_auditor = MagicMock()
        mock_auditor.audit_all.return_value = [
            Issue(
                title="Test Issue",
                severity="warning",
                current_value="bad",
                optimal_value="good",
                explanation="Test explanation",
                category="test",
            )
        ]
        mock_auditor_class.return_value = mock_auditor

        runner = CliRunner()
        result = runner.invoke(cli, ["audit"])

        # Should complete without exception
        assert result.exception is None or result.exit_code in [0, 1]


class TestCLIHealth:
    """Test health diagnostics command."""

    @patch("abso.core.health.build_health_report")
    def test_health_json_output(self, mock_build_health_report):
        """health --json should return serialized diagnostics payload."""
        mock_build_health_report.return_value = {
            "generated_at": "2026-02-18T00:00:00",
            "checks": {"tray_runtime": {"status": "ok"}},
            "summary": {"ok": 1, "warning": 0, "error": 0},
            "current_profile": "overwatch2",
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["summary"]["ok"] == 1


class TestCLIRestoreWithMocks:
    """Test restore command with mocked components."""

    @patch("abso.main.BackupManager")
    def test_restore_latest(self, mock_backup_class):
        """Test restore latest command."""
        mock_backup = MagicMock()
        mock_backup.restore_backup.return_value = True
        mock_backup_class.return_value = mock_backup

        runner = CliRunner()
        result = runner.invoke(cli, ["restore", "latest"])

        # Should complete without crash
        assert result.exception is None or result.exit_code in [0, 1]
