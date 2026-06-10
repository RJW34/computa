"""Hermetic tests for declarative watchdog rule evaluation (Tier B scaffold)."""

from __future__ import annotations

from abso.core import watchdog as wd
from abso.core.config import WatchdogConfig, WatchdogRule
from abso.core.watchdog import allowed_actions_for, evaluate_rule, rule_is_valid


class TestRuleValidity:
    def test_valid_rule(self) -> None:
        assert rule_is_valid(WatchdogRule(match="x.exe", metric="cpu", action="demote")) is True

    def test_unknown_metric_invalid(self) -> None:
        assert rule_is_valid(WatchdogRule(match="x.exe", metric="gpu", action="demote")) is False

    def test_unknown_action_invalid(self) -> None:
        # terminate is intentionally not a permitted action.
        assert rule_is_valid(WatchdogRule(match="x.exe", action="terminate")) is False

    def test_empty_match_invalid(self) -> None:
        assert rule_is_valid(WatchdogRule(match="")) is False


class TestEvaluate:
    def _rule(self, **kw) -> WatchdogRule:
        base = {
            "match": "discord.exe",
            "metric": "cpu",
            "threshold": 80.0,
            "sustain_s": 5.0,
            "action": "demote",
        }
        base.update(kw)
        return WatchdogRule(**base)

    def test_fires_when_over_threshold_and_sustained(self) -> None:
        action = evaluate_rule(
            self._rule(), image="Discord.exe", metric_value=90.0, sustained_s=6.0
        )
        assert action == "demote"

    def test_no_fire_below_threshold(self) -> None:
        assert evaluate_rule(self._rule(), image="Discord.exe", metric_value=50.0, sustained_s=6.0) is None

    def test_no_fire_when_not_sustained(self) -> None:
        assert evaluate_rule(self._rule(), image="Discord.exe", metric_value=90.0, sustained_s=1.0) is None

    def test_no_fire_on_image_mismatch(self) -> None:
        assert evaluate_rule(self._rule(), image="chrome.exe", metric_value=99.0, sustained_s=9.0) is None

    def test_invalid_rule_never_fires(self) -> None:
        bad = self._rule(action="terminate")
        assert evaluate_rule(bad, image="Discord.exe", metric_value=99.0, sustained_s=9.0) is None


class TestOnlineGating:
    def test_online_restricts_to_demote_only(self) -> None:
        assert allowed_actions_for(is_online=True) == frozenset({"demote"})
        assert "throttle" in allowed_actions_for(is_online=False)

    def test_throttle_blocked_for_online_profile(self) -> None:
        rule = WatchdogRule(match="x.exe", metric="cpu", threshold=10.0, sustain_s=0.0, action="throttle")
        # Offline: fires. Online: blocked.
        assert evaluate_rule(rule, image="x.exe", metric_value=99.0, sustained_s=9.0, is_online=False) == "throttle"
        assert evaluate_rule(rule, image="x.exe", metric_value=99.0, sustained_s=9.0, is_online=True) is None


class TestConfigCoercion:
    def test_rules_coerced_from_dicts(self) -> None:
        cfg = WatchdogConfig(enabled=True, rules=[{"match": "discord.exe", "action": "demote"}])
        assert len(cfg.rules) == 1
        assert isinstance(cfg.rules[0], WatchdogRule)
        assert cfg.rules[0].match == "discord.exe"

    def test_default_has_no_rules(self) -> None:
        assert WatchdogConfig().rules == []


class TestEnabledGate:
    def test_disabled_by_default(self, monkeypatch) -> None:
        class _Cfg:
            watchdog = WatchdogConfig()

        import abso.core.config as config_mod

        monkeypatch.setattr(config_mod, "get_config", lambda: _Cfg())
        assert wd.watchdog_enabled() is False
