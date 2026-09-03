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
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
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

    system_cpu_threshold: int = 55
    """System-wide CPU % that triggers background scanning.

    Tuned for a high-core-count desktop (e.g. 24C/32T): the system metric is
    the aggregate across *all* logical processors, so a capped game leaves it
    low and only a genuine background spike crosses this floor. Keep in sync
    with :class:`abso.core.config.CpuBalancerConfig`.
    """

    process_cpu_threshold: int = 8
    """Per-process CPU % above which a background process is restrained.

    Normalized to *total* system capacity, so on a 32-thread box one fully
    saturated core is ~3%. 8% (~2.5 cores) catches multi-core offenders
    (shader compiles, AV scans, encoders) without demoting light single-
    threaded background apps. Tune against live measurement on the rig.
    """

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

    def __init__(
        self,
        game_pid: int,
        config: CpuBalancerConfig | None = None,
        *,
        extra_excluded: Iterable[str] | None = None,
        stop_file: str | os.PathLike[str] | None = None,
        enable_cpu_sets: bool = False,
        enable_eco: bool = False,
        eco_images: Iterable[str] | None = None,
        enable_watchdog: bool = False,
        watchdog_rules: Any = None,
        is_online: bool = False,
        watchdog_keep_cores: int = 4,
        enable_restraint: bool = True,
        steer_background_images: Iterable[str] | None = None,
        enable_auto_steer: bool = False,
        auto_steer_process_threshold: int = 4,
        auto_steer_sustain_ms: int = 5000,
        smt_avoid: bool = False,
        allow_x3d: bool = True,
        steer_journal_path: os.PathLike[str] | str | None = None,
    ) -> None:
        self._game_pid = game_pid
        self._config = config or CpuBalancerConfig()

        # Optional Tier B session behaviors (default OFF -> keystone unchanged).
        self._enable_cpu_sets = bool(enable_cpu_sets)
        self._enable_eco = bool(enable_eco)
        self._eco_images = list(eco_images or [])
        self._eco_herder: Any = None
        self._enable_watchdog = bool(enable_watchdog)
        self._watchdog_rules = list(watchdog_rules or [])
        self._is_online = bool(is_online)
        self._watchdog_keep_cores = int(watchdog_keep_cores)
        self._watchdog_engine: Any = None
        # Separate CPU-time store so the watchdog's cpu metric never double-
        # samples (and corrupts) the restraint loop's per-process deltas.
        self._watchdog_cpu_times: dict[int, tuple[int, int]] = {}

        # ProBalance restraint can be disabled (steer-only sessions) while the
        # governor still hosts the partition steerer / eco herder / watchdog.
        self._enable_restraint = bool(enable_restraint)
        # Core-partition steering (game -> fast cores, background -> the rest).
        self._steer_background_images = list(steer_background_images or [])
        self._enable_auto_steer = bool(enable_auto_steer)
        self._auto_steer_threshold = int(auto_steer_process_threshold)
        self._auto_steer_sustain_ms = int(auto_steer_sustain_ms)
        self._smt_avoid = bool(smt_avoid)
        self._allow_x3d = bool(allow_x3d)
        self._steer_journal_path = steer_journal_path
        self._steerer: Any = None
        # Auto-steer keeps its own CPU-time store (see watchdog note above)
        # plus first-seen-high timestamps for the sustain qualification.
        self._auto_steer_cpu_times: dict[int, tuple[int, int]] = {}
        self._auto_steer_high_since: dict[int, float] = {}
        self._restrained: dict[int, RestrainedProcess] = {}
        self._events: list[BalancerEvent] = []
        self._stop_event = threading.Event()
        self._high_cpu_since: float | None = None

        # Pre-compute the lowercased exclusion set once. ``extra_excluded``
        # carries the anti-cheat / launcher / protect-list images sourced from
        # ProcessJanitor.NEVER_KILL_IMAGES + abso.yaml process_overrides.protect
        # so the balancer never even *demotes* a protected or game-critical
        # process -- the online-safety guarantee for running during ranked play.
        excluded = {p.lower() for p in self._config.excluded_processes}
        if extra_excluded:
            excluded |= {str(p).lower() for p in extra_excluded}
        self._excluded_lower: frozenset[str] = frozenset(excluded)

        # When set, the presence of this file signals a graceful stop so the
        # ``run()`` finally-block restores every demoted process. The tray uses
        # this instead of TerminateProcess (.Kill), which would skip the
        # restore and strand background apps at BelowNormal.
        self._stop_file: Path | None = Path(stop_file) if stop_file else None

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
        self._start_session_extras()
        try:
            while not self._stop_requested():
                if not self._is_game_running():
                    logger.info("Game PID %d exited, stopping balancer", self._game_pid)
                    break
                self._poll_once()
                self._stop_event.wait(self._config.poll_interval_ms / 1000.0)
        finally:
            self._release_all()
            self._stop_session_extras()
            logger.info("CPU Balancer stopped. %d events logged.", len(self._events))

    def stop(self) -> None:
        """Signal the balancer loop to exit."""
        self._stop_event.set()

    def _stop_requested(self) -> bool:
        """Return ``True`` when the loop should exit.

        Either an in-process :meth:`stop` call or the appearance of the
        configured stop-sentinel file ends the loop. The sentinel path lets a
        separate process (the tray) request a *graceful* shutdown so the
        ``finally`` block in :meth:`run` restores demoted priorities.
        """
        if self._stop_event.is_set():
            return True
        if self._stop_file is not None and self._stop_file.exists():
            logger.info("Stop sentinel %s present; stopping balancer", self._stop_file)
            return True
        return False

    def get_events(self) -> list[BalancerEvent]:
        """Return a copy of all restrain/release events."""
        return list(self._events)

    # ------------------------------------------------------------------
    # Core polling logic
    # ------------------------------------------------------------------

    def _poll_once(self) -> None:
        """Single poll iteration."""
        now = time.monotonic()

        if self._enable_restraint:
            system_cpu = self._get_system_cpu()
            if system_cpu is not None:
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

        # One toolhelp snapshot per poll shared by the steerer, auto-steer,
        # and watchdog (each keeps its own CPU-time store where relevant).
        processes: list[tuple[int, str, int]] | None = None
        if self._steerer is not None or self._watchdog_engine is not None:
            processes = self._enumerate_processes()

        # Core-partition steering: re-sweep every poll -- CPU Sets are not
        # inherited, so late-spawned game children and background apps are
        # picked up within one poll period.
        if self._steerer is not None and processes is not None:
            try:
                newly_game, newly_bg = self._steerer.sweep(processes)
                if newly_game or newly_bg:
                    logger.info(
                        "Partition steer: +%d game-side, +%d background-side process(es)",
                        newly_game, newly_bg,
                    )
            except Exception as exc:
                logger.debug("Partition sweep failed: %s", exc)
            if self._enable_auto_steer:
                try:
                    self._auto_steer_offenders(processes, now)
                except Exception as exc:
                    logger.debug("Auto-steer failed: %s", exc)

        # Tier B: herd busy background images onto E-cores (idempotent; skips
        # already-throttled, the game, foreground, and never-eco images).
        if self._eco_herder is not None:
            try:
                self._eco_herder.herd()
            except Exception as exc:
                logger.debug("EcoQoS herd failed: %s", exc)

        # Tier B: evaluate declarative watchdog rules against live processes.
        if self._watchdog_engine is not None and processes is not None:
            try:
                self._watchdog_engine.tick(processes)
            except Exception as exc:
                logger.debug("Watchdog tick failed: %s", exc)

    def _auto_steer_offenders(
        self, processes: list[tuple[int, str, int]], now: float
    ) -> None:
        """Steer sustained-heavy background processes to the background side.

        The charlie754-style auto-detect: any process (outside the exclusion
        set, the game subtree, and the foreground app) that stays above the
        per-process CPU threshold for the sustain window is moved to the
        background partition for the rest of the session. Placement only --
        priorities and clocks are untouched.
        """
        if self._steerer is None or not self._steerer.partition.has_background_side:
            return
        parent_map = {pid: ppid for pid, _name, ppid in processes}
        game_descendants = self._compute_game_descendants(parent_map)
        already = self._steerer.steered_background_pids
        for pid, name, _ppid in processes:
            if pid in already:
                continue
            if self._is_excluded(name, pid, game_descendants):
                self._auto_steer_high_since.pop(pid, None)
                continue
            cpu = self._get_process_cpu(pid, times_store=self._auto_steer_cpu_times)
            if cpu is None:
                self._auto_steer_high_since.pop(pid, None)
                continue
            if cpu >= self._auto_steer_threshold:
                first = self._auto_steer_high_since.setdefault(pid, now)
                if (now - first) * 1000 >= self._auto_steer_sustain_ms:
                    if self._steerer.steer_extra(pid, name):
                        logger.info(
                            "Auto-steered %s (PID %d) to background cores (%.1f%% CPU sustained)",
                            name, pid, cpu,
                        )
                    self._auto_steer_high_since.pop(pid, None)
            else:
                self._auto_steer_high_since.pop(pid, None)

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

    def _get_process_cpu(
        self, pid: int, *, times_store: dict[int, tuple[int, int]] | None = None
    ) -> float | None:
        """Get per-process CPU usage percentage via ``GetProcessTimes``.

        Returns an approximate CPU % relative to total system capacity
        (number of logical CPUs x elapsed wall time). ``times_store`` selects
        which delta-tracking dict to use; the watchdog passes its own so it
        never corrupts the restraint loop's per-process deltas.
        """
        store = times_store if times_store is not None else self._last_process_times
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
            prev = store.get(pid)
            store[pid] = (kern_val, user_val)

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

    def _enumerate_processes(self) -> list[tuple[int, str, int]]:
        """List running processes as ``(pid, image, parent_pid)`` tuples."""
        snapshot = self._kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == -1:
            return []
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            processes: list[tuple[int, str, int]] = []
            if self._kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                while True:
                    processes.append(
                        (entry.th32ProcessID, entry.szExeFile, entry.th32ParentProcessID)
                    )
                    if not self._kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                        break
            return processes
        finally:
            self._kernel32.CloseHandle(snapshot)

    def _compute_game_descendants(self, parent_map: dict[int, int]) -> frozenset[int]:
        """Return every PID whose parent chain leads back to the game PID.

        The game often spawns helper children (anti-cheat brokers, EAC/BE
        children, shader-compile workers). Demoting those mid-match is exactly
        the online-safety hazard the balancer must avoid, and they are not all
        present in the static NEVER_KILL image set - so exclude the whole game
        subtree. Over-inclusion (from a stale recycled parent PID) only means a
        process is left alone, which is the safe direction.
        """
        children: dict[int, list[int]] = {}
        for pid, ppid in parent_map.items():
            children.setdefault(ppid, []).append(pid)

        descendants: set[int] = set()
        stack = list(children.get(self._game_pid, []))
        while stack:
            pid = stack.pop()
            if pid in descendants or pid == self._game_pid:
                continue
            descendants.add(pid)
            stack.extend(children.get(pid, []))
        return frozenset(descendants)

    def _is_excluded(
        self, name: str, pid: int, game_descendants: frozenset[int] | None = None
    ) -> bool:
        """Return ``True`` if the process must not be restrained."""
        if name.lower() in self._excluded_lower:
            return True
        if pid == self._game_pid:
            return True
        if game_descendants is not None and pid in game_descendants:
            return True
        if pid == self._get_foreground_pid():
            return True
        return pid <= 4  # System / Idle

    # ------------------------------------------------------------------
    # Restrain / release
    # ------------------------------------------------------------------

    def _find_and_restrain_offenders(self) -> None:
        """Find background processes using too much CPU and lower their priority."""
        processes = self._enumerate_processes()
        parent_map = {pid: ppid for pid, _name, ppid in processes}
        game_descendants = self._compute_game_descendants(parent_map)
        for pid, name, _ppid in processes:
            if self._is_excluded(name, pid, game_descendants):
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
            if (
                original
                and original > BELOW_NORMAL_PRIORITY_CLASS
                and self._kernel32.SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS)
            ):
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
    # Tier B session extras (opt-in, additive, exception-isolated)
    # ------------------------------------------------------------------

    def _start_session_extras(self) -> None:
        """Apply optional Tier B session behaviors at daemon start.

        A failure here must never break the core restraint loop, so every step
        is exception-isolated. No-ops entirely when the flags are off.
        """
        if self._enable_cpu_sets or self._steer_background_images:
            try:
                from abso.core import cpu_sets, partition_steer

                journal = (
                    Path(self._steer_journal_path)
                    if self._steer_journal_path
                    else partition_steer.default_journal_path()
                )
                try:
                    partition_steer.PartitionSteerer.recover_stale_journal(journal)
                except Exception as exc:
                    logger.debug("Stale steer-journal recovery failed: %s", exc)

                partition = cpu_sets.get_partition(
                    smt_avoid=self._smt_avoid, allow_x3d=self._allow_x3d
                )
                images = self._steer_background_images
                # Steering wins over EcoQoS for overlapping images: placement
                # at full clocks, not execution-speed throttling.
                if images and self._eco_images:
                    steered = {i.lower() for i in images}
                    self._eco_images = [
                        i for i in self._eco_images if i.lower() not in steered
                    ]
                self._steerer = partition_steer.PartitionSteerer(
                    self._game_pid, partition, images, journal_path=journal
                )
                self._steerer.sweep(self._enumerate_processes())
                logger.info(
                    "Core partition '%s': %d game-side / %d background-side "
                    "set(s); %d background image(s)%s",
                    partition.kind,
                    len(partition.game_ids),
                    len(partition.background_ids),
                    len(images),
                    ", auto-steer on" if self._enable_auto_steer else "",
                )
            except Exception as exc:
                logger.debug("Partition steer init failed: %s", exc)

        if self._enable_eco:
            try:
                from abso.core.efficiency_mode import EcoQosHerder

                self._eco_herder = EcoQosHerder(self._game_pid, self._eco_images)
                logger.info(
                    "EcoQoS herding enabled for %d background image(s)",
                    len(self._eco_images),
                )
            except Exception as exc:
                logger.debug("EcoQoS herder init failed: %s", exc)

        if self._enable_watchdog and self._watchdog_rules:
            try:
                from abso.core import proc_actions
                from abso.core.watchdog_engine import WatchdogEngine

                self._watchdog_engine = WatchdogEngine(
                    self._watchdog_rules,
                    is_online=self._is_online,
                    keep_cores=self._watchdog_keep_cores,
                    cpu_sampler=lambda pid: self._get_process_cpu(
                        pid, times_store=self._watchdog_cpu_times
                    ),
                    ram_sampler=proc_actions.get_working_set_mb,
                    priority_sampler=proc_actions.get_priority_class,
                )
                logger.info(
                    "Watchdog engine active with %d rule(s)%s",
                    self._watchdog_engine.active_rule_count,
                    " (online: demote-only)" if self._is_online else "",
                )
            except Exception as exc:
                logger.debug("Watchdog engine init failed: %s", exc)

    def _stop_session_extras(self) -> None:
        """Revert Tier B session behaviors at daemon stop."""
        if self._steerer is not None:
            try:
                self._steerer.release_all()
            except Exception as exc:
                logger.debug("Partition steer release failed: %s", exc)
            self._steerer = None
        elif self._enable_cpu_sets:
            # Steerer creation failed -- fall back to clearing the game PID.
            try:
                from abso.core import cpu_sets

                cpu_sets.clear_process_cpu_sets(self._game_pid)
            except Exception as exc:
                logger.debug("CPU Sets clear failed: %s", exc)

        if self._eco_herder is not None:
            try:
                self._eco_herder.release_all()
            except Exception as exc:
                logger.debug("EcoQoS release failed: %s", exc)
            self._eco_herder = None

        if self._watchdog_engine is not None:
            try:
                self._watchdog_engine.restore_all()
            except Exception as exc:
                logger.debug("Watchdog restore failed: %s", exc)
            self._watchdog_engine = None

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

