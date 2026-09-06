"""Hermetic tests for the ProBalance-style CPU balancer.

These never mutate real process priorities: they construct a balancer and
exercise the pure decision helpers (exclusion set, stop-sentinel, config
translation). The kernel32/user32 handles load on Windows but no
restrain/release is performed against any real process.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from abso.core import cpu_balancer as cb
from abso.core.cpu_balancer import CpuBalancer, CpuBalancerConfig


def _make_balancer(**kwargs) -> CpuBalancer:
    return CpuBalancer(game_pid=4242, config=CpuBalancerConfig(), **kwargs)


class TestExclusions:
    def test_os_critical_process_excluded(self) -> None:
        bal = _make_balancer()
        assert bal._is_excluded("dwm.exe", 9001) is True

    def test_game_pid_excluded(self) -> None:
        bal = _make_balancer()
        assert bal._is_excluded("anything.exe", 4242) is True

    def test_low_pids_excluded(self) -> None:
        bal = _make_balancer()
        assert bal._is_excluded("whatever.exe", 4) is True

    def test_anti_cheat_excluded_via_extra(self) -> None:
        bal = _make_balancer(extra_excluded={"easyanticheat.exe", "beservice.exe"})
        assert bal._is_excluded("EasyAntiCheat.exe", 5555) is True
        assert bal._is_excluded("BEService.exe", 5556) is True

    def test_extra_excluded_is_case_insensitive(self) -> None:
        bal = _make_balancer(extra_excluded={"MyApp.EXE"})
        assert bal._is_excluded("myapp.exe", 6000) is True

    def test_unprotected_process_not_excluded(self) -> None:
        bal = _make_balancer()
        # A random background app at a high PID is a valid restrain target.
        assert bal._is_excluded("randomupdater.exe", 31337) is False

    def test_game_descendants_excluded(self) -> None:
        """A child process of the game (e.g. anti-cheat broker) is never demoted."""
        bal = _make_balancer()  # game_pid=4242
        # 5000 is a direct child of the game; 5001 is a grandchild.
        descendants = bal._compute_game_descendants({5000: 4242, 5001: 5000, 9999: 1})
        assert 5000 in descendants
        assert 5001 in descendants
        assert 9999 not in descendants
        assert bal._is_excluded("EAC-broker.exe", 5001, descendants) is True
        # Without the descendant set, the same PID is a normal restrain target.
        assert bal._is_excluded("EAC-broker.exe", 5001) is False


class TestStopSentinel:
    def test_stop_requested_false_without_file(self) -> None:
        bal = _make_balancer()
        assert bal._stop_requested() is False

    def test_stop_requested_true_when_file_present(self, tmp_path) -> None:
        sentinel = tmp_path / "stop.flag"
        bal = _make_balancer(stop_file=sentinel)
        assert bal._stop_requested() is False
        sentinel.write_text("stop")
        assert bal._stop_requested() is True

    def test_stop_requested_true_after_stop_call(self) -> None:
        bal = _make_balancer()
        bal.stop()
        assert bal._stop_requested() is True


class TestRuntimeConfigTranslation:
    def test_cli_overrides_win(self) -> None:
        user = CpuBalancerConfig(system_cpu_threshold=55, process_cpu_threshold=8)
        cfg = cb._build_runtime_config_from_user(
            user, system_threshold=70, process_threshold=None
        )
        assert cfg.system_cpu_threshold == 70  # explicit override wins
        assert cfg.process_cpu_threshold == 8  # falls back to user config

    def test_excluded_processes_carried_over(self) -> None:
        user = CpuBalancerConfig(excluded_processes=["foo.exe"])
        cfg = cb._build_runtime_config_from_user(user)
        assert "foo.exe" in cfg.excluded_processes


class TestGatherExtraExcluded:
    def test_includes_anti_cheat_from_never_kill(self, monkeypatch) -> None:
        class _Overrides:
            protect: list[str] = []

        class _Cfg:
            process_overrides = _Overrides()

        import abso.core.config as config_mod

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        excluded = cb._gather_extra_excluded()
        assert "easyanticheat.exe" in excluded
        assert "beservice.exe" in excluded

    def test_includes_user_protect_list(self, monkeypatch) -> None:
        class _Overrides:
            protect = ["lghub.exe"]

        class _Cfg:
            process_overrides = _Overrides()

        import abso.core.config as config_mod

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        excluded = cb._gather_extra_excluded()
        assert "lghub.exe" in excluded


class TestSessionExtras:
    """Tier B behaviors hosted in the daemon: off by default, isolated on error."""

    def test_extras_off_is_noop(self) -> None:
        bal = _make_balancer()  # enable_cpu_sets / enable_eco default False
        bal._start_session_extras()
        assert bal._eco_herder is None
        bal._stop_session_extras()  # must not raise

    def test_cpu_sets_steer_on_start(self, monkeypatch) -> None:
        import abso.core.cpu_sets as cs

        calls: dict = {}

        def fake_steer(pid, ids):
            calls["steer"] = (pid, ids)
            return True

        monkeypatch.setattr(cs, "get_pcore_cpu_set_ids", lambda: [256, 257])
        monkeypatch.setattr(cs, "steer_process_to_pcores", fake_steer)

        bal = CpuBalancer(game_pid=4242, config=CpuBalancerConfig(), enable_cpu_sets=True)
        bal._start_session_extras()
        assert calls["steer"] == (4242, [256, 257])

    def test_cpu_sets_clear_on_stop(self, monkeypatch) -> None:
        import abso.core.cpu_sets as cs

        cleared: dict = {}

        def fake_clear(pid):
            cleared["pid"] = pid
            return True

        monkeypatch.setattr(cs, "clear_process_cpu_sets", fake_clear)
        bal = CpuBalancer(game_pid=4242, config=CpuBalancerConfig(), enable_cpu_sets=True)
        bal._stop_session_extras()
        assert cleared["pid"] == 4242

    def test_eco_herder_created_and_released(self) -> None:
        bal = CpuBalancer(
            game_pid=4242, config=CpuBalancerConfig(), enable_eco=True, eco_images=["updater.exe"]
        )
        bal._start_session_extras()
        assert bal._eco_herder is not None
        bal._stop_session_extras()
        assert bal._eco_herder is None

    def test_extras_failure_is_isolated(self, monkeypatch) -> None:
        import abso.core.cpu_sets as cs

        def boom():
            raise RuntimeError("topology query exploded")

        monkeypatch.setattr(cs, "get_pcore_cpu_set_ids", boom)
        bal = CpuBalancer(game_pid=4242, config=CpuBalancerConfig(), enable_cpu_sets=True)
        bal._start_session_extras()  # exception swallowed -> core loop safe


class TestResolveSessionExtras:
    def test_cli_flags_enable(self, monkeypatch) -> None:
        import abso.core.config as config_mod

        class _CpuSets:
            enabled = False

        class _Eco:
            enabled = False
            background_images: list[str] = []

        class _Cfg:
            cpu_sets = _CpuSets()
            efficiency_mode = _Eco()

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        cs_on, eco_on, imgs = cb._resolve_session_extras(cpu_sets_flag=True, eco_flag=False)
        assert cs_on is True
        assert eco_on is False

    def test_config_flags_enable(self, monkeypatch) -> None:
        import abso.core.config as config_mod

        class _CpuSets:
            enabled = False

        class _Eco:
            enabled = True
            background_images = ["updater.exe"]

        class _Cfg:
            cpu_sets = _CpuSets()
            efficiency_mode = _Eco()

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        cs_on, eco_on, imgs = cb._resolve_session_extras(cpu_sets_flag=False, eco_flag=False)
        assert eco_on is True
        assert imgs == ["updater.exe"]


class TestWatchdogIntegration:
    def _rule(self, **kw):
        from abso.core.config import WatchdogRule

        base = {"match": "x.exe", "metric": "cpu", "threshold": 50.0, "sustain_s": 1.0, "action": "demote"}
        base.update(kw)
        return WatchdogRule(**base)

    def test_off_is_noop(self) -> None:
        bal = _make_balancer()
        bal._start_session_extras()
        assert bal._watchdog_engine is None
        bal._stop_session_extras()

    def test_engine_built_and_restored(self) -> None:
        bal = CpuBalancer(
            game_pid=4242, config=CpuBalancerConfig(),
            enable_watchdog=True, watchdog_rules=[self._rule()],
        )
        bal._start_session_extras()
        assert bal._watchdog_engine is not None
        assert bal._watchdog_engine.active_rule_count == 1
        bal._stop_session_extras()
        assert bal._watchdog_engine is None

    def test_online_restricts_to_demote_only(self) -> None:
        bal = CpuBalancer(
            game_pid=4242, config=CpuBalancerConfig(),
            enable_watchdog=True, watchdog_rules=[self._rule(action="throttle")], is_online=True,
        )
        bal._start_session_extras()
        # A throttle rule is dropped for online profiles.
        assert bal._watchdog_engine.active_rule_count == 0
        bal._stop_session_extras()

    def test_separate_cpu_store_does_not_corrupt_restraint(self) -> None:
        bal = _make_balancer()
        # The watchdog store is distinct from the restraint store.
        assert bal._watchdog_cpu_times is not bal._last_process_times


class TestResolveWatchdog:
    def _cfg(self, *, enabled, rules, keep_cores):
        class _Watchdog:
            pass

        class _Limiter:
            pass

        wd = _Watchdog()
        wd.enabled = enabled
        wd.rules = rules
        lim = _Limiter()
        lim.keep_cores = keep_cores

        class _Cfg:
            watchdog = wd
            cpu_limiter = lim

        return _Cfg()

    def test_flag_enables(self, monkeypatch) -> None:
        import abso.core.config as config_mod

        monkeypatch.setattr(config_mod, "get_config",
                            lambda: self._cfg(enabled=False, rules=[], keep_cores=4))
        enable, rules, keep = cb._resolve_watchdog(watchdog_flag=True)
        assert enable is True
        assert keep == 4

    def test_config_enables_with_rules(self, monkeypatch) -> None:
        import abso.core.config as config_mod
        from abso.core.config import WatchdogRule

        rule = WatchdogRule(match="x.exe", action="demote")
        monkeypatch.setattr(config_mod, "get_config",
                            lambda: self._cfg(enabled=True, rules=[rule], keep_cores=6))
        enable, rules, keep = cb._resolve_watchdog(watchdog_flag=False)
        assert enable is True
        assert len(rules) == 1
        assert keep == 6


class TestPriorityIntervention:
    @pytest.mark.parametrize("priority", [
        cb.NORMAL_PRIORITY_CLASS, cb.ABOVE_NORMAL_PRIORITY_CLASS, cb.HIGH_PRIORITY_CLASS,
    ])
    def test_all_eligible_priority_classes_are_demoted(self, monkeypatch, priority):
        bal = _make_balancer()
        bal._kernel32 = MagicMock()
        bal._kernel32.GetPriorityClass.return_value = priority
        monkeypatch.setattr(bal, "_read_process_times", lambda handle: (123, 0, 0))
        bal._restrain(9001, "background.exe", 15)
        assert bal._restrained[9001].original_priority == priority
        bal._kernel32.SetPriorityClass.assert_called_once_with(
            bal._kernel32.OpenProcess.return_value, cb.BELOW_NORMAL_PRIORITY_CLASS
        )

    @pytest.mark.parametrize("priority", [
        0, cb.IDLE_PRIORITY_CLASS, cb.BELOW_NORMAL_PRIORITY_CLASS, cb.REALTIME_PRIORITY_CLASS,
    ])
    def test_never_promotes_low_priority_or_touches_realtime(self, monkeypatch, priority):
        bal = _make_balancer()
        bal._kernel32 = MagicMock()
        bal._kernel32.GetPriorityClass.return_value = priority
        monkeypatch.setattr(bal, "_read_process_times", lambda handle: (123, 0, 0))
        bal._restrain(9001, "background.exe", 15)
        bal._kernel32.SetPriorityClass.assert_not_called()
        assert not bal._restrained

    def test_recycled_pid_is_never_restored(self, monkeypatch):
        bal = _make_balancer()
        bal._kernel32 = MagicMock()
        bal._restrained[9001] = cb.RestrainedProcess(9001, "old.exe", 32, 0, 15, 123)
        monkeypatch.setattr(bal, "_read_process_times", lambda handle: (456, 0, 0))
        bal._release(9001)
        bal._kernel32.SetPriorityClass.assert_not_called()
        assert not bal._restrained
        assert not bal.get_events()

    def test_restore_failure_is_retained_and_not_reported_as_release(self, monkeypatch):
        bal = _make_balancer()
        bal._kernel32 = MagicMock()
        bal._kernel32.GetPriorityClass.return_value = cb.BELOW_NORMAL_PRIORITY_CLASS
        bal._kernel32.SetPriorityClass.return_value = False
        bal._restrained[9001] = cb.RestrainedProcess(9001, "old.exe", 32, 0, 15, 123)
        monkeypatch.setattr(bal, "_read_process_times", lambda handle: (123, 0, 0))
        bal._release(9001)
        assert 9001 in bal._restrained
        assert not bal.get_events()
        bal._kernel32.SetPriorityClass.return_value = True
        bal._release(9001)
        assert not bal._restrained
        assert bal.get_events()[0].action == "release"

    def test_later_user_priority_change_is_preserved(self, monkeypatch):
        bal = _make_balancer()
        bal._kernel32 = MagicMock()
        bal._kernel32.GetPriorityClass.return_value = cb.HIGH_PRIORITY_CLASS
        bal._restrained[9001] = cb.RestrainedProcess(9001, "old.exe", 32, 0, 15, 123)
        monkeypatch.setattr(bal, "_read_process_times", lambda handle: (123, 0, 0))
        bal._release(9001)
        bal._kernel32.SetPriorityClass.assert_not_called()
        assert not bal._restrained


class TestCpuSampling:
    def test_delayed_scan_uses_elapsed_time_not_poll_interval(self, monkeypatch):
        bal = _make_balancer()
        bal._kernel32 = MagicMock()
        counters = iter([(123, 0, 0), (123, 10_000_000, 0)])
        stamps = iter([10.0, 20.0])
        monkeypatch.setattr(bal, "_read_process_times", lambda handle: next(counters))
        monkeypatch.setattr(cb.time, "monotonic", lambda: next(stamps))
        monkeypatch.setattr(cb.os, "cpu_count", lambda: 2)
        assert bal._get_process_cpu(9001) is None
        # 1 CPU second / 10 wall seconds / 2 CPUs = 5%, previously 50%.
        assert bal._get_process_cpu(9001) == pytest.approx(5.0)

    def test_pid_reuse_resets_sample(self, monkeypatch):
        bal = _make_balancer()
        bal._kernel32 = MagicMock()
        counters = iter([(123, 100_000_000, 0), (456, 1_000_000, 0)])
        monkeypatch.setattr(bal, "_read_process_times", lambda handle: next(counters))
        assert bal._get_process_cpu(9001) is None
        assert bal._get_process_cpu(9001) is None

    def test_snapshot_invalid_handle_is_pointer_sized(self):
        bal = _make_balancer()
        bal._kernel32 = MagicMock()
        bal._kernel32.CreateToolhelp32Snapshot.return_value = cb.ctypes.c_void_p(-1).value
        assert bal._enumerate_processes() == []
        bal._kernel32.Process32FirstW.assert_not_called()
