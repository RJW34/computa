"""Tests for CrashDetector auto-rollback target selection."""

from unittest.mock import MagicMock, patch

from abso.core.backup import BackupRestoreSummary
from abso.core.crash_detector import CrashDetector, CrashHistory


def _detector_with_mock_backup() -> tuple[CrashDetector, MagicMock]:
    backup_manager = MagicMock()
    with patch.object(CrashDetector, "_load_history", return_value=CrashHistory()):
        detector = CrashDetector(backup_manager)
    return detector, backup_manager


def test_auto_rollback_prefers_recorded_backup_id():
    """A crash rollback must restore the exact pre-apply backup, not 'latest'."""
    detector, backup_manager = _detector_with_mock_backup()
    backup_manager.restore_backup.return_value = BackupRestoreSummary(
        backup_id="2026-06-19_010101"
    )

    detector.record_profile_apply("overwatch2-gsync-hdr", backup_id="2026-06-19_010101")
    assert detector._auto_rollback("overwatch.exe", "overwatch2-gsync-hdr") is True

    backup_manager.restore_backup.assert_called_once_with("2026-06-19_010101")


def test_auto_rollback_falls_back_to_latest_without_backup_id():
    """When no concrete backup id was recorded, fall back to 'latest'."""
    detector, backup_manager = _detector_with_mock_backup()
    backup_manager.restore_backup.return_value = BackupRestoreSummary(backup_id="latest")

    detector.record_profile_apply("overwatch2-gsync-hdr")
    detector._auto_rollback("overwatch.exe", "overwatch2-gsync-hdr")

    backup_manager.restore_backup.assert_called_once_with("latest")
