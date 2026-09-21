"""Health diagnostics and bundle generation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from abso.core.backup import BackupManager
from abso.core.config import ConfigManager
from abso.core.display_diagnostics import (
    build_active_state_context,
    enrich_display_stability_with_active_state,
    summarize_display_diagnostics,
)
from abso.core.display_events import collect_recent_display_events
from abso.core.display_stability import collect_display_stability_snapshot
from abso.core.fallback_controller import FallbackController
from abso.core.profile_status import (
    format_manual_step,
    get_pending_manual_steps,
    summarize_profile_verification,
)
from abso.core.state_reconcile import (
    get_system_boot_time,
    reconcile_reboot_pending_after_verified_boot,
    state_file_write_targets,
)
from abso.core.state_store import write_state_snapshot
from abso.tray import ensure_tray_running, get_startup_status
from abso.utils.atomic_io import atomic_write_json

TRAY_RUNTIME_MODULES: tuple[str, ...] = (
    "ABSO-Theme.ps1",
    "ABSO-ThemePack.ps1",
    "ABSO-Icons.ps1",
    "ABSO-Notifications.ps1",
    "ABSO-Settings.ps1",
    "ABSO-StartupState.ps1",
    "ABSO-QuickPanel.ps1",
)


def _candidate_backup_dirs(primary: Path) -> list[Path]:
    """Return backup roots worth reporting in diagnostics."""
    candidates = [primary]

    workspace_backups = Path.cwd() / "backups"
    try:
        if workspace_backups.resolve() != primary.resolve():
            candidates.append(workspace_backups)
    except OSError:
        candidates.append(workspace_backups)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)

    return unique


def _compact_backup_summary(
    backup: dict[str, Any],
    *,
    role: str,
    source_path: Path,
    component_preview_limit: int = 8,
) -> dict[str, Any]:
    """Return a compact backup row suitable for frequent health diagnostics."""
    components = list(backup.get("components") or [])
    item: dict[str, Any] = {
        "id": backup.get("id"),
        "created_at": backup.get("created_at"),
        "profile_id": backup.get("profile_id"),
        "backup_type": backup.get("backup_type"),
        "component_count": len(components),
        "source": role,
        "source_path": str(source_path),
    }
    if components and component_preview_limit > 0:
        item["components_preview"] = components[:component_preview_limit]
        item["components_truncated"] = len(components) > component_preview_limit
    return item


def _backup_summary_key(summary: dict[str, Any]) -> str:
    """Return a stable identity for de-duplicating mirrored backup rows."""
    backup_id = summary.get("id")
    if backup_id:
        return f"id:{backup_id}"
    return "|".join(
        [
            "anonymous",
            str(summary.get("created_at") or ""),
            str(summary.get("profile_id") or ""),
            str(summary.get("backup_type") or ""),
            str(summary.get("source_path") or ""),
        ]
    )


def _append_backup_mirror(
    unique_summary: dict[str, Any],
    mirrored_summary: dict[str, Any],
) -> None:
    """Record that the same backup exists in another root without duplicating it."""
    mirrors = unique_summary.setdefault("mirrors", [])
    if isinstance(mirrors, list):
        mirrors.append(
            {
                "source": mirrored_summary.get("source"),
                "source_path": mirrored_summary.get("source_path"),
            }
        )


def _build_backups_check(
    backups_dir: Path,
    *,
    include_recent: bool = False,
) -> dict[str, Any]:
    """Build a backup summary across primary and workspace roots."""
    roots: list[dict[str, Any]] = []
    unique_summaries: dict[str, dict[str, Any]] = {}
    entry_count = 0

    for index, candidate in enumerate(_candidate_backup_dirs(backups_dir)):
        role = "primary" if index == 0 else "workspace"
        try:
            backup_list = BackupManager(candidate).list_backups()
            entry_count += len(backup_list)
            roots.append(
                {
                    "role": role,
                    "path": str(candidate),
                    "count": len(backup_list),
                }
            )
            for backup in backup_list:
                summary = _compact_backup_summary(
                    dict(backup),
                    role=role,
                    source_path=candidate,
                    component_preview_limit=8 if include_recent else 0,
                )
                key = _backup_summary_key(summary)
                if key in unique_summaries:
                    _append_backup_mirror(unique_summaries[key], summary)
                    continue
                unique_summaries[key] = summary
        except Exception as e:
            roots.append(
                {
                    "role": role,
                    "path": str(candidate),
                    "count": 0,
                    "error": str(e),
                }
            )

    recent = list(unique_summaries.values())
    recent.sort(key=lambda item: str(item.get("id", "")), reverse=True)
    unique_count = len(unique_summaries)
    data: dict[str, Any] = {
        "count": unique_count,
        "entry_count": entry_count,
        "mirror_count": max(entry_count - unique_count, 0),
        "roots": roots,
    }
    if include_recent:
        data["recent"] = recent[:5]
    elif recent:
        data["latest"] = recent[0]

    return {
        "status": "ok" if unique_count else "warning",
        "data": data,
    }


def _write_reconciled_state_targets(
    state_file: Path,
    state_data: dict[str, Any],
) -> list[dict[str, str]]:
    """Write reconciled state, treating mirror writes as best-effort."""
    return write_state_snapshot(
        state_file_write_targets(state_file),
        state_data,
        writer=atomic_write_json,
    )


def _build_tray_startup_check(startup_status: dict[str, Any]) -> dict[str, Any]:
    """Classify tray startup registration, including stale task actions."""
    warnings: list[str] = []
    installed = bool(startup_status.get("installed"))
    mode = startup_status.get("mode")

    if not installed:
        warnings.append("tray startup is not registered")

    if mode == "scheduled_task" and not bool(startup_status.get("task_highest", True)):
        warnings.append("scheduled task is not configured for highest privileges")

    if (
        startup_status.get("task_action_path_current") is False
        and not startup_status.get("task_action_path_installed")
    ):
        warnings.append("scheduled task action points at a different tray path")

    check: dict[str, Any] = {
        "status": "ok" if not warnings else "warning",
        "data": startup_status,
    }
    if warnings:
        check["warnings"] = warnings
    return check


def _hash_file_sha256(path: Path) -> str | None:
    """Return lowercase sha256 for a file, or None when unavailable."""
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _is_process_running(pid: int) -> bool:
    """Return whether a PID currently exists without mutating process state."""
    if pid <= 0:
        return False

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        error_access_denied = 5
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return ctypes.get_last_error() == error_access_denied

    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _paths_match(left: str | None, right: Path) -> bool:
    """Compare paths with Windows-safe normalization."""
    if not left:
        return False
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(
        os.path.normpath(str(right))
    )


def _build_tray_runtime_marker_check(
    root_dir: Path,
    tray_runtime: dict[str, Any],
) -> dict[str, Any]:
    """Compare the running tray marker with installed tray scripts/modules."""
    marker_path = root_dir / "tray-runtime.json"
    installed_tray_dir = root_dir / "abso" / "tray"
    installed_script = installed_tray_dir / "ABSO-Tray.ps1"
    running = bool(tray_runtime.get("running_after"))
    warnings: list[str] = []
    data: dict[str, Any] = {
        "running": running,
        "marker_path": str(marker_path),
        "installed_script": str(installed_script),
    }

    if not running:
        data["not_applicable_reason"] = "tray is not running"
        return {"status": "ok", "data": data}

    installed_hash = _hash_file_sha256(installed_script)
    data["installed_script_hash_sha256"] = installed_hash
    if installed_hash is None:
        warnings.append("installed tray script is missing or unreadable")

    installed_modules: dict[str, dict[str, str | None]] = {}
    for module_name in TRAY_RUNTIME_MODULES:
        module_path = installed_tray_dir / module_name
        installed_modules[module_name] = {
            "path": str(module_path),
            "hash_sha256": _hash_file_sha256(module_path),
        }
    data["installed_modules"] = installed_modules

    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(marker, dict):
            raise ValueError("marker JSON root is not an object")
    except FileNotFoundError:
        marker = None
        warnings.append("running tray has not written a runtime marker")
    except Exception as exc:
        marker = None
        warnings.append(f"tray runtime marker is unreadable: {exc}")

    if marker is not None:
        marker_hash = str(marker.get("script_hash_sha256") or "").lower() or None
        marker_pid = marker.get("pid")
        marker_script_path = str(marker.get("script_path") or "") or None
        data["marker"] = marker
        data["marker_script_hash_sha256"] = marker_hash
        data["marker_pid_running"] = None
        if installed_hash and marker_hash and marker_hash != installed_hash:
            warnings.append("running tray script hash differs from installed tray script")
        if installed_hash and not marker_hash:
            warnings.append("tray runtime marker has no script hash")
        if not marker_script_path:
            warnings.append("tray runtime marker has no script path")
        elif not _paths_match(marker_script_path, installed_script):
            warnings.append("running tray script path differs from installed tray script")

        marker_modules = marker.get("module_hashes")
        if not isinstance(marker_modules, dict):
            marker_modules = {}
            warnings.append("tray runtime marker has no module hashes")
        data["marker_module_hashes"] = marker_modules
        for module_name, installed_module in installed_modules.items():
            installed_module_hash = installed_module.get("hash_sha256")
            if not installed_module_hash:
                warnings.append(f"installed tray module is missing or unreadable: {module_name}")
                continue
            marker_module = marker_modules.get(module_name)
            if not isinstance(marker_module, dict):
                warnings.append(f"tray runtime marker has no module hash for {module_name}")
                continue
            marker_module_hash = str(marker_module.get("hash_sha256") or "").lower() or None
            marker_module_path = str(marker_module.get("path") or "") or None
            if not marker_module_hash:
                warnings.append(f"tray runtime marker has empty module hash for {module_name}")
            elif marker_module_hash != installed_module_hash:
                warnings.append(
                    f"running tray module hash differs from installed tray module: {module_name}"
                )
            if marker_module_path and not _paths_match(
                marker_module_path,
                Path(str(installed_module["path"])),
            ):
                warnings.append(
                    f"running tray module path differs from installed tray module: {module_name}"
                )
        try:
            marker_pid_int = int(marker_pid)
        except (TypeError, ValueError):
            marker_pid_int = 0
        if marker_pid_int <= 0:
            warnings.append("tray runtime marker has no valid pid")
        else:
            marker_pid_running = _is_process_running(marker_pid_int)
            data["marker_pid_running"] = marker_pid_running
            if not marker_pid_running:
                warnings.append("tray runtime marker pid is not running")

    check: dict[str, Any] = {
        "status": "warning" if warnings else "ok",
        "data": data,
    }
    if warnings:
        check["warnings"] = warnings
    return check


def _build_display_events_check() -> dict[str, Any]:
    """Classify recent read-only display event-log evidence."""
    events_payload = collect_recent_display_events()
    warnings: list[str] = []

    if events_payload.get("error"):
        warnings.append("display event log query failed")
    elif events_payload.get("channel_error_count", 0):
        warnings.append("display event log channel query failed")
    elif events_payload.get("actionable_count", events_payload.get("count", 0)):
        warnings.append("recent actionable display/driver/power events found")

    check: dict[str, Any] = {
        "status": "warning" if warnings else "ok",
        "data": events_payload,
    }
    if warnings:
        check["warnings"] = warnings
    return check


def _build_display_stability_check(
    state_data: dict[str, Any] | None,
    *,
    display_events: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify passive display-topology black-flash risk."""
    snapshot = collect_display_stability_snapshot()
    warnings: list[str] = []

    if snapshot.get("error"):
        warnings.append("display topology stability probe failed")
    elif snapshot.get("risk_level") == "high":
        warnings.append("display topology has high compositor black-flash risk")
    elif snapshot.get("warnings"):
        warnings.append("display topology has actionable display warnings")

    active_state = build_active_state_context(state_data) if state_data else None
    if active_state:
        snapshot = enrich_display_stability_with_active_state(
            snapshot,
            active_state,
        )
    summary = summarize_display_diagnostics(
        display_events or {},
        snapshot,
        active_state,
    )
    snapshot["recommended_actions"] = list(summary.get("recommended_actions") or [])

    check: dict[str, Any] = {
        "status": "warning" if warnings else "ok",
        "data": snapshot,
    }
    if warnings:
        check["warnings"] = warnings
    return check


