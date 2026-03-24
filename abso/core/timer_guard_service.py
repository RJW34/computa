"""Lightweight service that holds NtSetTimerResolution for a game session.

This module is designed to be spawned by the ABSO tray app (PowerShell) as a
child process.  It keeps the timer resolution request alive for as long as the
target game process is running, then cleanly releases and exits.

Invocation::

    python -m abso.core.timer_guard_service --process game.exe --resolution 0.5

The service writes its status to ``%TEMP%\\abso_timer_guard.json`` so the tray
app can poll state without a full IPC channel.  Status values:

- ``"waiting"``  -- resolution set, waiting for the game to appear
- ``"active"``   -- game running, resolution held
- ``"released"`` -- game exited (or timeout), resolution restored
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import NoReturn

# Ensure the project root is on sys.path when invoked with ``python -m``
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from abso.settings.timer import TimerResolutionGuard  # noqa: E402

logger = logging.getLogger("abso.timer_guard_service")

STATUS_FILE = Path(os.environ.get("TEMP", "/tmp")) / "abso_timer_guard.json"


def _configure_logging(verbose: bool = False) -> None:
    """Set up console logging."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)


def _write_final_status(process_name: str, reason: str) -> None:
    """Write a released-status entry so the tray app sees clean shutdown."""
    payload = {
        "pid": os.getpid(),
        "process_name": process_name,
        "resolution_100ns": 0,
        "resolution_ms": 0.0,
        "start_time": time.time(),
        "status": "released",
        "exit_reason": reason,
    }
    try:
        STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def main(
    process_name: str,
    resolution_ms: float = 0.5,
    timeout_hours: float = 8.0,
    poll_interval: float = 5.0,
) -> None:
    """Hold timer resolution while *process_name* is running.

    Args:
        process_name: Executable to watch (e.g. ``"game.exe"``).
        resolution_ms: Target resolution in milliseconds.
        timeout_hours: Maximum hours to hold the resolution.
        poll_interval: Seconds between process-alive checks.
    """
    resolution_100ns = int(resolution_ms * 10000)
    timeout_seconds = timeout_hours * 3600

    logger.info(
        "Timer guard starting: process=%s, resolution=%.3f ms, timeout=%.1f h",
        process_name,
        resolution_ms,
        timeout_hours,
    )

    guard = TimerResolutionGuard(resolution_100ns=resolution_100ns)

    # Handle graceful shutdown on SIGTERM / Ctrl+C
    def _shutdown(signum: int, frame: object) -> None:
        logger.info("Received signal %s; releasing and exiting", signum)
        guard._release()
        _write_final_status(process_name, reason=f"signal_{signum}")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    # SIGINT is handled by KeyboardInterrupt below, but register anyway
    signal.signal(signal.SIGINT, _shutdown)

    try:
        with guard:
            guard.hold_for_process(
                process_name=process_name,
                poll_interval=poll_interval,
                timeout=timeout_seconds,
            )
        logger.info("Guard released normally; exiting")
    except KeyboardInterrupt:
        logger.info("Interrupted; releasing timer resolution")
        guard._release()
        _write_final_status(process_name, reason="keyboard_interrupt")
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        guard._release()
        _write_final_status(process_name, reason=f"error: {e}")
        sys.exit(1)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m abso.core.timer_guard_service",
        description=(
            "Hold NtSetTimerResolution for the lifetime of a game process. "
            "Designed to be spawned by the ABSO tray app."
        ),
    )
    parser.add_argument(
        "--process",
        required=True,
        help="Executable name to watch (e.g. game.exe)",
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=0.5,
        help="Target timer resolution in milliseconds (default: 0.5)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Maximum hours to hold the resolution (default: 8)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between process-alive checks (default: 5)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()
    _configure_logging(verbose=args.verbose)
    main(
        process_name=args.process,
        resolution_ms=args.resolution,
        timeout_hours=args.timeout,
        poll_interval=args.poll_interval,
    )
