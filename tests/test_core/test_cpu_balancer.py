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

    def test_cpu_sets_steer_on_start(self, monkeypatch, tmp_path) -> None:
        import abso.core.cpu_sets as cs
        from abso.core.cpu_sets import CorePartition

        calls: list = []

        def fake_steer(pid, ids):
            calls.append((pid, tuple(ids)))
            return True

        partition = CorePartition(
            kind="hybrid", game_ids=(256, 257), background_ids=(300,)
        )
        monkeypatch.setattr(cs, "get_partition", lambda **kw: partition)
        monkeypatch.setattr(cs, "steer_process_to_sets", fake_steer)

        bal = CpuBalancer(
            game_pid=4242,
            config=CpuBalancerConfig(),
            enable_cpu_sets=True,
            steer_journal_path=tmp_path / "steer.journal",
        )
        monkeypatch.setattr(
            bal, "_enumerate_processes", lambda: [(4242, "game.exe", 1)]
        )
        bal._start_session_extras()
        assert (4242, (256, 257)) in calls
        assert bal._steerer is not None

    def test_cpu_sets_steer_covers_game_descendants(self, monkeypatch, tmp_path) -> None:
        import abso.core.cpu_sets as cs
        from abso.core.cpu_sets import CorePartition

        steered: list = []
        partition = CorePartition(kind="hybrid", game_ids=(1, 2), background_ids=(9,))
        monkeypatch.setattr(cs, "get_partition", lambda **kw: partition)
        monkeypatch.setattr(
            cs, "steer_process_to_sets", lambda pid, ids: steered.append(pid) or True
        )

        bal = CpuBalancer(
            game_pid=100,
            config=CpuBalancerConfig(),
            enable_cpu_sets=True,
            steer_journal_path=tmp_path / "steer.journal",
        )
        # 100 -> 101 -> 102 chain plus an unrelated process.
        monkeypatch.setattr(
            bal,
            "_enumerate_processes",
            lambda: [
                (100, "game.exe", 1),
                (101, "eac_child.exe", 100),
                (102, "shader_worker.exe", 101),
                (500, "chrome.exe", 1),
            ],
        )
        bal._start_session_extras()
        assert set(steered) == {100, 101, 102}

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

    def test_extras_failure_is_isolated(self, monkeypatch, tmp_path) -> None:
        import abso.core.cpu_sets as cs

        def boom(**kw):
            raise RuntimeError("topology query exploded")

        monkeypatch.setattr(cs, "get_partition", boom)
        bal = CpuBalancer(
            game_pid=4242,
            config=CpuBalancerConfig(),
            enable_cpu_sets=True,
            steer_journal_path=tmp_path / "steer.journal",
        )
        bal._start_session_extras()  # exception swallowed -> core loop safe
        assert bal._steerer is None


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


class TestRestraintGate:
    def test_no_restraint_skips_priority_logic(self, monkeypatch) -> None:
        bal = _make_balancer(enable_restraint=False)

        def boom():
            raise AssertionError("restraint path must not run")

        monkeypatch.setattr(bal, "_get_system_cpu", boom)
        monkeypatch.setattr(bal, "_find_and_restrain_offenders", boom)
        bal._poll_once()  # no steerer/watchdog -> nothing else runs either

    def test_restraint_on_by_default(self) -> None:
        bal = _make_balancer()
        assert bal._enable_restraint is True


