"""Small backup command actions shared by CLI and future frontends."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from abso.core.backup import BackupManager


def _manager(backups_dir: Path) -> BackupManager:
    backups_dir.mkdir(parents=True, exist_ok=True)
    return BackupManager(backups_dir)


def list_backup_payloads(backups_dir: Path) -> list[dict[str, Any]]:
    """Return all known backup manifests, newest first."""

    return _manager(backups_dir).list_backups()


def create_manual_backup_payload(
    backups_dir: Path,
    *,
    current_profile: str | None,
    now_factory: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    """Create a manual backup and return its manifest-style payload."""

    backup_manager = _manager(backups_dir)
    backup_id = backup_manager.create_backup(
        profile_id=current_profile,
        backup_type="manual",
    )
    return next(
        (item for item in backup_manager.list_backups() if item["id"] == backup_id),
        {"id": backup_id, "created_at": now_factory().isoformat(), "components": []},
    )


def delete_backup_payload(backups_dir: Path, backup_id: str) -> dict[str, Any]:
    """Delete a backup and return a small command payload."""

    _manager(backups_dir).delete_backup(backup_id)
    return {"success": True, "backup_id": backup_id}


def prune_backup_payload(backups_dir: Path, *, keep: int) -> dict[str, Any]:
    """Prune backups and return counts using the pre-prune list as baseline."""

    backup_manager = _manager(backups_dir)
    existing = backup_manager.list_backups()
    deleted = backup_manager.prune(max_backups=keep)
    return {
        "kept": keep,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "remaining": len(existing) - len(deleted),
    }
