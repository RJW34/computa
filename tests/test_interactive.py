"""Tests for interactive CLI module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from abso import interactive


class TestClearScreen:
    """Tests for clear_screen function."""

    def test_clear_screen_calls_console_clear(self):
        """Test clear_screen calls console.clear()."""
        with patch.object(interactive.console, "clear") as mock_clear:
            interactive.clear_screen()
            mock_clear.assert_called_once()


class TestPrintHeader:
    """Tests for print_header function."""

    def test_print_header_prints_panel(self):
        """Test print_header outputs to console."""
        with patch.object(interactive.console, "print") as mock_print:
            interactive.print_header()
            # Should print panel and empty line
            assert mock_print.call_count >= 2


class TestPrintAdminWarning:
    """Tests for print_admin_warning function."""

    @patch("abso.interactive.is_admin", return_value=True)
    def test_no_warning_when_admin(self, mock_is_admin):
        """Test no warning printed when running as admin."""
        with patch.object(interactive.console, "print") as mock_print:
            interactive.print_admin_warning()
            # Should not print anything when admin
            mock_print.assert_not_called()

    @patch("abso.interactive.is_admin", return_value=False)
    def test_warning_when_not_admin(self, mock_is_admin):
        """Test warning printed when not running as admin."""
        with patch.object(interactive.console, "print") as mock_print:
            interactive.print_admin_warning()
            # Should print warning panel
            assert mock_print.call_count >= 1


class TestShowMainMenu:
    """Tests for show_main_menu function."""

    @patch("abso.interactive.Prompt.ask", return_value="1")
    def test_returns_choice_lowercase(self, mock_ask):
        """Test main menu returns lowercase choice."""
        with patch.object(interactive.console, "print"):
            result = interactive.show_main_menu()
            assert result == "1"

    @patch("abso.interactive.Prompt.ask", return_value="Q")
    def test_returns_quit_lowercase(self, mock_ask):
        """Test main menu returns 'q' for uppercase Q."""
        with patch.object(interactive.console, "print"):
            result = interactive.show_main_menu()
            assert result == "q"


class TestShowProfileMenu:
    """Tests for show_profile_menu function."""

    @patch("abso.interactive.Prompt.ask", return_value="0")
    @patch("abso.interactive.ProfileApplier")
    def test_returns_none_on_cancel(self, mock_applier_class, mock_ask):
        """Test show_profile_menu returns None when user cancels."""
        mock_applier = MagicMock()
        mock_applier.list_profiles.return_value = [
            {"id": "test", "display_name": "Test", "optimization_target": "latency"}
        ]
        mock_applier_class.return_value = mock_applier

        with patch.object(interactive.console, "print"):
            result = interactive.show_profile_menu()
            assert result is None

    @patch("abso.interactive.Prompt.ask", return_value="1")
    @patch("abso.interactive.ProfileApplier")
    def test_returns_profile_id_on_selection(self, mock_applier_class, mock_ask):
        """Test show_profile_menu returns selected profile ID."""
        mock_applier = MagicMock()
        mock_applier.list_profiles.return_value = [
            {"id": "slippi_melee", "display_name": "Slippi Melee", "optimization_target": "latency"}
        ]
        mock_applier_class.return_value = mock_applier

        with patch.object(interactive.console, "print"):
            result = interactive.show_profile_menu()
            assert result == "slippi_melee"


class TestRunAudit:
    """Tests for run_audit function."""

    @patch("abso.interactive.Prompt.ask", return_value="")
    @patch("abso.interactive.ConfigurationAuditor")
    def test_run_audit_no_issues(self, mock_auditor_class, mock_ask):
        """Test run_audit displays success when no issues found."""
        mock_auditor = MagicMock()
        mock_auditor.audit_all.return_value = []
        mock_auditor_class.return_value = mock_auditor

        with patch.object(interactive.console, "print") as mock_print:
            interactive.run_audit()
            mock_auditor.audit_all.assert_called_once()
            # Should have printed success panel
            assert mock_print.call_count >= 1

    @patch("abso.interactive.Prompt.ask", return_value="")
    @patch("abso.interactive.ConfigurationAuditor")
    def test_run_audit_with_issues(self, mock_auditor_class, mock_ask):
        """Test run_audit displays issues when found."""
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

        with patch.object(interactive.console, "print") as mock_print:
            interactive.run_audit()
            mock_auditor.audit_all.assert_called_once()
            assert mock_print.call_count >= 1


class TestRunDetectHardware:
    """Tests for run_detect_hardware function."""

    @patch("abso.interactive.Prompt.ask", return_value="")
    @patch("abso.interactive.HardwareDetector")
    def test_run_detect_hardware_with_data(self, mock_detector_class, mock_ask):
        """Test run_detect_hardware displays hardware info."""
        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = {
            "gpu": {"name": "RTX 4090", "driver_version": "555.0", "vram_mb": 24576},
            "cpu": {"name": "Intel i9", "cores": 8, "threads": 16},
            "ram": {"total_gb": 32},
            "monitors": [
                {
                    "name": "Monitor 1",
                    "resolution": "1920x1080",
                    "refresh_rate": 144,
                    "is_primary": True,
                    "vrr_supported": True,
                    "vrr_type": "g-sync",
                }
            ],
        }
        mock_detector_class.return_value = mock_detector

        with patch.object(interactive.console, "print") as mock_print:
            interactive.run_detect_hardware()
            mock_detector.detect_all.assert_called_once()
            assert mock_print.call_count >= 1

    @patch("abso.interactive.Prompt.ask", return_value="")
    @patch("abso.interactive.HardwareDetector")
    def test_run_detect_hardware_empty_data(self, mock_detector_class, mock_ask):
        """Test run_detect_hardware handles missing hardware gracefully."""
        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = {}
        mock_detector_class.return_value = mock_detector

        with patch.object(interactive.console, "print") as mock_print:
            interactive.run_detect_hardware()
            mock_detector.detect_all.assert_called_once()
            # Should handle empty results gracefully
            assert mock_print.call_count >= 1


class TestShowProfilesInfo:
    """Tests for show_profiles_info function."""

    @patch("abso.interactive.Prompt.ask", return_value="")
    @patch("abso.interactive.ProfileApplier")
    def test_show_profiles_info_displays_profiles(self, mock_applier_class, mock_ask):
        """Test show_profiles_info displays profile information."""
        mock_profile = MagicMock()
        mock_profile.display_name = "Test Game"
        mock_profile.description = "Test description"
        mock_profile.optimization_target = "latency"
        mock_profile.executable_hints = ["test.exe"]
        mock_profile.get_handlers.return_value = []
        mock_profile.get_settings.return_value = {}

        mock_applier = MagicMock()
        mock_applier.list_profiles.return_value = [
            {"id": "test", "display_name": "Test Game", "optimization_target": "latency"}
        ]
        mock_applier._get_profile.return_value = mock_profile
        mock_applier_class.return_value = mock_applier

        with patch.object(interactive.console, "print") as mock_print:
            interactive.show_profiles_info()
            assert mock_print.call_count >= 1


class TestRunRestoreBackup:
    """Tests for run_restore_backup function."""

    @patch("abso.interactive.Prompt.ask", return_value="")
    def test_no_backups_dir(self, mock_ask, tmp_path):
        """Test run_restore_backup handles missing backup directory."""
        with (patch.object(interactive, "BACKUPS_DIR", tmp_path / "nonexistent"),
              patch.object(interactive.console, "print") as mock_print):
            interactive.run_restore_backup()
            # Should print "no backups" message
            assert mock_print.call_count >= 1

    @patch("abso.interactive.Prompt.ask", return_value="0")
    def test_cancel_restore(self, mock_ask, tmp_path):
        """Test run_restore_backup allows cancellation."""
        # Create backup directory with a backup
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "backup_20240101_120000").mkdir()

        with (patch.object(interactive, "BACKUPS_DIR", backup_dir),
              patch.object(interactive.console, "print")):
            # User selects "0" to cancel
            interactive.run_restore_backup()


class TestRunApplyProfile:
    """Tests for run_apply_profile function."""

    @patch("abso.interactive.ProfileApplier")
    def test_apply_profile_invalid_profile(self, mock_applier_class):
        """Test run_apply_profile handles invalid profile ID."""
        mock_applier = MagicMock()
        mock_applier._get_profile.side_effect = ValueError("Profile not found")
        mock_applier_class.return_value = mock_applier

        with patch.object(interactive.console, "print") as mock_print:
            interactive.run_apply_profile("nonexistent")
            # Should print error message
            assert any("Error" in str(call) for call in mock_print.call_args_list)

    @patch("abso.interactive.Prompt.ask", return_value="")
    @patch("abso.interactive.Confirm.ask", return_value=False)
    @patch("abso.interactive.is_admin", return_value=True)
    @patch("abso.interactive.ProfileApplier")
    def test_apply_profile_cancelled(self, mock_applier_class, mock_is_admin, mock_confirm, mock_prompt):
        """Test run_apply_profile allows user cancellation."""
        mock_profile = MagicMock()
        mock_profile.display_name = "Test"
        mock_profile.description = "Test desc"
        mock_profile.optimization_target = "latency"
        mock_profile.get_handlers.return_value = []

        mock_applier = MagicMock()
        mock_applier._get_profile.return_value = mock_profile
        mock_applier_class.return_value = mock_applier

        with patch.object(interactive.console, "print"):
            interactive.run_apply_profile("test")
            # Should not apply since user cancelled

    @patch("abso.interactive.Prompt.ask", return_value="")
    @patch("abso.interactive.Confirm.ask", return_value=True)
    @patch("abso.interactive.is_admin", return_value=True)
    @patch("abso.interactive.ProfileTransactionManager")
    @patch("abso.interactive.ProfileApplier")
    def test_apply_profile_uses_transaction_manager(
        self,
        mock_applier_class,
        mock_tx_manager_class,
        mock_is_admin,
        mock_confirm,
        mock_prompt,
    ):
        """Interactive apply must use the transactional apply path."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "WindowsSettingsHandler"
        mock_handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.display_name = "Test"
        mock_profile.description = "Test desc"
        mock_profile.optimization_target = "latency"
        mock_profile.get_handlers.return_value = [mock_handler]
        mock_profile.get_settings.return_value = {"game_mode": True}
        mock_profile.has_in_game_settings.return_value = False

        mock_applier = MagicMock()
        mock_applier._get_profile.return_value = mock_profile
        mock_applier_class.return_value = mock_applier

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.requires_reboot = False
        mock_result.reboot_reasons = []
        mock_result.warnings = []
        mock_result.notices = []

        mock_tx = MagicMock()
        mock_tx.success = True
        mock_tx.apply_result = mock_result
        mock_tx.backup_id = "backup-test"
        mock_tx.checkpoints = []

        mock_tx_manager = MagicMock()
        mock_tx_manager.execute.return_value = mock_tx
        mock_tx_manager_class.return_value = mock_tx_manager

        with (
            patch.object(interactive.console, "print"),
            patch("abso.main.set_current_profile") as mock_set_current_profile,
        ):
            interactive.run_apply_profile("test")

        mock_tx_manager_class.assert_called_once_with(interactive.BACKUPS_DIR, applier=mock_applier)
        mock_tx_manager.execute.assert_called_once_with(profile_id="test", create_backup=True)
        mock_handler.apply.assert_not_called()
        mock_set_current_profile.assert_called_once()


