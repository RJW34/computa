"""Tests for transactional profile apply flow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from abso.core.applier import ApplyResult
from abso.core.backup import BackupRestoreSummary
from abso.core.transaction import ProfileTransactionManager


def _make_applier() -> MagicMock:
    applier = MagicMock()
    applier.PROFILES = {"test-profile": object()}
    applier.validate_profile_prerequisites.return_value = None
    applier.get_prepared_transition_fallback.return_value = None
    applier.get_prepared_failure_result.side_effect = lambda profile_id, error: ApplyResult(
        success=False, error=error
    )
    return applier


def _complete_restore_summary() -> BackupRestoreSummary:
    return BackupRestoreSummary(backup_id="test-backup")


def _incomplete_restore_summary(*, blocking: bool) -> BackupRestoreSummary:
    return BackupRestoreSummary(backup_id="test-backup", skipped_components=[
        {
            "handler": "NvidiaSettingsHandler",
            "detail": "restore unavailable",
            "blocking": blocking,
        }
    ])


def _non_critical_compliance_report() -> MagicMock:
    report = MagicMock()
    report.has_critical = False
    report.warnings = []
    report.to_dict.return_value = {"summary": {"critical": 0, "warning": 0}}
    return report


def test_transaction_commits_on_success_without_backup(tmp_path: Path) -> None:
    applier = _make_applier()
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


def test_transaction_does_not_rollback_failed_noop_handlers(tmp_path: Path) -> None:
    """A later failure should not restore backups if prior successes were proven no-ops."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=False,
        error="late handler failure",
        applied_settings=["WindowsSettingsHandler"],
        changed_settings=[],
        failed_settings=["NvidiaSettingsHandler: failed"],
    )
    applier.verify_profile.return_value = {"all_active": False, "handlers": {}}
    compliance = MagicMock()
    compliance.evaluate.return_value = _non_critical_compliance_report()

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-123"
        restore_manager = MagicMock()
        restore_manager.get_baseline_backup.return_value = None
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "backup-123"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(
            tmp_path,
            applier=applier,
            compliance_engine=compliance,
        )
        tx = manager.execute("test-profile", create_backup=True)

    rollback_manager.restore_backup.assert_not_called()
    assert tx.rollback_performed is False
    assert tx.state == "failed"
    assert tx.error == "late handler failure"


def test_transaction_rolls_back_failed_mutating_handlers(tmp_path: Path) -> None:
    """Partial apply rollback still fires when a successful handler changed state."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=False,
        error="late handler failure",
        applied_settings=["WindowsSettingsHandler"],
        changed_settings=["WindowsSettingsHandler.hdr"],
        failed_settings=["NvidiaSettingsHandler: failed"],
    )
    applier.verify_profile.return_value = {"all_active": False, "handlers": {}}
    compliance = MagicMock()
    compliance.evaluate.return_value = _non_critical_compliance_report()

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-123"
        rollback_manager.restore_backup.return_value = _complete_restore_summary()
        restore_manager = MagicMock()
        restore_manager.get_baseline_backup.return_value = None
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "backup-123"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(
            tmp_path,
            applier=applier,
            compliance_engine=compliance,
        )
        tx = manager.execute("test-profile", create_backup=True)

    rollback_manager.restore_backup.assert_called_once_with("rollback-123")
    assert tx.rollback_performed is True
    assert tx.state == "rolled_back"
    assert "Partial apply failure" in (tx.error or "")


def test_transaction_rolls_back_on_critical_when_backup_available(tmp_path: Path) -> None:
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=False,
        error="handler failure",
        failed_settings=["WindowsSettingsHandler: failed"],
    )
    applier.verify_profile.return_value = {"all_active": False, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-123"
        rollback_manager.restore_backup.return_value = _complete_restore_summary()
        restore_manager = MagicMock()
        restore_manager.get_baseline_backup.return_value = None  # No previous backup
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "backup-123"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        rollback_manager.restore_backup.assert_called_once_with("rollback-123")
        assert tx.success is False
        assert tx.rollback_performed is True
        assert tx.state == "rolled_back"
        assert tx.backup_id == "backup-123"
        assert tx.rollback_backup_id == "rollback-123"


def test_transaction_commits_reboot_gated_written_verify_gap(tmp_path: Path) -> None:
    """A written reboot-gated setting should commit and ask for reboot, not roll back."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["GraphicsSettingsHandler"],
        changed_settings=["GraphicsSettingsHandler.disable_mpo"],
        requires_reboot=True,
        reboot_reasons=["GraphicsSettingsHandler"],
    )
    applier.verify_profile.return_value = {
        "all_active": False,
        "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
        "handlers": {
            "GraphicsSettingsHandler": {
                "all_active": False,
                "pending_reboot_gated_settings": ["mpo_disabled"],
                "settings": {
                    "mpo_disabled": {
                        "target": False,
                        "current": False,
                        "active": True,
                        "reboot_gated": True,
                        "registry_target_written": True,
                        "live_commit_pending": True,
                    }
                },
            }
        },
    }

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-live-state"
        rollback_manager.restore_backup.return_value = _complete_restore_summary()
        restore_manager = MagicMock()
        restore_manager.get_baseline_backup.return_value = None
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "baseline-for-next-switch"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

    rollback_manager.restore_backup.assert_not_called()
    applier.verify_profile.assert_called_once_with("test-profile", reboot_pending=True)
    assert tx.success is True
    assert tx.state == "committed"
    assert tx.error is None
    assert tx.compliance_report is not None
    assert tx.compliance_report.has_critical is False
    assert [issue.code for issue in tx.compliance_report.warnings] == [
        "VERIFY_PENDING_REBOOT"
    ]
    assert any(cp.phase == "compliance" and cp.status == "warn" for cp in tx.checkpoints)
    assert any(cp.phase == "commit" and cp.status == "ok" for cp in tx.checkpoints)