class TestAutoSteer:
    def _hybrid_steerer(self, tmp_path):
        from abso.core.cpu_sets import CorePartition
        from abso.core.partition_steer import PartitionSteerer

        steered: list = []
        steerer = PartitionSteerer(
            4242,
            CorePartition(kind="hybrid", game_ids=(1,), background_ids=(9,)),
            (),
            steer=lambda pid, ids: steered.append((pid, tuple(ids))) or True,
            clear=lambda pid: True,
            journal_path=tmp_path / "steer.journal",
        )
        return steerer, steered

    def _auto_balancer(self, tmp_path, **kw):
        bal = _make_balancer(
            enable_auto_steer=True,
            auto_steer_process_threshold=4,
            auto_steer_sustain_ms=1000,
            steer_journal_path=tmp_path / "steer.journal",
            **kw,
        )
        steerer, steered = self._hybrid_steerer(tmp_path)
        bal._steerer = steerer
        return bal, steered

    def test_sustained_heavy_process_is_steered(self, monkeypatch, tmp_path) -> None:
        bal, steered = self._auto_balancer(tmp_path)
        monkeypatch.setattr(bal, "_get_foreground_pid", lambda: None)
        monkeypatch.setattr(
            bal, "_get_process_cpu", lambda pid, times_store=None: 12.0
        )
        procs = [(7000, "encoder.exe", 1)]
        bal._auto_steer_offenders(procs, now=100.0)  # first sighting
        assert steered == []
        bal._auto_steer_offenders(procs, now=101.5)  # sustained past 1000ms
        assert (7000, (9,)) in steered

    def test_calm_process_resets_sustain(self, monkeypatch, tmp_path) -> None:
        bal, steered = self._auto_balancer(tmp_path)
        monkeypatch.setattr(bal, "_get_foreground_pid", lambda: None)
        cpu_values = iter([12.0, 1.0, 12.0, 12.0])
        monkeypatch.setattr(
            bal, "_get_process_cpu", lambda pid, times_store=None: next(cpu_values)
        )
        procs = [(7000, "encoder.exe", 1)]
        bal._auto_steer_offenders(procs, now=100.0)  # high
        bal._auto_steer_offenders(procs, now=101.5)  # calm -> reset
        bal._auto_steer_offenders(procs, now=102.0)  # high again (restart clock)
        bal._auto_steer_offenders(procs, now=102.5)  # only 500ms sustained
        assert steered == []

    def test_excluded_images_never_auto_steered(self, monkeypatch, tmp_path) -> None:
        bal, steered = self._auto_balancer(tmp_path)
        monkeypatch.setattr(bal, "_get_foreground_pid", lambda: None)
        monkeypatch.setattr(
            bal, "_get_process_cpu", lambda pid, times_store=None: 50.0
        )
        procs = [(900, "dwm.exe", 1)]
        bal._auto_steer_offenders(procs, now=100.0)
        bal._auto_steer_offenders(procs, now=200.0)
        assert steered == []

    def test_game_descendants_never_auto_steered(self, monkeypatch, tmp_path) -> None:
        bal, steered = self._auto_balancer(tmp_path)
        monkeypatch.setattr(bal, "_get_foreground_pid", lambda: None)
        monkeypatch.setattr(
            bal, "_get_process_cpu", lambda pid, times_store=None: 50.0
        )
        procs = [(5000, "shaderworker.exe", 4242)]
        bal._auto_steer_offenders(procs, now=100.0)
        bal._auto_steer_offenders(procs, now=200.0)
        assert steered == []

    def test_uses_isolated_cpu_time_store(self, tmp_path) -> None:
        bal, _ = self._auto_balancer(tmp_path)
        assert bal._auto_steer_cpu_times is not bal._last_process_times
        assert bal._auto_steer_cpu_times is not bal._watchdog_cpu_times


