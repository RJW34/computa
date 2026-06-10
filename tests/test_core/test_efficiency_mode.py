"""Hermetic tests for EcoQoS efficiency-mode herding (Tier B scaffold).

No real process is throttled: the Win32 layer is injected. Tests cover the
mode->mask mapping, the OpenProcess/Set/Close call flow, and the herder's
inclusion/exclusion decisions and reset bookkeeping.
"""

from __future__ import annotations

import pytest

from abso.core import efficiency_mode as em
from abso.core.efficiency_mode import (
    PROCESS_POWER_THROTTLING,
    PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
    EcoQosHerder,
    set_process_eco_qos,
)


class _FakeKernel32:
    """Records OpenProcess/SetProcessInformation/CloseHandle calls."""

    def __init__(self, *, open_handle: int = 0x1234, set_ok: int = 1) -> None:
        self._open_handle = open_handle
        self._set_ok = set_ok
        self.set_calls: list[tuple] = []
        self.closed: list[int] = []

    def OpenProcess(self, access, inherit, pid):  # noqa: N802
        self.last_open = (access, inherit, pid)
        return self._open_handle

    def SetProcessInformation(self, handle, info_class, ptr, size):  # noqa: N802
        self.set_calls.append((handle, info_class, size))
        return self._set_ok

    def CloseHandle(self, handle):  # noqa: N802
        self.closed.append(handle)
        return 1


class TestStateMasks:
    def test_eco_mode_throttles_execution_speed(self) -> None:
        state = em._build_throttling_state("eco")
        assert state.ControlMask == PROCESS_POWER_THROTTLING_EXECUTION_SPEED
        assert state.StateMask == PROCESS_POWER_THROTTLING_EXECUTION_SPEED
        assert state.Version == em.PROCESS_POWER_THROTTLING_CURRENT_VERSION

    def test_high_mode_forces_high_qos(self) -> None:
        state = em._build_throttling_state("high")
        assert state.ControlMask == PROCESS_POWER_THROTTLING_EXECUTION_SPEED
        assert state.StateMask == 0

    def test_reset_mode_returns_to_system_management(self) -> None:
        state = em._build_throttling_state("reset")
        assert state.ControlMask == 0
        assert state.StateMask == 0


class TestSetProcessEcoQos:
    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            set_process_eco_qos(1234, "bogus", kernel32=_FakeKernel32())

    def test_success_flow_opens_sets_and_closes(self) -> None:
        fake = _FakeKernel32(open_handle=0xABCD, set_ok=1)
        assert set_process_eco_qos(4321, "eco", kernel32=fake) is True
        assert fake.last_open[2] == 4321
        assert len(fake.set_calls) == 1
        assert fake.set_calls[0][1] == PROCESS_POWER_THROTTLING
        assert fake.closed == [0xABCD]

    def test_open_failure_returns_false_without_set(self) -> None:
        fake = _FakeKernel32(open_handle=0)  # OpenProcess failed
        assert set_process_eco_qos(4321, "eco", kernel32=fake) is False
        assert fake.set_calls == []
        assert fake.closed == []  # nothing to close

    def test_set_failure_returns_false_but_closes(self) -> None:
        fake = _FakeKernel32(open_handle=0x5, set_ok=0)
        assert set_process_eco_qos(4321, "eco", kernel32=fake) is False
        assert fake.closed == [0x5]


class TestEcoQosHerder:
    def _herder(self, processes, background, **kw):
        calls: list[tuple[int, str]] = []

        def setter(pid, mode):
            calls.append((pid, mode))
            return True

        herder = EcoQosHerder(
            game_pid=1000,
            background_images=background,
            lister=lambda: processes,
            setter=setter,
            foreground_pid_getter=lambda: 2000,
            **kw,
        )
        return herder, calls

    def test_throttles_only_background_images(self) -> None:
        procs = [(1000, "game.exe"), (3000, "updater.exe"), (3001, "randomapp.exe")]
        herder, calls = self._herder(procs, ["updater.exe"])
        assert herder.herd() == 1
        assert calls == [(3000, "eco")]
        assert herder.throttled_pids == frozenset({3000})

    def test_skips_game_and_foreground_and_low_pids(self) -> None:
        procs = [(1000, "updater.exe"), (2000, "updater.exe"), (4, "updater.exe"), (3000, "updater.exe")]
        herder, calls = self._herder(procs, ["updater.exe"])
        herder.herd()
        # game pid 1000, foreground 2000, low pid 4 all skipped; only 3000 acted on.
        assert [pid for pid, _ in calls] == [3000]

    def test_never_eco_images_are_protected(self) -> None:
        # Discord + an anti-cheat image must never be throttled even if listed.
        procs = [(3000, "Discord.exe"), (3001, "EasyAntiCheat.exe"), (3002, "updater.exe")]
        herder, calls = self._herder(procs, ["discord.exe", "easyanticheat.exe", "updater.exe"])
        herder.herd()
        assert [pid for pid, _ in calls] == [3002]

    def test_release_all_resets_touched(self) -> None:
        procs = [(3000, "updater.exe")]
        herder, calls = self._herder(procs, ["updater.exe"])
        herder.herd()
        calls.clear()
        herder.release_all()
        assert calls == [(3000, "reset")]
        assert herder.throttled_pids == frozenset()

    def test_empty_background_is_noop(self) -> None:
        procs = [(3000, "updater.exe")]
        herder, calls = self._herder(procs, [])
        assert herder.herd() == 0
        assert calls == []

    def test_herd_is_idempotent_on_already_throttled(self) -> None:
        procs = [(3000, "updater.exe")]
        herder, calls = self._herder(procs, ["updater.exe"])
        herder.herd()
        herder.herd()  # second pass: already throttled, no new call
        assert calls == [(3000, "eco")]


class TestNeverEcoSet:
    def test_includes_anti_cheat_and_capture_tools(self) -> None:
        assert "easyanticheat.exe" in em.NEVER_ECO_IMAGES
        assert "discord.exe" in em.NEVER_ECO_IMAGES
        assert "obs64.exe" in em.NEVER_ECO_IMAGES  # capture tool


class TestEnabledGate:
    def test_disabled_by_default(self, monkeypatch) -> None:
        class _Eco:
            enabled = False

        class _Cfg:
            efficiency_mode = _Eco()

        import abso.core.config as config_mod

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        assert em.efficiency_mode_enabled() is False

    def test_enabled_when_configured(self, monkeypatch) -> None:
        class _Eco:
            enabled = True

        class _Cfg:
            efficiency_mode = _Eco()

        import abso.core.config as config_mod

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        assert em.efficiency_mode_enabled() is True