def test_transaction_restores_baseline_before_apply(tmp_path: Path) -> None:
    """When a previous backup exists, restore it before applying new profile."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        # First call captures rollback anchor, second restores baseline, third creates next baseline
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-123"
        restore_manager = MagicMock()
        baseline_path = MagicMock()
        baseline_path.exists.return_value = True
        baseline_path.name = "old-backup"
        restore_manager.get_baseline_backup.return_value = baseline_path
        restore_manager.restore_backup.return_value = _complete_restore_summary()
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "new-backup"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        restore_manager.restore_backup.assert_called_once_with("old-backup", native_config_handlers=set())
        assert any(cp.phase == "baseline_restore" and cp.status == "ok" for cp in tx.checkpoints)
        assert tx.success is True


def test_transaction_skips_baseline_restore_when_no_backups(tmp_path: Path) -> None:
    """On first-ever apply, skip restore since there's no previous backup."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-123"
        restore_manager = MagicMock()
        restore_manager.get_baseline_backup.return_value = None
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "new-backup"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        restore_manager.restore_backup.assert_not_called()
        assert any(
            cp.phase == "baseline_restore" and cp.status == "skipped" for cp in tx.checkpoints
        )
        assert tx.success is True


def test_transaction_skips_baseline_restore_when_no_backup_flag(tmp_path: Path) -> None:
    """When --no-backup is used, skip the baseline restore phase entirely."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    manager = ProfileTransactionManager(tmp_path, applier=applier)
    tx = manager.execute("test-profile", create_backup=False)

    assert not any(cp.phase == "baseline_restore" for cp in tx.checkpoints)
    assert tx.success is True


def test_transaction_fails_when_baseline_restore_raises(tmp_path: Path) -> None:
    """A crashing baseline restore must fail closed before apply."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-123"
        restore_manager = MagicMock()
        baseline_path = MagicMock()
        baseline_path.exists.return_value = True
        baseline_path.name = "old-backup"
        restore_manager.get_baseline_backup.return_value = baseline_path
        restore_manager.restore_backup.side_effect = RuntimeError("restore broke")
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "new-backup"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        assert any(
            cp.phase == "baseline_restore" and cp.status == "failed" for cp in tx.checkpoints
        )
        applier.apply_profile.assert_not_called()
        assert tx.success is False


