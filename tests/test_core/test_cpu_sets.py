"""Hermetic tests for CPU Sets soft P-core steering (Tier B scaffold).

No real CPU Set is applied: the Win32 layer is injected. Tests focus on the
buffer parser, the P-core classifier (incl. the non-hybrid no-op), and the
OpenProcess/Set/Close call flow.
"""

from __future__ import annotations

import struct

from abso.core import cpu_sets as cs
from abso.core.cpu_sets import (
    CpuSetEntry,
    classify_pcore_ids,
    clear_process_cpu_sets,
    steer_process_to_pcores,
)


def _pack_entry(
    id_: int,
    logical_index: int,
    efficiency_class: int,
    *,
    type_: int = 0,
    group: int = 0,
    core_index: int = 0,
    llc: int = 0,
) -> bytes:
    """Pack one 32-byte SYSTEM_CPU_SET_INFORMATION entry."""
    return struct.pack(
        "<IIIHBBBBBBIQ",
        32,  # Size
        type_,  # Type (0 = CpuSetInformation)
        id_,  # Id
        group,  # Group
        logical_index,  # LogicalProcessorIndex
        core_index,  # CoreIndex
        llc,  # LastLevelCacheIndex
        0,  # NumaNodeIndex
        efficiency_class,  # EfficiencyClass
        0,  # AllFlags
        0,  # Reserved/SchedulingClass
        0,  # AllocationTag
    )


def _pack_cache_entry(
    level: int,
    cache_size: int,
    masks: list[tuple[int, int]],
    *,
    relationship: int = 2,
) -> bytes:
    """Pack one SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX RelationCache entry.

    ``masks`` is a list of ``(mask, group)`` GROUP_AFFINITY tuples.
    """
    body = struct.pack(
        "<BBHII",
        level,  # Level
        8,  # Associativity
        64,  # LineSize
        cache_size,  # CacheSize
        0,  # Type (unified)
    )
    body += b"\x00" * 18  # Reserved
    body += struct.pack("<H", len(masks))  # GroupCount
    for mask, group in masks:
        body += struct.pack("<QHHHH", mask, group, 0, 0, 0)
    header = struct.pack("<II", relationship, 8 + len(body))
    return header + body


class _FakeKernel32:
    def __init__(self, *, open_handle: int = 0x1234, set_ok: int = 1) -> None:
        self._open_handle = open_handle
        self._set_ok = set_ok
        self.set_calls: list[tuple] = []
        self.closed: list[int] = []

    def OpenProcess(self, access, inherit, pid):  # noqa: N802
        self.last_open = (access, inherit, pid)
        return self._open_handle

    def SetProcessDefaultCpuSets(self, handle, arr, count):  # noqa: N802
        self.set_calls.append((handle, count))
        return self._set_ok

    def CloseHandle(self, handle):  # noqa: N802
        self.closed.append(handle)
        return 1


class TestParseBuffer:
    def test_parses_multiple_entries(self) -> None:
        buf = _pack_entry(256, 0, 1) + _pack_entry(257, 1, 0)
        entries = cs._parse_cpu_set_buffer(buf)
        assert [e.id for e in entries] == [256, 257]
        assert [e.efficiency_class for e in entries] == [1, 0]
        assert [e.logical_index for e in entries] == [0, 1]

    def test_skips_non_cpuset_type(self) -> None:
        buf = _pack_entry(256, 0, 1, type_=99) + _pack_entry(257, 1, 0)
        entries = cs._parse_cpu_set_buffer(buf)
        assert [e.id for e in entries] == [257]

    def test_empty_buffer(self) -> None:
        assert cs._parse_cpu_set_buffer(b"") == []

    def test_truncated_trailing_entry_is_ignored(self) -> None:
        buf = _pack_entry(256, 0, 1) + b"\x20\x00\x00\x00"  # claims size 32 but short
        entries = cs._parse_cpu_set_buffer(buf)
        assert [e.id for e in entries] == [256]


class TestClassify:
    def test_hybrid_returns_high_class_ids(self) -> None:
        entries = [
            CpuSetEntry(id=256, logical_index=0, core_index=0, efficiency_class=1),  # P
            CpuSetEntry(id=257, logical_index=1, core_index=1, efficiency_class=1),  # P
            CpuSetEntry(id=258, logical_index=2, core_index=2, efficiency_class=0),  # E
        ]
        assert classify_pcore_ids(entries) == [256, 257]

    def test_non_hybrid_returns_empty(self) -> None:
        entries = [
            CpuSetEntry(id=256, logical_index=0, core_index=0, efficiency_class=0),
            CpuSetEntry(id=257, logical_index=1, core_index=1, efficiency_class=0),
        ]
        assert classify_pcore_ids(entries) == []

    def test_empty_returns_empty(self) -> None:
        assert classify_pcore_ids([]) == []


