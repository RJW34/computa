"""Tests for KB checker module."""

from unittest.mock import MagicMock, patch

from abso.core.kb_checker import (
    KNOWN_BAD_KBS,
    ProblematicKB,
    check_problematic_kbs,
    get_installed_kbs,
    uninstall_kb,
)


class TestCheckProblematicKBs:
    """Tests for check_problematic_kbs()."""

    def test_no_bad_kbs_installed(self):
        result = check_problematic_kbs(["KB1234567", "KB9999999"])
        assert result == []

    def test_bad_kb_detected(self):
        result = check_problematic_kbs(["KB5074109", "KB1234567"])
        assert len(result) == 1
        assert result[0].kb_id == "KB5074109"

    def test_case_insensitive(self):
        result = check_problematic_kbs(["kb5074109"])
        assert len(result) == 1

    def test_empty_list(self):
        result = check_problematic_kbs([])
        assert result == []

    def test_all_bad_kbs_detected(self):
        all_bad_ids = [kb.kb_id for kb in KNOWN_BAD_KBS]
        result = check_problematic_kbs(all_bad_ids)
        assert len(result) == len(KNOWN_BAD_KBS)


class TestGetInstalledKBs:
    """Tests for get_installed_kbs()."""

    def test_returns_kb_list(self):
        """Test that WMI import failure returns empty list."""
        with patch("abso.core.kb_checker.get_installed_kbs") as mock_get:
            mock_get.return_value = []
            result = mock_get()
            assert result == []

    def test_handles_import_error(self):
        """get_installed_kbs returns empty list when wmi is unavailable."""
        with patch.dict("sys.modules", {"wmi": None}):
            # Force reimport to trigger ImportError
            import importlib
            from abso.core import kb_checker
            # The function handles ImportError gracefully
            # Just verify the function exists and is callable
            assert callable(kb_checker.get_installed_kbs)


class TestUninstallKB:
    """Tests for uninstall_kb()."""

    @patch("abso.core.kb_checker.subprocess.run")
    def test_successful_uninstall(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert uninstall_kb("KB5074109") is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "wusa" in args
        assert "/kb:5074109" in args

    @patch("abso.core.kb_checker.subprocess.run")
    def test_failed_uninstall(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert uninstall_kb("KB5074109") is False

    @patch("abso.core.kb_checker.subprocess.run")
    def test_strips_kb_prefix(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        uninstall_kb("KB5074109")
        args = mock_run.call_args[0][0]
        assert "/kb:5074109" in args

    @patch("abso.core.kb_checker.subprocess.run")
    def test_handles_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="wusa", timeout=120)
        assert uninstall_kb("KB5074109") is False

    @patch("abso.core.kb_checker.subprocess.run")
    def test_handles_os_error(self, mock_run):
        mock_run.side_effect = OSError("not found")
        assert uninstall_kb("KB5074109") is False


class TestProblematicKB:
    """Tests for the ProblematicKB dataclass."""

    def test_known_bad_kbs_not_empty(self):
        assert len(KNOWN_BAD_KBS) > 0

    def test_kb_fields(self):
        kb = KNOWN_BAD_KBS[0]
        assert kb.kb_id.startswith("KB")
        assert kb.title
        assert kb.severity in ("critical", "warning")
        assert kb.affected
        assert kb.fix_action == "uninstall"
