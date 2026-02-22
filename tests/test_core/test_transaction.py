"""Tests for transactional profile apply flow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from abso.core.applier import ApplyResult
from abso.core.transaction import ProfileTransactionManager


def test_transaction_commits_on_success_without_backup(tmp_path: Path) -> None:
    applier = MagicMock()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    manager = ProfileTransactionManager(tmp_path, applier=applier)
    tx = manager.execute("test-profile", create_backup=False)

    assert tx.success is True
    assert tx.state == "committed"
    assert tx.rollback_performed is False
    assert any(cp.phase == "backup" and cp.status == "skipped" for cp in tx.checkpoints)
    assert any(cp.phase == "commit" and cp.status == "ok" for cp in tx.checkpoints)


def test_transaction_rolls_back_on_critical_when_backup_available(tmp_path: Path) -> None:
    applier = MagicMock()
    applier.apply_profile.return_value = ApplyResult(
        success=False,
        error="handler failure",
        failed_settings=["WindowsSettingsHandler: failed"],
    )
    applier.verify_profile.return_value = {"all_active": False, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        restore_manager = MagicMock()
        restore_manager.list_backups.return_value = []  # No previous backup
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "backup-123"
        mock_backup_cls.side_effect = [restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        backup_manager.restore_backup.assert_called_once_with("backup-123")
        assert tx.success is False
        assert tx.rollback_performed is True
        assert tx.state == "rolled_back"
        assert tx.backup_id == "backup-123"


def test_transaction_restores_baseline_before_apply(tmp_path: Path) -> None:
    """When a previous backup exists, restore it before applying new profile."""
    applier = MagicMock()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        # First call is the restore-phase manager, second is the backup-phase manager
        restore_manager = MagicMock()
        restore_manager.list_backups.return_value = [{"id": "old-backup"}]
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "new-backup"
        mock_backup_cls.side_effect = [restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        restore_manager.restore_backup.assert_called_once_with("latest")
        assert any(
            cp.phase == "baseline_restore" and cp.status == "ok"
            for cp in tx.checkpoints
        )
        assert tx.success is True


def test_transaction_skips_baseline_restore_when_no_backups(tmp_path: Path) -> None:
    """On first-ever apply, skip restore since there's no previous backup."""
    applier = MagicMock()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        restore_manager = MagicMock()
        restore_manager.list_backups.return_value = []
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "new-backup"
        mock_backup_cls.side_effect = [restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        restore_manager.restore_backup.assert_not_called()
        assert any(
            cp.phase == "baseline_restore" and cp.status == "skipped"
            for cp in tx.checkpoints
        )
        assert tx.success is True


def test_transaction_skips_baseline_restore_when_no_backup_flag(tmp_path: Path) -> None:
    """When --no-backup is used, skip the baseline restore phase entirely."""
    applier = MagicMock()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    manager = ProfileTransactionManager(tmp_path, applier=applier)
    tx = manager.execute("test-profile", create_backup=False)

    assert not any(cp.phase == "baseline_restore" for cp in tx.checkpoints)
    assert tx.success is True


def test_transaction_continues_when_baseline_restore_fails(tmp_path: Path) -> None:
    """If baseline restore fails, log warning and continue with apply."""
    applier = MagicMock()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        restore_manager = MagicMock()
        restore_manager.list_backups.return_value = [{"id": "old-backup"}]
        restore_manager.restore_backup.side_effect = RuntimeError("restore broke")
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "new-backup"
        mock_backup_cls.side_effect = [restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        assert any(
            cp.phase == "baseline_restore" and cp.status == "warn"
            for cp in tx.checkpoints
        )
        # Apply still proceeded and succeeded
        assert tx.success is True


def test_transaction_handles_apply_exception_and_fails_cleanly(tmp_path: Path) -> None:
    applier = MagicMock()
    applier.apply_profile.side_effect = RuntimeError("boom")
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    manager = ProfileTransactionManager(tmp_path, applier=applier)
    tx = manager.execute("test-profile", create_backup=False)

    assert tx.success is False
    assert tx.state == "failed"
    assert tx.apply_result is not None
    assert "Profile apply crashed" in (tx.apply_result.error or "")
    assert any(cp.phase == "apply" and cp.status == "failed" for cp in tx.checkpoints)
