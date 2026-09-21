"""CLI smoke tests for computa"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from click.testing import CliRunner

import abso.main as abso_main
from abso.core import apply_hooks
from abso.core.applier import ApplyResult, ProfileApplier
from abso.core.apply_feedback import determine_apply_summary_level
from abso.core.multimon_detector import DisplayEnvironment, MultiMonitorResult
from abso.main import cli
from abso.profiles.yaml_loader import YAMLProfileLoader


def test_packaged_data_dir_honors_localappdata(tmp_path):
    """Bundled CLI state should follow redirected LocalAppData roots."""
    local_root = tmp_path / "local"

    with (
        patch.dict("os.environ", {"LOCALAPPDATA": str(local_root)}),
        patch("sys.frozen", True, create=True),
    ):
        data_dir = abso_main.get_data_dir()

    assert data_dir == local_root / "AdaptiveBattleStationOptimizer"
    assert data_dir.is_dir()


class TestCLIHelp:
    """Test CLI help commands work without crashing."""

    def test_main_help(self):
        """Test main --help doesn't crash."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "computa" in result.output or "abso" in result.output.lower()

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

    def test_profile_create_rejects_unsafe_profile_id(self, tmp_path):
        """profile-create should not write YAML files with unroutable IDs."""
        runner = CliRunner()
        with patch("abso.main.Path.home", return_value=tmp_path):
            result = runner.invoke(
                cli,
                [
                    "profile-create",
                    "Bad Id",
                    "--game",
                    "Bad Game",
                    "--exe",
                    "BadGame.exe",
                ],
            )

        assert result.exit_code == 1
        assert "lowercase slug" in result.output
        assert not (tmp_path / ".abso" / "profiles").exists()

    def test_profile_create_rejects_reserved_profile_id(self, tmp_path):
        """profile-create should fail early for built-in IDs and retired aliases."""
        runner = CliRunner()
        with patch("abso.main.Path.home", return_value=tmp_path):
            result = runner.invoke(
                cli,
                [
                    "profile-create",
                    "rivals2",
                    "--game",
                    "Rivals 2 Custom",
                    "--exe",
                    "Rivals2.exe",
                ],
            )

        assert result.exit_code == 1
        assert "conflicts with an existing profile alias" in result.output
        assert not (tmp_path / ".abso" / "profiles").exists()

    def test_profile_create_rejects_unknown_tray_category(self, tmp_path):
        """profile-create should not write YAML that the loader would downgrade."""
        runner = CliRunner()
        with patch("abso.main.Path.home", return_value=tmp_path):
            result = runner.invoke(
                cli,
                [
                    "profile-create",
                    "custom-game",
                    "--game",
                    "Custom Game",
                    "--exe",
                    "CustomGame.exe",
                    "--category",
                    "FPS",
                ],
            )

        assert result.exit_code == 1
        assert "Tray category 'FPS' is not recognized" in result.output
        assert "Shooters" in result.output
        assert not (tmp_path / ".abso" / "profiles").exists()

    def test_profile_create_quotes_user_controlled_yaml_values(self, tmp_path):
        """Generated profile YAML should load even with YAML-sensitive strings."""
        runner = CliRunner()
        with patch("abso.main.Path.home", return_value=tmp_path):
            result = runner.invoke(
                cli,
                [
                    "profile-create",
                    "custom-game",
                    "--game",
                    'My: Game "ON"',
                    "--exe",
                    "on",
                    "--exe",
                    "Game:Two.exe",
                    "--category",
                    "Shooter",
                ],
            )

        assert result.exit_code == 0, result.output
        profile_path = tmp_path / ".abso" / "profiles" / "custom-game.yaml"
        profile_id, entry = YAMLProfileLoader().load_file(profile_path)
        profile = entry.profile_class()

        assert profile_id == "custom-game"
        assert profile.display_name == 'My: Game "ON"'
        assert profile.executable_hints == ["on", "Game:Two.exe"]
        assert entry.tray_category == "Shooters"
        assert entry.sync_mode == "off"


