"""Standby list management settings handler.

ISLC (Intelligent Standby List Cleaner) equivalent for purging the Windows
standby page list to reclaim memory during gaming sessions.  Uses
NtSetSystemInformation via ctypes -- requires admin privileges and
SeProfileSingleProcessPrivilege.

Includes StandbyListHandler for one-shot detect/audit/apply and
StandbyListMonitor for continuous background purging while a game runs.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from typing import Any

from abso.core.models import EvidenceTier, Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Win32 structures
# ---------------------------------------------------------------------------


class MEMORYSTATUSEX(ctypes.Structure):
    """Win32 MEMORYSTATUSEX structure for GlobalMemoryStatusEx."""

    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# NtSetSystemInformation class
_SYSTEM_MEMORY_LIST_INFORMATION = 80

# Memory list commands
_MEMORY_PURGE_STANDBY_LIST = 4
_MEMORY_PURGE_LOW_PRIORITY_STANDBY_LIST = 5

# Privilege index for RtlAdjustPrivilege
_SE_PROF_SINGLE_PROCESS_PRIVILEGE = 13

# Thresholds
_LOW_AVAILABLE_MB = 2048  # 2 GB — audit warning threshold


# ---------------------------------------------------------------------------
# StandbyListHandler
# ---------------------------------------------------------------------------


class StandbyListHandler(SettingsHandler):
    """Manages Windows standby page list purging.

    Equivalent to ISLC: when available memory drops below a threshold the
    standby list is flushed so the pages become truly free.  This prevents
    stutters caused by the memory manager reclaiming standby pages under
    pressure during a game.

    Requires administrator privileges.  All methods degrade gracefully when
    the required NT APIs are unavailable.
    """

    def __init__(self) -> None:
        """Initialize standby list handler and load NT APIs."""
        self._ntdll: ctypes.WinDLL | None = None
        self._kernel32: ctypes.WinDLL | None = None
        self._privilege_enabled: bool = False
        self._load_apis()

    # -- internal helpers ---------------------------------------------------

    def _load_apis(self) -> bool:
        """Load ntdll.dll and kernel32.dll.

        Returns:
            True if both DLLs were loaded successfully.
        """
        try:
            self._ntdll = ctypes.WinDLL("ntdll")
            self._kernel32 = ctypes.WinDLL("kernel32")
            return True
        except Exception as e:
            logger.error("Failed to load system DLLs: %s", e)
            self._ntdll = None
            self._kernel32 = None
            return False

    def _enable_privilege(self) -> bool:
        """Enable SeProfileSingleProcessPrivilege via RtlAdjustPrivilege.

        This privilege is required for NtSetSystemInformation to accept
        memory-list commands.  Must be running as administrator.

        Returns:
            True if the privilege was enabled (or was already enabled).
        """
        if self._privilege_enabled:
            return True

        if not self._ntdll:
            logger.warning("Cannot enable privilege: ntdll not loaded")
            return False

        try:
            old = ctypes.c_bool()
            status = self._ntdll.RtlAdjustPrivilege(
                ctypes.c_ulong(_SE_PROF_SINGLE_PROCESS_PRIVILEGE),
                ctypes.c_bool(True),   # Enable
                ctypes.c_bool(False),  # Not thread-only
                ctypes.byref(old),
            )
            if status == 0:
                self._privilege_enabled = True
                logger.debug("SeProfileSingleProcessPrivilege enabled")
                return True

            logger.warning(
                "RtlAdjustPrivilege failed with NTSTATUS 0x%08X — "
                "are you running as administrator?",
                status & 0xFFFFFFFF,
            )
            return False
        except Exception as e:
            logger.error("Failed to enable privilege: %s", e)
            return False

    def _get_memory_status(self) -> MEMORYSTATUSEX | None:
        """Query system memory via GlobalMemoryStatusEx.

        Returns:
            Populated MEMORYSTATUSEX structure, or None on failure.
        """
        if not self._kernel32:
            return None

        try:
            mem = MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if self._kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                return mem
            logger.warning("GlobalMemoryStatusEx returned False")
            return None
        except Exception as e:
            logger.error("Failed to query memory status: %s", e)
            return None

    @staticmethod
    def _bytes_to_mb(b: int) -> int:
        """Convert bytes to whole megabytes."""
        return int(b / (1024 * 1024))

    # -- public purge methods -----------------------------------------------

    def clear_standby_list(self) -> bool:
        """Purge the entire standby page list.

        Equivalent to ISLC's "Purge Standby List" button.

        Returns:
            True if the purge succeeded.
        """
        if not self._ntdll:
            logger.error("Cannot purge standby list: ntdll not loaded")
            return False

        if not self._enable_privilege():
            return False

        try:
            command = ctypes.c_int(_MEMORY_PURGE_STANDBY_LIST)
            status = self._ntdll.NtSetSystemInformation(
                _SYSTEM_MEMORY_LIST_INFORMATION,
                ctypes.byref(command),
                ctypes.sizeof(command),
            )
            if status == 0:
                logger.info("Standby list purged successfully")
                return True

            logger.warning(
                "NtSetSystemInformation (purge standby) returned NTSTATUS 0x%08X",
                status & 0xFFFFFFFF,
            )
            return False
        except Exception as e:
            logger.error("Failed to purge standby list: %s", e)
            return False

    def clear_low_priority_standby(self) -> bool:
        """Purge only the low-priority standby page list.

        Less aggressive than a full purge — only reclaims pages that Windows
        has already deprioritised.

        Returns:
            True if the purge succeeded.
        """
        if not self._ntdll:
            logger.error("Cannot purge low-priority standby: ntdll not loaded")
            return False

        if not self._enable_privilege():
            return False

        try:
            command = ctypes.c_int(_MEMORY_PURGE_LOW_PRIORITY_STANDBY_LIST)
            status = self._ntdll.NtSetSystemInformation(
                _SYSTEM_MEMORY_LIST_INFORMATION,
                ctypes.byref(command),
                ctypes.sizeof(command),
            )
            if status == 0:
                logger.info("Low-priority standby list purged successfully")
                return True

            logger.warning(
                "NtSetSystemInformation (purge low-priority) returned NTSTATUS 0x%08X",
                status & 0xFFFFFFFF,
            )
            return False
        except Exception as e:
            logger.error("Failed to purge low-priority standby list: %s", e)
            return False

    # -- SettingsHandler interface ------------------------------------------

    def detect(self) -> dict[str, Any]:
        """Detect current system memory state.

        Returns:
            Dictionary with total_mb, available_mb, and memory_load_percent.
        """
        result: dict[str, Any] = {
            "total_mb": 0,
            "available_mb": 0,
            "memory_load_percent": 0,
        }

        mem = self._get_memory_status()
        if mem is None:
            return result

        result["total_mb"] = self._bytes_to_mb(mem.ullTotalPhys)
        result["available_mb"] = self._bytes_to_mb(mem.ullAvailPhys)
        result["memory_load_percent"] = mem.dwMemoryLoad
        return result

    def audit(self) -> list[Issue]:
        """Audit memory for low-available-memory conditions.

        Returns:
            List of issues found.  An info-level issue is raised when
            available memory is below 2 GB.
        """
        issues: list[Issue] = []

        mem = self._get_memory_status()
        if mem is None:
            issues.append(Issue(
                title="Memory status unavailable",
                severity="warning",
                current_value="Unknown",
                optimal_value="Known",
                explanation=(
                    "Could not query system memory via GlobalMemoryStatusEx. "
                    "Standby list management will not function."
                ),
                category="memory",
                evidence_tier=EvidenceTier.VERIFIED,
            ))
            return issues

        available_mb = self._bytes_to_mb(mem.ullAvailPhys)
        total_mb = self._bytes_to_mb(mem.ullTotalPhys)

        if available_mb < _LOW_AVAILABLE_MB:
            issues.append(Issue(
                title="Low available memory — standby list may need purging",
                severity="info",
                current_value=f"{available_mb} MB available of {total_mb} MB",
                optimal_value=f">= {_LOW_AVAILABLE_MB} MB available",
                explanation=(
                    "Available memory (free + standby) is below 2 GB. "
                    "The standby list may be consuming reclaimable pages that "
                    "could cause stutters when a game allocates memory.  "
                    "Running a standby list purge can reclaim this memory."
                ),
                category="memory",
                evidence_tier=EvidenceTier.EMPIRICAL,
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply standby list settings (purge on demand).

        Args:
            settings: Dictionary with optional keys:
                - clear_on_apply (bool): Purge the standby list now.
                  Defaults to True.

        Returns:
            Result dict with success status.
        """
        clear_on_apply: bool = settings.get("clear_on_apply", True)

        if not clear_on_apply:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
            }

        success = self.clear_standby_list()

        stats = self.detect()
        return {
            "success": success,
            "error": None if success else "Failed to purge standby list (admin required)",
            "requires_reboot": False,
            "available_mb_after": stats.get("available_mb"),
        }

    def backup(self) -> dict[str, Any]:
        """Backup current memory state (informational only).

        Returns:
            Dictionary with current memory stats.  Standby list state
            cannot be meaningfully backed up.
        """
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore standby list state (no-op).

        Memory state is transient and cannot be restored.  Always succeeds.

        Args:
            data: Previously backed-up memory stats (ignored).

        Returns:
            Always True.
        """
        return True


# ---------------------------------------------------------------------------
# StandbyListMonitor — background thread that polls and purges
# ---------------------------------------------------------------------------


class StandbyListMonitor:
    """Background monitor that periodically purges the standby list.

    Equivalent to running ISLC in the background with a configured free-
    memory threshold and poll interval.

    Usage::

        monitor = StandbyListMonitor(free_threshold_mb=1024, poll_interval_ms=1000)
        monitor.start()
        # ... game runs ...
        monitor.stop()
    """

    def __init__(
        self,
        threshold_mb: int = 1024,
        free_threshold_mb: int = 1024,
        poll_interval_ms: int = 1000,
    ) -> None:
        """Initialize the standby list monitor.

        Args:
            threshold_mb: Legacy alias for free_threshold_mb (kept for
                backward compatibility).
            free_threshold_mb: When available memory drops below this value
                (in MB) the standby list is purged.
            poll_interval_ms: How often to check memory, in milliseconds.
        """
        self._handler = StandbyListHandler()
        self._threshold_mb = threshold_mb
        self._free_threshold_mb = free_threshold_mb
        self._poll_interval: float = poll_interval_ms / 1000.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._purge_count: int = 0
        self._lock = threading.Lock()

    @property
    def purge_count(self) -> int:
        """Number of purges performed since the monitor was started."""
        return self._purge_count

    @property
    def is_running(self) -> bool:
        """Whether the monitor thread is currently running."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start background monitoring in a daemon thread.

        If the monitor is already running this is a no-op.
        """
        with self._lock:
            if self.is_running:
                logger.warning("StandbyListMonitor is already running")
                return

            self._stop_event.clear()
            self._purge_count = 0
            self._thread = threading.Thread(
                target=self._poll_loop,
                name="abso-standby-monitor",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "StandbyListMonitor started (threshold=%d MB, interval=%d ms)",
                self._free_threshold_mb,
                int(self._poll_interval * 1000),
            )

    def stop(self) -> None:
        """Signal the monitor to stop and wait for the thread to exit."""
        with self._lock:
            if self._thread is None:
                return

            self._stop_event.set()
            self._thread.join(timeout=self._poll_interval + 2.0)

            if self._thread.is_alive():
                logger.warning("StandbyListMonitor thread did not exit cleanly")
            else:
                logger.info(
                    "StandbyListMonitor stopped after %d purges",
                    self._purge_count,
                )

            self._thread = None

    def _poll_loop(self) -> None:
        """Main poll loop: check memory stats, purge if threshold hit."""
        while not self._stop_event.is_set():
            try:
                stats = self._handler.detect()
                available_mb: int = stats.get("available_mb", 0)

                if available_mb > 0 and available_mb < self._free_threshold_mb:
                    logger.debug(
                        "Available memory %d MB < threshold %d MB — purging standby list",
                        available_mb,
                        self._free_threshold_mb,
                    )
                    if self._handler.clear_standby_list():
                        self._purge_count += 1
            except Exception as e:
                logger.error("StandbyListMonitor poll error: %s", e)

            self._stop_event.wait(self._poll_interval)
