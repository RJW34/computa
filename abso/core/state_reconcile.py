"""Shared helpers for active-profile state reconciliation."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from abso.core.app_paths import app_state_file


def local_appdata_state_file() -> Path:
    """Return the packaged-app state-file location used by tray/GUI clients."""
    return app_state_file()


def state_file_write_targets(
    primary: Path,
    *,
    package_root: Path | None = None,
    frozen: bool | None = None,
) -> list[Path]:
    """Return state file paths that should stay in sync for this runtime.

    Source-mode commands use the repository state file but the elevated tray and
    installed GUI read LocalAppData. Mirroring only the default repo state avoids
    leaking test or custom state-file paths into the user's real app data.
    """
    targets = [primary]
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        return targets

    package_root = package_root or Path(__file__).resolve().parents[2]
    try:
        is_default_dev_state = primary.resolve() == (package_root / ".abso_state.json").resolve()
    except OSError:
        return targets

    if not is_default_dev_state:
        return targets

    local_state = local_appdata_state_file()
    try:
        if local_state.resolve() != primary.resolve():
            targets.append(local_state)
    except OSError:
        targets.append(local_state)
    return targets


def get_system_boot_time() -> datetime | None:
    """Return the local system boot time when it can be determined cheaply."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes

        uptime_ms = int(ctypes.windll.kernel32.GetTickCount64())  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - state reads should not fail on uptime probes
        return None
    return datetime.now() - timedelta(milliseconds=uptime_ms)


def parse_state_timestamp(value: Any) -> float | None:
    """Parse an ISO state timestamp into a local timestamp for comparisons."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OSError):
        return None


def verification_proves_reboot_committed(verification: dict[str, Any]) -> bool:
    """Return True when live verification no longer shows reboot/apply work."""
    if not bool(verification.get("all_active")):
        return False
    status = verification.get("status")
    if status is not None and status != "active":
        return False
    return (
        not (verification.get("pending_apply_settings") or [])
        and not (verification.get("pending_reboot_gated_settings") or [])
        and not (verification.get("mismatched_handlers") or [])
        and not verification.get("error")
    )


def reconcile_reboot_pending_after_verified_boot(
    snapshot: dict[str, Any],
    verification: dict[str, Any],
    *,
    boot_time: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return state with stale reboot-pending cleared when a later boot is proven.

    Some settings, notably MPO, can only be committed by the Windows compositor
    at boot. Once the machine has booted after the write and live verification is
    clean, keeping ``reboot_pending`` set only creates stale tray/GUI warnings.
    """
    if not snapshot.get("reboot_pending"):
        return snapshot, False
    if not verification_proves_reboot_committed(verification):
        return snapshot, False

    applied_at_ts = parse_state_timestamp(snapshot.get("applied_at"))
    boot_time = boot_time or get_system_boot_time()
    if applied_at_ts is None or boot_time is None:
        return snapshot, False

    if boot_time.timestamp() <= applied_at_ts:
        return snapshot, False

    updated = dict(snapshot)
    updated["reboot_pending"] = False
    updated["reboot_reasons"] = []
    return updated, True
