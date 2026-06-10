"""Hermetic tests for the watchdog actuator + engine runtime."""

from __future__ import annotations

from abso.core import proc_actions
from abso.core.config import WatchdogRule
from abso.core.watchdog_engine import WatchdogActuator, WatchdogEngine, priority_rank


class _FakePriorityDeps:
    def __init__(self, default: int = proc_actions.NORMAL_PRIORITY_CLASS) -> None:
        self.priorities: dict[int, int] = {}
        self.default = default
        self.trimmed: list[int] = []

    def get_priority(self, pid):
        return self.priorities.get(pid, self.default)

    def set_priority(self, pid, cls):
        self.priorities[pid] = cls
        return True

    def trim(self, pid):
        self.trimmed.append(pid)
        return True


class _FakeLimiter:
    def __init__(self) -> None:
        self.limited: list[int] = []
        self.restored = False

    def limit(self, pid):
        self.limited.append(pid)
        return True

    def restore_all(self):
        self.restored = True


class _RecordingActuator:
    def __init__(self) -> None:
        self.applied: list[tuple[str, int]] = []
        self.restored = False

    def apply(self, action, pid):
        self.applied.append((action, pid))
        return True

    def restore_all(self):
        self.restored = True


def _rule(**kw) -> WatchdogRule:
    base = {"match": "discord.exe", "metric": "cpu", "threshold": 50.0, "sustain_s": 5.0, "action": "demote"}
    base.update(kw)
    return WatchdogRule(**base)


class TestActuator:
    def test_demote_snapshots_and_restores(self) -> None:
        deps = _FakePriorityDeps(default=proc_actions.NORMAL_PRIORITY_CLASS)
        lim = _FakeLimiter()
        act = WatchdogActuator(
            get_priority=deps.get_priority, set_priority=deps.set_priority, trim=deps.trim, limiter=lim
        )
        assert act.apply("demote", 100) is True
        assert deps.priorities[100] == proc_actions.BELOW_NORMAL_PRIORITY_CLASS
        act.restore_all()
        assert deps.priorities[100] == proc_actions.NORMAL_PRIORITY_CLASS
        assert act.demoted_pids == frozenset()

    def test_demote_idempotent(self) -> None:
        deps = _FakePriorityDeps()
        act = WatchdogActuator(get_priority=deps.get_priority, set_priority=deps.set_priority,
                               trim=deps.trim, limiter=_FakeLimiter())
        act.apply("demote", 100)
        # Manually change the live value; a second demote must NOT re-snapshot it.
        deps.priorities[100] = proc_actions.IDLE_PRIORITY_CLASS
        assert act.apply("demote", 100) is True
        act.restore_all()
        assert deps.priorities[100] == proc_actions.NORMAL_PRIORITY_CLASS  # original snapshot

    def test_throttle_delegates_to_limiter(self) -> None:
        lim = _FakeLimiter()
        act = WatchdogActuator(limiter=lim, get_priority=lambda p: 0, set_priority=lambda p, c: True,
                               trim=lambda p: True)
        assert act.apply("throttle", 7) is True
        assert lim.limited == [7]

    def test_trim_one_shot(self) -> None:
        deps = _FakePriorityDeps()
        act = WatchdogActuator(get_priority=deps.get_priority, set_priority=deps.set_priority,
                               trim=deps.trim, limiter=_FakeLimiter())
        assert act.apply("trim", 9) is True
        assert deps.trimmed == [9]

    def test_demote_fails_when_priority_unreadable(self) -> None:
        act = WatchdogActuator(get_priority=lambda p: None, set_priority=lambda p, c: True,
                               trim=lambda p: True, limiter=_FakeLimiter())
        assert act.apply("demote", 5) is False


class TestPriorityRank:
    def test_rank_ordering(self) -> None:
        assert priority_rank(proc_actions.IDLE_PRIORITY_CLASS) < priority_rank(proc_actions.NORMAL_PRIORITY_CLASS)
        assert priority_rank(proc_actions.NORMAL_PRIORITY_CLASS) < priority_rank(proc_actions.HIGH_PRIORITY_CLASS)
        assert priority_rank(proc_actions.BELOW_NORMAL_PRIORITY_CLASS) < priority_rank(proc_actions.NORMAL_PRIORITY_CLASS)


