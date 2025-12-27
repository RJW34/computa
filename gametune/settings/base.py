"""Base settings handler interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from gametune.core.models import Issue


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
    def audit(self) -> list["Issue"]:
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
