"""Hermetic tests for the reversible CPU limiter (Tier B scaffold)."""

from __future__ import annotations

from abso.core import cpu_limiter as cl
from abso.core.cpu_limiter import CpuLimiter, shrink_mask


class TestShrinkMask:
    def test_picks_lowest_bits(self) -> None:
        # 8-core system, keep 2 -> two lowest cores.
        assert shrink_mask(0xFF, 2) == 0b11

    def test_respects_sparse_system_mask(self) -> None:
        # System has cores 1 and 3 only (mask 0b1010); keep 1 -> lowest set bit.
        assert shrink_mask(0b1010, 1) == 0b10

    def test_keep_zero_is_noop(self) -> None:
        assert shrink_mask(0xFF, 0) == 0

    def test_empty_system_is_noop(self) -> None:
        assert shrink_mask(0, 4) == 0

    def test_keep_more_than_available_returns_all(self) -> None:
        assert shrink_mask(0b111, 10) == 0b111


class _FakeAffinity:
    """Injectable getter/setter recording set calls."""

    def __init__(self, proc_mask: int, sys_mask: int, *, set_ok: bool = True) -> None:
        self._masks: tuple[int, int] | None = (proc_mask, sys_mask)
        self._set_ok = set_ok
        self.set_calls: list[tuple[int, int]] = []

    def getter(self, pid):
        return self._masks

    def setter(self, pid, mask):
        self.set_calls.append((pid, mask))
        return self._set_ok


class TestCpuLimiter:
    def test_limit_shrinks_and_snapshots(self) -> None:
        fake = _FakeAffinity(proc_mask=0xFF, sys_mask=0xFF)
        limiter = CpuLimiter(keep_cores=2, getter=fake.getter, setter=fake.setter)
        assert limiter.limit(5000) is True
        assert fake.set_calls == [(5000, 0b11)]
        assert limiter.limited_pids == frozenset({5000})

    def test_restore_returns_original_mask(self) -> None:
        fake = _FakeAffinity(proc_mask=0xFF, sys_mask=0xFF)
        limiter = CpuLimiter(keep_cores=2, getter=fake.getter, setter=fake.setter)
        limiter.limit(5000)
        fake.set_calls.clear()
        assert limiter.restore(5000) is True
        assert fake.set_calls == [(5000, 0xFF)]
        assert limiter.limited_pids == frozenset()

    def test_limit_noop_when_already_at_target(self) -> None:
        # proc mask already equals the shrink target -> no change.
        fake = _FakeAffinity(proc_mask=0b11, sys_mask=0xFF)
        limiter = CpuLimiter(keep_cores=2, getter=fake.getter, setter=fake.setter)
        assert limiter.limit(5000) is False
        assert fake.set_calls == []

    def test_limit_noop_when_process_unreadable(self) -> None:
        fake = _FakeAffinity(0, 0)
        fake._masks = None  # GetProcessAffinityMask failed
        limiter = CpuLimiter(getter=fake.getter, setter=fake.setter)
        assert limiter.limit(5000) is False

    def test_restore_unknown_pid_is_false(self) -> None:
        fake = _FakeAffinity(0xFF, 0xFF)
        limiter = CpuLimiter(getter=fake.getter, setter=fake.setter)
        assert limiter.restore(9999) is False

    def test_restore_all(self) -> None:
        fake = _FakeAffinity(proc_mask=0xFF, sys_mask=0xFF)
        limiter = CpuLimiter(keep_cores=1, getter=fake.getter, setter=fake.setter)
        limiter.limit(1), limiter.limit(2)
        fake.set_calls.clear()
        limiter.restore_all()
        assert sorted(fake.set_calls) == [(1, 0xFF), (2, 0xFF)]
        assert limiter.limited_pids == frozenset()


class TestEnabledGate:
    def test_disabled_by_default(self, monkeypatch) -> None:
        class _Lim:
            enabled = False

        class _Cfg:
            cpu_limiter = _Lim()

        import abso.core.config as config_mod

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        assert cl.cpu_limiter_enabled() is False
