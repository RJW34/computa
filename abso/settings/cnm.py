"""Deprecated CNM (Celio's Network Machine) settings handler.

CNM used to be managed by ABSO as a local relay bridge. That bridge is now
retired, so the handler remains only as a compatibility shim for existing
profiles, configs, and backups. It never starts, stops, audits, or restores CNM.
"""

from __future__ import annotations

from typing import Any

from abso.settings.base import SettingsHandler


class CNMSettingsHandler(SettingsHandler):
    """Compatibility shim for the retired CNM bridge."""

    def __init__(self) -> None:
        self._deprecated = True

    def detect(self) -> dict[str, Any]:
        """Report CNM as intentionally unavailable."""
        return {
            "installed": False,
            "deprecated": True,
            "server_running": False,
            "server_pid": None,
            "tray_running": False,
            "tray_pid": None,
            "task_enabled": False,
            "is_active": False,
        }

    def audit(self) -> list[Any]:
        """CNM is deprecated, so ABSO no longer audits it."""
        return []

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Ignore CNM settings because the bridge is retired."""
        return {
            "success": True,
            "skipped": True,
            "message": "CNM bridge is deprecated; ABSO does not manage it",
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current CNM state."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Do not restore deprecated CNM state."""
        return True