def _build_runtime_config_from_user(
    user_cfg: Any,
    *,
    system_threshold: int | None = None,
    process_threshold: int | None = None,
    poll_interval: int | None = None,
    trigger_delay: int | None = None,
    restraint_duration: int | None = None,
) -> CpuBalancerConfig:
    """Translate the YAML-facing config into a runtime config.

    ``user_cfg`` is an :class:`abso.core.config.CpuBalancerConfig` -- a distinct
    dataclass that also carries the ``enabled`` flag. Explicit CLI arguments
    win over the configured values; anything left ``None`` falls back to the
    user config.
    """

    def pick(override: int | None, configured: int) -> int:
        return override if override is not None else configured

    return CpuBalancerConfig(
        system_cpu_threshold=pick(system_threshold, user_cfg.system_cpu_threshold),
        process_cpu_threshold=pick(process_threshold, user_cfg.process_cpu_threshold),
        trigger_delay_ms=pick(trigger_delay, user_cfg.trigger_delay_ms),
        restraint_duration_ms=pick(restraint_duration, user_cfg.restraint_duration_ms),
        poll_interval_ms=pick(poll_interval, user_cfg.poll_interval_ms),
        excluded_processes=list(user_cfg.excluded_processes),
    )


def _gather_extra_excluded() -> frozenset[str]:
    """Union the never-kill safety net + user protect list for exclusions.

    The balancer must never demote anti-cheat, game launchers, audio, the
    user's interactive/agentic tooling, or anything marked protected in
    ``abso.yaml``. :data:`~abso.core.process_janitor.NEVER_KILL_IMAGES` already
    encodes the curated safety net (pre-lowercased); we add the per-machine
    protect list on top. Failures are swallowed so config issues never break
    the balancer.
    """
    from abso.core.process_janitor import NEVER_KILL_IMAGES

    excluded: set[str] = set(NEVER_KILL_IMAGES)
    try:
        from abso.core.config import get_config

        overrides = getattr(get_config(), "process_overrides", None)
        for name in getattr(overrides, "protect", []) or []:
            cleaned = str(name).strip().lower()
            if cleaned:
                excluded.add(cleaned)
    except Exception as exc:
        logger.debug("Could not load process_overrides.protect: %s", exc)
    return frozenset(excluded)


