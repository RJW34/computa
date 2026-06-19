"""Subprocess helpers for windowless child execution on Windows.

When ABSO runs as a windowless process (the frozen GUI executable, or a backend
spawned hidden by the PowerShell tray), shelling out to ``tasklist`` /
``taskkill`` / ``powercfg`` / ``powershell`` makes a console window flash for
each call. Passing ``CREATE_NO_WINDOW`` suppresses that flash. On non-Windows
platforms the flag does not exist, so the helper returns 0 (a no-op).
"""

from __future__ import annotations

import subprocess
import sys

# Fall back to the documented constant value if the attribute is missing
# (e.g. on a non-Windows host running the test suite).
CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def no_window_creationflags() -> int:
    """Return ``CREATE_NO_WINDOW`` on Windows, ``0`` elsewhere."""
    return CREATE_NO_WINDOW if sys.platform == "win32" else 0
