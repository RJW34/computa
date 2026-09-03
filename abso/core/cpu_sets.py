"""CPU Sets soft P-core steering (Tier B scaffold, default OFF).

The hybrid-correct, anti-cheat-safe alternative to hard affinity. Hard affinity
(``SetProcessAffinityMask``) is wrong on Intel hybrid CPUs because it blocks the
Thread Director and can starve a game when its threads spill is forbidden -- so
ABSO ships every gaming base with ``strategy=None``. CPU Sets
(``SetProcessDefaultCpuSets``) are a scheduler *preference*: threads are biased
toward the listed cores but the process's full hard-affinity mask stays intact,
so under load threads still spill to E-cores instead of starving. Process Lasso
uses exactly this under EAC/BattlEye without bans.

State is per-process and runtime-only (the OS clears it at process exit), so
there is nothing to persist -- it maps onto the "ephemeral" restore tier.

Nothing here runs until the tray wires it on a game-launch edge AND config opts
in; see ``CpuSetsConfig.enabled``. Default OFF.

Honest framing: on a Thread-Director-competent Raptor Lake this is a frame-time
*consistency* / 1%-low smoother (catching a stray thread on an E-core), NOT an
average-FPS gain.
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

# GetLogicalProcessorInformationEx relationship selector for cache entries.
_RELATION_CACHE = 2
# SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX header: Relationship(u32) Size(u32).
_LPI_EX_HEADER_SIZE = 8
# CACHE_RELATIONSHIP fixed prefix after the header: Level(u8) Associativity(u8)
# LineSize(u16) CacheSize(u32) Type(u32) Reserved[18] GroupCount(u16), then
# GROUP_AFFINITY GroupMasks[] (Mask u64, Group u16, Reserved u16*3 = 16 bytes).
_CACHE_GROUP_COUNT_OFFSET = _LPI_EX_HEADER_SIZE + 1 + 1 + 2 + 4 + 4 + 18
_CACHE_GROUP_MASKS_OFFSET = _CACHE_GROUP_COUNT_OFFSET + 2
_GROUP_AFFINITY_SIZE = 16


@dataclass(frozen=True)
class CpuSetEntry:
    """The subset of SYSTEM_CPU_SET_INFORMATION we care about.

    ``id`` is the CPU Set Id (NOT the processor number -- a common bug).
    ``efficiency_class`` ranks performance: on Raptor Lake the P-cores carry
    the highest class, E-cores a lower one. ``last_level_cache_index``
    identifies the LLC domain (the CCD on multi-chiplet AMD parts), and
    ``group``/``logical_index`` locate the processor for cache-mask matching.
    """

    id: int
    logical_index: int
    core_index: int
    efficiency_class: int
    group: int = 0
    last_level_cache_index: int = 0


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
            id_, group, logical_index, core_index, llc, _numa, efficiency_class, _flags = (
                struct.unpack_from("<IHBBBBBB", buf, offset + 8)
            )
            entries.append(
                CpuSetEntry(
                    id=id_,
                    logical_index=logical_index,
                    core_index=core_index,
                    efficiency_class=efficiency_class,
                    group=group,
                    last_level_cache_index=llc,
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


# ---------------------------------------------------------------------------
# L3 cache domains (AMD multi-CCD / X3D classification input)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class L3CacheDomain:
    """One L3 cache instance: its size and the processors it serves.

    ``mask`` bits are group-relative logical-processor numbers within
    ``group`` -- match them against ``CpuSetEntry.group``/``logical_index``.
    """

    size_bytes: int
    group: int
    mask: int


def _parse_cache_relationship_buffer(buf: bytes) -> list[L3CacheDomain]:
    """Extract every L3 cache instance from a RelationCache result buffer.

    Each SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX entry is walked by its Size.
    Pre-20H2 layouts without GroupCount report 0 there; treat that as one
    GROUP_AFFINITY at the same offset.
    """
    domains: list[L3CacheDomain] = []
    offset = 0
    total = len(buf)
    while offset + _LPI_EX_HEADER_SIZE <= total:
        relationship, size = struct.unpack_from("<II", buf, offset)
        if size < _LPI_EX_HEADER_SIZE or offset + size > total:
            break
        if relationship == _RELATION_CACHE and size >= _CACHE_GROUP_MASKS_OFFSET:
            level = buf[offset + _LPI_EX_HEADER_SIZE]
            (cache_size,) = struct.unpack_from("<I", buf, offset + _LPI_EX_HEADER_SIZE + 4)
            (group_count,) = struct.unpack_from("<H", buf, offset + _CACHE_GROUP_COUNT_OFFSET)
            if level == 3:
                count = max(1, group_count)
                for i in range(count):
                    mask_offset = offset + _CACHE_GROUP_MASKS_OFFSET + i * _GROUP_AFFINITY_SIZE
                    if mask_offset + _GROUP_AFFINITY_SIZE > offset + size:
                        break
                    mask, group = struct.unpack_from("<QH", buf, mask_offset)
                    if mask:
                        domains.append(
                            L3CacheDomain(size_bytes=cache_size, group=group, mask=mask)
                        )
        offset += size
    return domains


def get_l3_cache_domains(kernel32: ctypes.WinDLL | None = None) -> list[L3CacheDomain]:
    """Query live L3 cache instances via ``GetLogicalProcessorInformationEx``."""
    k = kernel32 or _kernel32()
    length = wintypes.DWORD(0)
    k.GetLogicalProcessorInformationEx(_RELATION_CACHE, None, ctypes.byref(length))
    if length.value == 0:
        return []
    buf = (ctypes.c_byte * length.value)()
    ok = k.GetLogicalProcessorInformationEx(_RELATION_CACHE, buf, ctypes.byref(length))
    if not ok:
        logger.debug("GetLogicalProcessorInformationEx(RelationCache) failed")
        return []
    return _parse_cache_relationship_buffer(bytes(buf))


def l3_size_by_llc_index(
    entries: list[CpuSetEntry], domains: list[L3CacheDomain]
) -> dict[int, int]:
    """Map each LastLevelCacheIndex to the size of the L3 serving its cores.

    A CCD's LLC index groups its CPU-set entries; the matching L3 instance is
    the one whose group mask covers those processors. On an X3D part the
    V-Cache CCD reports the (much) larger size.
    """
    sizes: dict[int, int] = {}
    for entry in entries:
        if entry.last_level_cache_index in sizes:
            continue
        for domain in domains:
            if domain.group == entry.group and (domain.mask >> entry.logical_index) & 1:
                sizes[entry.last_level_cache_index] = domain.size_bytes
                break
    return sizes


# ---------------------------------------------------------------------------
# Core partition classification (game side vs background side)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CorePartition:
    """A game/background split of the machine's CPU Set Ids.

    ``kind`` records why the split exists:
      * ``hybrid`` -- multiple efficiency classes (Intel P/E): game side is
        the top class, background side is everything else.
      * ``x3d_cache`` -- single efficiency class, multiple LLC domains with
        unequal L3 sizes (AMD X3D dual-CCD): game side is the V-Cache CCD.
      * ``symmetric_multi_ccd`` -- multiple equal LLC domains: no principled
        split, both sides empty (callers must no-op).
      * ``single`` -- one cache/efficiency domain: no split (unless
        ``smt_avoid`` selected the primary SMT threads as the game side).
      * ``none`` -- topology unavailable.
    """

    kind: str
    game_ids: tuple[int, ...] = ()
    background_ids: tuple[int, ...] = ()

    @property
    def has_game_side(self) -> bool:
        return bool(self.game_ids)

    @property
    def has_background_side(self) -> bool:
        return bool(self.background_ids)


def _primary_smt_ids(entries: list[CpuSetEntry]) -> list[int]:
    """One CPU Set Id per physical core (lowest logical index wins)."""
    best: dict[tuple[int, int], CpuSetEntry] = {}
    for entry in entries:
        key = (entry.group, entry.core_index)
        current = best.get(key)
        if current is None or entry.logical_index < current.logical_index:
            best[key] = entry
    return [e.id for e in best.values()]


def classify_partition(
    entries: list[CpuSetEntry],
    l3_sizes: dict[int, int] | None = None,
    *,
    smt_avoid: bool = False,
    allow_x3d: bool = True,
) -> CorePartition:
    """Classify the topology into a game/background CPU Set partition.

    Args:
        entries: CPU Set topology (``get_system_cpu_sets``).
        l3_sizes: Optional LLC-index -> L3-size map (``l3_size_by_llc_index``);
            only consulted for single-efficiency-class multi-LLC topologies.
        smt_avoid: Restrict the game side to one thread per physical core.
        allow_x3d: Permit the unequal-L3 (X3D cache-CCD) split. When False a
            multi-LLC part always classifies as ``symmetric_multi_ccd``.
    """
    if not entries:
        return CorePartition(kind="none")

    classes = {e.efficiency_class for e in entries}
    if len(classes) >= 2:
        top = max(classes)
        game = [e for e in entries if e.efficiency_class == top]
        background = [e.id for e in entries if e.efficiency_class != top]
        game_ids = _primary_smt_ids(game) if smt_avoid else [e.id for e in game]
        return CorePartition(
            kind="hybrid", game_ids=tuple(game_ids), background_ids=tuple(background)
        )

    llcs = {e.last_level_cache_index for e in entries}
    if len(llcs) >= 2:
        sizes = l3_sizes or {}
        known = {llc: sizes[llc] for llc in llcs if llc in sizes}
        if allow_x3d and len(known) >= 2 and max(known.values()) > min(known.values()):
            cache_llc = max(known, key=lambda llc: known[llc])
            game = [e for e in entries if e.last_level_cache_index == cache_llc]
            background = [e.id for e in entries if e.last_level_cache_index != cache_llc]
            game_ids = _primary_smt_ids(game) if smt_avoid else [e.id for e in game]
            return CorePartition(
                kind="x3d_cache",
                game_ids=tuple(game_ids),
                background_ids=tuple(background),
            )
        return CorePartition(kind="symmetric_multi_ccd")

    if smt_avoid:
        primaries = _primary_smt_ids(entries)
        if len(primaries) < len(entries):
            return CorePartition(kind="single", game_ids=tuple(primaries))
    return CorePartition(kind="single")


def get_partition(
    *,
    smt_avoid: bool = False,
    allow_x3d: bool = True,
    kernel32: ctypes.WinDLL | None = None,
) -> CorePartition:
    """Query the live topology and classify it into a CorePartition.

    The L3 cache sizes are only queried when they can matter (a single
    efficiency class spread over multiple LLC domains). On an ``x3d_cache``
    result a warning reminds that Windows Game Mode's own CCD parking can
    conflict with manual steering on Ryzen X3D parts.
    """
    entries = get_system_cpu_sets(kernel32=kernel32)
    l3_sizes: dict[int, int] | None = None
    if (
        entries
        and len({e.efficiency_class for e in entries}) < 2
        and len({e.last_level_cache_index for e in entries}) >= 2
    ):
        l3_sizes = l3_size_by_llc_index(entries, get_l3_cache_domains(kernel32=kernel32))
    partition = classify_partition(
        entries, l3_sizes, smt_avoid=smt_avoid, allow_x3d=allow_x3d
    )
    if partition.kind == "x3d_cache":
        logger.warning(
            "X3D cache-CCD partition active (%d game / %d background sets). "
            "Windows Game Mode's own CCD parking may conflict with manual "
            "steering on Ryzen X3D -- disable Game Mode if performance regresses.",
            len(partition.game_ids),
            len(partition.background_ids),
        )
    else:
        logger.debug(
            "Core partition: kind=%s game=%d background=%d",
            partition.kind,
            len(partition.game_ids),
            len(partition.background_ids),
        )
    return partition


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
        k.GetLogicalProcessorInformationEx.restype = wintypes.BOOL
        k.GetLogicalProcessorInformationEx.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
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


def steer_process_to_sets(
    pid: int, cpu_set_ids: list[int] | tuple[int, ...], *, kernel32: ctypes.WinDLL | None = None
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


def steer_process_to_pcores(
    pid: int, cpu_set_ids: list[int], *, kernel32: ctypes.WinDLL | None = None
) -> bool:
    """Back-compat alias for :func:`steer_process_to_sets` (P-core steering)."""
    return steer_process_to_sets(pid, cpu_set_ids, kernel32=kernel32)


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
