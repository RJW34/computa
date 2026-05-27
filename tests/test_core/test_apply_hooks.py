"""Tests for post-apply hook safety policy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.core.apply_hooks import run_post_apply_sweep
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