class TestEngine:
    def test_fires_after_sustain(self) -> None:
        clock = [0.0]
        act = _RecordingActuator()
        eng = WatchdogEngine([_rule()], actuator=act, cpu_sampler=lambda p: 90.0, clock=lambda: clock[0])
        eng.tick([(100, "Discord.exe")])  # t=0: starts the sustain window, not yet fired
        assert act.applied == []
        clock[0] = 6.0
        eng.tick([(100, "Discord.exe")])  # sustained 6s >= 5s -> fires
        assert act.applied == [("demote", 100)]
        eng.tick([(100, "Discord.exe")])  # fires only once per (rule, pid)
        assert act.applied == [("demote", 100)]

    def test_no_fire_below_threshold(self) -> None:
        act = _RecordingActuator()
        eng = WatchdogEngine([_rule(sustain_s=0.0)], actuator=act, cpu_sampler=lambda p: 10.0, clock=lambda: 0.0)
        eng.tick([(100, "Discord.exe")])
        assert act.applied == []

    def test_no_fire_before_sustain_elapsed(self) -> None:
        clock = [0.0]
        act = _RecordingActuator()
        eng = WatchdogEngine([_rule(sustain_s=5.0)], actuator=act, cpu_sampler=lambda p: 99.0, clock=lambda: clock[0])
        eng.tick([(100, "Discord.exe")])
        clock[0] = 2.0  # only 2s sustained
        eng.tick([(100, "Discord.exe")])
        assert act.applied == []

    def test_image_mismatch_never_fires(self) -> None:
        act = _RecordingActuator()
        eng = WatchdogEngine([_rule(sustain_s=0.0)], actuator=act, cpu_sampler=lambda p: 99.0, clock=lambda: 0.0)
        eng.tick([(100, "chrome.exe")])
        assert act.applied == []

    def test_online_gating_drops_throttle_rule(self) -> None:
        throttle_rule = _rule(action="throttle")
        online = WatchdogEngine([throttle_rule], is_online=True, cpu_sampler=lambda p: 99.0, clock=lambda: 0.0)
        offline = WatchdogEngine([throttle_rule], is_online=False, cpu_sampler=lambda p: 99.0, clock=lambda: 0.0)
        assert online.active_rule_count == 0
        assert offline.active_rule_count == 1

    def test_invalid_rule_dropped(self) -> None:
        bad = _rule(action="terminate")  # not an allowed reversible action
        eng = WatchdogEngine([bad], cpu_sampler=lambda p: 99.0, clock=lambda: 0.0)
        assert eng.active_rule_count == 0

    def test_priority_metric_uses_rank(self) -> None:
        rule = _rule(metric="priority", threshold=3.0, sustain_s=0.0)  # >= ABOVE_NORMAL
        hi = _RecordingActuator()
        eng_hi = WatchdogEngine([rule], actuator=hi,
                                priority_sampler=lambda p: proc_actions.HIGH_PRIORITY_CLASS, clock=lambda: 0.0)
        eng_hi.tick([(1, "discord.exe")])
        assert hi.applied == [("demote", 1)]

        lo = _RecordingActuator()
        eng_lo = WatchdogEngine([rule], actuator=lo,
                                priority_sampler=lambda p: proc_actions.NORMAL_PRIORITY_CLASS, clock=lambda: 0.0)
        eng_lo.tick([(1, "discord.exe")])
        assert lo.applied == []

    def test_restore_all_resets(self) -> None:
        act = _RecordingActuator()
        eng = WatchdogEngine([_rule(sustain_s=0.0)], actuator=act, cpu_sampler=lambda p: 99.0, clock=lambda: 0.0)
        eng.tick([(100, "discord.exe")])
        assert act.applied == [("demote", 100)]
        eng.restore_all()
        assert act.restored is True
        eng.tick([(100, "discord.exe")])  # state cleared -> can fire again
        assert act.applied == [("demote", 100), ("demote", 100)]