class TestResolvePartition:
    def _cpu_sets_cfg(self, **kw):
        class _Sets:
            background_steer = kw.get("background_steer", True)
            background_images = kw.get("background_images", [])
            auto_steer = kw.get("auto_steer", True)
            auto_steer_process_threshold = kw.get("threshold", 4)
            auto_steer_sustain_ms = kw.get("sustain", 5000)
            smt_avoid = kw.get("smt_avoid", False)
            x3d_partition = kw.get("x3d", True)

        class _Cfg:
            cpu_sets = _Sets()

        return _Cfg()

    def _patch(self, monkeypatch, *, policy, images=(), cfg=None):
        import abso.core.config as config_mod
        import abso.profiles.catalog as catalog_mod

        monkeypatch.setattr(
            catalog_mod, "get_profile_partition", lambda pid: (policy, tuple(images))
        )
        monkeypatch.setattr(
            config_mod, "get_config", lambda: cfg or self._cpu_sets_cfg()
        )

    def test_full_policy_enables_everything(self, monkeypatch) -> None:
        self._patch(monkeypatch, policy="full", images=("obs64.exe", "chrome.exe"))
        kw = cb._resolve_partition(steer_flag=False, profile_id="overwatch2-gsync-hdr")
        assert kw["enable_cpu_sets"] is True
        assert kw["steer_background_images"] == ["obs64.exe", "chrome.exe"]
        assert kw["enable_auto_steer"] is True

    def test_game_only_policy_has_no_background(self, monkeypatch) -> None:
        self._patch(monkeypatch, policy="game_only", images=())
        kw = cb._resolve_partition(steer_flag=False, profile_id="x")
        assert kw["enable_cpu_sets"] is True
        assert kw["steer_background_images"] == []
        assert kw["enable_auto_steer"] is False

    def test_off_policy_is_fully_off(self, monkeypatch) -> None:
        self._patch(monkeypatch, policy="off")
        kw = cb._resolve_partition(steer_flag=False, profile_id="desktop")
        assert kw["enable_cpu_sets"] is False
        assert kw["steer_background_images"] == []
        assert kw["enable_auto_steer"] is False

    def test_steer_flag_forces_background_with_defaults(self, monkeypatch) -> None:
        from abso.core.partition_steer import DEFAULT_BACKGROUND_STEER_IMAGES

        self._patch(monkeypatch, policy="off")
        kw = cb._resolve_partition(steer_flag=True, profile_id="desktop")
        assert kw["steer_background_images"] == list(DEFAULT_BACKGROUND_STEER_IMAGES)

    def test_config_background_veto(self, monkeypatch) -> None:
        self._patch(
            monkeypatch,
            policy="full",
            images=("obs64.exe",),
            cfg=self._cpu_sets_cfg(background_steer=False),
        )
        kw = cb._resolve_partition(steer_flag=False, profile_id="x")
        assert kw["steer_background_images"] == []
        assert kw["enable_auto_steer"] is False
        assert kw["enable_cpu_sets"] is True  # game side unaffected

    def test_config_extra_images_deduped(self, monkeypatch) -> None:
        self._patch(
            monkeypatch,
            policy="full",
            images=("obs64.exe",),
            cfg=self._cpu_sets_cfg(background_images=["OBS64.EXE", "krita.exe"]),
        )
        kw = cb._resolve_partition(steer_flag=False, profile_id="x")
        assert kw["steer_background_images"] == ["obs64.exe", "krita.exe"]

    def test_auto_steer_config_veto(self, monkeypatch) -> None:
        self._patch(
            monkeypatch,
            policy="full",
            images=("obs64.exe",),
            cfg=self._cpu_sets_cfg(auto_steer=False),
        )
        kw = cb._resolve_partition(steer_flag=False, profile_id="x")
        assert kw["enable_auto_steer"] is False

    def test_tuning_knobs_pass_through(self, monkeypatch) -> None:
        self._patch(
            monkeypatch,
            policy="full",
            images=("a.exe",),
            cfg=self._cpu_sets_cfg(threshold=7, sustain=9000, smt_avoid=True, x3d=False),
        )
        kw = cb._resolve_partition(steer_flag=False, profile_id="x")
        assert kw["auto_steer_process_threshold"] == 7
        assert kw["auto_steer_sustain_ms"] == 9000
        assert kw["smt_avoid"] is True
        assert kw["allow_x3d"] is False

    def test_resolver_failure_is_safe(self, monkeypatch) -> None:
        import abso.core.config as config_mod
        import abso.profiles.catalog as catalog_mod

        def boom(*a, **kw):
            raise RuntimeError("no catalog")

        monkeypatch.setattr(catalog_mod, "get_profile_partition", boom)
        monkeypatch.setattr(config_mod, "get_config", boom)
        kw = cb._resolve_partition(steer_flag=False, profile_id="x")
        assert kw["enable_cpu_sets"] is False
        assert kw["steer_background_images"] == []