def test_transaction_continues_for_non_blocking_baseline_restore_gaps(tmp_path: Path) -> None:
    """Known non-restorable handlers should warn but not block the next apply."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-123"
        restore_manager = MagicMock()
        baseline_path = MagicMock()
        baseline_path.exists.return_value = True
        baseline_path.name = "old-backup"
        restore_manager.get_baseline_backup.return_value = baseline_path
        restore_manager.restore_backup.return_value = _incomplete_restore_summary(blocking=False)
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "new-backup"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        assert any(cp.phase == "baseline_restore" and cp.status == "warn" for cp in tx.checkpoints)
        applier.apply_profile.assert_called_once_with("test-profile")
        assert tx.success is True


def test_transaction_fails_for_blocking_baseline_restore_gaps(tmp_path: Path) -> None:
    """Restorable handler restore gaps must block the next apply."""
    applier = _make_applier()
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-123"
        restore_manager = MagicMock()
        baseline_path = MagicMock()
        baseline_path.exists.return_value = True
        baseline_path.name = "old-backup"
        restore_manager.get_baseline_backup.return_value = baseline_path
        restore_manager.restore_backup.return_value = _incomplete_restore_summary(blocking=True)
        backup_manager = MagicMock()
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        assert any(
            cp.phase == "baseline_restore" and cp.status == "failed" for cp in tx.checkpoints
        )
        applier.apply_profile.assert_not_called()
        backup_manager.create_backup.assert_not_called()
        assert tx.success is False


@pytest.mark.parametrize("failure", ["reported", "exception"])
def test_failed_baseline_recovers_pre_switch_state_before_returning(tmp_path: Path, failure: str):
    """A late audio restore error must undo the baseline's earlier mutations."""
    applier = _make_applier()
    previous = {"hdr": True, "power_plan": "gaming"}
    live = dict(previous)
    rollback_manager = MagicMock()
    rollback_manager.create_backup.return_value = "pre-switch"

    def recover(backup_id):
        assert backup_id == "pre-switch"
        live.update(previous)
        return BackupRestoreSummary(backup_id, restored_components=["Windows", "Power"])

    rollback_manager.restore_backup.side_effect = recover
    restore_manager = MagicMock()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    restore_manager.get_baseline_backup.return_value = baseline

    def fail_after_restoring_display(_backup_id, *, native_config_handlers):
        assert native_config_handlers == set()
        live.update(hdr=False, power_plan="balanced")
        if failure == "exception":
            raise RuntimeError("audio restore crashed")
        return BackupRestoreSummary("baseline", failed_components=[{
            "handler": "AudioEngineHandler", "detail": "Access denied", "blocking": True,
        }])

    restore_manager.restore_backup.side_effect = fail_after_restoring_display
    with patch("abso.core.transaction.BackupManager", side_effect=[rollback_manager, restore_manager]):
        tx = ProfileTransactionManager(tmp_path, applier=applier).execute("test-profile")

    assert live == previous
    applier.apply_profile.assert_not_called()
    assert tx.success is False
    assert tx.rollback_attempted is True
    assert tx.rollback_performed is True
    assert tx.state == "rolled_back"
    assert tx.to_dict()["rollback_summary"]["complete"] is True
    assert "Baseline restore" in tx.error
    assert [cp.phase for cp in tx.checkpoints][-2:] == ["baseline_restore", "rollback"]


@pytest.mark.parametrize("recovery", ["nonblocking_gap", "blocking_failure", "exception"])
def test_failed_baseline_does_not_claim_incomplete_snapshot_recovery(tmp_path: Path, recovery: str):
    applier = _make_applier()
    rollback_manager = MagicMock()
    rollback_manager.create_backup.return_value = "pre-switch"
    if recovery == "exception":
        rollback_manager.restore_backup.side_effect = RuntimeError("snapshot read failed")
    else:
        rollback_manager.restore_backup.return_value = _incomplete_restore_summary(
            blocking=recovery == "blocking_failure"
        )
    restore_manager = MagicMock()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    restore_manager.get_baseline_backup.return_value = baseline
    restore_manager.restore_backup.return_value = BackupRestoreSummary("baseline", failed_components=[{
        "handler": "AudioEngineHandler", "detail": "Access denied", "blocking": True,
    }])
    with patch("abso.core.transaction.BackupManager", side_effect=[rollback_manager, restore_manager]):
        tx = ProfileTransactionManager(tmp_path, applier=applier).execute("test-profile")

    rollback_manager.restore_backup.assert_called_once_with("pre-switch")
    applier.apply_profile.assert_not_called()
    assert tx.success is False
    assert tx.rollback_attempted is True
    assert tx.rollback_performed is False
    assert tx.state == "failed"
    assert "AudioEngineHandler" in tx.error
    if recovery == "exception":
        assert tx.rollback_summary is None
        assert tx.rollback_error == "snapshot read failed"
    else:
        assert "NvidiaSettingsHandler" in tx.rollback_error
        assert tx.to_dict()["rollback_summary"]["complete"] is False
        assert "restored backup automatically" not in tx.error