class TestSteer:
    def test_empty_ids_is_safe_noop(self) -> None:
        fake = _FakeKernel32()
        assert steer_process_to_pcores(1234, [], kernel32=fake) is False
        assert fake.set_calls == []  # never opened the process

    def test_success_flow(self) -> None:
        fake = _FakeKernel32(open_handle=0xAA, set_ok=1)
        assert steer_process_to_pcores(1234, [256, 257], kernel32=fake) is True
        assert fake.last_open == (cs.PROCESS_SET_LIMITED_INFORMATION, False, 1234)
        assert fake.set_calls == [(0xAA, 2)]
        assert fake.closed == [0xAA]

    def test_open_failure_returns_false(self) -> None:
        fake = _FakeKernel32(open_handle=0)
        assert steer_process_to_pcores(1234, [256], kernel32=fake) is False
        assert fake.set_calls == []

    def test_clear_resets_cpu_sets(self) -> None:
        fake = _FakeKernel32(open_handle=0xBB)
        assert clear_process_cpu_sets(1234, kernel32=fake) is True
        assert fake.set_calls == [(0xBB, 0)]  # null array, count 0
        assert fake.closed == [0xBB]


def _entry(
    id_: int,
    *,
    eff: int = 0,
    llc: int = 0,
    core: int | None = None,
    logical: int | None = None,
    group: int = 0,
) -> CpuSetEntry:
    logical_index = logical if logical is not None else id_ - 256
    core_index = core if core is not None else logical_index
    return CpuSetEntry(
        id=id_,
        logical_index=logical_index,
        core_index=core_index,
        efficiency_class=eff,
        group=group,
        last_level_cache_index=llc,
    )


class TestParseCacheBuffer:
    def test_extracts_l3_domains_only(self) -> None:
        buf = (
            _pack_cache_entry(2, 1024, [(0xF, 0)])  # L2: ignored
            + _pack_cache_entry(3, 96 * 1024 * 1024, [(0xFFFF, 0)])
            + _pack_cache_entry(3, 32 * 1024 * 1024, [(0xFFFF0000, 0)])
        )
        domains = cs._parse_cache_relationship_buffer(buf)
        assert [(d.size_bytes, d.mask) for d in domains] == [
            (96 * 1024 * 1024, 0xFFFF),
            (32 * 1024 * 1024, 0xFFFF0000),
        ]

    def test_skips_non_cache_relationships(self) -> None:
        buf = _pack_cache_entry(3, 1, [(0x1, 0)], relationship=0)
        assert cs._parse_cache_relationship_buffer(buf) == []

    def test_multiple_group_masks(self) -> None:
        buf = _pack_cache_entry(3, 64, [(0x3, 0), (0xC, 1)])
        domains = cs._parse_cache_relationship_buffer(buf)
        assert [(d.group, d.mask) for d in domains] == [(0, 0x3), (1, 0xC)]

    def test_empty_and_truncated(self) -> None:
        assert cs._parse_cache_relationship_buffer(b"") == []
        assert cs._parse_cache_relationship_buffer(b"\x02\x00\x00\x00") == []


class TestL3SizeByLlc:
    def test_maps_llc_index_to_matching_domain_size(self) -> None:
        entries = [
            _entry(256, llc=0, logical=0),
            _entry(257, llc=0, logical=1),
            _entry(258, llc=1, logical=16),
            _entry(259, llc=1, logical=17),
        ]
        domains = [
            cs.L3CacheDomain(size_bytes=96, group=0, mask=0xFFFF),
            cs.L3CacheDomain(size_bytes=32, group=0, mask=0xFFFF0000),
        ]
        assert cs.l3_size_by_llc_index(entries, domains) == {0: 96, 1: 32}

    def test_group_mismatch_is_skipped(self) -> None:
        entries = [_entry(256, llc=0, logical=0, group=1)]
        domains = [cs.L3CacheDomain(size_bytes=96, group=0, mask=0x1)]
        assert cs.l3_size_by_llc_index(entries, domains) == {}


