"""Base settings handler interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from abso.core.models import Issue


class SettingsHandler(ABC):
    """Abstract base class for settings handlers.

    Each settings domain (Nvidia, Windows, registry, etc.) should implement
    this interface to provide consistent behavior across the application.
    """

    @abstractmethod
    def detect(self) -> dict[str, Any]:
        """Detect current state of settings.

        Returns:
            Dictionary of current settings values.
        """
        pass

    @abstractmethod
    def audit(self) -> list[Issue]:
        """Audit settings for optimization issues.

        Returns:
            List of issues found.
        """
        pass

    @abstractmethod
    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply settings from a profile.

        Args:
            settings: Dictionary of settings to apply.

        Returns:
            Result dict with 'success' bool and optional 'error', 'requires_reboot'.
        """
        pass

    @abstractmethod
    def backup(self) -> dict[str, Any]:
        """Export current settings for backup.

        Returns:
            Dictionary of settings that can be restored later.
        """
        pass

    @abstractmethod
    def restore(self, data: dict[str, Any]) -> bool:
        """Restore settings from backup data.

        Args:
            data: Previously backed up settings data.

        Returns:
            True if restore succeeded, False otherwise.
        """
        pass

    @property
    def restore_guarantee(self) -> str:
        """Describe how completely this handler can restore prior state.

        Returns:
            "full" when ABSO can restore the handler end to end,
            "partial" when restore is best-effort,
            "ephemeral" when the handler's state naturally reverts at
                process exit so there is nothing to restore (e.g. timer
                resolution via NtSetTimerResolution), or
            "none" when ABSO cannot safely promise automatic restore.

        The backup manager treats "ephemeral" and "none" as non-blocking
        when a restore summary reports them as skipped — there is no state
        to restore that the user cares about.
        """
        return "full"

    def preflight(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Validate prerequisites before apply side effects begin.

        Handlers can override this when they need to block unsafe or
        unprovable operations before ABSO creates backups or writes state.
        """
        return {
            "success": True,
            "error": None,
            "warnings": [],
            "notices": [],
        }
