"""Memory management settings handler."""

from __future__ import annotations

import logging
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class MemorySettingsHandler(SettingsHandler):
    """Handles memory management optimization settings.

    Manages:
    - Large System Cache - Optimizes for file server vs applications
    - Disable Paging Executive - Keeps kernel code in RAM
    - Clear Page File at Shutdown - Security/privacy setting

    Registry path:
    HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Memory Management

    Technical notes:
    - LargeSystemCache: 0 = optimize for applications (gaming), 1 = optimize for file server
    - DisablePagingExecutive: 1 = keep kernel in RAM (requires sufficient RAM)
    - ClearPageFileAtShutdown: 1 = clear pagefile on shutdown (security, minor perf impact)
    """

    # Registry paths
    MEMORY_MGMT_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"

    def detect(self) -> dict[str, Any]:
        """Detect current memory management settings."""
        return {
            "large_system_cache": self._get_large_system_cache(),
            "disable_paging_executive": self._get_disable_paging_executive(),
            "clear_page_file_at_shutdown": self._get_clear_page_file_at_shutdown(),
        }

    def audit(self) -> list[Issue]:
        """Audit memory management settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check Large System Cache (should be 0 for gaming)
        large_cache = current.get("large_system_cache")
        if large_cache is not None and large_cache != 0:
            issues.append(Issue(
                title="Large System Cache is enabled",
                severity="info",
                current_value="Enabled (file server mode)",
                optimal_value="Disabled (application mode)",
                explanation=(
                    "LargeSystemCache optimizes memory for file server workloads. "
                    "Setting to 0 optimizes for applications/games, giving more RAM to processes."
                ),
                category="memory",
            ))

        # Check Disable Paging Executive (optional, for systems with enough RAM)
        disable_paging = current.get("disable_paging_executive")
        if disable_paging is None or disable_paging != 1:
            issues.append(Issue(
                title="Kernel paging is enabled",
                severity="info",
                current_value="Enabled (kernel can be paged to disk)",
                optimal_value="Disabled (keep kernel in RAM)",
                explanation=(
                    "DisablePagingExecutive keeps Windows kernel code in RAM instead of "
                    "allowing it to be paged to disk. Reduces latency on systems with 16GB+ RAM."
                ),
                category="memory",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply memory management settings."""
        errors: list[str] = []
        requires_reboot = False

        try:
            if "large_system_cache" in settings:
                self._set_large_system_cache(settings["large_system_cache"])
                requires_reboot = True

            if "disable_paging_executive" in settings:
                self._set_disable_paging_executive(settings["disable_paging_executive"])
                requires_reboot = True

            if "clear_page_file_at_shutdown" in settings:
                self._set_clear_page_file_at_shutdown(settings["clear_page_file_at_shutdown"])

        except PermissionError as e:
            errors.append(f"Permission denied (requires admin): {e}")
        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": requires_reboot,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current memory management settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore memory management settings from backup."""
        try:
            if "large_system_cache" in data and data["large_system_cache"] is not None:
                self._set_large_system_cache(data["large_system_cache"])
            if "disable_paging_executive" in data and data["disable_paging_executive"] is not None:
                self._set_disable_paging_executive(data["disable_paging_executive"])
            if "clear_page_file_at_shutdown" in data and data["clear_page_file_at_shutdown"] is not None:
                self._set_clear_page_file_at_shutdown(data["clear_page_file_at_shutdown"])
            return True
        except Exception as e:
            logger.error(f"Failed to restore memory management settings: {e}")
            return False

    # Private helper methods

    def _get_large_system_cache(self) -> int | None:
        """Get LargeSystemCache value."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MEMORY_MGMT_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "LargeSystemCache")[0]
                return value
            except FileNotFoundError:
                return 0  # Default is 0 on desktop Windows
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get LargeSystemCache: {e}")
            return None

    def _set_large_system_cache(self, value: int) -> None:
        """Set LargeSystemCache value."""
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            self.MEMORY_MGMT_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "LargeSystemCache", 0, winreg.REG_DWORD, value)
        finally:
            winreg.CloseKey(key)

    def _get_disable_paging_executive(self) -> int | None:
        """Get DisablePagingExecutive value."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MEMORY_MGMT_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "DisablePagingExecutive")[0]
                return value
            except FileNotFoundError:
                return 0  # Default is 0 (paging enabled)
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get DisablePagingExecutive: {e}")
            return None

    def _set_disable_paging_executive(self, value: int) -> None:
        """Set DisablePagingExecutive value."""
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            self.MEMORY_MGMT_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "DisablePagingExecutive", 0, winreg.REG_DWORD, value)
        finally:
            winreg.CloseKey(key)

    def _get_clear_page_file_at_shutdown(self) -> int | None:
        """Get ClearPageFileAtShutdown value."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MEMORY_MGMT_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "ClearPageFileAtShutdown")[0]
                return value
            except FileNotFoundError:
                return 0  # Default is 0 (don't clear)
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get ClearPageFileAtShutdown: {e}")
            return None

    def _set_clear_page_file_at_shutdown(self, value: int) -> None:
        """Set ClearPageFileAtShutdown value."""
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            self.MEMORY_MGMT_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "ClearPageFileAtShutdown", 0, winreg.REG_DWORD, value)
        finally:
            winreg.CloseKey(key)
