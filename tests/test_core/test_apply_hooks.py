"""Tests for post-apply hook safety policy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.core.apply_hooks import live_monitor_count, run_post_apply_sweep
from abso.core.multimon_detector import DisplayEnvironment, MultiMonitorResult
from abso.core.process_janitor import LaunchKillset


def test_post_apply_sweep_excludes_opt_in_tier_by_default() -> None:
    """Normal profile apply must not run the aggressive process tier."""

    class Profile:
        def launch_process_killset(self) -> LaunchKillset:
            return LaunchKillset(
                always_safe=("SafeOverlay.exe",),
                opt_in=("SearchIndexer.exe",),
            )

    tx = MagicMock(success=True)
    result = MagicMock(success=True)
    janitor = MagicMock()
    janitor.sweep.return_value.to_dict.return_value = {
        "attempted": ["SafeOverlay.exe"],
        "stopped": [],
        "not_running": ["SafeOverlay.exe"],
        "failed": [],
        "warnings": [],
        "changed": False,
    }

    with (
        patch("abso.profiles.catalog.get_profile_instances", return_value={"game": Profile()}),
        patch("abso.core.process_janitor.ProcessJanitor", return_value=janitor),
    ):
        sweep = run_post_apply_sweep("game", tx, result)

    janitor.sweep.assert_called_once_with(["SafeOverlay.exe"], dry_run=False)
    assert sweep["attempted"] == ["SafeOverlay.exe"]


def test_live_monitor_count_returns_confident_reading() -> None:
    env = DisplayEnvironment(monitor_count=2, detection_confident=True)
    result = MultiMonitorResult(environment=env)
    with patch(
        "abso.core.multimon_detector.MultiMonitorDetector.detect", return_value=result
    ):
        count, error = live_monitor_count()
    assert count == 2
    assert error is None


def test_live_monitor_count_fails_closed_when_detection_not_confident() -> None:
    """A fallback monitor count must not look like a confident single monitor."""
    env = DisplayEnvironment(monitor_count=1, detection_confident=False)
    result = MultiMonitorResult(environment=env)
    with patch(
        "abso.core.multimon_detector.MultiMonitorDetector.detect", return_value=result
    ):
        count, error = live_monitor_count()
    assert count is None
    assert error is not None
