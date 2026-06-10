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


def boot_commits_reboot_gated_writes(
    snapshot: dict[str, Any],
    verification: dict[str, Any],
    *,
    boot_time: datetime | None = None,
) -> bool:
    """Return True when a post-write boot has committed the reboot-gated writes.

    A reboot is exactly what commits reboot-gated registry writes (MPO, HAGS,
    VBS). Once the machine has booted *after* ``applied_at`` and the targets are
    present -- i.e. nothing is still awaiting a live apply and there is no hard
    error -- those settings are committed even though live verification cannot
    directly observe DWM's MPO compositor state. Unrelated handler drift does
    not gate this (that surfaces via its own mismatch indicator), so we do NOT
    require a fully-clean verification here.
    """
    if verification.get("error"):
        return False
    if verification.get("pending_apply_settings") or []:
        return False
    applied_at_ts = parse_state_timestamp(snapshot.get("applied_at"))
    boot_time = boot_time or get_system_boot_time()
    if applied_at_ts is None or boot_time is None:
        return False
    return boot_time.timestamp() > applied_at_ts


def reconcile_reboot_pending_after_verified_boot(
    snapshot: dict[str, Any],
    verification: dict[str, Any],
    *,
    boot_time: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return state with stale reboot-pending cleared once a boot has committed it.

    Clears ``reboot_pending`` only when a boot has occurred after ``applied_at``
    and the reboot-gated targets are present (see
    :func:`boot_commits_reboot_gated_writes`). A reboot is what commits
    reboot-gated writes (MPO/HAGS/VBS); a clean registry verify *before* a boot
    does NOT clear it (the write is written but not yet effective). The old
    behavior additionally demanded a fully-clean live verify, which left
    ``reboot_pending`` stuck forever for MPO-using profiles since MPO's
    committed compositor state is unobservable.
    """
    if not snapshot.get("reboot_pending"):
        return snapshot, False

    if not boot_commits_reboot_gated_writes(snapshot, verification, boot_time=boot_time):
        return snapshot, False

    updated = dict(snapshot)
    updated["reboot_pending"] = False
    updated["reboot_reasons"] = []
    return updated, True
