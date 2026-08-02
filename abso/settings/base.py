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

    # The backup scan runs handlers concurrently on worker threads. Handlers
    # whose backup() reaches COM/WMI must set this True so the scan keeps them
    # on the main thread: WMI proxies created inside a worker apartment leak a
    # release-after-CoUninitialize warning at interpreter shutdown.
    backup_requires_main_thread: bool = False

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

    @property
    def is_critical_verify(self) -> bool:
        """Whether post-apply verify mismatches must escalate to CRITICAL.

        Handlers that touch system-wide state where a divergence between
        the desired and observed value indicates a genuine apply failure
        (Windows core, NVIDIA driver, power plan, network/registry, mouse,
        graphics, process priority, the per-game config handlers) override
        this to True. Detect-only and best-effort handlers leave the
        default — their verify mismatches surface as WARNING, not CRITICAL.

        ABSO's ComplianceEngine reads this property instead of carrying a
        hardcoded class-name set so handler renames don't quietly downgrade
        criticality.
        """
        return False

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
