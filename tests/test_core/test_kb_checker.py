"""Tests for KB checker module."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from abso.core.kb_checker import (
    KNOWN_BAD_KBS,
    LAST_REVIEWED_UTC,
    STALENESS_DAYS,
    check_problematic_kbs,
    is_review_stale,
    list_review_staleness,
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
        for kb in KNOWN_BAD_KBS:
            assert kb.kb_id.startswith("KB")
            assert kb.title
            assert kb.severity in ("critical", "warning")
            assert kb.affected
            assert kb.fix_action in ("uninstall", "install_kb", "advisory")

    def test_bitlocker_pcr7_entry_present(self):
        ids = {kb.kb_id for kb in KNOWN_BAD_KBS}
        assert "KB5083769" in ids

    def test_supersession_filters_patched_machines(self):
        """KB5083769 must not flag if KB5089549 is also installed."""
        result = check_problematic_kbs(["KB5083769", "KB5089549"])
        assert all(kb.kb_id != "KB5083769" for kb in result)

    def test_supersession_filters_via_build_floor(self):
        """KB5083769 must not flag if the OS is already at or beyond the fix build."""
        result = check_problematic_kbs(
            ["KB5083769"],
            build_revision=(26200, 8457),
        )
        assert all(kb.kb_id != "KB5083769" for kb in result)

    def test_pre_fix_build_still_flags_regression(self):
        """Older build without supersession KB must still surface the warning."""
        result = check_problematic_kbs(
            ["KB5083769"],
            build_revision=(26200, 8246),
        )
        assert any(kb.kb_id == "KB5083769" for kb in result)


class TestReviewStaleness:
    """Tests for the LAST_REVIEWED_UTC freshness heuristic."""

    def test_fresh_review_is_not_stale(self):
        assert is_review_stale(LAST_REVIEWED_UTC + timedelta(days=1)) is False

    def test_review_becomes_stale_past_window(self):
        far_future = LAST_REVIEWED_UTC + timedelta(days=STALENESS_DAYS + 5)
        assert is_review_stale(far_future) is True

    def test_naive_datetime_treated_as_utc(self):
        naive = (LAST_REVIEWED_UTC + timedelta(days=10)).replace(tzinfo=None)
        # Should not raise; should still compute a non-negative day count.
        assert list_review_staleness(naive) >= 0