class TestClassifyPartition:
    def test_hybrid_splits_by_efficiency_class(self) -> None:
        entries = [
            _entry(256, eff=1),
            _entry(257, eff=1),
            _entry(258, eff=0),
            _entry(259, eff=0),
        ]
        p = cs.classify_partition(entries)
        assert p.kind == "hybrid"
        assert p.game_ids == (256, 257)
        assert p.background_ids == (258, 259)
        assert p.has_game_side and p.has_background_side

    def test_x3d_cache_ccd_is_game_side(self) -> None:
        entries = [
            _entry(256, llc=0),
            _entry(257, llc=0),
            _entry(258, llc=1),
            _entry(259, llc=1),
        ]
        p = cs.classify_partition(entries, {0: 32 << 20, 1: 96 << 20})
        assert p.kind == "x3d_cache"
        assert p.game_ids == (258, 259)  # bigger L3 = V-Cache CCD
        assert p.background_ids == (256, 257)

    def test_symmetric_multi_ccd_never_splits(self) -> None:
        entries = [_entry(256, llc=0), _entry(257, llc=1)]
        p = cs.classify_partition(entries, {0: 32 << 20, 1: 32 << 20})
        assert p.kind == "symmetric_multi_ccd"
        assert not p.has_game_side and not p.has_background_side

    def test_multi_llc_without_sizes_never_splits(self) -> None:
        entries = [_entry(256, llc=0), _entry(257, llc=1)]
        p = cs.classify_partition(entries)
        assert p.kind == "symmetric_multi_ccd"
        assert not p.has_game_side

    def test_x3d_disallowed_never_splits(self) -> None:
        entries = [_entry(256, llc=0), _entry(257, llc=1)]
        p = cs.classify_partition(entries, {0: 32, 1: 96}, allow_x3d=False)
        assert p.kind == "symmetric_multi_ccd"
        assert not p.has_game_side

    def test_single_domain_never_splits(self) -> None:
        p = cs.classify_partition([_entry(256), _entry(257)])
        assert p.kind == "single"
        assert not p.has_game_side and not p.has_background_side

    def test_empty_topology(self) -> None:
        assert cs.classify_partition([]).kind == "none"

    def test_smt_avoid_picks_one_thread_per_core(self) -> None:
        entries = [
            _entry(256, eff=1, core=0, logical=0),
            _entry(257, eff=1, core=0, logical=1),  # HT sibling
            _entry(258, eff=1, core=1, logical=2),
            _entry(259, eff=0, core=2, logical=3),
        ]
        p = cs.classify_partition(entries, smt_avoid=True)
        assert p.kind == "hybrid"
        assert sorted(p.game_ids) == [256, 258]
        assert p.background_ids == (259,)

    def test_smt_avoid_on_single_domain_selects_primaries(self) -> None:
        entries = [
            _entry(256, core=0, logical=0),
            _entry(257, core=0, logical=1),
            _entry(258, core=1, logical=2),
        ]
        p = cs.classify_partition(entries, smt_avoid=True)
        assert p.kind == "single"
        assert sorted(p.game_ids) == [256, 258]
        assert p.background_ids == ()


class TestGetPartition:
    def test_composes_topology_and_cache_sizes(self, monkeypatch) -> None:
        entries = [_entry(256, llc=0, logical=0), _entry(257, llc=1, logical=1)]
        monkeypatch.setattr(cs, "get_system_cpu_sets", lambda **kw: entries)
        monkeypatch.setattr(
            cs,
            "get_l3_cache_domains",
            lambda **kw: [
                cs.L3CacheDomain(size_bytes=96, group=0, mask=0x1),
                cs.L3CacheDomain(size_bytes=32, group=0, mask=0x2),
            ],
        )
        p = cs.get_partition()
        assert p.kind == "x3d_cache"
        assert p.game_ids == (256,)

    def test_hybrid_skips_cache_query(self, monkeypatch) -> None:
        entries = [_entry(256, eff=1), _entry(257, eff=0)]
        monkeypatch.setattr(cs, "get_system_cpu_sets", lambda **kw: entries)

        def boom(**kw):
            raise AssertionError("cache query should not run for hybrid")

        monkeypatch.setattr(cs, "get_l3_cache_domains", boom)
        assert cs.get_partition().kind == "hybrid"

    def test_steer_process_to_sets_alias(self) -> None:
        fake = _FakeKernel32(open_handle=0xCC)
        assert cs.steer_process_to_sets(99, (300, 301), kernel32=fake) is True
        assert fake.set_calls == [(0xCC, 2)]


class TestEnabledGate:
    def test_disabled_by_default(self, monkeypatch) -> None:
        class _Sets:
            enabled = False

        class _Cfg:
            cpu_sets = _Sets()

        import abso.core.config as config_mod

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        assert cs.cpu_sets_enabled() is False

    def test_enabled_when_configured(self, monkeypatch) -> None:
        class _Sets:
            enabled = True

        class _Cfg:
            cpu_sets = _Sets()

        import abso.core.config as config_mod

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        assert cs.cpu_sets_enabled() is True
