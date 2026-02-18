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
        backup_manager = mock_backup_cls.return_value
        backup_manager.create_backup.return_value = "backup-123"

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        backup_manager.restore_backup.assert_called_once_with("backup-123")
        assert tx.success is False
        assert tx.rollback_performed is True
        assert tx.state == "rolled_back"
        assert tx.backup_id == "backup-123"


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