def _build_profile_verify_warnings(
    profile_verify_data: dict[str, Any],
    *,
    profile_ok: bool,
) -> list[str]:
    """Return concise plain-health warnings for active-profile verification."""
    warnings: list[str] = []
    reboot_reasons = list(profile_verify_data.get("reboot_reasons") or [])
    if profile_verify_data.get("reboot_pending"):
        reason_text = ", ".join(str(reason) for reason in reboot_reasons) or "unknown"
        warnings.append(f"active profile is reboot pending: {reason_text}")

    pending_apply = list(profile_verify_data.get("pending_apply_settings") or [])
    if pending_apply:
        warnings.append("active profile has pending apply settings: " + ", ".join(pending_apply))

    pending_reboot = list(profile_verify_data.get("pending_reboot_gated_settings") or [])
    if pending_reboot:
        warnings.append(
            "active profile has reboot-gated pending settings: " + ", ".join(pending_reboot)
        )

    for step in get_pending_manual_steps(profile_verify_data.get("manual_steps")):
        warnings.append("manual setup needed: " + format_manual_step(step))

    if not profile_ok and not warnings:
        warnings.append("active profile verification is not fully active")
    return warnings


def build_health_report(
    root_dir: Path,
    backups_dir: Path,
    state_file: Path,
    *,
    include_verify_details: bool = False,
    include_backup_details: bool = False,
) -> dict[str, Any]:
    """Build a structured diagnostics snapshot."""
    generated_at = datetime.now().isoformat()
    checks: dict[str, Any] = {}

    try:
        startup_status = get_startup_status()
        checks["tray_startup"] = _build_tray_startup_check(startup_status)
    except Exception as e:
        checks["tray_startup"] = {"status": "error", "error": str(e)}

    try:
        tray_runtime = ensure_tray_running(start_if_missing=False)
        checks["tray_runtime"] = {
            "status": "ok" if tray_runtime.get("running_after") else "warning",
            "data": tray_runtime,
        }
        checks["tray_runtime_marker"] = _build_tray_runtime_marker_check(
            root_dir,
            tray_runtime,
        )
    except Exception as e:
        checks["tray_runtime"] = {"status": "error", "error": str(e)}
        checks["tray_runtime_marker"] = {"status": "error", "error": str(e)}

    state_data: dict[str, Any] | None = None
    try:
        if state_file.exists():
            state_data = json.loads(state_file.read_text(encoding="utf-8"))
            checks["state_file"] = {"status": "ok", "data": state_data}
        else:
            checks["state_file"] = {"status": "warning", "error": "State file not found"}
    except Exception as e:
        checks["state_file"] = {"status": "error", "error": str(e)}

    checks["backups"] = _build_backups_check(
        backups_dir,
        include_recent=include_backup_details,
    )

    try:
        config_manager = ConfigManager()
        config_warnings = config_manager.validate()
        checks["config"] = {
            "status": "ok" if not config_warnings else "warning",
            "data": {"warnings": config_warnings},
        }
    except Exception as e:
        checks["config"] = {"status": "error", "error": str(e)}

    current_profile = state_data.get("current_profile") if state_data else None
    try:
        if current_profile:
            from abso.core.applier import ProfileApplier

            verify_result = ProfileApplier().verify_profile(str(current_profile))
            updated_state, cleared_reboot_pending = reconcile_reboot_pending_after_verified_boot(
                state_data,
                verify_result,
                boot_time=get_system_boot_time(),
            )
            if cleared_reboot_pending:
                mirror_warnings = _write_reconciled_state_targets(state_file, updated_state)
                state_data = updated_state
                checks["state_file"] = {
                    "status": "warning" if mirror_warnings else "ok",
                    "data": state_data,
                }
                if mirror_warnings:
                    checks["state_file"]["mirror_warnings"] = mirror_warnings

            reboot_pending = bool(state_data.get("reboot_pending")) if state_data else False
            verification_summary = summarize_profile_verification(
                str(current_profile),
                verify_result,
            )
            profile_ok = (
                bool(verification_summary.get("all_active"))
                and not reboot_pending
                and not verification_summary.get("pending_apply_settings")
                and not verification_summary.get("pending_reboot_gated_settings")
                and not get_pending_manual_steps(verification_summary.get("manual_steps"))
            )
            profile_verify_data = {
                "profile": current_profile,
                "all_active": bool(verification_summary.get("all_active")),
                "verification_status": verification_summary.get("status"),
                "manual_steps": list(verification_summary.get("manual_steps") or []),
                "reboot_pending": reboot_pending,
                "reboot_reasons": (
                    list(state_data.get("reboot_reasons") or []) if state_data else []
                ),
                "pending_apply_settings": list(
                    verification_summary.get("pending_apply_settings") or []
                ),
                "pending_reboot_gated_settings": list(
                    verification_summary.get("pending_reboot_gated_settings") or []
                ),
                "verification_summary": verification_summary,
                "verify_detail_included": include_verify_details,
                "verify_detail_command": "abso state --json --verify",
            }
            if include_verify_details:
                profile_verify_data["verify"] = verify_result

            profile_warnings = _build_profile_verify_warnings(
                profile_verify_data,
                profile_ok=profile_ok,
            )
            profile_check: dict[str, Any] = {
                "status": "ok" if profile_ok else "warning",
                "data": profile_verify_data,
            }
            if profile_warnings:
                profile_check["warnings"] = profile_warnings
            checks["profile_verify"] = profile_check
        else:
            checks["profile_verify"] = {
                "status": "warning",
                "error": "No current profile recorded",
            }
    except Exception as e:
        checks["profile_verify"] = {"status": "warning", "error": str(e)}

    try:
        fallback_rows = FallbackController().list_all()
        checks["fallback"] = {
            "status": "ok" if not fallback_rows else "warning",
            "data": {"tracked_executables": len(fallback_rows), "entries": fallback_rows},
        }
    except Exception as e:
        checks["fallback"] = {"status": "error", "error": str(e)}

    checks["display_events"] = _build_display_events_check()
    display_events_data = checks["display_events"].get("data")
    checks["display_stability"] = _build_display_stability_check(
        state_data,
        display_events=display_events_data if isinstance(display_events_data, dict) else {},
    )

    status_counts = {"ok": 0, "warning": 0, "error": 0}
    for check in checks.values():
        status = check.get("status", "error")
        if status not in status_counts:
            status = "error"
        status_counts[status] += 1

    return {
        "generated_at": generated_at,
        "root_dir": str(root_dir),
        "backups_dir": str(backups_dir),
        "state_file": str(state_file),
        "current_profile": current_profile,
        "checks": checks,
        "summary": status_counts,
    }


def write_health_bundle(report: dict[str, Any], output_dir: Path) -> Path:
    """Write diagnostics report and logs to a zipped bundle."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_root = output_dir / f"abso_health_{stamp}"
    bundle_root.mkdir(parents=True, exist_ok=True)

    report_path = bundle_root / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    temp_dir = Path(tempfile.gettempdir())
    log_candidates = [
        temp_dir / "abso_tray.log",
        temp_dir / "abso_tray_startup.log",
    ]
    logs_dir = bundle_root / "logs"
    copied_any = False
    for log_path in log_candidates:
        if not log_path.exists():
            continue
        logs_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log_path, logs_dir / log_path.name)
        copied_any = True
    if not copied_any:
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "README.txt").write_text(
            "No tray logs were found in temp directory.", encoding="utf-8"
        )

    archive_path = Path(shutil.make_archive(str(bundle_root), "zip", root_dir=bundle_root))
    return archive_path
