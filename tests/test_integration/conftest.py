"""Integration test fixtures and helpers.

WARNING: These tests interact with REAL system state (Windows registry,
power plans, WMI, etc.).  They are designed to be safe -- every write is
preceded by a backup and followed by a restore -- but they CAN modify your
system if something goes wrong.

DO NOT run these tests unless:
  1. You are on a Windows machine you own.
  2. You are running in an admin-elevated terminal.
  3. You explicitly opt in via: pytest -m integration
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any, Generator

import pytest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Admin detection helper
# ---------------------------------------------------------------------------

def _is_admin() -> bool:
    """Check whether the current process has administrator privileges."""
    if sys.platform != "win32":
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, OSError):
        return False


# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------

requires_admin = pytest.mark.skipif(
    not _is_admin(),
    reason="Requires admin elevation",
)


# ---------------------------------------------------------------------------
# Registry backup / restore fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def registry_backup():
    """Context-manager fixture that saves and restores a single registry value.

    Usage inside a test::

        def test_something(self, registry_backup):
            with registry_backup(hive, subkey, value_name) as original:
                # original is the value before the test (may be None)
                ...  # do writes
            # value is automatically restored here

    The fixture guarantees restoration even if the test raises an exception.
    """
    import contextlib
    import winreg

    @contextlib.contextmanager
    def _backup_ctx(
        hive: int,
        subkey: str,
        value_name: str,
    ) -> Generator[Any, None, None]:
        """Save the current value, yield it, then restore on exit."""
        original_value: Any = None
        original_type: int | None = None
        value_existed = False

        # --- Read current value -------------------------------------------
        try:
            key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
            try:
                original_value, original_type = winreg.QueryValueEx(key, value_name)
                value_existed = True
            except FileNotFoundError:
                pass
            finally:
                winreg.CloseKey(key)
        except OSError as exc:
            logger.warning(
                "registry_backup: cannot read %s\\%s -- %s",
                subkey,
                value_name,
                exc,
            )

        try:
            yield original_value
        finally:
            # --- Restore original value -----------------------------------
            try:
                key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_ALL_ACCESS)
                try:
                    if value_existed and original_type is not None:
                        winreg.SetValueEx(
                            key, value_name, 0, original_type, original_value,
                        )
                        logger.debug(
                            "registry_backup: restored %s\\%s = %r",
                            subkey,
                            value_name,
                            original_value,
                        )
                    else:
                        # Value did not exist before -- delete what the test created.
                        with contextlib.suppress(FileNotFoundError):
                            winreg.DeleteValue(key, value_name)
                            logger.debug(
                                "registry_backup: deleted %s\\%s (did not exist before)",
                                subkey,
                                value_name,
                            )
                finally:
                    winreg.CloseKey(key)
            except OSError as exc:
                logger.error(
                    "registry_backup: FAILED to restore %s\\%s -- %s.  "
                    "Manual intervention may be required.",
                    subkey,
                    value_name,
                    exc,
                )

    return _backup_ctx