@pytest.mark.parametrize("failure_phase", ["backup", "apply"])
def test_failure_after_baseline_recovers_even_without_new_handler_changes(tmp_path: Path, failure_phase: str):
    """Baseline restoration itself is a mutation that needs recovery on failure."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(success=False, error="preflight failed")
    applier.verify_profile.return_value = {"all_active": False, "handlers": {}}
    compliance = MagicMock()
    compliance.evaluate.return_value = _non_critical_compliance_report()
    rollback_manager = MagicMock()
    rollback_manager.create_backup.return_value = "pre-switch"
    rollback_manager.restore_backup.return_value = _complete_restore_summary()
    restore_manager = MagicMock()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    restore_manager.get_baseline_backup.return_value = baseline
    restore_manager.restore_backup.return_value = _complete_restore_summary()
    backup_manager = MagicMock()
    if failure_phase == "backup":
        backup_manager.create_backup.side_effect = OSError("disk full")
    else:
        backup_manager.create_backup.return_value = "pre-apply"
    with patch("abso.core.transaction.BackupManager", side_effect=[
        rollback_manager, restore_manager, backup_manager,
    ]):
        tx = ProfileTransactionManager(tmp_path, applier=applier, compliance_engine=compliance).execute(
            "test-profile"
        )

    rollback_manager.restore_backup.assert_called_once_with("pre-switch")
    assert tx.rollback_performed is True
    assert tx.success is False
    if failure_phase == "backup":
        applier.apply_profile.assert_not_called()
    else:
        assert not tx.apply_result.changed_settings


def test_transaction_uses_pre_switch_snapshot_as_rollback_target(tmp_path: Path) -> None:
    """Critical rollback should restore the live pre-switch snapshot, not the clean baseline."""
    applier = _make_applier()
    applier.apply_profile.return_value = ApplyResult(
        success=False,
        error="handler failure",
        failed_settings=["NvidiaSettingsHandler: failed"],
    )
    applier.verify_profile.return_value = {"all_active": False, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-live-state"
        rollback_manager.restore_backup.return_value = _complete_restore_summary()

        restore_manager = MagicMock()
        baseline_path = MagicMock()
        baseline_path.exists.return_value = True
        baseline_path.name = "baseline-clean"
        restore_manager.get_baseline_backup.return_value = baseline_path
        restore_manager.restore_backup.return_value = _complete_restore_summary()

        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "baseline-for-next-switch"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

        restore_manager.restore_backup.assert_called_once_with("baseline-clean", native_config_handlers=set())
        backup_manager.create_backup.assert_called_once()
        rollback_manager.restore_backup.assert_called_once_with("rollback-live-state")
        assert tx.rollback_backup_id == "rollback-live-state"
        assert tx.backup_id == "baseline-for-next-switch"


def test_transaction_handles_apply_exception_and_fails_cleanly(tmp_path: Path) -> None:
    applier = _make_applier()
    applier.apply_profile.side_effect = RuntimeError("boom")
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    manager = ProfileTransactionManager(tmp_path, applier=applier)
    tx = manager.execute("test-profile", create_backup=False)

    assert tx.success is False
    assert tx.state == "failed"
    assert tx.apply_result is not None
    assert "Profile apply crashed" in (tx.apply_result.error or "")
    assert any(cp.phase == "apply" and cp.status == "failed" for cp in tx.checkpoints)


def test_transaction_rejects_unknown_profile_before_touching_backups(tmp_path: Path) -> None:
    applier = MagicMock()
    applier.PROFILES = {}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("missing-profile", create_backup=True)

    mock_backup_cls.assert_not_called()
    assert tx.success is False
    assert tx.error == "Unknown profile: missing-profile"
    assert any(cp.phase == "validate" and cp.status == "failed" for cp in tx.checkpoints)


def test_transaction_rejects_capability_blocker_before_touching_backups(tmp_path: Path) -> None:
    applier = _make_applier()
    applier.validate_profile_prerequisites.return_value = (
        "This profile requires at least one HDR-capable active display, but none were detected."
    )

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("test-profile", create_backup=True)

    mock_backup_cls.assert_not_called()
    applier.apply_profile.assert_not_called()
    assert tx.success is False
    assert tx.error == (
        "This profile requires at least one HDR-capable active display, but none were detected."
    )
    assert tx.apply_result is not None
    assert tx.apply_result.error == tx.error
    assert any(cp.phase == "validate" and cp.status == "failed" for cp in tx.checkpoints)


def test_transaction_retries_capability_blocker_fallback_before_backups(tmp_path: Path) -> None:
    applier = _make_applier()
    applier.PROFILES = {"strict-profile": object(), "safe-profile": object()}
    blocker = (
        "This fullscreen-only VRR profile is blocked because the active display "
        "path has 2 monitors with mixed refresh rates."
    )

    def validate(profile_id: str) -> str | None:
        if profile_id == "strict-profile":
            return blocker
        return None

    def prepared_fallback(profile_id: str) -> str | None:
        if profile_id == "strict-profile":
            return "safe-profile"
        return None

    applier.validate_profile_prerequisites.side_effect = validate
    applier.get_prepared_transition_fallback.side_effect = prepared_fallback
    applier.apply_profile.return_value = ApplyResult(
        success=True,
        applied_settings=["WindowsSettingsHandler"],
    )
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        rollback_manager = MagicMock()
        rollback_manager.create_backup.return_value = "rollback-safe"
        restore_manager = MagicMock()
        restore_manager.get_baseline_backup.return_value = None
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = "backup-safe"
        mock_backup_cls.side_effect = [rollback_manager, restore_manager, backup_manager]

        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute("strict-profile", create_backup=True)

    assert tx.success is True
    assert tx.profile_id == "safe-profile"
    assert tx.requested_profile_id == "strict-profile"
    assert tx.fallback_chain == [
        {"from": "strict-profile", "to": "safe-profile", "reason": blocker}
    ]
    applier.apply_profile.assert_called_once_with("safe-profile")
    rollback_manager.create_backup.assert_called_once_with(
        profile_id="safe-profile",
        backup_type="pre_switch",
    )
    backup_manager.create_backup.assert_called_once_with(
        profile_id="safe-profile",
        backup_type="pre_apply",
    )
    assert any(cp.phase == "fallback" and cp.status == "ok" for cp in tx.checkpoints)


def test_transaction_can_fail_capability_blocker_without_fallback(tmp_path: Path) -> None:
    applier = _make_applier()
    applier.PROFILES = {"strict-profile": object(), "safe-profile": object()}
    blocker = (
        "This fullscreen-only VRR profile is blocked because the active display "
        "path has 2 monitors with mixed refresh rates."
    )
    applier.validate_profile_prerequisites.return_value = blocker
    applier.get_prepared_transition_fallback.return_value = "safe-profile"

    with patch("abso.core.transaction.BackupManager") as mock_backup_cls:
        manager = ProfileTransactionManager(tmp_path, applier=applier)
        tx = manager.execute(
            "strict-profile",
            create_backup=True,
            allow_capability_fallback=False,
        )

    mock_backup_cls.assert_not_called()
    applier.apply_profile.assert_not_called()
    assert tx.success is False
    assert tx.profile_id == "strict-profile"
    assert tx.requested_profile_id == "strict-profile"
    assert tx.fallback_chain == []
    assert tx.error == blocker
    assert tx.apply_result is not None
    assert tx.apply_result.error == blocker
    assert any(cp.phase == "validate" and cp.status == "failed" for cp in tx.checkpoints)
