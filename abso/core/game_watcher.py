"""GameWatcher - WMI event-based game process monitoring.

This module uses WMI event subscriptions (Win32_ProcessStartTrace /
Win32_ProcessStopTrace) to detect game process lifecycle events without
polling.  When WMI event subscriptions are unavailable (some Windows
editions restrict them), it falls back to periodic ``tasklist`` polling.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS: float = 3.0


@dataclass
class ProcessInfo:
    """Snapshot of a tracked game process."""

    pid: int
    name: str
    start_time: datetime
    profile_id: str | None = None


class GameWatcher:
    """Watches for game process start/exit via WMI events.

    Primary path uses ``Win32_ProcessStartTrace`` / ``Win32_ProcessStopTrace``
    subscriptions delivered in a daemon thread.  If subscription fails the
    watcher transparently falls back to ``tasklist`` polling every 3 seconds.

    Args:
        on_game_start: Callback invoked with a ``ProcessInfo`` when a
            watched process starts.
        on_game_exit: Callback invoked with a ``ProcessInfo`` when a
            watched process exits.
    """

    def __init__(
        self,
        on_game_start: Callable[[ProcessInfo], Any],
        on_game_exit: Callable[[ProcessInfo], Any],
    ) -> None:
        self._on_game_start = on_game_start
        self._on_game_exit = on_game_exit

        self._executable_names: list[str] = []
        self._active: dict[int, ProcessInfo] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._using_fallback: bool = False

    # -- public interface ---------------------------------------------------

    def watch(self, executable_names: list[str]) -> None:
        """Start watching for the given process names.

        Args:
            executable_names: List of executable file names to watch
                (e.g. ``["RivalsofAether2.exe", "Slippi Dolphin.exe"]``).
                Matching is case-insensitive.
        """
        self._executable_names = [n.lower() for n in executable_names]
        self._stop_event.clear()

        logger.info("GameWatcher starting for: %s", executable_names)

        try:
            self._start_wmi_watchers()
        except Exception:
            logger.warning(
                "WMI event subscription unavailable, falling back to "
                "tasklist polling (every %.0fs)",
                _POLL_INTERVAL_SECONDS,
                exc_info=True,
            )
            self._using_fallback = True
            self._start_polling_watcher()

    def stop(self) -> None:
        """Stop all watcher threads."""
        logger.info("GameWatcher stopping")
        self._stop_event.set()

        for thread in self._threads:
            thread.join(timeout=10.0)
        self._threads.clear()

    def get_active_games(self) -> list[ProcessInfo]:
        """Return a snapshot of currently-tracked active game processes."""
        with self._lock:
            return list(self._active.values())

    # -- WMI event path -----------------------------------------------------

    def _start_wmi_watchers(self) -> None:
        """Subscribe to WMI process start/stop trace events."""
        import wmi  # type: ignore[import-untyped]

        # Verify subscriptions work before spawning threads.
        connection = wmi.WMI()
        # The watch_for call validates that the subscription is allowed.
        _test_watcher = connection.Win32_ProcessStartTrace.watch_for(
            delay_secs=1,
        )
        # If the above did not raise, subscriptions are available.
        del _test_watcher
        del connection

        start_thread = threading.Thread(
            target=self._wmi_start_listener,
            name="abso-wmi-start",
            daemon=True,
        )
        stop_thread = threading.Thread(
            target=self._wmi_stop_listener,
            name="abso-wmi-stop",
            daemon=True,
        )

        start_thread.start()
        stop_thread.start()
        self._threads.extend([start_thread, stop_thread])

        logger.info("WMI event subscriptions active")

    def _wmi_start_listener(self) -> None:
        """Thread body: listen for process creation events."""
        try:
            import wmi  # type: ignore[import-untyped]

            connection = wmi.WMI()
            watcher = connection.Win32_ProcessStartTrace.watch_for()

            while not self._stop_event.is_set():
                try:
                    event = watcher(timeout_ms=1000)
                except wmi.x_wmi_timed_out:
                    continue

                process_name: str = event.ProcessName
                if process_name.lower() not in self._executable_names:
                    continue

                pid: int = int(event.ProcessID)
                info = ProcessInfo(
                    pid=pid,
                    name=process_name,
                    start_time=datetime.now(),
                )

                with self._lock:
                    self._active[pid] = info

                logger.info("Game started: %s (PID %d)", process_name, pid)

                try:
                    self._on_game_start(info)
                except Exception:
                    logger.error(
                        "on_game_start callback failed for %s",
                        process_name,
                        exc_info=True,
                    )

        except Exception:
            if not self._stop_event.is_set():
                logger.error("WMI start listener crashed", exc_info=True)

    def _wmi_stop_listener(self) -> None:
        """Thread body: listen for process exit events."""
        try:
            import wmi  # type: ignore[import-untyped]

            connection = wmi.WMI()
            watcher = connection.Win32_ProcessStopTrace.watch_for()

            while not self._stop_event.is_set():
                try:
                    event = watcher(timeout_ms=1000)
                except wmi.x_wmi_timed_out:
                    continue

                process_name: str = event.ProcessName
                if process_name.lower() not in self._executable_names:
                    continue

                pid: int = int(event.ProcessID)

                with self._lock:
                    info = self._active.pop(pid, None)

                if info is None:
                    # Process exited that we didn't see start (was
                    # running before the watcher started).
                    info = ProcessInfo(
                        pid=pid,
                        name=process_name,
                        start_time=datetime.now(),
                    )

                logger.info("Game exited: %s (PID %d)", process_name, pid)

                try:
                    self._on_game_exit(info)
                except Exception:
                    logger.error(
                        "on_game_exit callback failed for %s",
                        process_name,
                        exc_info=True,
                    )

        except Exception:
            if not self._stop_event.is_set():
                logger.error("WMI stop listener crashed", exc_info=True)

    # -- polling fallback ---------------------------------------------------

    def _start_polling_watcher(self) -> None:
        """Start a single daemon thread that polls ``tasklist``."""
        thread = threading.Thread(
            target=self._polling_loop,
            name="abso-poll-watcher",
            daemon=True,
        )
        thread.start()
        self._threads.append(thread)

        logger.info("Polling watcher active (interval=%.0fs)", _POLL_INTERVAL_SECONDS)

    def _polling_loop(self) -> None:
        """Thread body: periodically check running processes via tasklist."""
        seen_pids: dict[int, str] = {}

        while not self._stop_event.is_set():
            current_pids = self._poll_running_processes()

            # Detect new processes.
            for pid, name in current_pids.items():
                if pid not in seen_pids:
                    info = ProcessInfo(
                        pid=pid,
                        name=name,
                        start_time=datetime.now(),
                    )
                    with self._lock:
                        self._active[pid] = info

                    logger.info(
                        "Game started (poll): %s (PID %d)", name, pid,
                    )

                    try:
                        self._on_game_start(info)
                    except Exception:
                        logger.error(
                            "on_game_start callback failed for %s",
                            name,
                            exc_info=True,
                        )

            # Detect exited processes.
            for pid, name in list(seen_pids.items()):
                if pid not in current_pids:
                    with self._lock:
                        info = self._active.pop(pid, None)

                    if info is None:
                        info = ProcessInfo(
                            pid=pid,
                            name=name,
                            start_time=datetime.now(),
                        )

                    logger.info(
                        "Game exited (poll): %s (PID %d)", name, pid,
                    )

                    try:
                        self._on_game_exit(info)
                    except Exception:
                        logger.error(
                            "on_game_exit callback failed for %s",
                            name,
                            exc_info=True,
                        )

            seen_pids = current_pids
            self._stop_event.wait(timeout=_POLL_INTERVAL_SECONDS)

    def _poll_running_processes(self) -> dict[int, str]:
        """Query ``tasklist`` for matching game processes.

        Returns:
            Mapping of PID to process name for watched executables that
            are currently running.
        """
        matches: dict[int, str] = {}

        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
            )

            for line in result.stdout.strip().splitlines():
                # Format: "name.exe","PID","Session Name","Session#","Mem Usage"
                parts = line.split('","')
                if len(parts) < 2:
                    continue

                name = parts[0].strip('"')
                try:
                    pid = int(parts[1].strip('"'))
                except (ValueError, IndexError):
                    continue

                if name.lower() in self._executable_names:
                    matches[pid] = name

        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.error("tasklist polling failed: %s", exc)

        return matches
