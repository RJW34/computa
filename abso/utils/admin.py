"""UAC / Admin elevation handling."""

from __future__ import annotations

import ctypes
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


def is_admin() -> bool:
    """Check if the current process has admin privileges.

    Returns:
        True if running as admin, False otherwise.
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, OSError) as e:
        logger.debug(f"Failed to check admin status: {e}")
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
        # list2cmdline applies the Windows quoting rules so paths with spaces
        # (e.g. "C:\Users\Name With Space\...") survive the re-launch.
        params = subprocess.list2cmdline(sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            params,
            None,
            1  # SW_SHOWNORMAL
        )
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to elevate: {e}")
        raise RuntimeError("Admin privileges required but elevation failed") from e