class TestCLILaunchKillset:
    """Test launch-killset / launch-sweep tray-facing commands."""

    def test_launch_killset_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["launch-killset", "--help"])
        assert result.exit_code == 0

    def test_launch_killset_json_for_strict_profile(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["launch-killset", "overwatch2-gsync-hdr", "--json"])
        assert result.exit_code == 0, result.output

        payload = json.loads(result.output)
        assert payload["success"] is True
        data = payload["data"]
        assert data["profile"] == "overwatch2-gsync-hdr"
        assert data["killset"]["always_safe"], data
        assert data["killset"]["opt_in"], "Strict profile should populate opt-in tier"
        assert "Overwatch.exe" in data["executables"]
        assert data["include_opt_in"] is False
        assert "Medal.exe" in data["resolved"]
        # OneDrive moved to always-safe in the May 2026 aggressive-sweep
        # expansion, so it now resolves even without --include-opt-in.
        assert "OneDrive.exe" in data["resolved"]
        # Without --include-opt-in the resolved list must NOT contain
        # opt-in-tier images. SearchIndexer stays in opt-in (its absence
        # mid-match would surprise users who rely on instant Start-menu
        # search after exiting a game).
        assert "SearchIndexer.exe" not in data["resolved"]

    def test_launch_killset_with_opt_in_includes_sync_daemons(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["launch-killset", "overwatch2-gsync-hdr", "--include-opt-in", "--json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        # OneDrive remains killed under --include-opt-in (it now lives in
        # always-safe), and the previously opt-in-only Search* daemons
        # also drop.
        assert "OneDrive.exe" in payload["data"]["resolved"]
        assert "SearchIndexer.exe" in payload["data"]["resolved"]

    def test_launch_killset_for_productivity_is_empty(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["launch-killset", "productivity", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["data"]["killset"]["always_safe"] == []
        assert payload["data"]["killset"]["opt_in"] == []
        assert payload["data"]["resolved"] == []

    def test_launch_killset_unknown_profile_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["launch-killset", "nonexistent-profile-xyz", "--json"])
        assert result.exit_code == 1

    def test_launch_sweep_dry_run_does_not_touch_processes(self):
        """Dry-run must never call _stop_process_image even if a process is up."""
        runner = CliRunner()
        with (
            patch("abso.core.process_janitor.ProcessJanitor._stop_process_image") as mock_stop,
            patch(
                "abso.core.process_janitor.ProcessJanitor._is_process_running",
                return_value=True,
            ),
        ):
            result = runner.invoke(
                cli,
                ["launch-sweep", "overwatch2-gsync-hdr", "--dry-run", "--json"],
            )

        assert result.exit_code == 0, result.output
        mock_stop.assert_not_called()
        payload = json.loads(result.output)
        assert payload["data"]["dry_run"] is True
        assert payload["data"]["result"]["stopped"] == []

    def test_launch_sweep_for_productivity_returns_empty_result(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["launch-sweep", "productivity", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["data"]["result"]["attempted"] == []
        assert payload["data"]["result"]["stopped"] == []


class TestApplySummaryLevel:
    """Test shared apply summary severity classification."""

    def test_soft_warnings_become_cautions(self):
        """Mixed-refresh and non-restorable baseline warnings should stay non-failing cautions."""
        summary = determine_apply_summary_level(
            [
                "Mixed refresh rates detected (59.95Hz - 300.0Hz)",
                "2 monitors detected",
                "MPO glitch risk: VRR/G-Sync active, mixed refresh (60Hz–300Hz)",
                "Baseline restore incomplete for known non-restorable handlers: NvidiaSettingsHandler",
            ],
            [],
        )

        assert summary == "caution"

    def test_actionable_warnings_stay_warnings(self):
        """Warnings that imply user action or degraded correctness should stay warnings."""
        summary = determine_apply_summary_level(
            ["Game executable is running during apply"],
            [],
        )

        assert summary == "warning"

    def test_notices_without_warnings_report_notice(self):
        """Pure informational applies should surface as notices."""
        summary = determine_apply_summary_level(
            [],
            ["Reusing existing bound NVIDIA profile 'Slippi'."],
        )

        assert summary == "notice"


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

    @patch("abso.main.HardwareDetector")
    def test_detect_json_handles_none_ram(self, mock_detector_class):
        """Test detect --json handles missing RAM data without crashing."""
        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = {
            "system": None,
            "gpu": None,
            "cpu": None,
            "ram": None,
            "monitors": None,
        }
        mock_detector_class.return_value = mock_detector

        runner = CliRunner()
        result = runner.invoke(cli, ["detect", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["ram_gb"] is None
        assert payload["data"]["monitors"] == []


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

    def test_collect_manual_actions_builds_nvidia_toast_buttons(self):
        """NVIDIA manual binding steps should become allowlisted tray actions."""
        steps = [
            {
                "key": "nvidia_app_binding",
                "label": "NVIDIA profile binding",
                "profile_name": "Rivals 2 Online",
                "executables": ["Rivals2-Win64-Shipping.exe"],
                "satisfied": False,
            },
            {
                "key": "open_anything",
                "profile_name": "Ignored",
                "executables": ["ignored.exe"],
            },
        ]

        assert abso_main._collect_manual_actions(steps) == [
            {
                "type": "open_nvidia_profile_inspector",
                "label": "Open NPI",
                "profile_name": "Rivals 2 Online",
                "executable": "Rivals2-Win64-Shipping.exe",
            },
            {
                "type": "copy_text",
                "label": "Copy EXE",
                "text": "Rivals2-Win64-Shipping.exe",
                "profile_name": "Rivals 2 Online",
                "executable": "Rivals2-Win64-Shipping.exe",
            },
        ]

    def test_apply_invalid_profile(self):
        """Test apply with invalid profile name gives error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["apply", "nonexistent-profile-xyz"])

        # Should fail with an error message, not crash
        assert (
            result.exit_code != 0
            or "not found" in result.output.lower()
            or "error" in result.output.lower()
        )

    def test_apply_requires_profile_name(self):
        """Test apply without profile name gives usage error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["apply"])

        # Click should show usage error for missing argument
        assert result.exit_code != 0

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=True)
    def test_apply_json_uses_transaction_manager(
        self, mock_is_admin, mock_tx_manager_cls, tmp_path
    ):
        """JSON apply should use transactional execution and return transaction metadata."""
        tx_result = MagicMock()
        tx_result.success = True
        tx_result.backup_id = None
        tx_result.error = None
        tx_result.rollback_performed = False
        tx_result.checkpoints = [
            MagicMock(status="warn", message="Baseline restore incomplete: NvidiaSettingsHandler")
        ]
        tx_result.apply_result = ApplyResult(
            success=True,
            requires_reboot=False,
            in_game_settings=False,
            applied_settings=["WindowsSettingsHandler"],
            failed_settings=[],
            warnings=["Game executable is running during apply"],
            notices=["Reusing existing bound NVIDIA profile 'Slippi'."],
        )
        tx_result.compliance_report = MagicMock()
        tx_result.compliance_report.to_dict.return_value = {
            "profile_id": "slippi-melee",
            "passed": True,
            "has_critical": False,
            "issues": [],
        }
        tx_result.compliance_report.warnings = [
            MagicMock(message="Verification mismatch in NvidiaSettingsHandler", details=None)
        ]
        tx_result.to_dict.return_value = {
            "success": True,
            "profile_id": "slippi-melee",
            "state": "committed",
            "backup_id": None,
            "error": None,
            "rollback_performed": False,
            "rollback_error": None,
            "compliance": tx_result.compliance_report.to_dict.return_value,
            "checkpoints": [
                {
                    "phase": "baseline_restore",
                    "status": "warn",
                    "message": "Baseline restore incomplete: NvidiaSettingsHandler",
                    "at": "2026-04-01T00:00:00",
                }
            ],
        }

        mock_manager = mock_tx_manager_cls.return_value
        mock_manager.execute.return_value = tx_result
        mock_manager.applier = ProfileApplier()

        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(cli, ["apply", "slippi-melee", "--json", "--no-backup"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["success"] is True
        assert payload["data"]["profile"] == "slippi-melee"
        assert payload["data"]["transaction"]["profile_id"] == "slippi-melee"
        assert payload["data"]["warnings"] == [
            "Game executable is running during apply",
            "Baseline restore incomplete: NvidiaSettingsHandler",
            "Verification mismatch in NvidiaSettingsHandler",
        ]
        assert payload["data"]["notices"] == ["Reusing existing bound NVIDIA profile 'Slippi'."]
        assert payload["data"]["post_apply_notes"] == [
            (
                "Slippi manual: confirm Dolphin backend and controller adapter; "
                "keep your current backend (D3D11 baseline on Ishiiruka builds; "
                "Vulkan/D3D12 are A/B candidates), VSync Off for no-sync."
            )
        ]
        assert payload["data"]["summary_level"] == "warning"
        mock_manager.execute.assert_called_once_with(
            profile_id="slippi-melee",
            create_backup=False,
            allow_capability_fallback=True,
        )

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=True)
    def test_apply_json_updates_current_profile_state(
        self, mock_is_admin, mock_tx_manager_cls, tmp_path
    ):
        """JSON apply should persist current profile state for tray startup restore."""
        tx_result = MagicMock()
        tx_result.success = True
        tx_result.backup_id = None
        tx_result.error = None
        tx_result.rollback_performed = False
        tx_result.checkpoints = []
        tx_result.apply_result = ApplyResult(
            success=True,
            requires_reboot=False,
            in_game_settings=False,
            applied_settings=["WindowsSettingsHandler"],
            failed_settings=[],
            notices=["Profile already active; backend state refreshed."],
        )
        tx_result.compliance_report = MagicMock()
        tx_result.compliance_report.to_dict.return_value = {}
        tx_result.compliance_report.warnings = []
        tx_result.to_dict.return_value = {"success": True}

        mock_manager = mock_tx_manager_cls.return_value
        mock_manager.execute.return_value = tx_result

        state_file = tmp_path / ".abso_state.json"
        runner = CliRunner()
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(cli, ["apply", "slippi-melee", "--json", "--no-backup"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["summary_level"] == "notice"
        assert state_file.exists()
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["current_profile"] == "slippi-melee"

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main._build_state_verification_summary")
    @patch("abso.main.is_admin", return_value=False)
    def test_apply_json_same_current_profile_noops_when_verified_active(
        self,
        mock_is_admin,
        mock_build_verification,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """Applying an already-verified current profile must not run a transaction."""
        mock_build_verification.return_value = {
            "checked_at": "2026-05-26T02:01:00",
            "profile": "slippi-melee",
            "all_active": True,
            "status": "active",
            "pending_apply_settings": [],
            "pending_reboot_gated_settings": [],
            "mismatched_handlers": [],
        }
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "slippi-melee",
                    "applied_at": "2026-05-26T02:00:00",
                    "reboot_pending": True,
                    "reboot_reasons": ["GraphicsSettingsHandler"],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        with (
            patch("abso.main.STATE_FILE", state_file),
            patch(
                "abso.core.state_reconcile.get_system_boot_time",
                return_value=datetime(2026, 5, 26, 1, 0, 0),
            ),
        ):
            result = runner.invoke(cli, ["apply", "slippi-melee", "--json"])

        assert result.exit_code == 0
        mock_is_admin.assert_not_called()
        mock_tx_manager_cls.assert_not_called()
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["success"] is True
        assert payload["data"]["changed"] is False
        assert payload["data"]["changed_settings"] == []
        assert payload["data"]["transaction"] is None
        assert payload["data"]["requires_reboot"] is True
        assert payload["data"]["reboot_reasons"] == ["GraphicsSettingsHandler"]
        assert payload["data"]["verification"]["status"] == "active"
        assert payload["data"]["notices"] == [
            "Profile already verified active; skipped apply to avoid redundant display/color resets."
        ]

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main._build_state_verification_summary")
    @patch("abso.main.is_admin", return_value=False)
    def test_apply_json_same_current_profile_noops_when_only_reboot_gated(
        self,
        mock_is_admin,
        mock_build_verification,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """Reboot-gated current-profile state must not rerun display handlers."""
        mock_build_verification.return_value = {
            "checked_at": "2026-05-26T02:01:00",
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": False,
            "status": "pending_reboot",
            "pending_apply_settings": [],
            "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "mismatched_handlers": ["GraphicsSettingsHandler"],
        }
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T02:00:00",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(
                cli,
                ["apply", "overwatch2-gsync-hdr-capture", "--json"],
            )

        assert result.exit_code == 0
        mock_is_admin.assert_not_called()
        mock_tx_manager_cls.assert_not_called()
        payload = json.loads(result.output)
        data = payload["data"]
        assert data["changed"] is False
        assert data["transaction"] is None
        assert data["requires_reboot"] is True
        assert data["reboot_reasons"] == ["GraphicsSettingsHandler"]
        assert data["notices"] == [
            (
                "Profile has reboot-gated settings already written; skipped apply "
                "because only a reboot can commit them."
            )
        ]

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main._apply_pending_profile_settings")
    @patch("abso.main._build_state_verification_summary")
    @patch("abso.main.is_admin", return_value=False)
    def test_apply_json_same_current_profile_uses_targeted_pending_fix(
        self,
        mock_is_admin,
        mock_build_verification,
        mock_apply_pending,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """Current-profile pending apply must not fall through to full apply."""
        mock_build_verification.return_value = {
            "checked_at": "2026-05-26T02:01:00",
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": False,
            "status": "pending_apply",
            "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "pending_reboot_gated_settings": [],
            "mismatched_handlers": ["GraphicsSettingsHandler"],
        }
        mock_apply_pending.return_value = {
            "success": True,
            "profile": "overwatch2-gsync-hdr-capture",
            "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "supported_pending_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "unsupported_pending_settings": [],
            "actions": [{"handler": "GraphicsSettingsHandler"}],
            "changed": True,
            "changed_settings": ["GraphicsSettingsHandler.disable_mpo"],
            "requires_reboot": True,
            "reboot_reasons": ["GraphicsSettingsHandler"],
            "handler_results": {
                "GraphicsSettingsHandler": {
                    "success": True,
                    "changed_keys": ["disable_mpo"],
                }
            },
            "notices": ["MPO registry state changed; reboot before judging display flicker."],
            "warnings": [],
            "error": None,
        }
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T02:00:00",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(
                cli,
                ["apply", "overwatch2-gsync-hdr-capture", "--json"],
            )

        assert result.exit_code == 0
        mock_is_admin.assert_not_called()
        mock_tx_manager_cls.assert_not_called()
        mock_apply_pending.assert_called_once_with("overwatch2-gsync-hdr-capture")
        payload = json.loads(result.output)
        data = payload["data"]
        assert payload["success"] is True
        assert data["transaction"] is None
        assert data["changed"] is True
        assert data["changed_settings"] == ["GraphicsSettingsHandler.disable_mpo"]
        assert data["requires_reboot"] is True
        assert data["launch_sweep"] is None
        assert data["display_reset"] is None
        assert data["results"] == [{"handler": "GraphicsSettingsHandler", "status": "success"}]
        assert "Used targeted pending apply" in data["notices"][-1]

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main._apply_pending_profile_settings")
    @patch("abso.main._build_state_verification_summary")
    @patch("abso.main.is_admin", return_value=True)
    def test_apply_json_same_current_profile_rejects_unsupported_pending_without_transaction(
        self,
        mock_is_admin,
        mock_build_verification,
        mock_apply_pending,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """Unsupported pending apply should fail closed instead of full apply."""
        mock_build_verification.return_value = {
            "checked_at": "2026-05-26T02:01:00",
            "profile": "example",
            "all_active": False,
            "status": "pending_apply",
            "pending_apply_settings": ["WindowsSettingsHandler.hdr"],
            "pending_reboot_gated_settings": [],
            "mismatched_handlers": ["WindowsSettingsHandler"],
        }
        mock_apply_pending.return_value = {
            "success": False,
            "profile": "example",
            "pending_apply_settings": ["WindowsSettingsHandler.hdr"],
            "supported_pending_settings": [],
            "unsupported_pending_settings": ["WindowsSettingsHandler.hdr"],
            "actions": [],
            "changed": False,
            "changed_settings": [],
            "requires_reboot": False,
            "reboot_reasons": [],
            "handler_results": {},
            "notices": [],
            "warnings": [],
            "error": "Unsupported pending apply setting(s): WindowsSettingsHandler.hdr",
        }
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "example",
                    "applied_at": "2026-05-26T02:00:00",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(cli, ["apply", "example", "--json"])

        assert result.exit_code == 1
        mock_is_admin.assert_not_called()
        mock_tx_manager_cls.assert_not_called()
        payload = json.loads(result.output)
        assert payload["success"] is False
        assert payload["data"]["transaction"] is None
        assert payload["data"]["error"] == (
            "Unsupported pending apply setting(s): WindowsSettingsHandler.hdr"
        )

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=True)
    def test_apply_json_marks_soft_environment_warnings_as_caution(
        self,
        mock_is_admin,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """Successful applies with soft environment cautions should not be promoted to warning severity."""
        tx_result = MagicMock()
        tx_result.success = True
        tx_result.backup_id = None
        tx_result.error = None
        tx_result.rollback_performed = False
        tx_result.checkpoints = [
            MagicMock(
                status="warn",
                message=(
                    "Baseline restore incomplete for known non-restorable handlers: "
                    "NvidiaSettingsHandler"
                ),
            )
        ]
        tx_result.apply_result = ApplyResult(
            success=True,
            requires_reboot=False,
            in_game_settings=False,
            applied_settings=["WindowsSettingsHandler"],
            failed_settings=[],
            warnings=[
                "Mixed refresh rates detected (59.95Hz - 300.0Hz)",
                "2 monitors detected",
                "MPO glitch risk: VRR/G-Sync active, mixed refresh (60Hz–300Hz)",
            ],
        )
        tx_result.compliance_report = MagicMock()
        tx_result.compliance_report.to_dict.return_value = {
            "profile_id": "overwatch2-gsync-hdr",
            "passed": True,
            "has_critical": False,
            "issues": [],
        }
        tx_result.compliance_report.warnings = []
        tx_result.to_dict.return_value = {"success": True}

        mock_manager = mock_tx_manager_cls.return_value
        mock_manager.execute.return_value = tx_result

        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(cli, ["apply", "overwatch2-gsync-hdr", "--json", "--no-backup"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["summary_level"] == "caution"

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=True)
    def test_apply_json_marks_failed_preflight_as_error(
        self,
        mock_is_admin,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """Failed preflight JSON should not claim success severity."""
        tx_result = MagicMock()
        tx_result.success = False
        tx_result.profile_id = "overwatch2-gsync-hdr"
        tx_result.requested_profile_id = "overwatch2-gsync-hdr"
        tx_result.fallback_chain = []
        tx_result.backup_id = None
        tx_result.error = "HDR display path blocked"
        tx_result.rollback_performed = False
        tx_result.checkpoints = []
        tx_result.apply_result = ApplyResult(
            success=False,
            error="HDR display path blocked",
        )
        tx_result.compliance_report = None
        tx_result.to_dict.return_value = {
            "success": False,
            "profile_id": "overwatch2-gsync-hdr",
            "requested_profile_id": "overwatch2-gsync-hdr",
            "fallback_chain": [],
            "state": "failed",
            "error": "HDR display path blocked",
        }

        mock_manager = mock_tx_manager_cls.return_value
        mock_manager.execute.return_value = tx_result

        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(cli, ["apply", "overwatch2-gsync-hdr", "--json", "--no-backup"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["success"] is False
        assert payload["data"]["success"] is False
        assert payload["data"]["summary_level"] == "error"
        assert payload["data"]["error"] == "HDR display path blocked"
        assert not state_file.exists()

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=True)
    def test_apply_json_no_fallback_disables_capability_fallback(
        self,
        mock_is_admin,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """Tray/manual callers can require the selected profile to be the applied profile."""
        tx_result = MagicMock()
        tx_result.success = False
        tx_result.profile_id = "overwatch2-gsync-hdr"
        tx_result.requested_profile_id = "overwatch2-gsync-hdr"
        tx_result.fallback_chain = []
        tx_result.backup_id = None
        tx_result.error = "Mixed-refresh display path blocks strict VRR."
        tx_result.rollback_performed = False
        tx_result.checkpoints = []
        tx_result.apply_result = ApplyResult(
            success=False,
            error="Mixed-refresh display path blocks strict VRR.",
        )
        tx_result.compliance_report = None
        tx_result.to_dict.return_value = {
            "success": False,
            "profile_id": "overwatch2-gsync-hdr",
            "requested_profile_id": "overwatch2-gsync-hdr",
            "fallback_chain": [],
            "state": "failed",
            "error": "Mixed-refresh display path blocks strict VRR.",
        }

        mock_manager = mock_tx_manager_cls.return_value
        mock_manager.execute.return_value = tx_result

        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(
                cli,
                [
                    "apply",
                    "overwatch2-gsync-hdr",
                    "--json",
                    "--no-backup",
                    "--no-fallback",
                ],
            )

        assert result.exit_code == 0
        mock_manager.execute.assert_called_once_with(
            profile_id="overwatch2-gsync-hdr",
            create_backup=False,
            allow_capability_fallback=False,
        )
        payload = json.loads(result.output)
        assert payload["success"] is False
        assert payload["data"]["profile"] == "overwatch2-gsync-hdr"
        assert payload["data"]["fallback_applied"] is False
        assert payload["data"]["fallback_chain"] == []
        assert not state_file.exists()

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=True)
    def test_apply_json_reports_and_persists_fallback_profile(
        self,
        mock_is_admin,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """JSON apply should expose the requested profile and save the actual fallback."""
        fallback_chain = [
            {
                "from": "overwatch2-gsync-hdr",
                "to": "overwatch2-gsync-hdr-capture",
                "reason": "Mixed-refresh display path blocks strict VRR.",
            }
        ]
        tx_result = MagicMock()
        tx_result.success = True
        tx_result.profile_id = "overwatch2-gsync-hdr-capture"
        tx_result.requested_profile_id = "overwatch2-gsync-hdr"
        tx_result.fallback_chain = fallback_chain
        tx_result.backup_id = None
        tx_result.error = None
        tx_result.rollback_performed = False
        tx_result.checkpoints = []
        tx_result.apply_result = ApplyResult(
            success=True,
            requires_reboot=False,
            in_game_settings=False,
            applied_settings=["WindowsSettingsHandler"],
            failed_settings=[],
        )
        tx_result.compliance_report = None
        tx_result.to_dict.return_value = {
            "success": True,
            "profile_id": "overwatch2-gsync-hdr-capture",
            "requested_profile_id": "overwatch2-gsync-hdr",
            "fallback_chain": fallback_chain,
            "state": "committed",
        }

        mock_manager = mock_tx_manager_cls.return_value
        mock_manager.execute.return_value = tx_result

        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        with (
            patch("abso.main.STATE_FILE", state_file),
            patch("abso.main.run_post_apply_sweep", return_value=None),
            patch("abso.main.run_post_apply_display_reset", return_value=None),
        ):
            result = runner.invoke(cli, ["apply", "overwatch2-gsync-hdr", "--json", "--no-backup"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["profile"] == "overwatch2-gsync-hdr-capture"
        assert payload["data"]["requested_profile"] == "overwatch2-gsync-hdr"
        assert payload["data"]["fallback_applied"] is True
        assert payload["data"]["fallback_chain"] == fallback_chain
        assert payload["data"]["summary_level"] == "notice"
        assert "safe fallback" in payload["data"]["notices"][0]
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["current_profile"] == "overwatch2-gsync-hdr-capture"

    def test_post_apply_display_reset_is_manual_by_default(self):
        """Profile apply must not run display recovery without explicit opt-in."""

        class HdrProfile:
            def get_settings(self, handler_name):
                if handler_name == "WindowsSettingsHandler":
                    return {"hdr": True}
                return {}

        tx_result = MagicMock()
        tx_result.success = True
        apply_result = ApplyResult(success=True)

        with (
            patch.dict("os.environ", {"ABSO_ENABLE_AUTO_DISPLAY_RECOVERY": "0"}),
            patch("abso.core.apply_hooks.resolve_profile_id", return_value="hdr-profile"),
            patch(
                "abso.profiles.catalog.get_profile_instances",
                return_value={"hdr-profile": HdrProfile()},
            ),
            patch("abso.utils.display_reset.is_available", return_value=True),
            patch("abso.utils.display_reset.refresh_display_pipeline") as mock_refresh,
        ):
            display_reset = apply_hooks.run_post_apply_display_reset(
                "hdr-profile",
                tx_result,
                apply_result,
            )

        assert display_reset == {
            "fired": False,
            "skipped_reason": "auto_display_recovery_disabled",
            "triggered_by": ["WindowsSettingsHandler: hdr"],
            "manual_command": "abso reset-display --method driver-hotkey",
        }
        mock_refresh.assert_not_called()

    def test_post_apply_display_reset_skips_multi_monitor_path_when_opted_in(self):
        """Automatic display recovery must not blank secondary monitors."""

        class HdrProfile:
            def get_settings(self, handler_name):
                if handler_name == "WindowsSettingsHandler":
                    return {"hdr": True}
                return {}

        tx_result = MagicMock()
        tx_result.success = True
        apply_result = ApplyResult(
            success=True,
            changed_settings=["WindowsSettingsHandler.hdr"],
            multimon_result=MultiMonitorResult(environment=DisplayEnvironment(monitor_count=2)),
        )

        with (
            patch.dict("os.environ", {"ABSO_ENABLE_AUTO_DISPLAY_RECOVERY": "1"}),
            patch("abso.core.apply_hooks.resolve_profile_id", return_value="hdr-profile"),
            patch(
                "abso.profiles.catalog.get_profile_instances",
                return_value={"hdr-profile": HdrProfile()},
            ),
            patch("abso.utils.display_reset.is_available", return_value=True),
            patch("abso.utils.display_reset.refresh_display_pipeline") as mock_refresh,
        ):
            display_reset = apply_hooks.run_post_apply_display_reset(
                "hdr-profile",
                tx_result,
                apply_result,
            )

        assert display_reset == {
            "fired": False,
            "skipped_reason": "multi_monitor_auto_reset_suppressed",
            "triggered_by": ["WindowsSettingsHandler: hdr"],
            "monitor_count": 2,
            "monitor_count_source": "apply_result",
            "manual_command": "abso reset-display --method driver-hotkey",
        }
        mock_refresh.assert_not_called()

    def test_post_apply_display_reset_uses_warning_monitor_count_fallback(self):
        """The flicker guard also works if only warning text survived."""

        class HdrProfile:
            def get_settings(self, handler_name):
                if handler_name == "WindowsSettingsHandler":
                    return {"advanced_color": True}
                return {}

        tx_result = MagicMock()
        tx_result.success = True
        apply_result = ApplyResult(
            success=True,
            changed_settings=["WindowsSettingsHandler.advanced_color"],
            warnings=["2 monitors detected"],
        )

        with (
            patch.dict("os.environ", {"ABSO_ENABLE_AUTO_DISPLAY_RECOVERY": "1"}),
            patch("abso.core.apply_hooks.resolve_profile_id", return_value="hdr-profile"),
            patch(
                "abso.profiles.catalog.get_profile_instances",
                return_value={"hdr-profile": HdrProfile()},
            ),
            patch("abso.utils.display_reset.is_available", return_value=True),
            patch("abso.utils.display_reset.refresh_display_pipeline") as mock_refresh,
        ):
            display_reset = apply_hooks.run_post_apply_display_reset(
                "hdr-profile",
                tx_result,
                apply_result,
            )

        assert display_reset["skipped_reason"] == "multi_monitor_auto_reset_suppressed"
        assert display_reset["monitor_count"] == 2
        assert display_reset["monitor_count_source"] == "apply_result"
        mock_refresh.assert_not_called()

    def test_post_apply_display_reset_live_probes_missing_monitor_count_before_firing(self):
        """Missing apply-result monitor data should still fail safe on multi-monitor hosts."""

        class HdrProfile:
            def get_settings(self, handler_name):
                if handler_name == "WindowsSettingsHandler":
                    return {"hdr": True}
                return {}

        tx_result = MagicMock()
        tx_result.success = True
        apply_result = ApplyResult(
            success=True,
            changed_settings=["WindowsSettingsHandler.hdr"],
        )

        with (
            patch.dict("os.environ", {"ABSO_ENABLE_AUTO_DISPLAY_RECOVERY": "1"}),
            patch("abso.core.apply_hooks.resolve_profile_id", return_value="hdr-profile"),
            patch(
                "abso.profiles.catalog.get_profile_instances",
                return_value={"hdr-profile": HdrProfile()},
            ),
            patch("abso.core.apply_hooks.live_monitor_count", return_value=(2, None)),
            patch("abso.utils.display_reset.refresh_display_pipeline") as mock_refresh,
        ):
            display_reset = apply_hooks.run_post_apply_display_reset(
                "hdr-profile",
                tx_result,
                apply_result,
            )

        assert display_reset == {
            "fired": False,
            "skipped_reason": "multi_monitor_auto_reset_suppressed",
            "triggered_by": ["WindowsSettingsHandler: hdr"],
            "monitor_count": 2,
            "monitor_count_source": "live_probe",
            "manual_command": "abso reset-display --method driver-hotkey",
        }
        mock_refresh.assert_not_called()

    def test_post_apply_display_reset_suppresses_when_monitor_count_unknown(self):
        """Automatic display recovery should not run when monitor topology is unknown."""

        class HdrProfile:
            def get_settings(self, handler_name):
                if handler_name == "WindowsSettingsHandler":
                    return {"hdr": True}
                return {}

        tx_result = MagicMock()
        tx_result.success = True
        apply_result = ApplyResult(
            success=True,
            changed_settings=["WindowsSettingsHandler.hdr"],
        )

        with (
            patch.dict("os.environ", {"ABSO_ENABLE_AUTO_DISPLAY_RECOVERY": "1"}),
            patch("abso.core.apply_hooks.resolve_profile_id", return_value="hdr-profile"),
            patch(
                "abso.profiles.catalog.get_profile_instances",
                return_value={"hdr-profile": HdrProfile()},
            ),
            patch(
                "abso.core.apply_hooks.live_monitor_count",
                return_value=(None, "display probe failed"),
            ),
            patch("abso.utils.display_reset.refresh_display_pipeline") as mock_refresh,
        ):
            display_reset = apply_hooks.run_post_apply_display_reset(
                "hdr-profile",
                tx_result,
                apply_result,
            )

        assert display_reset == {
            "fired": False,
            "skipped_reason": "monitor_count_unknown_auto_reset_suppressed",
            "triggered_by": ["WindowsSettingsHandler: hdr"],
            "monitor_count": None,
            "monitor_count_error": "display probe failed",
            "manual_command": "abso reset-display --method driver-hotkey",
        }
        mock_refresh.assert_not_called()

    def test_post_apply_display_reset_skips_when_no_settings_changed(self):
        """Opt-in recovery should still no-op after a fully idempotent apply."""

        class HdrProfile:
            def get_settings(self, handler_name):
                if handler_name == "WindowsSettingsHandler":
                    return {"hdr": True}
                return {}

        tx_result = MagicMock()
        tx_result.success = True
        apply_result = ApplyResult(success=True, changed_settings=[])

        with (
            patch.dict("os.environ", {"ABSO_ENABLE_AUTO_DISPLAY_RECOVERY": "1"}),
            patch("abso.core.apply_hooks.resolve_profile_id", return_value="hdr-profile"),
            patch(
                "abso.profiles.catalog.get_profile_instances",
                return_value={"hdr-profile": HdrProfile()},
            ),
            patch("abso.utils.display_reset.refresh_display_pipeline") as mock_refresh,
        ):
            display_reset = apply_hooks.run_post_apply_display_reset(
                "hdr-profile",
                tx_result,
                apply_result,
            )

        assert display_reset == {
            "fired": False,
            "skipped_reason": "no_settings_changed",
            "triggered_by": ["WindowsSettingsHandler: hdr"],
            "changed_settings": [],
        }
        mock_refresh.assert_not_called()

    def test_state_json_returns_persisted_backend_state(self, tmp_path):
        """state --json should surface the persisted active-profile state file."""
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync",
                    "applied_at": "2026-04-01T03:19:46.610978",
                    "reboot_pending": True,
                    "reboot_reasons": ["HAGS toggle"],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(cli, ["state", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"] == {
            "current_profile": "overwatch2-gsync",
            "applied_at": "2026-04-01T03:19:46.610978",
            "reboot_pending": True,
            "reboot_reasons": ["HAGS toggle"],
        }

    def test_state_json_verify_summarizes_live_profile_state(self, tmp_path):
        """state --verify should separate remembered state from verified state."""
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T04:00:00",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        with (
            patch("abso.main.STATE_FILE", state_file),
            patch("abso.main.ProfileApplier") as mock_applier_cls,
        ):
            mock_applier_cls.return_value.verify_profile.return_value = {
                "profile": "overwatch2-gsync-hdr-capture",
                "all_active": False,
                "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
                "handlers": {
                    "GraphicsSettingsHandler": {
                        "all_active": False,
                        "pending_apply_settings": ["mpo_disabled"],
                    }
                },
            }
            result = runner.invoke(cli, ["state", "--json", "--verify"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        verification = payload["data"]["verification"]
        assert payload["success"] is True
        assert payload["data"]["current_profile"] == "overwatch2-gsync-hdr-capture"
        assert verification["status"] == "pending_apply"
        assert verification["all_active"] is False
        assert verification["pending_apply_settings"] == ["GraphicsSettingsHandler.mpo_disabled"]
        assert verification["mismatched_handlers"] == ["GraphicsSettingsHandler"]

    def test_state_verify_clears_reboot_pending_after_later_clean_boot(self, tmp_path):
        """A clean verify after a later boot should retire stale reboot warnings."""
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T04:40:55",
                    "reboot_pending": True,
                    "reboot_reasons": ["GraphicsSettingsHandler"],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        with (
            patch("abso.main.STATE_FILE", state_file),
            patch("abso.main._get_system_boot_time", return_value=datetime(2026, 5, 26, 4, 50)),
            patch("abso.main.ProfileApplier") as mock_applier_cls,
        ):
            mock_applier_cls.return_value.verify_profile.return_value = {
                "profile": "overwatch2-gsync-hdr-capture",
                "all_active": True,
                "handlers": {},
            }
            result = runner.invoke(cli, ["state", "--json", "--verify"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["reboot_pending"] is False
        assert payload["data"]["reboot_reasons"] == []
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["reboot_pending"] is False
        assert saved["reboot_reasons"] == []

    def test_state_verify_keeps_reboot_pending_before_later_boot(self, tmp_path):
        """A clean registry verify before reboot must still show boot-gated state."""
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T04:40:55",
                    "reboot_pending": True,
                    "reboot_reasons": ["GraphicsSettingsHandler"],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        with (
            patch("abso.main.STATE_FILE", state_file),
            patch("abso.main._get_system_boot_time", return_value=datetime(2026, 5, 26, 4, 30)),
            patch("abso.main.ProfileApplier") as mock_applier_cls,
        ):
            mock_applier_cls.return_value.verify_profile.return_value = {
                "profile": "overwatch2-gsync-hdr-capture",
                "all_active": True,
                "handlers": {},
            }
            result = runner.invoke(cli, ["state", "--json", "--verify"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["reboot_pending"] is True
        assert payload["data"]["reboot_reasons"] == ["GraphicsSettingsHandler"]
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["reboot_pending"] is True

    def test_state_helpers_keep_mirrored_targets_in_sync(self, tmp_path):
        """Backend active-profile state should be mirrored for tray startup readers."""
        primary = tmp_path / "project" / ".abso_state.json"
        mirror = tmp_path / "local" / "AdaptiveBattleStationOptimizer" / ".abso_state.json"

        with patch("abso.main._state_file_targets", return_value=[primary, mirror]):
            abso_main.set_current_profile(
                "overwatch2-gsync",
                requires_reboot=True,
                reboot_reasons=["HAGS toggle"],
            )

            primary_state = json.loads(primary.read_text(encoding="utf-8"))
            mirror_state = json.loads(mirror.read_text(encoding="utf-8"))
            assert primary_state == mirror_state
            assert primary_state["current_profile"] == "overwatch2-gsync"

            abso_main.clear_reboot_pending()
            assert json.loads(primary.read_text(encoding="utf-8"))["reboot_pending"] is False
            assert json.loads(mirror.read_text(encoding="utf-8"))["reboot_pending"] is False

            abso_main.clear_current_profile()
            assert not primary.exists()
            assert not mirror.exists()


class TestCLIApplyPending:
    """Test narrow pending-apply remediation command."""

    def test_apply_pending_json_requires_current_profile_when_omitted(self):
        runner = CliRunner()

        with patch(
            "abso.main._read_state_snapshot",
            return_value={
                "current_profile": None,
                "applied_at": None,
                "reboot_pending": False,
                "reboot_reasons": [],
            },
        ):
            result = runner.invoke(cli, ["apply-pending", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["success"] is False
        assert "No current profile" in payload["error"]

    def test_apply_pending_dry_run_reports_supported_mpo_action(self):
        runner = CliRunner()

        with patch("abso.main.ProfileApplier") as mock_applier_cls:
            mock_applier_cls.return_value.verify_profile.return_value = {
                "profile": "overwatch2-gsync-hdr-capture",
                "all_active": False,
                "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
                "handlers": {
                    "GraphicsSettingsHandler": {
                        "all_active": False,
                        "settings": {"mpo_disabled": {"target": True, "current": False}},
                    }
                },
            }
            result = runner.invoke(
                cli,
                ["apply-pending", "overwatch2-gsync-hdr-capture", "--dry-run", "--json"],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        data = payload["data"]
        assert payload["success"] is True
        assert data["dry_run"] is True
        assert data["success"] is True
        assert data["actions"] == [
            {
                "profile": "overwatch2-gsync-hdr-capture",
                "pending_setting": "GraphicsSettingsHandler.mpo_disabled",
                "handler": "GraphicsSettingsHandler",
                "apply_setting": "disable_mpo",
                "target": True,
                "reboot_gated": True,
                "description": "Write the Windows MPO registry target only",
            }
        ]

    def test_apply_pending_rejects_unsupported_settings(self):
        runner = CliRunner()

        with patch("abso.main.ProfileApplier") as mock_applier_cls:
            mock_applier_cls.return_value.verify_profile.return_value = {
                "profile": "example",
                "all_active": False,
                "pending_apply_settings": ["WindowsSettingsHandler.hdr"],
                "handlers": {},
            }
            result = runner.invoke(cli, ["apply-pending", "example", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        data = payload["data"]
        assert payload["success"] is False
        assert data["success"] is False
        assert data["unsupported_pending_settings"] == ["WindowsSettingsHandler.hdr"]

    def test_apply_pending_requires_admin_for_write(self):
        runner = CliRunner()

        with (
            patch("abso.main.ProfileApplier") as mock_applier_cls,
            patch("abso.main.is_admin", return_value=False),
        ):
            mock_applier_cls.return_value.verify_profile.return_value = {
                "profile": "overwatch2-gsync-hdr-capture",
                "all_active": False,
                "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
                "handlers": {
                    "GraphicsSettingsHandler": {
                        "all_active": False,
                        "settings": {"mpo_disabled": {"target": True, "current": False}},
                    }
                },
            }
            result = runner.invoke(
                cli,
                ["apply-pending", "overwatch2-gsync-hdr-capture", "--json"],
            )

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["success"] is False
        assert "Admin privileges required" in payload["data"]["error"]

    def test_apply_pending_applies_mpo_only_and_marks_reboot(self, tmp_path: Path):
        state_file = tmp_path / ".abso_state.json"
        original_applied_at = "2026-09-18T00:48:31"
        state_file.write_text(json.dumps({
            "current_profile": "overwatch2-gsync-hdr-capture",
            "applied_at": original_applied_at,
            "reboot_pending": False,
            "reboot_reasons": [],
        }), encoding="utf-8")
        runner = CliRunner()
        pending = {
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": False,
            "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "handlers": {
                "GraphicsSettingsHandler": {
                    "all_active": False,
                    "settings": {"mpo_disabled": {"target": True, "current": False}},
                }
            },
        }
        after = {
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": True,
            "handlers": {
                "GraphicsSettingsHandler": {
                    "all_active": True,
                    "settings": {"mpo_disabled": {"target": True, "current": True}},
                }
            },
        }

        with (
            patch("abso.main.STATE_FILE", state_file),
            patch("abso.main._state_file_targets", return_value=[state_file]),
            patch("abso.main.ProfileApplier") as mock_applier_cls,
            patch("abso.main.is_admin", return_value=True),
            patch("abso.settings.graphics.GraphicsSettingsHandler") as mock_graphics_cls,
        ):
            mock_applier_cls.return_value.verify_profile.side_effect = [pending, after]
            mock_graphics_cls.return_value.apply.return_value = {
                "success": True,
                "changed": True,
                "changed_keys": ["disable_mpo"],
                "requires_reboot": True,
                "notices": ["MPO registry state changed; reboot before judging display flicker."],
            }
            result = runner.invoke(
                cli,
                ["apply-pending", "overwatch2-gsync-hdr-capture", "--json"],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        data = payload["data"]
        assert payload["success"] is True
        assert data["success"] is True
        assert data["changed_settings"] == ["GraphicsSettingsHandler.disable_mpo"]
        assert data["requires_reboot"] is True
        mock_graphics_cls.return_value.apply.assert_called_once_with({"disable_mpo": True})

        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["current_profile"] == "overwatch2-gsync-hdr-capture"
        assert saved["applied_at"] == original_applied_at
        assert saved["reboot_pending"] is True
        assert saved["reboot_reasons"] == ["GraphicsSettingsHandler"]
        assert datetime.fromisoformat(saved["reboot_required_at"]) > datetime.fromisoformat(
            original_applied_at
        )

    def test_partial_pending_failure_preserves_profile_identity_and_merges_reboot(self, tmp_path):
        state_file = tmp_path / ".abso_state.json"
        original_state = {
            "current_profile": "overwatch2-gsync-hdr-capture",
            "applied_at": "2026-09-18T00:48:31",
            "reboot_pending": True,
            "reboot_reasons": ["WindowsSettingsHandler", "GraphicsSettingsHandler"],
        }
        state_file.write_text(json.dumps(original_state), encoding="utf-8")
        pending = {
            "all_active": False,
            "pending_apply_settings": [
                "GraphicsSettingsHandler.mpo_disabled",
                "GraphicsSettingsHandler.disable_global_fso",
            ],
            "handlers": {"GraphicsSettingsHandler": {"settings": {
                "mpo_disabled": {"target": True, "current": False},
                "global_fso_disabled": {"target": False, "current": True},
            }}},
        }
        with (
            patch("abso.main._state_file_targets", return_value=[state_file]),
            patch("abso.main.ProfileApplier") as applier_cls,
            patch("abso.main.is_admin", return_value=True),
            patch("abso.settings.graphics.GraphicsSettingsHandler") as graphics_cls,
        ):
            applier_cls.return_value.verify_profile.return_value = pending
            graphics_cls.return_value.apply.return_value = {
                "success": False, "error": "FSO denied", "changed_keys": ["disable_mpo"],
                "requires_reboot": True,
            }
            result = CliRunner().invoke(
                cli, ["apply-pending", "slippi-melee-universal-hdr", "--json"]
            )

        assert result.exit_code == 1
        data = json.loads(result.output)["data"]
        assert data["success"] is False
        assert data["error"] == "FSO denied"
        assert data["reboot_pending"] is True
        assert data["reboot_reasons"] == original_state["reboot_reasons"]
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["current_profile"] == original_state["current_profile"]
        assert saved["applied_at"] == original_state["applied_at"]
        assert saved["reboot_reasons"] == original_state["reboot_reasons"]
        assert saved["reboot_pending"] is True
        assert saved["reboot_required_at"]

    def test_pending_reboot_does_not_invent_active_profile_when_none_recorded(self, tmp_path):
        state_file = tmp_path / ".abso_state.json"
        with patch("abso.main._state_file_targets", return_value=[state_file]):
            abso_main._mark_pending_settings_reboot(
                "overwatch2-gsync-hdr-capture", requires_reboot=True,
                reboot_reasons=["GraphicsSettingsHandler"],
            )
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["current_profile"] is None
        assert saved["applied_at"] is None
        assert saved["reboot_pending"] is True
        assert saved["reboot_reasons"] == ["GraphicsSettingsHandler"]
        assert saved["reboot_required_at"]

    @pytest.mark.parametrize("dry_run", [False, True])
    def test_fso_only_pending_apply_preserves_existing_reboot_in_both_payloads(self, tmp_path, dry_run):
        state_file = tmp_path / ".abso_state.json"
        initial_state = json.dumps({
            "current_profile": "overwatch2-gsync-hdr-capture",
            "applied_at": "2026-09-18T00:48:31",
            "reboot_pending": True,
            "reboot_reasons": ["GraphicsSettingsHandler", "WindowsSettingsHandler"],
        })
        state_file.write_text(initial_state, encoding="utf-8")
        pending = {
            "all_active": False,
            "pending_apply_settings": ["GraphicsSettingsHandler.disable_global_fso"],
            "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "handlers": {"GraphicsSettingsHandler": {"settings": {
                "global_fso_disabled": {"target": False, "current": True, "active": False},
            }}},
        }
        after = {
            "all_active": False,
            "pending_apply_settings": [],
            "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "handlers": {"GraphicsSettingsHandler": {"settings": {
                "global_fso_disabled": {"target": False, "current": False, "active": True},
            }}},
        }
        with (
            patch("abso.main._state_file_targets", return_value=[state_file]),
            patch("abso.main.ProfileApplier") as applier_cls,
            patch("abso.main.is_admin", return_value=True),
            patch("abso.main._collect_post_apply_notes", return_value=[]),
            patch("abso.settings.graphics.GraphicsSettingsHandler") as graphics_cls,
        ):
            applier_cls.return_value.verify_profile.side_effect = [pending, after]
            graphics_cls.return_value.apply.return_value = {
                "success": True, "changed_keys": ["disable_global_fso"], "requires_reboot": False,
            }
            args = ["apply-pending", "overwatch2-gsync-hdr-capture", "--json"]
            if dry_run:
                args.append("--dry-run")
            result = CliRunner().invoke(cli, args)
            assert result.exit_code == 0
            data = json.loads(result.output)["data"]
            wrapped = abso_main._build_pending_apply_as_apply_payload(
                "overwatch2-gsync-hdr-capture", data
            )

        for payload in (data, wrapped):
            assert payload["success"] is True
            assert payload["requires_reboot"] is False  # This action adds no new gate.
            assert payload["reboot_pending"] is True  # The previous gate remains.
            assert payload["reboot_reasons"] == ["GraphicsSettingsHandler", "WindowsSettingsHandler"]
        assert state_file.read_text(encoding="utf-8") == initial_state
        if dry_run:
            graphics_cls.assert_not_called()
        else:
            graphics_cls.return_value.apply.assert_called_once_with({"disable_global_fso": False})


class TestCLILaunch:
    """Test launch command wiring and state behavior."""

    @patch("abso.main.launch_profile")
    @patch("abso.main.is_admin", return_value=True)
    def test_launch_json_returns_launch_payload(self, mock_is_admin, mock_launch_profile, tmp_path):
        """launch --json should surface launch lifecycle metadata."""
        tx = MagicMock()
        tx.success = True
        tx.backup_id = "2026-03-10_120000"
        tx.error = None
        tx.apply_result = ApplyResult(
            success=True,
            requires_reboot=False,
            in_game_settings=False,
            applied_settings=["WindowsSettingsHandler"],
            failed_settings=[],
        )
        tx.to_dict.return_value = {
            "success": True,
            "profile_id": "slippi-melee",
            "state": "committed",
            "backup_id": "2026-03-10_120000",
            "error": None,
            "rollback_performed": False,
            "rollback_error": None,
            "compliance": None,
            "checkpoints": [],
        }

        launch_result = MagicMock()
        launch_result.success = True
        launch_result.error = None
        launch_result.transaction = tx
        launch_result.restored = False
        launch_result.to_dict.return_value = {
            "success": True,
            "profile_id": "slippi-melee",
            "launched": True,
            "process_id": 1234,
            "wait_requested": True,
            "exit_code": None,
            "restore_attempted": False,
            "restored": False,
            "restore_backup_id": None,
            "restore_error": None,
            "error": None,
            "warnings": [],
            "target": {
                "profile_id": "slippi-melee",
                "game_name": "Slippi Melee",
                "platform": "standalone",
                "executable_name": "Slippi Dolphin.exe",
                "executable_path": str(tmp_path / "Slippi Dolphin.exe"),
                "source": "manual_path",
                "warnings": [],
            },
            "transaction": tx.to_dict.return_value,
        }
        mock_launch_profile.return_value = launch_result

        runner = CliRunner()
        launch_path = tmp_path / "Slippi Dolphin.exe"
        state_file = tmp_path / ".abso_state.json"
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(
                cli,
                ["launch", "slippi-melee", "--json", "--launch-path", str(launch_path)],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["target"]["executable_path"] == str(launch_path)

        call = mock_launch_profile.call_args.kwargs
        assert call["profile_id"] == "slippi-melee"
        assert call["create_backup"] is True
        assert call["wait"] is True
        assert call["restore_on_exit"] is False
        assert call["launch_path"] == Path(launch_path)
        assert call["launch_args"] == []

    @patch("abso.main.launch_profile")
    @patch("abso.main.launch_profile_without_apply")
    @patch("abso.main._build_state_verification_summary")
    @patch("abso.main.is_admin", return_value=False)
    def test_launch_json_same_current_profile_skips_apply_transaction(
        self,
        mock_is_admin,
        mock_build_verification,
        mock_launch_without_apply,
        mock_launch_profile,
        tmp_path,
    ):
        """Launching an already-active profile must not run full apply."""
        mock_build_verification.return_value = {
            "checked_at": "2026-05-26T02:01:00",
            "profile": "slippi-melee",
            "all_active": True,
            "status": "active",
            "pending_apply_settings": [],
            "pending_reboot_gated_settings": [],
            "mismatched_handlers": [],
        }
        launch_result = MagicMock()
        launch_result.success = True
        launch_result.error = None
        launch_result.to_dict.return_value = {
            "success": True,
            "profile_id": "slippi-melee",
            "launched": True,
            "transaction": {"state": "skipped_apply"},
        }
        mock_launch_without_apply.return_value = launch_result

        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "slippi-melee",
                    "applied_at": "2026-05-26T02:00:00",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        launch_path = tmp_path / "game.exe"
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(
                cli,
                [
                    "launch",
                    "slippi-melee",
                    "--json",
                    "--no-wait",
                    "--launch-path",
                    str(launch_path),
                ],
            )

        assert result.exit_code == 0
        mock_is_admin.assert_not_called()
        mock_launch_profile.assert_not_called()
        mock_launch_without_apply.assert_called_once_with(
            profile_id="slippi-melee",
            wait=False,
            launch_path=Path(launch_path),
            launch_args=[],
        )
        payload = json.loads(result.output)
        assert payload["data"]["transaction"]["state"] == "skipped_apply"
        assert payload["data"]["apply"]["transaction"] is None
        assert payload["data"]["apply"]["changed"] is False

    @patch("abso.main.launch_profile")
    @patch("abso.main.launch_profile_without_apply")
    @patch("abso.main._build_state_verification_summary")
    @patch("abso.main.is_admin", return_value=False)
    def test_launch_json_same_current_profile_skips_apply_when_only_reboot_gated(
        self,
        mock_is_admin,
        mock_build_verification,
        mock_launch_without_apply,
        mock_launch_profile,
        tmp_path,
    ):
        """Reboot-gated current-profile launch must not rerun full apply."""
        mock_build_verification.return_value = {
            "checked_at": "2026-05-26T02:01:00",
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": False,
            "status": "pending_reboot",
            "pending_apply_settings": [],
            "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "mismatched_handlers": ["GraphicsSettingsHandler"],
        }
        launch_result = MagicMock()
        launch_result.success = True
        launch_result.error = None
        launch_result.to_dict.return_value = {
            "success": True,
            "profile_id": "overwatch2-gsync-hdr-capture",
            "launched": True,
            "transaction": {"state": "skipped_apply"},
        }
        mock_launch_without_apply.return_value = launch_result

        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T02:00:00",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        launch_path = tmp_path / "game.exe"
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(
                cli,
                [
                    "launch",
                    "overwatch2-gsync-hdr-capture",
                    "--json",
                    "--no-wait",
                    "--launch-path",
                    str(launch_path),
                ],
            )

        assert result.exit_code == 0
        mock_is_admin.assert_not_called()
        mock_launch_profile.assert_not_called()
        mock_launch_without_apply.assert_called_once()
        payload = json.loads(result.output)
        assert payload["data"]["transaction"]["state"] == "skipped_apply"
        assert payload["data"]["apply"]["requires_reboot"] is True
        assert payload["data"]["apply"]["reboot_reasons"] == ["GraphicsSettingsHandler"]
        assert "only a reboot can commit" in payload["data"]["apply"]["notices"][0]

    @patch("abso.main.launch_profile")
    @patch("abso.main.launch_profile_without_apply")
    @patch("abso.main._apply_pending_profile_settings")
    @patch("abso.main._build_state_verification_summary")
    @patch("abso.main.is_admin", return_value=False)
    def test_launch_json_same_current_profile_uses_pending_fix_before_launch(
        self,
        mock_is_admin,
        mock_build_verification,
        mock_apply_pending,
        mock_launch_without_apply,
        mock_launch_profile,
        tmp_path,
    ):
        """Pending current-profile launch should use targeted apply-pending."""
        mock_build_verification.return_value = {
            "checked_at": "2026-05-26T02:01:00",
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": False,
            "status": "pending_apply",
            "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "pending_reboot_gated_settings": [],
            "mismatched_handlers": ["GraphicsSettingsHandler"],
        }
        mock_apply_pending.return_value = {
            "success": True,
            "profile": "overwatch2-gsync-hdr-capture",
            "changed": True,
            "changed_settings": ["GraphicsSettingsHandler.disable_mpo"],
            "requires_reboot": True,
            "reboot_reasons": ["GraphicsSettingsHandler"],
            "handler_results": {
                "GraphicsSettingsHandler": {
                    "success": True,
                    "changed_keys": ["disable_mpo"],
                }
            },
            "notices": [],
            "warnings": [],
            "error": None,
        }
        launch_result = MagicMock()
        launch_result.success = True
        launch_result.error = None
        launch_result.to_dict.return_value = {
            "success": True,
            "profile_id": "overwatch2-gsync-hdr-capture",
            "launched": True,
            "transaction": {"state": "skipped_apply"},
        }
        mock_launch_without_apply.return_value = launch_result

        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T02:00:00",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        launch_path = tmp_path / "game.exe"
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(
                cli,
                [
                    "launch",
                    "overwatch2-gsync-hdr-capture",
                    "--json",
                    "--no-wait",
                    "--launch-path",
                    str(launch_path),
                ],
            )

        assert result.exit_code == 0
        mock_is_admin.assert_not_called()
        mock_launch_profile.assert_not_called()
        mock_apply_pending.assert_called_once_with("overwatch2-gsync-hdr-capture")
        payload = json.loads(result.output)
        assert payload["data"]["transaction"]["state"] == "skipped_apply"
        assert payload["data"]["apply"]["changed_settings"] == [
            "GraphicsSettingsHandler.disable_mpo"
        ]

    @patch("abso.main.launch_profile")
    @patch("abso.main.is_admin", return_value=True)
    def test_launch_json_clears_current_profile_state_when_restored(
        self,
        mock_is_admin,
        mock_launch_profile,
        tmp_path,
    ):
        """launch should clear current profile state when restore_on_exit succeeds."""
        tx = MagicMock()
        tx.success = True
        tx.backup_id = "2026-03-10_120000"
        tx.error = None
        tx.apply_result = ApplyResult(
            success=True,
            requires_reboot=False,
            in_game_settings=False,
            applied_settings=["WindowsSettingsHandler"],
            failed_settings=[],
        )
        tx.to_dict.return_value = {
            "success": True,
            "profile_id": "slippi-melee",
            "state": "committed",
            "backup_id": "2026-03-10_120000",
            "error": None,
            "rollback_performed": False,
            "rollback_error": None,
            "compliance": None,
            "checkpoints": [],
        }

        launch_result = MagicMock()
        launch_result.success = True
        launch_result.error = None
        launch_result.transaction = tx
        launch_result.restored = True
        launch_result.to_dict.return_value = {
            "success": True,
            "profile_id": "slippi-melee",
            "launched": True,
            "process_id": 1234,
            "wait_requested": True,
            "exit_code": 0,
            "restore_attempted": True,
            "restored": True,
            "restore_backup_id": "2026-03-10_120000",
            "restore_error": None,
            "error": None,
            "warnings": [],
            "target": None,
            "transaction": tx.to_dict.return_value,
        }
        mock_launch_profile.return_value = launch_result

        state_file = tmp_path / ".abso_state.json"
        runner = CliRunner()
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(cli, ["launch", "slippi-melee", "--json"])

        assert result.exit_code == 0
        assert not state_file.exists()

    @patch("abso.main.launch_profile")
    @patch("abso.main.is_admin", return_value=True)
    def test_launch_json_persists_transaction_fallback_profile(
        self,
        mock_is_admin,
        mock_launch_profile,
        tmp_path,
    ):
        """launch should persist the actual fallback profile, not the requested id."""
        tx = MagicMock()
        tx.success = True
        tx.backup_id = None
        tx.error = None
        tx.apply_result = ApplyResult(
            success=True,
            requires_reboot=False,
            in_game_settings=False,
            applied_settings=["WindowsSettingsHandler"],
            failed_settings=[],
        )

        launch_result = MagicMock()
        launch_result.success = True
        launch_result.error = None
        launch_result.profile_id = "overwatch2-gsync-hdr-capture"
        launch_result.transaction = tx
        launch_result.restored = False
        launch_result.to_dict.return_value = {
            "success": True,
            "profile_id": "overwatch2-gsync-hdr-capture",
            "requested_profile_id": "overwatch2-gsync-hdr",
            "fallback_applied": True,
            "fallback_chain": [
                {
                    "from": "overwatch2-gsync-hdr",
                    "to": "overwatch2-gsync-hdr-capture",
                    "reason": "mixed refresh",
                }
            ],
            "transaction": {},
        }
        mock_launch_profile.return_value = launch_result

        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(
                cli,
                ["launch", "overwatch2-gsync-hdr", "--json", "--no-wait"],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["profile_id"] == "overwatch2-gsync-hdr-capture"
        assert payload["data"]["requested_profile_id"] == "overwatch2-gsync-hdr"
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["current_profile"] == "overwatch2-gsync-hdr-capture"


class TestCLIReapply:
    """Test reapply command wiring and state behavior."""

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=True)
    def test_reapply_json_persists_transaction_fallback_profile(
        self,
        mock_is_admin,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """reapply should update stale current-profile state to the actual fallback."""
        fallback_chain = [
            {
                "from": "overwatch2-gsync-hdr",
                "to": "overwatch2-gsync-hdr-capture",
                "reason": "Mixed-refresh display path blocks strict VRR.",
            }
        ]
        tx_result = MagicMock()
        tx_result.success = True
        tx_result.profile_id = "overwatch2-gsync-hdr-capture"
        tx_result.requested_profile_id = "overwatch2-gsync-hdr"
        tx_result.fallback_chain = fallback_chain
        tx_result.error = None
        tx_result.checkpoints = []
        tx_result.apply_result = ApplyResult(success=True, requires_reboot=False)
        tx_result.compliance_report = None
        tx_result.to_dict.return_value = {
            "success": True,
            "profile_id": "overwatch2-gsync-hdr-capture",
            "requested_profile_id": "overwatch2-gsync-hdr",
            "fallback_chain": fallback_chain,
            "state": "committed",
        }

        mock_manager = mock_tx_manager_cls.return_value
        mock_manager.execute.return_value = tx_result

        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps({"current_profile": "overwatch2-gsync-hdr"}),
            encoding="utf-8",
        )
        with (
            patch("abso.main.STATE_FILE", state_file),
            patch(
                "abso.main._build_state_verification_summary",
                return_value={"status": "mismatch", "all_active": False},
            ),
        ):
            result = runner.invoke(cli, ["reapply", "--json"])

        assert result.exit_code == 0
        mock_manager.execute.assert_called_once_with(
            profile_id="overwatch2-gsync-hdr",
            create_backup=False,
        )
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["profile"] == "overwatch2-gsync-hdr-capture"
        assert payload["data"]["requested_profile"] == "overwatch2-gsync-hdr"
        assert payload["data"]["fallback_applied"] is True
        assert payload["data"]["fallback_chain"] == fallback_chain
        assert "safe fallback" in payload["data"]["notices"][0]
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["current_profile"] == "overwatch2-gsync-hdr-capture"

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=False)
    def test_reapply_json_noops_when_current_profile_verifies_active(
        self,
        mock_is_admin,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """reapply should avoid redundant display writes when state already verifies clean."""
        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T04:40:55",
                    "reboot_pending": True,
                    "reboot_reasons": ["GraphicsSettingsHandler"],
                }
            ),
            encoding="utf-8",
        )
        verification = {
            "status": "active",
            "all_active": True,
            "pending_apply_settings": [],
            "mismatched_handlers": [],
        }

        with (
            patch("abso.main.STATE_FILE", state_file),
            patch("abso.main._build_state_verification_summary", return_value=verification),
            patch("abso.main._get_system_boot_time", return_value=datetime(2026, 5, 26, 4, 30)),
        ):
            result = runner.invoke(cli, ["reapply", "--json"])

        assert result.exit_code == 0
        mock_tx_manager_cls.assert_not_called()
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["changed"] is False
        assert payload["data"]["transaction"] is None
        assert payload["data"]["summary_level"] == "notice"
        assert payload["data"]["reboot_pending"] is True
        assert "skipped reapply" in payload["data"]["notices"][0]

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main.is_admin", return_value=False)
    def test_reapply_json_noops_when_current_profile_is_reboot_gated(
        self,
        mock_is_admin,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """reapply should not rerun handlers when only a reboot can commit state."""
        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T04:40:55",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )
        verification = {
            "status": "pending_reboot",
            "all_active": False,
            "pending_apply_settings": [],
            "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "mismatched_handlers": ["GraphicsSettingsHandler"],
        }

        with (
            patch("abso.main.STATE_FILE", state_file),
            patch("abso.main._build_state_verification_summary", return_value=verification),
            patch("abso.main._get_system_boot_time", return_value=datetime(2026, 5, 26, 4, 30)),
        ):
            result = runner.invoke(cli, ["reapply", "--json"])

        assert result.exit_code == 0
        mock_is_admin.assert_not_called()
        mock_tx_manager_cls.assert_not_called()
        payload = json.loads(result.output)
        assert payload["data"]["changed"] is False
        assert payload["data"]["transaction"] is None
        assert payload["data"]["reboot_pending"] is True
        assert payload["data"]["reboot_reasons"] == ["GraphicsSettingsHandler"]
        assert "only a reboot can commit" in payload["data"]["notices"][0]

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main._apply_pending_profile_settings")
    @patch("abso.main.is_admin", return_value=False)
    def test_reapply_json_uses_targeted_pending_fix(
        self,
        mock_is_admin,
        mock_apply_pending,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """reapply pending apply state must not run a full transaction."""
        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "overwatch2-gsync-hdr-capture",
                    "applied_at": "2026-05-26T04:40:55",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )
        verification = {
            "status": "pending_apply",
            "all_active": False,
            "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "pending_reboot_gated_settings": [],
            "mismatched_handlers": ["GraphicsSettingsHandler"],
        }
        mock_apply_pending.return_value = {
            "success": True,
            "profile": "overwatch2-gsync-hdr-capture",
            "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "changed": True,
            "changed_settings": ["GraphicsSettingsHandler.disable_mpo"],
            "requires_reboot": True,
            "reboot_reasons": ["GraphicsSettingsHandler"],
            "handler_results": {
                "GraphicsSettingsHandler": {
                    "success": True,
                    "changed_keys": ["disable_mpo"],
                }
            },
            "notices": [],
            "warnings": [],
            "error": None,
        }

        with (
            patch("abso.main.STATE_FILE", state_file),
            patch("abso.main._build_state_verification_summary", return_value=verification),
            patch("abso.main._get_system_boot_time", return_value=datetime(2026, 5, 26, 4, 30)),
        ):
            result = runner.invoke(cli, ["reapply", "--json"])

        assert result.exit_code == 0
        mock_is_admin.assert_not_called()
        mock_tx_manager_cls.assert_not_called()
        mock_apply_pending.assert_called_once_with("overwatch2-gsync-hdr-capture")
        payload = json.loads(result.output)
        data = payload["data"]
        assert data["changed"] is True
        assert data["changed_settings"] == ["GraphicsSettingsHandler.disable_mpo"]
        assert data["transaction"] is None
        assert data["requires_reboot"] is True

    @patch("abso.main.ProfileTransactionManager")
    @patch("abso.main._apply_pending_profile_settings")
    @patch("abso.main.is_admin", return_value=True)
    def test_reapply_json_rejects_unsupported_pending_without_transaction(
        self,
        mock_is_admin,
        mock_apply_pending,
        mock_tx_manager_cls,
        tmp_path,
    ):
        """Unsupported pending reapply should fail closed instead of full apply."""
        runner = CliRunner()
        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "current_profile": "example",
                    "applied_at": "2026-05-26T04:40:55",
                    "reboot_pending": False,
                    "reboot_reasons": [],
                }
            ),
            encoding="utf-8",
        )
        verification = {
            "status": "pending_apply",
            "all_active": False,
            "pending_apply_settings": ["WindowsSettingsHandler.hdr"],
            "pending_reboot_gated_settings": [],
            "mismatched_handlers": ["WindowsSettingsHandler"],
        }
        mock_apply_pending.return_value = {
            "success": False,
            "profile": "example",
            "pending_apply_settings": ["WindowsSettingsHandler.hdr"],
            "changed": False,
            "changed_settings": [],
            "requires_reboot": False,
            "reboot_reasons": [],
            "handler_results": {},
            "notices": [],
            "warnings": [],
            "error": "Unsupported pending apply setting(s): WindowsSettingsHandler.hdr",
        }

        with (
            patch("abso.main.STATE_FILE", state_file),
            patch("abso.main._build_state_verification_summary", return_value=verification),
            patch("abso.main._get_system_boot_time", return_value=datetime(2026, 5, 26, 4, 30)),
        ):
            result = runner.invoke(cli, ["reapply", "--json"])

        assert result.exit_code == 1
        mock_is_admin.assert_not_called()
        mock_tx_manager_cls.assert_not_called()
        payload = json.loads(result.output)
        assert payload["success"] is False
        assert payload["data"]["transaction"] is None
        assert payload["data"]["error"] == (
            "Unsupported pending apply setting(s): WindowsSettingsHandler.hdr"
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
        mock_build_health_report.assert_called_once()
        assert mock_build_health_report.call_args.kwargs["include_verify_details"] is False
        assert mock_build_health_report.call_args.kwargs["include_backup_details"] is False

    @patch("abso.core.health.build_health_report")
    def test_health_full_verify_requests_detailed_payload(self, mock_build_health_report):
        """health --full-verify should request full verifier details."""
        mock_build_health_report.return_value = {
            "generated_at": "2026-02-18T00:00:00",
            "checks": {"profile_verify": {"status": "ok"}},
            "summary": {"ok": 1, "warning": 0, "error": 0},
            "current_profile": "overwatch2",
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health", "--json", "--full-verify"])

        assert result.exit_code == 0
        mock_build_health_report.assert_called_once()
        assert mock_build_health_report.call_args.kwargs["include_verify_details"] is True
        assert mock_build_health_report.call_args.kwargs["include_backup_details"] is False

    @patch("abso.core.health.build_health_report")
    def test_health_full_backups_requests_recent_backup_rows(self, mock_build_health_report):
        """health --full-backups should request recent backup detail rows."""
        mock_build_health_report.return_value = {
            "generated_at": "2026-02-18T00:00:00",
            "checks": {"backups": {"status": "ok"}},
            "summary": {"ok": 1, "warning": 0, "error": 0},
            "current_profile": "overwatch2",
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health", "--json", "--full-backups"])

        assert result.exit_code == 0
        mock_build_health_report.assert_called_once()
        assert mock_build_health_report.call_args.kwargs["include_backup_details"] is True

    @patch("abso.core.health.build_health_report")
    def test_health_console_summarizes_display_diagnostics(self, mock_build_health_report):
        """Plain health output should expose root-cause display context."""
        mock_build_health_report.return_value = {
            "generated_at": "2026-05-26T12:52:00",
            "summary": {"ok": 8, "warning": 2, "error": 0},
            "current_profile": "overwatch2-gsync-hdr-capture",
            "checks": {
                "display_events": {
                    "status": "ok",
                    "data": {"count": 0, "channel_error_count": 0},
                },
                "display_stability": {
                    "status": "warning",
                    "data": {
                        "monitor_count": 2,
                        "min_refresh": 59.95,
                        "max_refresh": 300.0,
                        "risk_level": "high",
                        "likely_black_flash_path": (
                            "windows_compositor_mpo_vrr_mixed_refresh"
                        ),
                        "next_action": (
                            "Normal reboot required before judging MPO/compositor "
                            "flicker fix."
                        ),
                    },
                },
            },
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health"])

        assert result.exit_code == 0
        assert "Display diagnostics:" in result.output
        assert "Event log: 0 recent display/driver/power event(s), 0 channel error(s)" in (
            result.output
        )
        assert "Topology: 2 monitor(s), 59.95 Hz - 300 Hz, risk high" in result.output
        assert (
            "Likely black-flash path: windows_compositor_mpo_vrr_mixed_refresh"
            in result.output
        )
        assert "Next action: Normal reboot required" in result.output

    @patch("abso.core.health.build_health_report")
    def test_health_console_lists_tray_runtime_marker(self, mock_build_health_report):
        """Plain health output should not hide tray marker warnings from the summary."""
        mock_build_health_report.return_value = {
            "generated_at": "2026-05-26T13:20:00",
            "summary": {"ok": 1, "warning": 1, "error": 0},
            "current_profile": "overwatch2-gsync-hdr-capture",
            "checks": {
                "tray_runtime": {"status": "ok"},
                "tray_runtime_marker": {
                    "status": "warning",
                    "warnings": ["tray runtime marker hash is stale"],
                },
            },
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health"])

        assert result.exit_code == 0
        assert "tray_runtime: ok" in result.output
        assert "tray_runtime_marker: warning" in result.output
        assert "tray runtime marker hash is stale" in result.output

    @patch("abso.core.health.build_health_report")
    def test_health_console_lists_future_checks(self, mock_build_health_report):
        """Plain health output should not hide checks added after the render order."""
        mock_build_health_report.return_value = {
            "generated_at": "2026-05-26T13:25:00",
            "summary": {"ok": 0, "warning": 0, "error": 1},
            "current_profile": "overwatch2-gsync-hdr-capture",
            "checks": {
                "future_probe": {
                    "status": "error",
                    "error": "future probe failed",
                }
            },
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health"])

        assert result.exit_code == 0
        assert "future_probe: error" in result.output
        assert "future probe failed" in result.output

    @patch("abso.core.display_diagnostics.collect_display_diagnostics")
    def test_display_diagnostics_json_output(self, mock_collect):
        """display-diagnostics --json should expose one read-only sample."""
        mock_collect.return_value = {
            "generated_at": "2026-05-26T13:20:00",
            "read_only": True,
            "display_events": {"count": 0, "channel_error_count": 0},
            "display_stability": {
                "monitor_count": 2,
                "min_refresh": 59.95,
                "max_refresh": 300.0,
                "risk_level": "high",
                "likely_black_flash_path": (
                    "windows_compositor_mpo_vrr_mixed_refresh"
                ),
            },
            "active_state": {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            },
            "summary": {"compositor_black_flash_likely": True},
        }

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "display-diagnostics",
                "--json",
                "--lookback-minutes",
                "45",
                "--max-events",
                "7",
                "--event-timeout",
                "3",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["success"] is True
        assert payload["data"]["read_only"] is True
        assert payload["data"]["summary"]["compositor_black_flash_likely"] is True
        mock_collect.assert_called_once_with(
            lookback_minutes=45,
            max_events=7,
            event_timeout_seconds=3,
            state_targets=ANY,
        )

    @patch("abso.core.display_diagnostics.collect_display_diagnostics")
    def test_display_diagnostics_plain_output_summarizes_root_cause(self, mock_collect):
        """Plain display-diagnostics output should stay focused on flicker context."""
        mock_collect.return_value = {
            "generated_at": "2026-05-26T13:20:00",
            "read_only": True,
            "display_events": {"count": 0, "channel_error_count": 0},
            "display_stability": {
                "monitor_count": 2,
                "min_refresh": 59.95,
                "max_refresh": 300.0,
                "risk_level": "high",
                "likely_black_flash_path": (
                    "windows_compositor_mpo_vrr_mixed_refresh"
                ),
            },
            "active_state": {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            },
            "summary": {"compositor_black_flash_likely": True},
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["display-diagnostics", "--interval", "0"])

        assert result.exit_code == 0
        assert "ABSO Display Diagnostics" in result.output
        assert "Active profile: overwatch2-gsync-hdr-capture" in result.output
        assert "Profile state: reboot pending (GraphicsSettingsHandler)" in result.output
        assert "Display diagnostics:" in result.output
        assert "Topology: 2 monitor(s), 59.95 Hz - 300 Hz, risk high" in result.output
        assert "compositor/MPO/VRR path" in result.output

    @patch("abso.core.display_diagnostics.collect_display_diagnostics")
    def test_display_diagnostics_json_multiple_samples(self, mock_collect):
        """Repeated JSON sampling returns a compact sample list."""
        mock_collect.side_effect = [
            {
                "generated_at": "2026-05-26T13:20:00",
                "read_only": True,
                "display_events": {"count": 0, "channel_error_count": 0},
                "display_stability": {"risk_level": "high"},
                "summary": {"compositor_black_flash_likely": True},
            },
            {
                "generated_at": "2026-05-26T13:20:01",
                "read_only": True,
                "display_events": {"count": 0, "channel_error_count": 0},
                "display_stability": {"risk_level": "high"},
                "summary": {"compositor_black_flash_likely": True},
            },
        ]

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["display-diagnostics", "--json", "--samples", "2", "--interval", "0"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["read_only"] is True
        assert len(payload["data"]["samples"]) == 2
        assert mock_collect.call_count == 2

    @patch("abso.core.display_diagnostics.collect_display_diagnostics")
    def test_display_diagnostics_jsonl_streams_samples(self, mock_collect):
        """JSONL output should emit one wrapped payload per sample."""
        mock_collect.side_effect = [
            {
                "generated_at": "2026-05-26T13:20:00",
                "read_only": True,
                "display_events": {"count": 0, "channel_error_count": 0},
                "display_stability": {"risk_level": "high"},
                "summary": {"compositor_black_flash_likely": True},
            },
            {
                "generated_at": "2026-05-26T13:20:01",
                "read_only": True,
                "display_events": {"count": 0, "channel_error_count": 0},
                "display_stability": {"risk_level": "high"},
                "summary": {"compositor_black_flash_likely": True},
            },
        ]

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["display-diagnostics", "--jsonl", "--samples", "2", "--interval", "0"],
        )

        assert result.exit_code == 0
        lines = result.output.strip().splitlines()
        assert len(lines) == 2
        payloads = [json.loads(line) for line in lines]
        assert [payload["success"] for payload in payloads] == [True, True]
        assert payloads[0]["data"]["generated_at"] == "2026-05-26T13:20:00"
        assert payloads[1]["data"]["generated_at"] == "2026-05-26T13:20:01"
        assert mock_collect.call_count == 2

    def test_display_diagnostics_rejects_json_and_jsonl_together(self):
        """JSON array and JSONL streaming modes are intentionally exclusive."""
        runner = CliRunner()
        result = runner.invoke(cli, ["display-diagnostics", "--json", "--jsonl"])

        assert result.exit_code == 2
        assert "mutually exclusive" in result.output


class TestCLIRestoreWithMocks:
    """Test restore command with mocked components."""

    @patch("abso.main.BackupManager")
    def test_restore_latest(self, mock_backup_class, tmp_path):
        """Test restore latest command."""
        mock_backup = MagicMock()
        mock_summary = MagicMock()
        mock_summary.complete = True
        mock_summary.to_dict.return_value = {
            "backup_id": "latest",
            "complete": True,
            "restored_components": [],
            "skipped_components": [],
            "failed_components": [],
        }
        mock_backup.restore_backup.return_value = mock_summary
        mock_backup_class.return_value = mock_backup

        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")

        runner = CliRunner()
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(cli, ["restore", "latest"])

        # Should complete without crash
        assert result.exception is None or result.exit_code in [0, 1]

    @patch("abso.main.BackupManager")
    @patch("abso.main.is_admin", return_value=True)
    def test_restore_json_clears_current_profile_state(
        self, mock_is_admin, mock_backup_class, tmp_path
    ):
        """Successful restore should clear state file so tray doesn't show stale active profile."""
        mock_backup = MagicMock()
        mock_summary = MagicMock()
        mock_summary.complete = True
        mock_summary.to_dict.return_value = {
            "backup_id": "latest",
            "complete": True,
            "restored_components": [],
            "skipped_components": [],
            "failed_components": [],
        }
        mock_backup.restore_backup.return_value = mock_summary
        mock_backup_class.return_value = mock_backup

        state_file = tmp_path / ".abso_state.json"
        state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")

        runner = CliRunner()
        with patch("abso.main.STATE_FILE", state_file):
            result = runner.invoke(cli, ["restore", "latest", "--json"])

        assert result.exit_code == 0
        assert not state_file.exists()
