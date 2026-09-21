"""Tests for reboot-pending reconciliation.

Regression: a profile with a reboot-gated setting whose committed state cannot
be directly observed (MPO) left ``reboot_pending`` stuck forever, because the
old reconcile demanded a fully-clean verification that MPO can never produce.
"""

from __future__ import annotations

from datetime import datetime

from abso.core.state_reconcile import (
    boot_commits_reboot_gated_writes,
    reconcile_reboot_pending_after_verified_boot,
)

APPLIED = "2026-06-03T17:15:53"
AFTER_BOOT = datetime(2026, 6, 9, 3, 48)   # system booted AFTER the write
BEFORE_BOOT = datetime(2026, 6, 1, 0, 0)   # "boot" predates the write

# The real-world stuck case: MPO reboot-gated, verify can't confirm it live.
MPO_PENDING_VERIFY = {
    "all_active": False,
    "status": "pending_reboot",
    "pending_apply_settings": [],
    "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
    "mismatched_handlers": ["GraphicsSettingsHandler"],
}


def _snapshot(**kw):
    base = {
        "current_profile": "overwatch2-gsync-hdr-capture",
        "applied_at": APPLIED,
        "reboot_pending": True,
        "reboot_reasons": ["GraphicsSettingsHandler"],
    }
    base.update(kw)
    return base


class TestReconcile:
    def test_clears_stale_mpo_reboot_after_boot(self) -> None:
        snap, changed = reconcile_reboot_pending_after_verified_boot(
            _snapshot(), MPO_PENDING_VERIFY, boot_time=AFTER_BOOT
        )
        assert changed is True
        assert snap["reboot_pending"] is False
        assert snap["reboot_reasons"] == []

    def test_no_clear_before_boot(self) -> None:
        snap, changed = reconcile_reboot_pending_after_verified_boot(
            _snapshot(), MPO_PENDING_VERIFY, boot_time=BEFORE_BOOT
        )
        assert changed is False
        assert snap["reboot_pending"] is True

    def test_no_clear_when_target_still_pending_apply(self) -> None:
        # A reboot-gated write that was never actually written must NOT clear.
        verify = dict(MPO_PENDING_VERIFY, pending_apply_settings=["GraphicsSettingsHandler.mpo_disabled"])
        _snap, changed = reconcile_reboot_pending_after_verified_boot(
            _snapshot(), verify, boot_time=AFTER_BOOT
        )
        assert changed is False

    def test_no_clear_on_verification_error(self) -> None:
        verify = dict(MPO_PENDING_VERIFY, error="verify exploded")
        _snap, changed = reconcile_reboot_pending_after_verified_boot(
            _snapshot(), verify, boot_time=AFTER_BOOT
        )
        assert changed is False

    def test_no_clear_when_not_reboot_pending(self) -> None:
        _snap, changed = reconcile_reboot_pending_after_verified_boot(
            _snapshot(reboot_pending=False), MPO_PENDING_VERIFY, boot_time=AFTER_BOOT
        )
        assert changed is False

    def test_clean_verify_before_boot_does_not_clear(self) -> None:
        # A clean registry verify is NOT enough before a reboot: the write is
        # present but not yet effective, so reboot_pending must persist.
        clean = {
            "all_active": True,
            "status": "active",
            "pending_apply_settings": [],
            "pending_reboot_gated_settings": [],
            "mismatched_handlers": [],
        }
        snap, changed = reconcile_reboot_pending_after_verified_boot(
            _snapshot(), clean, boot_time=BEFORE_BOOT
        )
        assert changed is False
        assert snap["reboot_pending"] is True


class TestBootCommitsHelper:
    def test_targeted_write_after_boot_keeps_reboot_pending(self) -> None:
        snapshot = _snapshot(reboot_required_at="2026-06-10T12:00:00")
        result, changed = reconcile_reboot_pending_after_verified_boot(
            snapshot, MPO_PENDING_VERIFY, boot_time=AFTER_BOOT,
        )
        assert changed is False
        assert result["applied_at"] == APPLIED
        assert result["reboot_pending"] is True

    def test_boot_after_targeted_write_clears_gate(self) -> None:
        result, changed = reconcile_reboot_pending_after_verified_boot(
            _snapshot(reboot_required_at="2026-06-08T12:00:00"),
            MPO_PENDING_VERIFY, boot_time=AFTER_BOOT,
        )
        assert changed is True
        assert result["applied_at"] == APPLIED
        assert result["reboot_pending"] is False
        assert "reboot_required_at" not in result

    def test_true_after_boot_no_blockers(self) -> None:
        assert boot_commits_reboot_gated_writes(_snapshot(), MPO_PENDING_VERIFY, boot_time=AFTER_BOOT) is True

    def test_false_with_pending_apply(self) -> None:
        verify = dict(MPO_PENDING_VERIFY, pending_apply_settings=["x"])
        assert boot_commits_reboot_gated_writes(_snapshot(), verify, boot_time=AFTER_BOOT) is False

    def test_false_before_boot(self) -> None:
        assert boot_commits_reboot_gated_writes(_snapshot(), MPO_PENDING_VERIFY, boot_time=BEFORE_BOOT) is False
