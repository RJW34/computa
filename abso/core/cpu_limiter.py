"""Reversible CPU limiter via hard-affinity shrink (Tier B scaffold, default OFF).

The one Process Lasso mechanism ABSO genuinely lacks: cap a runaway-but-wanted
background process by temporarily shrinking its HARD affinity mask to a small
core subset while it misbehaves, then restoring the original mask on
release/exit. The state is ephemeral (the OS drops affinity at process exit), so
there is nothing to persist.

Hard affinity is REQUIRED here -- ``SetProcessAffinityMask``, not CPU Sets. CPU
Sets are only a scheduler hint and would silently fail to cap CPU.

ONLINE SAFETY: mid-match affinity mutation is exactly the timing nondeterminism
RollbackGuard exists to prevent, and is higher anti-cheat risk than launch-time
IFEO. The limiter therefore MUST stay disabled for online profiles and must
never act on the game / foreground / anti-cheat PIDs. Those gates live with the
caller (tray/governor); this module is the dormant primitive. Default OFF.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_INFORMATION = 0x0400


def shrink_mask(system_mask: int, keep_cores: int) -> int:
    """Return an affinity mask of the lowest ``keep_cores`` set bits of the system.

    Returns 0 (a no-op signal) when the request is degenerate. Picking the
    lowest-indexed logical processors keeps the throttled process off the higher
    cores the game prefers without needing topology knowledge here.
    """
    if keep_cores <= 0 or system_mask == 0:
        return 0
    result = 0
    taken = 0
    bit = 0
    while taken < keep_cores and bit < 64:
        candidate = 1 << bit
        if system_mask & candidate:
            result |= candidate
            taken += 1
        bit += 1
    return result


_KERNEL32: ctypes.WinDLL | None = None


def _kernel32() -> ctypes.WinDLL:
    """Cached kernel32 with explicit prototypes.

    Setting ``restype``/``argtypes`` is mandatory on 64-bit Windows: the ctypes
    default ``c_int`` return would truncate the 64-bit HANDLE from OpenProcess,
    and DWORD_PTR affinity masks must be passed as ``c_size_t``.
    """
    global _KERNEL32
    if _KERNEL32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.CloseHandle.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.GetProcessAffinityMask.restype = wintypes.BOOL
        k.GetProcessAffinityMask.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        k.SetProcessAffinityMask.restype = wintypes.BOOL
        k.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
        _KERNEL32 = k
    return _KERNEL32


def get_process_affinity(
    pid: int, *, kernel32: ctypes.WinDLL | None = None
) -> tuple[int, int] | None:
    """Return ``(process_mask, system_mask)`` for a process, or ``None``."""
    k = kernel32 or _kernel32()
    handle = k.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        proc_mask = ctypes.c_size_t(0)
        sys_mask = ctypes.c_size_t(0)
        ok = k.GetProcessAffinityMask(handle, ctypes.byref(proc_mask), ctypes.byref(sys_mask))
        if not ok:
            return None
        return proc_mask.value, sys_mask.value
    finally:
        k.CloseHandle(handle)


def set_process_affinity(pid: int, mask: int, *, kernel32: ctypes.WinDLL | None = None) -> bool:
    """Set a process's hard affinity mask. Returns ``True`` on success."""
    k = kernel32 or _kernel32()
    handle = k.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        return bool(k.SetProcessAffinityMask(handle, ctypes.c_size_t(mask)))
    finally:
        k.CloseHandle(handle)


class CpuLimiter:
    """Tracks original affinity masks so a throttle can be cleanly reverted.

    Dependencies are injected so the snapshot/restore bookkeeping is fully
    unit-testable without touching real processes.
    """

    def __init__(
        self,
        keep_cores: int = 4,
        *,
        getter: Callable[[int], tuple[int, int] | None] | None = None,
        setter: Callable[[int, int], bool] | None = None,
    ) -> None:
        self._keep_cores = keep_cores
        self._getter = getter or get_process_affinity
        self._setter = setter or set_process_affinity
        self._original: dict[int, int] = {}

    def limit(self, pid: int) -> bool:
        """Shrink ``pid`` to ``keep_cores``; snapshot its original mask first.

        No-ops (returns ``False``) when the process cannot be read, the shrink
        is degenerate, or the target already equals the current mask.
        """
        masks = self._getter(pid)
        if masks is None:
            return False
        proc_mask, sys_mask = masks
        target = shrink_mask(sys_mask, self._keep_cores)
        if target == 0 or target == proc_mask:
            return False
        if self._setter(pid, target):
            self._original.setdefault(pid, proc_mask)
            return True
        return False

    def restore(self, pid: int) -> bool:
        """Restore a previously-limited process's original affinity mask."""
        original = self._original.pop(pid, None)
        if original is None:
            return False
        return self._setter(pid, original)

    def restore_all(self) -> None:
        """Restore every process this limiter throttled."""
        for pid in list(self._original):
            self.restore(pid)

    @property
    def limited_pids(self) -> frozenset[int]:
        return frozenset(self._original)


def cpu_limiter_enabled() -> bool:
    """Return ``True`` if the CPU limiter is opted in via ``abso.yaml``."""
    try:
        from abso.core.config import get_config

        return bool(get_config().cpu_limiter.enabled)
    except Exception as exc:
        logger.debug("cpu_limiter config unavailable: %s", exc)
        return False
