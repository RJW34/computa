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
from abso.profiles.catalog import resolve_profile_id

logger = logging.getLogger(__name__)


def _summarize_restore_issues(
    items: list[dict[str, Any]],
    *,
    blocking_only: bool = False,
) -> str:
    """Build a concise summary for restore issues."""
    relevant = [item for item in items if not blocking_only or bool(item.get("blocking", True))]
    if not relevant:
        return ""

    parts: list[str] = []
    for item in relevant:
        handler = str(item.get("handler", "UnknownHandler"))
        detail = str(item.get("detail") or item.get("reason") or "").strip()
        parts.append(f"{handler} ({detail})" if detail else handler)
    return ", ".join(parts)


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
    requested_profile_id: str | None = None
    fallback_chain: list[dict[str, str]] = field(default_factory=list)
    backup_id: str | None = None
    rollback_backup_id: str | None = None
    error: str | None = None
    rollback_attempted: bool = False
    rollback_performed: bool = False
    rollback_error: str | None = None
    rollback_summary: dict[str, Any] | None = None
    apply_result: ApplyResult | None = None
    verify_result: dict[str, Any] | None = None
    compliance_report: ComplianceReport | None = None
    checkpoints: list[TransactionCheckpoint] = field(default_factory=list)

    def add_checkpoint(self, phase: str, status: str, message: str) -> None:
        self.checkpoints.append(TransactionCheckpoint(phase=phase, status=status, message=message))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        return {
            "success": self.success,
            "profile_id": self.profile_id,
            "requested_profile_id": self.requested_profile_id,
            "fallback_chain": self.fallback_chain,
            "state": self.state,
            "backup_id": self.backup_id,
            "rollback_backup_id": self.rollback_backup_id,
            "error": self.error,
            "rollback_attempted": self.rollback_attempted,
            "rollback_performed": self.rollback_performed,
            "rollback_error": self.rollback_error,
            "rollback_summary": self.rollback_summary,
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
        auto_rollback_on_partial_apply: bool = True,
    ) -> None:
        """Initialize the transaction manager.

        Args:
            backup_dir: Directory where pre-apply snapshots live.
            applier: Optional ProfileApplier override (tests inject a mock).
            compliance_engine: Optional ComplianceEngine override.
            auto_rollback_on_critical: Roll back when compliance detects a
                critical issue after apply.
            auto_rollback_on_partial_apply: Roll back when the apply loop
                actually mutated state (``changed_settings`` is non-empty)
                but returned ``success=False``. This prevents leaving the
                system in a half-applied profile state — the class of bug
                that used to force users to run ``abso restore latest`` by
                hand after a single handler failure.
        """
        self.backup_dir = backup_dir
        self.applier = applier or ProfileApplier()
        self.compliance_engine = compliance_engine or ComplianceEngine()
        self.auto_rollback_on_critical = auto_rollback_on_critical
        self.auto_rollback_on_partial_apply = auto_rollback_on_partial_apply

    @staticmethod
    def _rollback_to_snapshot(
        tx: TransactionResult,
        manager: BackupManager,
        backup_id: str,
        reason: str,
    ) -> None:
        """Recover the pre-switch state without claiming unbacked settings restored."""
        tx.success = False
        tx.state = "rolling_back"
        tx.rollback_attempted = True
        try:
            summary = manager.restore_backup(backup_id)
            tx.rollback_summary = summary.to_dict()
            if summary.complete:
                tx.rollback_performed = True
                tx.state = "rolled_back"
                tx.error = f"{reason}; restored backup automatically."
                tx.add_checkpoint("rollback", "ok", f"Restored backup {backup_id}")
            else:
                # Non-blocking skips permit applying another profile, but do
                # not prove that an aborted switch restored the previous one.
                # Keep every gap (including unavailable NVIDIA restore) visible.
                tx.rollback_error = "Rollback incomplete for handlers: " + _summarize_restore_issues(
                    summary.skipped_components + summary.failed_components
                )
                tx.state = "failed"
                tx.error = f"{reason}; {tx.rollback_error}. Verify the previous profile before playing."
                tx.add_checkpoint("rollback", "failed", tx.error)
        except Exception as exc:
            tx.rollback_error = str(exc)
            tx.state = "failed"
            tx.error = f"{reason}; rollback failed: {exc}"
            tx.add_checkpoint("rollback", "failed", tx.error)

    def execute(
        self,
        profile_id: str,
        create_backup: bool = True,
        *,
        requested_profile_id: str | None = None,
        fallback_chain: list[dict[str, str]] | None = None,
        allow_capability_fallback: bool = True,
    ) -> TransactionResult:
        """Run full transactional apply flow."""
        canonical_profile_id = resolve_profile_id(profile_id) or profile_id
        requested = requested_profile_id or canonical_profile_id
        chain = list(fallback_chain or [])
        tx = TransactionResult(
            success=False,
            profile_id=canonical_profile_id,
            state="planned",
            requested_profile_id=requested,
            fallback_chain=chain,
        )
        tx.add_checkpoint("plan", "ok", "Transaction planned")
        if chain:
            tx.add_checkpoint(
                "fallback",
                "ok",
                (
                    f"Using fallback profile '{canonical_profile_id}' "
                    f"for requested profile '{requested}'"
                ),
            )

        if canonical_profile_id not in self.applier.PROFILES:
            tx.state = "failed"
            tx.error = f"Unknown profile: {profile_id}"
            tx.add_checkpoint("validate", "failed", tx.error)
            tx.apply_result = ApplyResult(success=False, error=tx.error)
            return tx

        try:
            prerequisite_error = self.applier.validate_profile_prerequisites(canonical_profile_id)
        except Exception as e:
            tx.state = "failed"
            tx.error = f"Prerequisite validation failed: {e}"
            tx.apply_result = ApplyResult(success=False, error=tx.error)
            tx.add_checkpoint("validate", "failed", tx.error)
            return tx

        if prerequisite_error:
            fallback_profile_id: str | None = None
            get_fallback = getattr(self.applier, "get_prepared_transition_fallback", None)
            if callable(get_fallback):
                candidate = get_fallback(canonical_profile_id)
                if isinstance(candidate, str) and candidate.strip():
                    fallback_profile_id = resolve_profile_id(candidate.strip()) or candidate.strip()

            visited = {canonical_profile_id}
            for item in chain:
                for key in ("from", "to"):
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        visited.add(resolve_profile_id(value) or value)

            if (
                allow_capability_fallback
                and fallback_profile_id
                and fallback_profile_id not in visited
            ):
                next_chain = chain + [
                    {
                        "from": canonical_profile_id,
                        "to": fallback_profile_id,
                        "reason": prerequisite_error,
                    }
                ]
                logger.info(
                    "Profile '%s' blocked during preflight; falling back to '%s': %s",
                    canonical_profile_id,
                    fallback_profile_id,
                    prerequisite_error,
                )
                return self.execute(
                    fallback_profile_id,
                    create_backup=create_backup,
                    requested_profile_id=requested,
                    fallback_chain=next_chain,
                    allow_capability_fallback=allow_capability_fallback,
                )

            tx.state = "failed"
            tx.error = prerequisite_error
            get_failure_result = getattr(self.applier, "get_prepared_failure_result", None)
            if callable(get_failure_result):
                failure_result = get_failure_result(canonical_profile_id, prerequisite_error)
                if isinstance(failure_result, ApplyResult):
                    tx.apply_result = failure_result
            if tx.apply_result is None:
                tx.apply_result = ApplyResult(success=False, error=prerequisite_error)
            tx.add_checkpoint("validate", "failed", prerequisite_error)
            return tx

        tx.add_checkpoint("validate", "ok", "Profile prerequisites satisfied")

        rollback_backup_manager: BackupManager | None = None
        rollback_backup_id: str | None = None
        if create_backup:
            try:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                rollback_backup_manager = BackupManager(self.backup_dir)
                rollback_backup_id = rollback_backup_manager.create_backup(
                    profile_id=canonical_profile_id,
                    backup_type="pre_switch",
                )
                tx.rollback_backup_id = rollback_backup_id
                tx.add_checkpoint(
                    "rollback_anchor",
                    "ok",
                    f"Captured pre-switch rollback snapshot: {rollback_backup_id}",
                )
            except Exception as e:
                tx.state = "failed"
                tx.error = f"Rollback snapshot failed: {e}"
                tx.add_checkpoint("rollback_anchor", "failed", tx.error)
                return tx

        # === PHASE 0: Restore previous baseline ===
        # When switching profiles, stale settings from the previous profile
        # can leak through if the new profile doesn't explicitly override them.
        # Restore shared system state and this game's native config from the
        # prior baseline. Other games' files are independent: reverting them
        # here would replace their latest settings with an old snapshot.
        baseline_restore_started = False
        if create_backup:
            try:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                restore_manager = BackupManager(self.backup_dir)
                baseline_path = restore_manager.get_baseline_backup()
                if baseline_path and baseline_path.exists():
                    target_handlers = {
                        type(handler).__name__
                        for handler in self.applier._get_profile(
                            canonical_profile_id
                        ).get_handlers()
                    }
                    baseline_restore_started = True
                    restore_summary = restore_manager.restore_backup(
                        baseline_path.name,
                        native_config_handlers=target_handlers,
                    )
                    if restore_summary.complete:
                        tx.add_checkpoint(
                            "baseline_restore", "ok", f"Restored baseline: {baseline_path.name}"
                        )
                    elif restore_summary.has_blocking_issues:
                        tx.state = "failed"
                        tx.error = (
                            "Baseline restore incomplete for restorable handlers: "
                            + _summarize_restore_issues(
                                restore_summary.skipped_components
                                + restore_summary.failed_components,
                                blocking_only=True,
                            )
                        )
                        tx.add_checkpoint("baseline_restore", "failed", tx.error)
                        assert rollback_backup_manager is not None and rollback_backup_id is not None
                        self._rollback_to_snapshot(
                            tx, rollback_backup_manager, rollback_backup_id, tx.error
                        )
                        return tx
                    else:
                        tx.add_checkpoint(
                            "baseline_restore",
                            "warn",
                            "Baseline restore incomplete for known non-restorable handlers: "
                            + _summarize_restore_issues(
                                restore_summary.skipped_components
                                + restore_summary.failed_components
                            ),
                        )
                else:
                    tx.add_checkpoint(
                        "baseline_restore", "skipped", "No previous backup - first application"
                    )
            except BackupNotFoundError:
                tx.add_checkpoint(
                    "baseline_restore", "skipped", "No baseline backup found - first application"
                )
            except BackupCorruptedError as e:
                tx.state = "failed"
                tx.error = f"Baseline backup corrupted: {e}"
                logger.error(tx.error)
                tx.add_checkpoint("baseline_restore", "failed", tx.error)
                if baseline_restore_started:
                    assert rollback_backup_manager is not None and rollback_backup_id is not None
                    self._rollback_to_snapshot(
                        tx, rollback_backup_manager, rollback_backup_id, tx.error
                    )
                return tx
            except Exception as e:
                tx.state = "failed"
                tx.error = f"Baseline restore failed: {e}"
                logger.error(tx.error)
                tx.add_checkpoint("baseline_restore", "failed", tx.error)
                if baseline_restore_started:
                    assert rollback_backup_manager is not None and rollback_backup_id is not None
                    self._rollback_to_snapshot(
                        tx, rollback_backup_manager, rollback_backup_id, tx.error
                    )
                return tx

        backup_manager: BackupManager | None = None
        if create_backup:
            try:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                backup_manager = BackupManager(self.backup_dir)
                tx.backup_id = backup_manager.create_backup(
                    profile_id=canonical_profile_id,
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
                if baseline_restore_started:
                    assert rollback_backup_manager is not None and rollback_backup_id is not None
                    self._rollback_to_snapshot(
                        tx, rollback_backup_manager, rollback_backup_id, tx.error
                    )
                return tx
        else:
            tx.add_checkpoint("backup", "skipped", "Backup creation skipped")

        tx.state = "applying"
        try:
            tx.apply_result = self.applier.apply_profile(canonical_profile_id)
            if tx.apply_result.success:
                tx.add_checkpoint("apply", "ok", "Profile apply completed")
            else:
                tx.add_checkpoint(
                    "apply",
                    "failed",
                    tx.apply_result.error or "Profile apply failed without a detailed error",
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
            tx.verify_result = self.applier.verify_profile(
                canonical_profile_id,
                reboot_pending=bool(tx.apply_result.requires_reboot),
            )
            if tx.verify_result.get("all_active", True):
                tx.add_checkpoint("verify", "ok", "Verification completed")
            else:
                tx.add_checkpoint("verify", "warn", "Verification reported mismatches")
        except Exception as e:
            tx.verify_result = {
                "profile": canonical_profile_id,
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
            profile_id=canonical_profile_id,
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

        rollback_target_id = rollback_backup_id or tx.backup_id
        rollback_manager = rollback_backup_manager or backup_manager

        partial_apply_failure = (
            tx.apply_result is not None
            and not tx.apply_result.success
            and (baseline_restore_started or bool(tx.apply_result.changed_settings))
        )

        should_rollback = bool(
            rollback_target_id
            and rollback_manager
            and (
                (has_critical and self.auto_rollback_on_critical)
                or (partial_apply_failure and self.auto_rollback_on_partial_apply)
            )
        )

        if should_rollback:
            # should_rollback above only goes True when both vars are truthy,
            # so these asserts are no-ops at runtime but they let mypy narrow
            # the Optional types and protect future refactors from drift.
            assert rollback_manager is not None
            assert rollback_target_id is not None
            rollback_reason = (
                "Critical compliance failure"
                if has_critical
                else "Partial apply failure after baseline restore"
                if baseline_restore_started
                else f"Partial apply failure ({len(tx.apply_result.changed_settings)} setting(s) mutated state before failure)"
            )
            self._rollback_to_snapshot(tx, rollback_manager, rollback_target_id, rollback_reason)
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
