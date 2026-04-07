"""Health diagnostics and bundle generation."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from abso.core.backup import BackupManager
from abso.core.config import ConfigManager
from abso.core.fallback_controller import FallbackController
from abso.tray import ensure_tray_running, get_startup_status


def build_health_report(
    root_dir: Path,
    backups_dir: Path,
    state_file: Path,
) -> dict[str, Any]:
    """Build a structured diagnostics snapshot."""
    generated_at = datetime.now().isoformat()
    checks: dict[str, Any] = {}

    try:
        startup_status = get_startup_status()
        startup_ok = bool(startup_status.get("installed"))
        if startup_status.get("mode") == "scheduled_task":
            startup_ok = startup_ok and bool(startup_status.get("task_highest", True))
        checks["tray_startup"] = {
            "status": "ok" if startup_ok else "warning",
            "data": startup_status,
        }
    except Exception as e:
        checks["tray_startup"] = {"status": "error", "error": str(e)}

    try:
        tray_runtime = ensure_tray_running(start_if_missing=False)
        checks["tray_runtime"] = {
            "status": "ok" if tray_runtime.get("running_after") else "warning",
            "data": tray_runtime,
        }
    except Exception as e:
        checks["tray_runtime"] = {"status": "error", "error": str(e)}

    state_data: dict[str, Any] | None = None
    try:
        if state_file.exists():
            state_data = json.loads(state_file.read_text(encoding="utf-8"))
            checks["state_file"] = {"status": "ok", "data": state_data}
        else:
            checks["state_file"] = {"status": "warning", "error": "State file not found"}
    except Exception as e:
        checks["state_file"] = {"status": "error", "error": str(e)}

    try:
        backup_manager = BackupManager(backups_dir)
        backup_list = backup_manager.list_backups()
        checks["backups"] = {
            "status": "ok" if backup_list else "warning",
            "data": {"count": len(backup_list), "recent": backup_list[:5]},
        }
    except Exception as e:
        checks["backups"] = {"status": "error", "error": str(e)}

    try:
        config_manager = ConfigManager()
        config_warnings = config_manager.validate()
        checks["config"] = {
            "status": "ok" if not config_warnings else "warning",
            "data": {"warnings": config_warnings},
        }
    except Exception as e:
        checks["config"] = {"status": "error", "error": str(e)}

    try:
        fallback_rows = FallbackController().list_all()
        checks["fallback"] = {
            "status": "ok" if not fallback_rows else "warning",
            "data": {"tracked_executables": len(fallback_rows), "entries": fallback_rows},
        }
    except Exception as e:
        checks["fallback"] = {"status": "error", "error": str(e)}

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
        "current_profile": state_data.get("current_profile") if state_data else None,
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
        (logs_dir / "README.txt").write_text("No tray logs were found in temp directory.", encoding="utf-8")

    archive_path = Path(shutil.make_archive(str(bundle_root), "zip", root_dir=bundle_root))
    return archive_path
