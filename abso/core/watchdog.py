"""Declarative process-watchdog rule evaluation (Tier B scaffold, default OFF).

Generalizes the tray's single hardcoded Discord ProcessGuard ceiling into a
small, constrained, declarative rule list (``abso.yaml`` -> WatchdogConfig).
This module is the pure decision layer; actuation (demote / throttle / trim)
is performed by the governor/tray using the existing reversible mechanisms.

Deliberately constrained, NOT a generic automation runtime:
  * Only a fixed vocabulary of REVERSIBLE actions is allowed
    (:data:`ALLOWED_ACTIONS`). Terminate is intentionally not expressible.
  * Online profiles must be restricted to the demote-only tier by the caller
    (see :func:`allowed_actions_for`).

Default: no rules, so nothing fires until the user adds them.
"""

from __future__ import annotations

import logging

from abso.core.config import WatchdogRule

logger = logging.getLogger(__name__)

ALLOWED_METRICS: frozenset[str] = frozenset({"cpu", "ram", "priority"})
ALLOWED_ACTIONS: frozenset[str] = frozenset({"demote", "throttle", "trim"})

# Online (is_online_profile) sessions are restricted to the conservative,
# always-reversible, timing-neutral action only.
ONLINE_SAFE_ACTIONS: frozenset[str] = frozenset({"demote"})


def rule_is_valid(rule: WatchdogRule) -> bool:
    """Return ``True`` if a rule is well-formed (known metric + action + match)."""
    return (
        bool(rule.match)
        and rule.metric in ALLOWED_METRICS
        and rule.action in ALLOWED_ACTIONS
        and rule.threshold >= 0
        and rule.sustain_s >= 0
    )


def allowed_actions_for(*, is_online: bool) -> frozenset[str]:
    """Return the action vocabulary permitted for a profile's online-ness."""
    return ONLINE_SAFE_ACTIONS if is_online else ALLOWED_ACTIONS


def evaluate_rule(
    rule: WatchdogRule,
    *,
    image: str,
    metric_value: float,
    sustained_s: float,
    is_online: bool = False,
) -> str | None:
    """Return the action to take for a process sample, or ``None``.

    A rule fires when: its image matches (case-insensitive), the rule is valid,
    the action is permitted for the profile's online-ness, the sample's metric
    has met/exceeded the threshold, and it has done so for at least
    ``sustain_s`` seconds.
    """
    if not rule_is_valid(rule):
        logger.debug("Skipping invalid watchdog rule: %r", rule)
        return None
    if image.lower() != rule.match.lower():
        return None
    if rule.action not in allowed_actions_for(is_online=is_online):
        return None
    if metric_value < rule.threshold:
        return None
    if sustained_s < rule.sustain_s:
        return None
    return rule.action


def watchdog_enabled() -> bool:
    """Return ``True`` if the watchdog is opted in via ``abso.yaml``."""
    try:
        from abso.core.config import get_config

        return bool(get_config().watchdog.enabled)
    except Exception as exc:
        logger.debug("watchdog config unavailable: %s", exc)
        return False
