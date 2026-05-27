"""Tests for GameWatcher tasklist fallback parsing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.core.game_watcher import GameWatcher


@patch("abso.core.game_watcher.subprocess.run")
def test_poll_running_processes_uses_exact_tasklist_image_names(mock_subprocess_run) -> None:
    mock_subprocess_run.return_value = MagicMock(
        stdout=(
            '"notgame.exe","1111","Console","1","10000 K"\n'
            '"game.exe","2222","Console","1","10000 K"\n'
        )
    )
    watcher = GameWatcher(on_game_start=lambda _info: None, on_game_exit=lambda _info: None)
    watcher._executable_names = ["game.exe"]

    matches = watcher._poll_running_processes()

    assert matches == {2222: "game.exe"}
