"""Backup and restore system."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from abso.core.exceptions import (
    BackupCorruptedError,
    BackupNotFoundError,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

DEFAULT_MAX_BACKUPS = 20


def _get_backup_handlers() -> list[SettingsHandler]:
    """Lazily import and instantiate settings handlers for backup.

    This avoids circular import issues between core and settings modules.
    All handlers that are used for audit are also backed up to ensure
    complete restore capability.
    """
    from abso.settings.audio import AudioSettingsHandler
    from abso.settings.cnm import CNMSettingsHandler
    from abso.settings.color import ColorProfileSettingsHandler
    from abso.settings.dolphin import DolphinConfigHandler
    from abso.settings.graphics import GraphicsSettingsHandler
    from abso.settings.memory import MemorySettingsHandler
    from abso.settings.mouse import MouseSettingsHandler
    from abso.settings.network import NetworkSettingsHandler
    from abso.settings.nvidia import NvidiaSettingsHandler
    from abso.settings.nvidia_notifications import NvidiaNotificationHandler
    from abso.settings.obs import OBSSettingsHandler
    from abso.settings.power import PowerSettingsHandler
    from abso.settings.process_priority import ProcessPriorityHandler
    from abso.settings.registry import RegistrySettingsHandler
    from abso.settings.rivals2_config import Rivals2ConfigHandler
    from abso.settings.services import ServicesSettingsHandler
    from abso.settings.storage import StorageSettingsHandler
    from abso.settings.tasks import TasksSettingsHandler
    from abso.settings.timer import TimerSettingsHandler
    from abso.settings.updates import UpdatesSettingsHandler
    from abso.settings.visual import VisualSettingsHandler
    from abso.settings.windows import WindowsSettingsHandler

    return [
        # Core handlers (always needed)
        WindowsSettingsHandler(),
        PowerSettingsHandler(),
        RegistrySettingsHandler(),
        NvidiaSettingsHandler(),
        TimerSettingsHandler(),
        # Additional handlers for complete backup coverage
        MouseSettingsHandler(),
        GraphicsSettingsHandler(),
        ServicesSettingsHandler(),
        TasksSettingsHandler(),
        MemorySettingsHandler(),
        NetworkSettingsHandler(),
        VisualSettingsHandler(),
        StorageSettingsHandler(),
        AudioSettingsHandler(),
        UpdatesSettingsHandler(),
        # Profile-specific handlers (prevent settings leak between profiles)
        DolphinConfigHandler(),
        Rivals2ConfigHandler(),
        NvidiaNotificationHandler(),
        OBSSettingsHandler(),
        ProcessPriorityHandler(),
        CNMSettingsHandler(),
        ColorProfileSettingsHandler(),
    ]


class BackupManager:
    """Manages backup and restore of system settings."""

    def __init__(self, backup_dir: Path) -> None:
        """Initialize backup manager.

        Args:
            backup_dir: Directory to store backups.
        """
        self.backup_dir = backup_dir
        self._handlers = _get_backup_handlers()

    def create_backup(
        self,
        profile_id: str | None = None,
        backup_type: str = "pre_apply",
    ) -> str:
        """Create a new backup of current settings.

        Args:
            profile_id: Profile being applied (for metadata tracking).
            backup_type: Type of backup (e.g. "pre_apply", "manual").

        Returns:
            Backup ID (timestamp string).
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_path = self.backup_dir / timestamp
        backup_path.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "timestamp": timestamp,
            "created_at": datetime.now().isoformat(),
            "profile_id": profile_id,
            "backup_type": backup_type,
            "components": {},
        }

        for handler in self._handlers:
            handler_name = handler.__class__.__name__

            try:
                data = handler.backup()

                # Save component backup
                component_path = backup_path / f"{handler_name}.json"
                component_path.write_text(
                    json.dumps(data, indent=2),
                    encoding="utf-8"
                )

                manifest["components"][handler_name] = {
                    "file": f"{handler_name}.json",
                    "success": True,
                }

                logger.info(f"Backed up {handler_name}")

            except PermissionError as e:
                logger.error(f"Permission denied backing up {handler_name}: {e}")
                manifest["components"][handler_name] = {
                    "file": None,
                    "success": False,
                    "error": f"Permission denied: {e}",
                }
            except OSError as e:
                logger.error(f"OS error backing up {handler_name}: {e}")
                manifest["components"][handler_name] = {
                    "file": None,
                    "success": False,
                    "error": f"OS error: {e}",
                }
            except (ValueError, TypeError) as e:
                logger.error(f"Data error backing up {handler_name}: {e}")
                manifest["components"][handler_name] = {
                    "file": None,
                    "success": False,
                    "error": f"Data error: {e}",
                }

        # Save manifest
        manifest_path = backup_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8"
        )

        logger.info(f"Backup created: {timestamp}")
        return timestamp

    def restore_backup(self, backup_id: str) -> None:
        """Restore settings from a backup.

        Args:
            backup_id: Backup ID (timestamp) or 'latest'.

        Raises:
            FileNotFoundError: If backup not found.
        """
        if backup_id == "latest":
            backup_path = self._get_latest_backup()
        else:
            backup_path = self.backup_dir / backup_id

        if not backup_path or not backup_path.exists():
            raise BackupNotFoundError(
                f"Backup not found: {backup_id}",
                details=f"Expected path: {self.backup_dir / backup_id}"
            )

        manifest_path = backup_path / "manifest.json"
        if not manifest_path.exists():
            raise BackupCorruptedError(
                f"Backup manifest not found: {backup_id}",
                details="The backup directory exists but manifest.json is missing"
            )

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise BackupCorruptedError(
                f"Backup manifest is corrupted: {backup_id}",
                details=str(e)
            ) from e

        # Create handler lookup
        handler_map = {
            handler.__class__.__name__: handler
            for handler in self._handlers
        }

        # Restore each component
        for handler_name, component_info in manifest["components"].items():
            if not component_info.get("success", False):
                logger.warning(f"Skipping {handler_name}: was not backed up successfully")
                continue

            handler = handler_map.get(handler_name)
            if not handler:
                logger.warning(f"No handler for {handler_name}")
                continue

            try:
                component_path = backup_path / component_info["file"]
                if not component_path.exists():
                    logger.error(f"Backup file missing for {handler_name}: {component_path}")
                    continue
                data = json.loads(component_path.read_text(encoding="utf-8"))

                handler.restore(data)
                logger.info(f"Restored {handler_name}")

            except json.JSONDecodeError as e:
                logger.error(f"Corrupted backup data for {handler_name}: {e}")
            except PermissionError as e:
                logger.error(f"Permission denied restoring {handler_name}: {e}")
            except OSError as e:
                logger.error(f"OS error restoring {handler_name}: {e}")
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Data error restoring {handler_name}: {e}")

        logger.info(f"Backup restored: {backup_id}")

    def list_backups(self) -> list[dict[str, Any]]:
        """List all available backups.

        Returns:
            List of backup info dicts, newest first.
        """
        backups: list[dict[str, Any]] = []

        if not self.backup_dir.exists():
            return backups

        for backup_path in self.backup_dir.iterdir():
            if not backup_path.is_dir():
                continue

            manifest_path = backup_path / "manifest.json"
            if not manifest_path.exists():
                continue

            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                backups.append({
                    "id": backup_path.name,
                    "created_at": manifest.get("created_at", "Unknown"),
                    "components": list(manifest.get("components", {}).keys()),
                    "profile_id": manifest.get("profile_id"),
                    "backup_type": manifest.get("backup_type"),
                })
            except json.JSONDecodeError as e:
                logger.warning(f"Corrupted manifest in backup {backup_path.name}: {e}")
            except OSError as e:
                logger.warning(f"Failed to read backup {backup_path.name}: {e}")

        # Sort by ID (timestamp) descending
        backups.sort(key=lambda x: x["id"], reverse=True)

        return backups

    def get_baseline_backup(self) -> Path | None:
        """Get the most recent pre-apply backup for baseline restoration.

        Scans backups newest-first and returns the first with backup_type
        "pre_apply" or None (old backups without metadata). Falls back to
        latest if no typed backups exist.

        Returns:
            Path to baseline backup or None if no backups exist.
        """
        backups = self.list_backups()
        if not backups:
            return None

        for backup in backups:
            backup_type = backup.get("backup_type")
            if backup_type in ("pre_apply", None):
                return self.backup_dir / backup["id"]

        # All backups have non-pre_apply types; fall back to latest
        return self.backup_dir / backups[0]["id"]

    def _get_latest_backup(self) -> Path | None:
        """Get the path to the latest backup.

        Returns:
            Path to latest backup or None if no backups exist.
        """
        backups = self.list_backups()
        if not backups:
            return None

        return self.backup_dir / backups[0]["id"]

    def prune(self, max_backups: int = DEFAULT_MAX_BACKUPS) -> list[str]:
        """Delete oldest backups exceeding the retention limit.

        Args:
            max_backups: Maximum number of backups to keep.

        Returns:
            List of backup IDs that were deleted.
        """
        backups = self.list_backups()
        if len(backups) <= max_backups:
            return []

        to_delete = backups[max_backups:]  # Already sorted newest-first
        deleted: list[str] = []

        for backup in to_delete:
            backup_id = backup["id"]
            try:
                self.delete_backup(backup_id)
                deleted.append(backup_id)
            except Exception as e:
                logger.warning(f"Failed to prune backup {backup_id}: {e}")

        if deleted:
            logger.info(f"Pruned {len(deleted)} backup(s), kept {max_backups}")

        return deleted

    def delete_backup(self, backup_id: str) -> None:
        """Delete a backup.

        Args:
            backup_id: Backup ID to delete.

        Raises:
            FileNotFoundError: If backup not found.
        """
        import shutil

        backup_path = self.backup_dir / backup_id

        if not backup_path.exists():
            raise BackupNotFoundError(
                f"Backup not found: {backup_id}",
                details=f"Expected path: {backup_path}"
            )

        shutil.rmtree(backup_path)
        logger.info(f"Deleted backup: {backup_id}")
