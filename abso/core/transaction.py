"""Transactional profile application orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from abso.core.applier import ApplyResult, ProfileApplier
from abso.core.backup import BackupManager
from abso.core.compliance import ComplianceEngine, ComplianceReport
from abso.core.config import get_config
from abso.core.exceptions import BackupCorruptedError, BackupNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class TransactionCheckpoint:
    """Phase checkpoint for resumable visibility."""

    phase: str
    status: str
    message: str
    at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TransactionResult:
    """Result of transactional profile application."""

    success: bool
    profile_id: str
    state: str
    backup_id: str | None = None
    error: str | None = None
    rollback_performed: bool = False
    rollback_error: str | None = None
    apply_result: ApplyResult | None = None
    verify_result: dict[str, Any] | None = None
    compliance_report: ComplianceReport | None = None
    checkpoints: list[TransactionCheckpoint] = field(default_factory=list)

    def add_checkpoint(self, phase: str, status: str, message: str) -> None:
        self.checkpoints.append(
            TransactionCheckpoint(phase=phase, status=status, message=message)
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        return {
            "success": self.success,
            "profile_id": self.profile_id,
            "state": self.state,
            "backup_id": self.backup_id,
            "error": self.error,
            "rollback_performed": self.rollback_performed,
            "rollback_error": self.rollback_error,
            "compliance": self.compliance_report.to_dict() if self.compliance_report else None,
            "checkpoints": [
                {
                    "phase": cp.phase,
                    "status": cp.status,
                    "message": cp.message,
                    "at": cp.at,
                }
                for cp in self.checkpoints
            ],
        }


class ProfileTransactionManager:
    """Executes profile apply with verify/compliance/rollback semantics."""

    def __init__(
        self,
        backup_dir: Path,
        applier: ProfileApplier | None = None,
        compliance_engine: ComplianceEngine | None = None,
        auto_rollback_on_critical: bool = True,
    ) -> None:
        self.backup_dir = backup_dir
        self.applier = applier or ProfileApplier()
        self.compliance_engine = compliance_engine or ComplianceEngine()
        self.auto_rollback_on_critical = auto_rollback_on_critical

    def execute(self, profile_id: str, create_backup: bool = True) -> TransactionResult:
        """Run full transactional apply flow."""
        tx = TransactionResult(
            success=False,
            profile_id=profile_id,
            state="planned",
        )
        tx.add_checkpoint("plan", "ok", "Transaction planned")

        if profile_id not in self.applier.PROFILES:
            tx.state = "failed"
            tx.error = f"Unknown profile: {profile_id}"
            tx.add_checkpoint("validate", "failed", tx.error)
            return tx

        try:
            prerequisite_error = self.applier.validate_profile_prerequisites(profile_id)
        except Exception as e:
            tx.state = "failed"
            tx.error = f"Prerequisite validation failed: {e}"
            tx.add_checkpoint("validate", "failed", tx.error)
            return tx

        if prerequisite_error:
            tx.state = "failed"
            tx.error = prerequisite_error
            tx.add_checkpoint("validate", "failed", prerequisite_error)
            return tx

        tx.add_checkpoint("validate", "ok", "Profile prerequisites satisfied")

        # === PHASE 0: Restore previous baseline ===
        # When switching profiles, stale settings from the previous profile
        # can leak through if the new profile doesn't explicitly override them.
        # Restore the latest backup (taken before the previous profile was applied)
        # to return to a clean pre-profile baseline before applying the new one.
        if create_backup:
            try:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                restore_manager = BackupManager(self.backup_dir)
                baseline_path = restore_manager.get_baseline_backup()
                if baseline_path and baseline_path.exists():
                    restore_summary = restore_manager.restore_backup(baseline_path.name)
                    if restore_summary.complete:
                        tx.add_checkpoint("baseline_restore", "ok", f"Restored baseline: {baseline_path.name}")
                    else:
                        incomplete_handlers = [
                            item["handler"]
                            for item in (
                                restore_summary.skipped_components
                                + restore_summary.failed_components
                            )
                        ]
                        tx.add_checkpoint(
                            "baseline_restore",
                            "warn",
                            "Baseline restore incomplete: "
                            + ", ".join(incomplete_handlers),
                        )
                else:
                    tx.add_checkpoint("baseline_restore", "skipped", "No previous backup — first application")
            except BackupNotFoundError:
                tx.add_checkpoint("baseline_restore", "skipped", "No baseline backup found — first application")
            except BackupCorruptedError as e:
                logger.warning(f"Baseline backup corrupted, continuing with apply: {e}")
                tx.add_checkpoint("baseline_restore", "warn", f"Baseline corrupted: {e}")
            except Exception as e:
                logger.warning(f"Baseline restore failed, continuing with apply: {e}")
                tx.add_checkpoint("baseline_restore", "warn", f"Restore failed: {e}")

        backup_manager: BackupManager | None = None
        if create_backup:
            try:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                backup_manager = BackupManager(self.backup_dir)
                tx.backup_id = backup_manager.create_backup(
                    profile_id=profile_id,
                    backup_type="pre_apply",
                )
                tx.add_checkpoint("backup", "ok", f"Backup created: {tx.backup_id}")

                # Auto-prune old backups (non-fatal)
                try:
                    cfg = get_config()
                    pruned = backup_manager.prune(max_backups=cfg.max_backups)
                    if pruned:
                        tx.add_checkpoint("prune", "ok", f"Pruned {len(pruned)} old backup(s)")
                except Exception as prune_err:
                    logger.warning(f"Auto-prune failed (non-fatal): {prune_err}")
                    tx.add_checkpoint("prune", "warn", f"Prune failed: {prune_err}")

            except Exception as e:
                tx.state = "failed"
                tx.error = f"Backup failed: {e}"
                tx.add_checkpoint("backup", "failed", tx.error)
                return tx
        else:
            tx.add_checkpoint("backup", "skipped", "Backup creation skipped")

        tx.state = "applying"
        try:
            tx.apply_result = self.applier.apply_profile(profile_id)
            if tx.apply_result.success:
                tx.add_checkpoint("apply", "ok", "Profile apply completed")
            else:
                tx.add_checkpoint(
                    "apply",
                    "failed",
                    tx.apply_result.error or "Profile apply failed",
                )
        except Exception as e:
            error = f"Profile apply crashed: {e}"
            tx.apply_result = ApplyResult(
                success=False,
                error=error,
                failed_settings=[f"ProfileApplier: {e}"],
            )
            tx.add_checkpoint("apply", "failed", error)

        tx.state = "verifying"
        try:
            tx.verify_result = self.applier.verify_profile(profile_id)
            if tx.verify_result.get("all_active", True):
                tx.add_checkpoint("verify", "ok", "Verification completed")
            else:
                tx.add_checkpoint("verify", "warn", "Verification reported mismatches")
        except Exception as e:
            tx.verify_result = {
                "profile": profile_id,
                "all_active": False,
                "handlers": {},
                "error": str(e),
            }
            tx.add_checkpoint("verify", "failed", f"Verification error: {e}")

        if tx.apply_result is None:
            tx.apply_result = ApplyResult(
                success=False,
                error="Profile apply did not return a result",
                failed_settings=["ProfileApplier: no result"],
            )

        tx.compliance_report = self.compliance_engine.evaluate(
            profile_id=profile_id,
            apply_result=tx.apply_result,
            verify_result=tx.verify_result,
        )

        has_critical = tx.compliance_report.has_critical
        if has_critical:
            tx.add_checkpoint("compliance", "failed", "Critical compliance issues detected")
        elif tx.compliance_report.warnings:
            tx.add_checkpoint("compliance", "warn", "Compliance warnings detected")
        else:
            tx.add_checkpoint("compliance", "ok", "Compliance checks passed")

        if has_critical and self.auto_rollback_on_critical and tx.backup_id and backup_manager:
            tx.state = "rolling_back"
            try:
                restore_summary = backup_manager.restore_backup(tx.backup_id)
                if restore_summary.complete:
                    tx.rollback_performed = True
                    tx.state = "rolled_back"
                    tx.error = "Critical compliance failure; restored backup automatically."
                    tx.add_checkpoint("rollback", "ok", f"Restored backup {tx.backup_id}")
                else:
                    incomplete_handlers = [
                        item["handler"]
                        for item in (
                            restore_summary.skipped_components
                            + restore_summary.failed_components
                        )
                    ]
                    tx.rollback_performed = False
                    tx.rollback_error = (
                        "Rollback incomplete for handlers: "
                        + ", ".join(incomplete_handlers)
                    )
                    tx.state = "failed"
                    tx.error = (
                        "Critical compliance failure and rollback was incomplete: "
                        f"{tx.rollback_error}"
                    )
                    tx.add_checkpoint("rollback", "failed", tx.error)
            except Exception as e:
                tx.rollback_error = str(e)
                tx.state = "failed"
                tx.error = (
                    "Critical compliance failure and rollback failed: "
                    f"{tx.rollback_error}"
                )
                tx.add_checkpoint("rollback", "failed", tx.error)
            tx.success = False
            return tx

        if tx.apply_result.success and not has_critical:
            tx.success = True
            tx.state = "committed"
            tx.add_checkpoint("commit", "ok", "Transaction committed")
        else:
            tx.success = False
            tx.state = "failed"
            tx.error = tx.apply_result.error or "Transaction failed"
            tx.add_checkpoint("commit", "failed", tx.error)

        return tx