def _resolve_session_extras(
    *, cpu_sets_flag: bool, eco_flag: bool
) -> tuple[bool, bool, list[str]]:
    """Resolve Tier B enablement: a behavior runs if its CLI flag is set OR its
    ``abso.yaml`` config flag is enabled. Returns
    ``(enable_cpu_sets, enable_eco, eco_images)``.
    """
    enable_cpu_sets = bool(cpu_sets_flag)
    enable_eco = bool(eco_flag)
    eco_images: list[str] = []
    try:
        from abso.core.config import get_config

        cfg = get_config()
        enable_cpu_sets = enable_cpu_sets or bool(cfg.cpu_sets.enabled)
        enable_eco = enable_eco or bool(cfg.efficiency_mode.enabled)
        eco_images = list(cfg.efficiency_mode.background_images)
    except Exception as exc:
        logger.debug("Could not load Tier B config: %s", exc)
    return enable_cpu_sets, enable_eco, eco_images


def _resolve_partition(*, steer_flag: bool, profile_id: str | None) -> dict[str, Any]:
    """Resolve profile-driven core partitioning for this session.

    The active profile's ``cpu_partition_policy`` decides the defaults
    (``off`` / ``game_only`` / ``full``); ``abso.yaml`` ``cpu_sets`` tunes or
    vetoes the background half; ``--steer-background`` forces the background
    half on. Returns kwargs for :class:`CpuBalancer`.
    """
    policy = ""
    images: list[str] = []
    resolved_profile = profile_id
    try:
        if not resolved_profile:
            from abso.core.app_paths import app_state_file
            from abso.core.state_store import read_state_file

            state = read_state_file(app_state_file()) or {}
            resolved_profile = state.get("current_profile")
        if resolved_profile:
            from abso.profiles.catalog import get_profile_partition

            policy, profile_images = get_profile_partition(resolved_profile)
            images = list(profile_images)
    except Exception as exc:
        logger.debug("Could not resolve profile partition policy: %s", exc)

    enable_game_side = policy in ("game_only", "full")
    background_allowed = policy == "full" or bool(steer_flag)

    auto_steer_default = True
    threshold = 4
    sustain_ms = 5000
    smt_avoid = False
    allow_x3d = True
    try:
        from abso.core.config import get_config

        cs = get_config().cpu_sets
        if not bool(cs.background_steer) and not steer_flag:
            background_allowed = False
        for extra in cs.background_images:
            cleaned = str(extra).strip()
            if cleaned:
                images.append(cleaned)
        auto_steer_default = bool(cs.auto_steer)
        threshold = int(cs.auto_steer_process_threshold)
        sustain_ms = int(cs.auto_steer_sustain_ms)
        smt_avoid = bool(cs.smt_avoid)
        allow_x3d = bool(cs.x3d_partition)
    except Exception as exc:
        logger.debug("Could not load cpu_sets partition config: %s", exc)

    if background_allowed and not images:
        from abso.core.partition_steer import DEFAULT_BACKGROUND_STEER_IMAGES

        images = list(DEFAULT_BACKGROUND_STEER_IMAGES)

    # Case-insensitive order-preserving dedupe.
    seen: set[str] = set()
    deduped: list[str] = []
    for image in images:
        key = image.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(image)

    return {
        "enable_cpu_sets": enable_game_side,
        "steer_background_images": deduped if background_allowed else [],
        "enable_auto_steer": background_allowed and auto_steer_default,
        "auto_steer_process_threshold": threshold,
        "auto_steer_sustain_ms": sustain_ms,
        "smt_avoid": smt_avoid,
        "allow_x3d": allow_x3d,
    }


