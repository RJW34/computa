"""UAC / Admin elevation handling."""

from __future__ import annotations

import ctypes
import sys
import logging

logger = logging.getLogger(__name__)


def is_admin() -> bool:
    """Check if the current process has admin privileges.

    Returns:
        True if running as admin, False otherwise.
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin() -> None:
    """Ensure the process is running with admin privileges.

    If not running as admin, attempts to re-launch with elevation.
    Exits the current process if elevation is triggered.
    """
    if is_admin():
        return

    logger.info("Requesting admin elevation...")

    try:
        # Re-run the script with admin privileges
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            " ".join(sys.argv),
            None,
            1  # SW_SHOWNORMAL
        )
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to elevate: {e}")
        raise RuntimeError("Admin privileges required but elevation failed")


def run_elevated(command: str) -> int:
    """Run a command with elevated privileges.

    Args:
        command: Command to run.

    Returns:
        Exit code from ShellExecuteW (>32 means success).
    """
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        "cmd.exe",
        f"/c {command}",
        None,
        0  # SW_HIDE
    )
    return result
