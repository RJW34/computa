"""Watchdog actuator + engine — the runtime that applies declarative rules.

The *policy* (which rules are valid, what actions are allowed online) lives in
:mod:`abso.core.watchdog`. This module is the *mechanism* + sustain-timing
runtime that the cpu-balance daemon hosts. Everything is dependency-injected so
the decision logic is fully unit-testable without touching real processes.

Reversibility (restored at session end via :meth:`WatchdogEngine.restore_all`):
  * demote   -> snapshot original priority, set BELOW_NORMAL; restore on stop.
  * throttle -> CpuLimiter (snapshots/restores the affinity mask).
  * trim     -> one-shot EmptyWorkingSet; nothing to revert.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence

from abso.core import proc_actions
from abso.core.config import WatchdogRule
from abso.core.cpu_limiter import CpuLimiter
from abso.core.watchdog import allowed_actions_for, rule_is_valid

logger = logging.getLogger(__name__)

# Ordered priority ranks so a "priority" rule can compare meaningfully (the raw
# class constants are NOT numerically ordered by actual scheduling priority).
_PRIORITY_RANK: dict[int, int] = {
    proc_actions.IDLE_PRIORITY_CLASS: 0,
    proc_actions.BELOW_NORMAL_PRIORITY_CLASS: 1,
    proc_actions.NORMAL_PRIORITY_CLASS: 2,
    proc_actions.ABOVE_NORMAL_PRIORITY_CLASS: 3,
    proc_actions.HIGH_PRIORITY_CLASS: 4,
    0x00000100: 5,  # REALTIME_PRIORITY_CLASS
}


def priority_rank(priority_class: int) -> int:
    """Map a priority class to an ordered rank (0=idle .. 5=realtime)."""
    return _PRIORITY_RANK.get(priority_class, 2)  # unknown -> treat as Normal


class WatchdogActuator:
    """Applies and reverts the reversible watchdog actions."""

    def __init__(
        self,
        *,
        keep_cores: int = 4,
        limiter: CpuLimiter | None = None,
        get_priority: Callable[[int], int | None] | None = None,
        set_priority: Callable[[int, int], bool] | None = None,
        trim: Callable[[int], bool] | None = None,
    ) -> None:
        self._get_priority = get_priority or proc_actions.get_priority_class
        self._set_priority = set_priority or proc_actions.set_priority_class
        self._trim = trim or proc_actions.trim_working_set
        self._limiter = limiter or CpuLimiter(keep_cores)
        self._demoted: dict[int, int] = {}  # pid -> original priority class

    def apply(self, action: str, pid: int) -> bool:
        if action == "demote":
            return self._demote(pid)
        if action == "throttle":
            return self._limiter.limit(pid)
        if action == "trim":
            return self._trim(pid)
        return False

    def _demote(self, pid: int) -> bool:
        if pid in self._demoted:
            return True  # already demoted by this actuator
        original = self._get_priority(pid)
        if original is None:
            return False
        if self._set_priority(pid, proc_actions.BELOW_NORMAL_PRIORITY_CLASS):
            self._demoted[pid] = original
            return True
        return False

    def restore_all(self) -> None:
        for pid, original in list(self._demoted.items()):
            self._set_priority(pid, original)
        self._demoted.clear()
        self._limiter.restore_all()

    @property
    def demoted_pids(self) -> frozenset[int]:
        return frozenset(self._demoted)


class WatchdogEngine:
    """Evaluates rules each poll; dispatches an action after a sustained breach.

    Metric samplers are callables ``pid -> value`` (cpu %, ram MB, or the raw
    priority class which is rank-converted internally). A rule fires once per
    ``(rule, pid)``; the action is reverted at :meth:`restore_all` (session end).
    """

    def __init__(
        self,
        rules: Sequence[WatchdogRule],
        *,
        is_online: bool = False,
        actuator: WatchdogActuator | None = None,
        keep_cores: int = 4,
        cpu_sampler: Callable[[int], float | None] | None = None,
        ram_sampler: Callable[[int], float | None] | None = None,
        priority_sampler: Callable[[int], int | None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        allowed = allowed_actions_for(is_online=is_online)
        self._rules = [r for r in rules if rule_is_valid(r) and r.action in allowed]
        self._actuator = actuator or WatchdogActuator(keep_cores=keep_cores)
        self._cpu = cpu_sampler
        self._ram = ram_sampler
        self._priority = priority_sampler
        self._clock = clock or time.monotonic
        self._sustain_start: dict[tuple[int, int], float] = {}
        self._applied: set[tuple[int, int]] = set()

    @property
    def active_rule_count(self) -> int:
        return len(self._rules)

    def _sample(self, metric: str, pid: int) -> float | None:
        if metric == "cpu" and self._cpu is not None:
            return self._cpu(pid)
        if metric == "ram" and self._ram is not None:
            return self._ram(pid)
        if metric == "priority" and self._priority is not None:
            cls = self._priority(pid)
            return None if cls is None else float(priority_rank(cls))
        return None

    def tick(self, processes: Sequence[tuple[int, str]]) -> None:
        if not self._rules:
            return
        now = self._clock()
        for idx, rule in enumerate(self._rules):
            match = rule.match.lower()
            for pid, name in processes:
                if name.lower() != match:
                    continue
                key = (idx, pid)
                if key in self._applied:
                    continue
                value = self._sample(rule.metric, pid)
                if value is None or value < rule.threshold:
                    self._sustain_start.pop(key, None)
                    continue
                start = self._sustain_start.setdefault(key, now)
                if (now - start) >= rule.sustain_s and self._actuator.apply(rule.action, pid):
                    self._applied.add(key)
                    logger.info(
                        "Watchdog: %s %s (pid %d) [rule %s %s>=%s sustained %ss]",
                        rule.action, name, pid, rule.match, rule.metric,
                        rule.threshold, rule.sustain_s,
                    )

    def restore_all(self) -> None:
        self._actuator.restore_all()
        self._sustain_start.clear()
        self._applied.clear()
