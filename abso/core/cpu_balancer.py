"""ProBalance-style CPU priority balancer.

Monitors system CPU usage during game sessions and temporarily lowers
background process priority when the game is being starved. All APIs
are standard Win32 via ctypes -- no kernel driver required.

Designed to be launched as a subprocess by the tray app::

    python -m abso.core.cpu_balancer --pid 12345
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Win32 priority class constants
# ---------------------------------------------------------------------------
IDLE_PRIORITY_CLASS = 0x00000040
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
NORMAL_PRIORITY_CLASS = 0x00000020
ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
HIGH_PRIORITY_CLASS = 0x00000080
REALTIME_PRIORITY_CLASS = 0x00000100

# Process access rights
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_SET_INFORMATION = 0x0200

# Snapshot flags
TH32CS_SNAPPROCESS = 0x00000002


# ---------------------------------------------------------------------------
# Win32 structures
# ---------------------------------------------------------------------------

class PROCESSENTRY32W(ctypes.Structure):
    """Win32 PROCESSENTRY32W for CreateToolhelp32Snapshot enumeration."""

    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class FILETIME(ctypes.Structure):
    """Win32 FILETIME (100-nanosecond intervals since 1601-01-01)."""

    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]

    def to_int(self) -> int:
        return (self.dwHighDateTime << 32) | self.dwLowDateTime


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RestrainedProcess:
    """Tracks a background process whose priority has been temporarily lowered."""

    pid: int
    name: str
    original_priority: int
    restrained_at: float  # time.monotonic()
    cpu_percent: float


@dataclass
class BalancerEvent:
    """Audit log entry for a restrain or release action."""

    timestamp: float
    action: str  # "restrain" or "release"
    pid: int
    process_name: str
    cpu_percent: float


@dataclass
class CpuBalancerConfig:
    """Tunable thresholds for the CPU balancer."""

    system_cpu_threshold: int = 85
    """System-wide CPU % that triggers background scanning."""

    process_cpu_threshold: int = 20
    """Per-process CPU % above which a background process is restrained."""

    trigger_delay_ms: int = 2800
    """How long system CPU must stay above threshold before we act."""

    restraint_duration_ms: int = 6000
    """Minimum time a process stays at lowered priority."""

    poll_interval_ms: int = 1000
    """How often the balancer polls CPU usage."""

    excluded_processes: list[str] = field(default_factory=lambda: [
        "csrss.exe",
        "dwm.exe",
        "audiodg.exe",
        "system",
        "svchost.exe",
        "wininit.exe",
        "services.exe",
        "smss.exe",
        "lsass.exe",
        "winlogon.exe",
        "registry",
        "idle",
    ])
    """Processes that must never be restrained (critical OS components)."""


# ---------------------------------------------------------------------------
# CpuBalancer
# ---------------------------------------------------------------------------

class CpuBalancer:
    """ProBalance-style real-time CPU priority intervention.

    Monitors system CPU usage and, when sustained high usage is detected,
    identifies background processes consuming significant CPU time and
    temporarily lowers their priority to ``BELOW_NORMAL_PRIORITY_CLASS``.
    Priorities are restored once the process calms down or the restraint
    duration elapses.

    Args:
        game_pid: The PID of the protected game process.
        config: Optional tuning parameters.
    """

    def __init__(self, game_pid: int, config: CpuBalancerConfig | None = None) -> None:
        self._game_pid = game_pid
        self._config = config or CpuBalancerConfig()
        self._restrained: dict[int, RestrainedProcess] = {}
        self._events: list[BalancerEvent] = []
        self._stop_event = threading.Event()
        self._high_cpu_since: float | None = None

        # CPU time tracking
        self._last_system_times: tuple[int, int, int] | None = None  # idle, kernel, user
        self._last_process_times: dict[int, tuple[int, int]] = {}  # pid -> (kernel, user)

        self._kernel32 = ctypes.WinDLL("kernel32")
        self._user32 = ctypes.WinDLL("user32")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the balancer loop (blocking). Call from main thread or a thread."""
        logger.info("CPU Balancer started for game PID %d", self._game_pid)
        try:
            while not self._stop_event.is_set():
                if not self._is_game_running():
                    logger.info("Game PID %d exited, stopping balancer", self._game_pid)
                    break
                self._poll_once()
                self._stop_event.wait(self._config.poll_interval_ms / 1000.0)
        finally:
            self._release_all()
            logger.info("CPU Balancer stopped. %d events logged.", len(self._events))

    def stop(self) -> None:
        """Signal the balancer loop to exit."""
        self._stop_event.set()

    def get_events(self) -> list[BalancerEvent]:
        """Return a copy of all restrain/release events."""
        return list(self._events)

    # ------------------------------------------------------------------
    # Core polling logic
    # ------------------------------------------------------------------

    def _poll_once(self) -> None:
        """Single poll iteration."""
        system_cpu = self._get_system_cpu()
        if system_cpu is None:
            return

        now = time.monotonic()

        # Check if system CPU is above threshold
        if system_cpu >= self._config.system_cpu_threshold:
            if self._high_cpu_since is None:
                self._high_cpu_since = now
            elif (now - self._high_cpu_since) * 1000 >= self._config.trigger_delay_ms:
                # Sustained high CPU -- find offenders
                self._find_and_restrain_offenders()
        else:
            self._high_cpu_since = None

        # Check if restrained processes can be released
        self._check_releases(now)

    # ------------------------------------------------------------------
    # System-wide CPU measurement
    # ------------------------------------------------------------------

    def _get_system_cpu(self) -> float | None:
        """Get system-wide CPU usage percentage via ``GetSystemTimes``."""
        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if not self._kernel32.GetSystemTimes(
            ctypes.byref(idle),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None

        idle_val = idle.to_int()
        kern_val = kernel.to_int()
        user_val = user.to_int()

        if self._last_system_times is None:
            self._last_system_times = (idle_val, kern_val, user_val)
            return None

        prev_idle, prev_kern, prev_user = self._last_system_times
        self._last_system_times = (idle_val, kern_val, user_val)

        idle_delta = idle_val - prev_idle
        total_delta = (kern_val - prev_kern) + (user_val - prev_user)

        if total_delta == 0:
            return 0.0

        return 100.0 * (1.0 - idle_delta / total_delta)

    # ------------------------------------------------------------------
    # Per-process CPU measurement
    # ------------------------------------------------------------------

    def _get_process_cpu(self, pid: int) -> float | None:
        """Get per-process CPU usage percentage via ``GetProcessTimes``.

        Returns an approximate CPU % relative to total system capacity
        (number of logical CPUs x elapsed wall time).
        """
        handle = self._kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creation = FILETIME()
            exit_t = FILETIME()
            kernel = FILETIME()
            user = FILETIME()
            if not self._kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_t),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None

            kern_val = kernel.to_int()
            user_val = user.to_int()
            prev = self._last_process_times.get(pid)
            self._last_process_times[pid] = (kern_val, user_val)

            if prev is None:
                return None

            prev_kern, prev_user = prev
            proc_delta = (kern_val - prev_kern) + (user_val - prev_user)

            # Approximate total available CPU time over the poll interval.
            # FILETIME units are 100-nanosecond intervals; poll_interval_ms
            # is in milliseconds (1 ms = 10_000 x 100 ns).
            num_cpus = os.cpu_count() or 1
            interval_100ns = self._config.poll_interval_ms * 10_000
            total_100ns = interval_100ns * num_cpus
            if total_100ns == 0:
                return 0.0
            return 100.0 * proc_delta / total_100ns
        finally:
            self._kernel32.CloseHandle(handle)

    # ------------------------------------------------------------------
    # Foreground / process enumeration helpers
    # ------------------------------------------------------------------

    def _get_foreground_pid(self) -> int | None:
        """Get PID of the foreground window's process."""
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value if pid.value else None

    def _enumerate_processes(self) -> list[tuple[int, str]]:
        """List all running processes via ``CreateToolhelp32Snapshot``."""
        snapshot = self._kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == -1:
            return []
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            processes: list[tuple[int, str]] = []
            if self._kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                while True:
                    processes.append((entry.th32ProcessID, entry.szExeFile))
                    if not self._kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                        break
            return processes
        finally:
            self._kernel32.CloseHandle(snapshot)

    def _is_excluded(self, name: str, pid: int) -> bool:
        """Return ``True`` if the process must not be restrained."""
        name_lower = name.lower()
        if name_lower in {p.lower() for p in self._config.excluded_processes}:
            return True
        if pid == self._game_pid:
            return True
        if pid == self._get_foreground_pid():
            return True
        if pid <= 4:  # System / Idle
            return True
        return False

    # ------------------------------------------------------------------
    # Restrain / release
    # ------------------------------------------------------------------

    def _find_and_restrain_offenders(self) -> None:
        """Find background processes using too much CPU and lower their priority."""
        for pid, name in self._enumerate_processes():
            if self._is_excluded(name, pid):
                continue
            if pid in self._restrained:
                continue

            cpu = self._get_process_cpu(pid)
            if cpu is not None and cpu >= self._config.process_cpu_threshold:
                self._restrain(pid, name, cpu)

    def _restrain(self, pid: int, name: str, cpu: float) -> None:
        """Lower a process's priority to ``BELOW_NORMAL_PRIORITY_CLASS``."""
        handle = self._kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_SET_INFORMATION, False, pid
        )
        if not handle:
            return
        try:
            original = self._kernel32.GetPriorityClass(handle)
            if original and original > BELOW_NORMAL_PRIORITY_CLASS:
                if self._kernel32.SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS):
                    self._restrained[pid] = RestrainedProcess(
                        pid=pid,
                        name=name,
                        original_priority=original,
                        restrained_at=time.monotonic(),
                        cpu_percent=cpu,
                    )
                    self._events.append(BalancerEvent(
                        timestamp=time.time(),
                        action="restrain",
                        pid=pid,
                        process_name=name,
                        cpu_percent=cpu,
                    ))
                    logger.info(
                        "Restrained %s (PID %d) from %d to BelowNormal (%.1f%% CPU)",
                        name, pid, original, cpu,
                    )
        finally:
            self._kernel32.CloseHandle(handle)

    def _check_releases(self, now: float) -> None:
        """Release restrained processes whose duration has elapsed and CPU calmed."""
        to_release: list[int] = []
        for pid, info in self._restrained.items():
            elapsed_ms = (now - info.restrained_at) * 1000
            if elapsed_ms < self._config.restraint_duration_ms:
                continue
            cpu = self._get_process_cpu(pid)
            if cpu is None:
                # Process exited
                to_release.append(pid)
            elif cpu < 10.0:
                to_release.append(pid)

        for pid in to_release:
            self._release(pid)

    def _release(self, pid: int) -> None:
        """Restore a process's original priority class."""
        info = self._restrained.pop(pid, None)
        if info is None:
            return
        handle = self._kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
        if handle:
            try:
                self._kernel32.SetPriorityClass(handle, info.original_priority)
                logger.info(
                    "Released %s (PID %d) back to priority %d",
                    info.name, pid, info.original_priority,
                )
            finally:
                self._kernel32.CloseHandle(handle)
        self._events.append(BalancerEvent(
            timestamp=time.time(),
            action="release",
            pid=pid,
            process_name=info.name,
            cpu_percent=0.0,
        ))

    def _release_all(self) -> None:
        """Release every currently restrained process."""
        for pid in list(self._restrained.keys()):
            self._release(pid)

    # ------------------------------------------------------------------
    # Game liveness check
    # ------------------------------------------------------------------

    def _is_game_running(self) -> bool:
        """Return ``True`` if the game process is still alive."""
        handle = self._kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION, False, self._game_pid
        )
        if handle:
            self._kernel32.CloseHandle(handle)
            return True
        return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Launch the CPU balancer from the command line."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="CPU Priority Balancer")
    parser.add_argument("--pid", type=int, required=True, help="Game process ID")
    parser.add_argument("--system-threshold", type=int, default=85)
    parser.add_argument("--process-threshold", type=int, default=20)
    parser.add_argument("--poll-interval", type=int, default=1000)
    args = parser.parse_args()

    config = CpuBalancerConfig(
        system_cpu_threshold=args.system_threshold,
        process_cpu_threshold=args.process_threshold,
        poll_interval_ms=args.poll_interval,
    )
    balancer = CpuBalancer(args.pid, config)

    def _shutdown(signum: int, frame: Any) -> None:
        balancer.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    balancer.run()


if __name__ == "__main__":
    main()
