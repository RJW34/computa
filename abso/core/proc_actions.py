"""Win32 process-action primitives for the watchdog actuator (Tier B).

Priority get/set, working-set trim (EmptyWorkingSet), and working-set size
read (the watchdog "ram" metric). These are the reversible mechanisms the
:mod:`abso.core.watchdog_engine` actuator dispatches.

All ctypes calls use explicit prototypes (mandatory on 64-bit Windows so the
OpenProcess HANDLE is not truncated) and accept an injectable ``kernel32`` so
the hermetic tests never touch a real process.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging

logger = logging.getLogger(__name__)

# Priority classes (SetPriorityClass / GetPriorityClass).
IDLE_PRIORITY_CLASS = 0x00000040
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
NORMAL_PRIORITY_CLASS = 0x00000020
ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
HIGH_PRIORITY_CLASS = 0x00000080

# Process access rights.
PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_QUOTA = 0x0100  # required (with QUERY) for EmptyWorkingSet


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    """Win32 PROCESS_MEMORY_COUNTERS (psapi)."""

    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_KERNEL32: ctypes.WinDLL | None = None


def _kernel32() -> ctypes.WinDLL:
    """Cached kernel32 with explicit prototypes (avoids Win64 HANDLE truncation)."""
    global _KERNEL32
    if _KERNEL32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.CloseHandle.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.GetPriorityClass.restype = wintypes.DWORD
        k.GetPriorityClass.argtypes = [wintypes.HANDLE]
        k.SetPriorityClass.restype = wintypes.BOOL
        k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.K32EmptyWorkingSet.restype = wintypes.BOOL
        k.K32EmptyWorkingSet.argtypes = [wintypes.HANDLE]
        k.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        k.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        _KERNEL32 = k
    return _KERNEL32


def get_priority_class(pid: int, *, kernel32: ctypes.WinDLL | None = None) -> int | None:
    """Return a process's priority class, or ``None`` if it can't be read."""
    k = kernel32 or _kernel32()
    handle = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        cls = k.GetPriorityClass(handle)
        return int(cls) if cls else None
    finally:
        k.CloseHandle(handle)


def set_priority_class(pid: int, priority_class: int, *, kernel32: ctypes.WinDLL | None = None) -> bool:
    """Set a process's priority class. Returns ``True`` on success."""
    k = kernel32 or _kernel32()
    handle = k.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        return bool(k.SetPriorityClass(handle, priority_class))
    finally:
        k.CloseHandle(handle)


def get_working_set_mb(pid: int, *, kernel32: ctypes.WinDLL | None = None) -> float | None:
    """Return a process's working-set size in MB (the watchdog 'ram' metric)."""
    k = kernel32 or _kernel32()
    handle = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        ptr = ctypes.pointer(counters)
        if not k.K32GetProcessMemoryInfo(handle, ptr, counters.cb):
            return None
        return counters.WorkingSetSize / (1024.0 * 1024.0)
    finally:
        k.CloseHandle(handle)


def trim_working_set(pid: int, *, kernel32: ctypes.WinDLL | None = None) -> bool:
    """Trim a process's working set via EmptyWorkingSet (the 'trim' action).

    One-shot and harmless: the OS re-pages the process on demand. Not tracked
    for restore (there is nothing to revert).
    """
    k = kernel32 or _kernel32()
    handle = k.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, pid)
    if not handle:
        return False
    try:
        return bool(k.K32EmptyWorkingSet(handle))
    finally:
        k.CloseHandle(handle)
