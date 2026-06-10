"""Hermetic tests for the ProBalance-style CPU balancer.

These never mutate real process priorities: they construct a balancer and
exercise the pure decision helpers (exclusion set, stop-sentinel, config
translation). The kernel32/user32 handles load on Windows but no
restrain/release is performed against any real process.
"""

from __future__ import annotations

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
