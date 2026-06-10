"""Hermetic tests for Win32 process-action primitives (watchdog mechanism)."""

from __future__ import annotations

from abso.core import proc_actions as pa
from abso.core.proc_actions import (
    BELOW_NORMAL_PRIORITY_CLASS,
    NORMAL_PRIORITY_CLASS,
    get_priority_class,
    get_working_set_mb,
    set_priority_class,
    trim_working_set,
)


class _FakeKernel32:
    def __init__(
        self,
        *,
        open_handle: int = 0x10,
        priority: int = NORMAL_PRIORITY_CLASS,
        set_ok: int = 1,
        empty_ok: int = 1,
        ws_bytes: int = 50 * 1024 * 1024,
        meminfo_ok: int = 1,
    ) -> None:
        self._open_handle = open_handle
        self._priority = priority
        self._set_ok = set_ok
        self._empty_ok = empty_ok
        self._ws_bytes = ws_bytes
        self._meminfo_ok = meminfo_ok
        self.set_calls: list[int] = []
        self.closed: list[int] = []
        self.emptied = False
        self.last_access: int | None = None

    def OpenProcess(self, access, inherit, pid):  # noqa: N802
        self.last_access = access
        return self._open_handle

    def CloseHandle(self, handle):  # noqa: N802
        self.closed.append(handle)
        return 1

    def GetPriorityClass(self, handle):  # noqa: N802
        return self._priority

    def SetPriorityClass(self, handle, cls):  # noqa: N802
        self.set_calls.append(cls)
        return self._set_ok

    def K32EmptyWorkingSet(self, handle):  # noqa: N802
        self.emptied = True
        return self._empty_ok

    def K32GetProcessMemoryInfo(self, handle, ptr, cb):  # noqa: N802
        ptr.contents.WorkingSetSize = self._ws_bytes
        return self._meminfo_ok


class TestPriority:
    def test_get_priority(self) -> None:
        fake = _FakeKernel32(priority=BELOW_NORMAL_PRIORITY_CLASS)
        assert get_priority_class(123, kernel32=fake) == BELOW_NORMAL_PRIORITY_CLASS
        assert fake.last_access == pa.PROCESS_QUERY_LIMITED_INFORMATION

    def test_get_priority_open_fail(self) -> None:
        fake = _FakeKernel32(open_handle=0)
        assert get_priority_class(123, kernel32=fake) is None

    def test_set_priority(self) -> None:
        fake = _FakeKernel32()
        assert set_priority_class(123, BELOW_NORMAL_PRIORITY_CLASS, kernel32=fake) is True
        assert fake.set_calls == [BELOW_NORMAL_PRIORITY_CLASS]
        assert fake.closed == [0x10]

    def test_set_priority_open_fail(self) -> None:
        fake = _FakeKernel32(open_handle=0)
        assert set_priority_class(123, NORMAL_PRIORITY_CLASS, kernel32=fake) is False
        assert fake.set_calls == []


class TestTrim:
    def test_trim_success(self) -> None:
        fake = _FakeKernel32()
        assert trim_working_set(123, kernel32=fake) is True
        assert fake.emptied is True
        assert fake.closed == [0x10]

    def test_trim_open_fail(self) -> None:
        fake = _FakeKernel32(open_handle=0)
        assert trim_working_set(123, kernel32=fake) is False
        assert fake.emptied is False


class TestWorkingSet:
    def test_working_set_mb(self) -> None:
        fake = _FakeKernel32(ws_bytes=128 * 1024 * 1024)
        assert get_working_set_mb(123, kernel32=fake) == 128.0

    def test_working_set_open_fail(self) -> None:
        fake = _FakeKernel32(open_handle=0)
        assert get_working_set_mb(123, kernel32=fake) is None

    def test_working_set_query_fail(self) -> None:
        fake = _FakeKernel32(meminfo_ok=0)
        assert get_working_set_mb(123, kernel32=fake) is None