class TestRunInteractive:
    """Tests for run_interactive main loop."""

    @patch("abso.interactive.is_admin", return_value=True)
    @patch("abso.interactive.show_main_menu", return_value="q")
    @patch("abso.interactive.clear_screen")
    @patch("abso.interactive.print_header")
    @patch("abso.interactive.print_admin_warning")
    def test_quit_exits_loop(
        self, mock_warning, mock_header, mock_clear, mock_menu, mock_is_admin
    ):
        """Test run_interactive exits on 'q'."""
        with patch.object(interactive.console, "print"):
            interactive.run_interactive()
            mock_menu.assert_called_once()

    @patch("abso.interactive.is_admin", return_value=False)
    @patch("abso.interactive.Confirm.ask", return_value=False)
    @patch("abso.interactive.show_main_menu", return_value="q")
    @patch("abso.interactive.clear_screen")
    @patch("abso.interactive.print_header")
    @patch("abso.interactive.print_admin_warning")
    def test_continue_without_admin(
        self, mock_warning, mock_header, mock_clear, mock_menu, mock_confirm, mock_is_admin
    ):
        """Test run_interactive continues when user declines admin."""
        with patch.object(interactive.console, "print"):
            interactive.run_interactive()
            mock_menu.assert_called_once()


class TestModuleLevel:
    """Tests for module-level variables and constants."""

    def test_paths_are_path_objects(self):
        """Test module paths are Path objects."""
        assert isinstance(interactive.ROOT_DIR, Path)
        assert isinstance(interactive.BACKUPS_DIR, Path)
        assert isinstance(interactive.REPORTS_DIR, Path)

    def test_console_is_initialized(self):
        """Test console is initialized."""
        from rich.console import Console
        assert isinstance(interactive.console, Console)
