"""Tests for overlay remediation."""

from __future__ import annotations

from unittest.mock import patch

from abso.core.overlay_manager import OverlayManager


@patch.object(OverlayManager, "_stop_process_image")
@patch.object(OverlayManager, "_is_process_running")
def test_overlay_manager_stops_known_overlay_processes(
    mock_is_process_running,
    mock_stop_process_image,
):
    manager = OverlayManager()
    mock_is_process_running.side_effect = lambda name: name in {"DiscordHookHelper64.exe", "GameBar.exe"}
    mock_stop_process_image.return_value = True

    result = manager.remediate(["Discord Overlay", "Xbox Game Bar"])

    assert result.changed is True
    assert sorted(result.stopped_labels) == ["Discord Overlay", "Xbox Game Bar"]
    assert result.remaining_labels == []
    assert any("Discord Overlay" in notice for notice in result.notices)
    assert any("Xbox Game Bar" in notice for notice in result.notices)


def test_overlay_manager_warns_for_unknown_overlay() -> None:
    manager = OverlayManager()

    result = manager.remediate(["Mystery Overlay"])

    assert result.changed is False
    assert result.remaining_labels == ["Mystery Overlay"]
    assert result.warnings == [
        "Overlay 'Mystery Overlay' was detected, but ABSO does not know how to disable it automatically."
    ]
