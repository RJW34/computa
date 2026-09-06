"""CPU Sets soft P-core steering (Tier B scaffold, default OFF).

CPU Sets (``SetProcessDefaultCpuSets``) assign eligible processors to threads
without changing the hard-affinity mask. Windows normally schedules an assigned
thread on one of those sets; an unchanged affinity mask does not guarantee that
the thread can spill onto E-cores under load. This can help or hurt a game's
CPU throughput and requires measurement. Use of a documented API does not prove
compatibility with every anti-cheat implementation.

State is per-process and runtime-only (the OS clears it at process exit), so
there is nothing to persist -- it maps onto the "ephemeral" restore tier.

Nothing here runs until the tray wires it on a game-launch edge AND config opts
in; see ``CpuSetsConfig.enabled``. Default OFF.

No local benchmark proves a frame-time, 1%-low, or average-FPS benefit from this
opt-in behavior. Native scheduling remains the default.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import struct
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PROCESS_SET_LIMITED_INFORMATION = 0x2000
_CPU_SET_INFORMATION_TYPE_CPUSET = 0  # CpuSetInformation
# Fixed prefix size of SYSTEM_CPU_SET_INFORMATION that carries the fields we
# read; the struct is 32 bytes on current Windows but we always advance by the
# per-entry Size so a future-extended struct still parses.
_CPU_SET_ENTRY_MIN_SIZE = 32


@dataclass(frozen=True)
class CpuSetEntry:
    """The subset of SYSTEM_CPU_SET_INFORMATION we care about.

    ``id`` is the CPU Set Id (NOT the processor number -- a common bug).
    ``efficiency_class`` ranks performance: on Raptor Lake the P-cores carry
    the highest class, E-cores a lower one.
    """

    id: int
    logical_index: int
    core_index: int
    efficiency_class: int


def _parse_cpu_set_buffer(buf: bytes) -> list[CpuSetEntry]:
    """Walk a SYSTEM_CPU_SET_INFORMATION array, entry-by-entry, by its Size.

    Layout per entry (packed, naturally aligned to 32 bytes on current Windows):
        Size(u32) Type(u32) Id(u32) Group(u16) LogicalProcessorIndex(u8)
        CoreIndex(u8) LastLevelCacheIndex(u8) NumaNodeIndex(u8)
        EfficiencyClass(u8) AllFlags(u8) (Reserved/SchedulingClass u32)
        AllocationTag(u64)
    """
    entries: list[CpuSetEntry] = []
    offset = 0
    total = len(buf)
    while offset + 8 <= total:
        size, type_ = struct.unpack_from("<II", buf, offset)
        if size < 8 or offset + size > total:
            break
        if type_ == _CPU_SET_INFORMATION_TYPE_CPUSET and size >= _CPU_SET_ENTRY_MIN_SIZE:
            id_, _group, logical_index, core_index, _llc, _numa, efficiency_class, _flags = (
                struct.unpack_from("<IHBBBBBB", buf, offset + 8)
            )
            entries.append(
                CpuSetEntry(
                    id=id_,
                    logical_index=logical_index,
                    core_index=core_index,
                    efficiency_class=efficiency_class,
                )
            )
        offset += size
    return entries


def classify_pcore_ids(entries: list[CpuSetEntry]) -> list[int]:
    """Return the CPU Set Ids of the performance cores.

    Returns an empty list when the topology is non-hybrid (a single efficiency
    class) -- there is no steering benefit, and callers must no-op rather than
    pin the whole machine.
    """
    if not entries:
        return []
    classes = {e.efficiency_class for e in entries}
    if len(classes) < 2:
        return []  # non-hybrid: nothing to steer
    top_class = max(classes)
    return [e.id for e in entries if e.efficiency_class == top_class]


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
        k.SetProcessDefaultCpuSets.restype = wintypes.BOOL
        k.SetProcessDefaultCpuSets.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_ulong),
            wintypes.ULONG,
        ]
        k.GetSystemCpuSetInformation.restype = wintypes.BOOL
        k.GetSystemCpuSetInformation.argtypes = [
            ctypes.c_void_p,
            wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG),
            wintypes.HANDLE,
            wintypes.ULONG,
        ]
        _KERNEL32 = k
    return _KERNEL32


def get_system_cpu_sets(kernel32: ctypes.WinDLL | None = None) -> list[CpuSetEntry]:
    """Query the live CPU Set topology via ``GetSystemCpuSetInformation``."""
    k = kernel32 or _kernel32()
    length = ctypes.c_ulong(0)
    # First call sizes the buffer (returns FALSE with ERROR_INSUFFICIENT_BUFFER).
    k.GetSystemCpuSetInformation(None, 0, ctypes.byref(length), None, 0)
    if length.value == 0:
        return []
    buf = (ctypes.c_byte * length.value)()
    ok = k.GetSystemCpuSetInformation(buf, length.value, ctypes.byref(length), None, 0)
    if not ok:
        logger.debug("GetSystemCpuSetInformation failed")
        return []
    return _parse_cpu_set_buffer(bytes(buf))


def get_pcore_cpu_set_ids(kernel32: ctypes.WinDLL | None = None) -> list[int]:
    """Convenience: live P-core CPU Set Ids ([] on non-hybrid / failure)."""
    return classify_pcore_ids(get_system_cpu_sets(kernel32=kernel32))


def steer_process_to_pcores(
    pid: int, cpu_set_ids: list[int], *, kernel32: ctypes.WinDLL | None = None
) -> bool:
    """Bias a process toward the given CPU Sets (soft; hard affinity untouched).

    Returns ``False`` (a safe no-op) when ``cpu_set_ids`` is empty -- e.g. a
    non-hybrid CPU -- so callers never accidentally pin the whole machine.
    """
    if not cpu_set_ids:
        return False
    k = kernel32 or _kernel32()
    handle = k.OpenProcess(PROCESS_SET_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        count = len(cpu_set_ids)
        arr = (ctypes.c_ulong * count)(*cpu_set_ids)
        ok = k.SetProcessDefaultCpuSets(handle, arr, count)
        return bool(ok)
    finally:
        k.CloseHandle(handle)


def clear_process_cpu_sets(pid: int, *, kernel32: ctypes.WinDLL | None = None) -> bool:
    """Clear a process's default CPU Sets (revert to system scheduling)."""
    k = kernel32 or _kernel32()
    handle = k.OpenProcess(PROCESS_SET_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        ok = k.SetProcessDefaultCpuSets(handle, None, 0)
        return bool(ok)
    finally:
        k.CloseHandle(handle)


def cpu_sets_enabled() -> bool:
    """Return ``True`` if CPU Sets steering is opted in via ``abso.yaml``."""
    try:
        from abso.core.config import get_config

        return bool(get_config().cpu_sets.enabled)
    except Exception as exc:
        logger.debug("cpu_sets config unavailable: %s", exc)
        return False