def _resolve_watchdog(*, watchdog_flag: bool) -> tuple[bool, list, int]:
    """Resolve the watchdog: enabled if ``--watchdog`` OR ``watchdog.enabled``.

    Returns ``(enable, rules, keep_cores)`` where ``rules`` come from
    ``watchdog.rules`` and ``keep_cores`` (the throttle-action shrink size) from
    ``cpu_limiter.keep_cores``.
    """
    enable = bool(watchdog_flag)
    rules: list = []
    keep_cores = 4
    try:
        from abso.core.config import get_config

        cfg = get_config()
        enable = enable or bool(cfg.watchdog.enabled)
        rules = list(cfg.watchdog.rules)
        keep_cores = int(cfg.cpu_limiter.keep_cores)
    except Exception as exc:
        logger.debug("Could not load watchdog config: %s", exc)
    return enable, rules, keep_cores


def main() -> None:
    """Launch the CPU balancer from the command line."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="CPU Priority Balancer")
    parser.add_argument("--pid", type=int, required=True, help="Game process ID")
    parser.add_argument("--system-threshold", type=int, default=None)
    parser.add_argument("--process-threshold", type=int, default=None)
    parser.add_argument("--poll-interval", type=int, default=None)
    parser.add_argument("--trigger-delay", type=int, default=None)
    parser.add_argument("--restraint-duration", type=int, default=None)
    parser.add_argument(
        "--stop-file",
        type=str,
        default=None,
        help="Graceful-stop sentinel: when this file appears the balancer "
        "exits and restores all demoted priorities.",
    )
    parser.add_argument(
        "--cpu-sets",
        action="store_true",
        help="Tier B: soft-steer the game toward P-cores (CPU Sets).",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Active profile id for partition-policy resolution (defaults to "
        "the recorded active profile).",
    )
    parser.add_argument(
        "--steer-background",
        action="store_true",
        help="Force background-app steering to the background core partition "
        "even when the profile policy does not request it.",
    )
    parser.add_argument(
        "--no-restraint",
        action="store_true",
        help="Disable ProBalance priority restraint (steer-only session).",
    )
    parser.add_argument(
        "--eco",
        action="store_true",
        help="Tier B: herd busy background images onto E-cores (EcoQoS).",
    )
    parser.add_argument(
        "--watchdog",
        action="store_true",
        help="Tier B: evaluate declarative watchdog.rules (demote/throttle/trim).",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="Restrict the watchdog to the demote-only tier for online play.",
    )
    args = parser.parse_args()

    try:
        from abso.core.config import get_config

        user_cfg: Any = get_config().cpu_balancer
    except Exception as exc:
        logger.warning("Falling back to default balancer config: %s", exc)
        user_cfg = CpuBalancerConfig()

    config = _build_runtime_config_from_user(
        user_cfg,
        system_threshold=args.system_threshold,
        process_threshold=args.process_threshold,
        poll_interval=args.poll_interval,
        trigger_delay=args.trigger_delay,
        restraint_duration=args.restraint_duration,
    )
    enable_cpu_sets, enable_eco, eco_images = _resolve_session_extras(
        cpu_sets_flag=args.cpu_sets, eco_flag=args.eco
    )
    enable_watchdog, watchdog_rules, watchdog_keep_cores = _resolve_watchdog(
        watchdog_flag=args.watchdog
    )
    partition_kwargs = _resolve_partition(
        steer_flag=args.steer_background, profile_id=args.profile
    )
    partition_kwargs["enable_cpu_sets"] = (
        enable_cpu_sets or partition_kwargs["enable_cpu_sets"]
    )
    balancer = CpuBalancer(
        args.pid,
        config,
        extra_excluded=_gather_extra_excluded(),
        stop_file=args.stop_file,
        enable_eco=enable_eco,
        eco_images=eco_images,
        enable_watchdog=enable_watchdog,
        watchdog_rules=watchdog_rules,
        is_online=args.online,
        watchdog_keep_cores=watchdog_keep_cores,
        enable_restraint=not args.no_restraint,
        **partition_kwargs,
    )

    def _shutdown(signum: int, frame: Any) -> None:
        balancer.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    balancer.run()


if __name__ == "__main__":
    main()
