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


def _pack_entry(id_: int, logical_index: int, efficiency_class: int, *, type_: int = 0) -> bytes:
    """Pack one 32-byte SYSTEM_CPU_SET_INFORMATION entry."""
    return struct.pack(
        "<IIIHBBBBBBIQ",
        32,  # Size
        type_,  # Type (0 = CpuSetInformation)
        id_,  # Id
        0,  # Group
        logical_index,  # LogicalProcessorIndex
        0,  # CoreIndex
        0,  # LastLevelCacheIndex
        0,  # NumaNodeIndex
        efficiency_class,  # EfficiencyClass
        0,  # AllFlags
        0,  # Reserved/SchedulingClass
        0,  # AllocationTag
    )


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
