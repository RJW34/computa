"""Tests for monitor Adaptive Sync DDC/CI prototype configuration.

These guard against the Win64 HANDLE-truncation class of bug: the DDC/CI
helpers must declare pointer-sized argtypes/restypes so HMONITOR/HANDLE values
are not silently narrowed to a 32-bit C int.
"""

from ctypes import wintypes
from unittest.mock import MagicMock

import abso.settings.nvidia.monitor_adaptive_sync as mas


def _reset_prototype_flag():
    mas._prototypes_configured = False


def test_configure_prototypes_sets_pointer_sized_handles():
    """MonitorFromPoint must return a pointer-sized HMONITOR, not a C int."""
    _reset_prototype_flag()
    user32 = MagicMock()
    dxva2 = MagicMock()

    mas._configure_prototypes(user32, dxva2)

    assert user32.MonitorFromPoint.restype is wintypes.HMONITOR
    # The enumeration calls must accept the HMONITOR as their first argument.
    assert dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes[0] is wintypes.HMONITOR
    assert dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes[0] is wintypes.HMONITOR
    assert mas._prototypes_configured is True


def test_configure_prototypes_is_idempotent():
    """A second call must not re-touch the cached module prototypes."""
    _reset_prototype_flag()
    user32 = MagicMock()
    dxva2 = MagicMock()
    mas._configure_prototypes(user32, dxva2)

    user32_2 = MagicMock()
    dxva2_2 = MagicMock()
    mas._configure_prototypes(user32_2, dxva2_2)

    # Already configured: the second module objects are left untouched.
    assert not user32_2.MonitorFromPoint.method_calls
    assert user32_2.MonitorFromPoint.restype is not wintypes.HMONITOR
