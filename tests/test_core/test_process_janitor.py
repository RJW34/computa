"""Tests for ProcessJanitor (launch-time sanitizer)."""

from __future__ import annotations

from unittest.mock import patch

from abso.core.process_janitor import (
    ALWAYS_SAFE_LAUNCH_KILLSET,
    NEVER_KILL_IMAGES,
    OPT_IN_LAUNCH_KILLSET,
    LaunchKillset,
    ProcessJanitor,
)


@patch.object(ProcessJanitor, "_stop_process_image")
@patch.object(ProcessJanitor, "_is_process_running")
def test_janitor_stops_running_images(mock_is_running, mock_stop) -> None:
    janitor = ProcessJanitor()
    mock_is_running.side_effect = lambda name: name in {"Medal.exe", "GameBar.exe"}
    mock_stop.return_value = True

    result = janitor.sweep(["Medal.exe", "GameBar.exe", "NahimicService.exe"])

    assert sorted(result.attempted) == ["GameBar.exe", "Medal.exe", "NahimicService.exe"]
    assert sorted(result.stopped) == ["GameBar.exe", "Medal.exe"]
    assert sorted(result.not_running) == ["NahimicService.exe"]
    assert result.failed == []
    assert result.changed is True


@patch.object(ProcessJanitor, "_is_process_running", return_value=False)
def test_janitor_skips_protected_images(mock_is_running) -> None:
    janitor = ProcessJanitor()

    result = janitor.sweep(["EasyAntiCheat.exe", "Steam.exe", "explorer.exe"])

    # Protected images must NEVER trigger _is_process_running probes.
    mock_is_running.assert_not_called()
    assert result.stopped == []
    assert result.not_running == []
    assert len(result.warnings) == 3
    for warning in result.warnings:
        assert "refused to sweep protected image" in warning


@patch.object(ProcessJanitor, "_stop_process_image")
@patch.object(ProcessJanitor, "_is_process_running")
def test_janitor_dry_run_does_not_invoke_taskkill(mock_is_running, mock_stop) -> None:
    janitor = ProcessJanitor()
    mock_is_running.return_value = True

    result = janitor.sweep(["Medal.exe"], dry_run=True)

    mock_stop.assert_not_called()
    assert result.stopped == []
    assert "Would stop Medal.exe" in result.notices[0]


def test_janitor_deduplicates_case_insensitive_input() -> None:
    janitor = ProcessJanitor()

    with patch.object(ProcessJanitor, "_is_process_running", return_value=False):
        result = janitor.sweep(["Medal.exe", "medal.exe", "MEDAL.EXE"])

    # Same image, only one attempt.
    assert len(result.attempted) == 1


@patch.object(ProcessJanitor, "_stop_process_image", return_value=False)
@patch.object(ProcessJanitor, "_is_process_running", return_value=True)
def test_janitor_records_failures_when_taskkill_cannot_stop_image(
    mock_is_running, mock_stop
) -> None:
    janitor = ProcessJanitor()

    result = janitor.sweep(["StubbornProcess.exe"])

    assert result.failed == ["StubbornProcess.exe"]
    assert any("could not stop StubbornProcess.exe" in w for w in result.warnings)


def test_launch_killset_resolve_default_excludes_opt_in() -> None:
    killset = LaunchKillset(always_safe=("a.exe",), opt_in=("b.exe",))

    assert killset.resolve() == ["a.exe"]
    assert killset.resolve(include_opt_in=False) == ["a.exe"]


def test_launch_killset_resolve_with_opt_in_concatenates() -> None:
    killset = LaunchKillset(always_safe=("a.exe",), opt_in=("b.exe", "c.exe"))

    assert killset.resolve(include_opt_in=True) == ["a.exe", "b.exe", "c.exe"]


def test_always_safe_killset_includes_canonical_overlays() -> None:
    # The launch killset must cover the overlay surfaces that the apply-time
    # OverlayManager already targets, otherwise mid-session respawns slip
    # through after the apply-time sweep finishes.
    for canonical_overlay in (
        "NVIDIA Share.exe",
        "GameOverlayUI.exe",
        "GameBar.exe",
        "GameBarFTServer.exe",
        "DiscordHookHelper.exe",
        "DiscordHookHelper64.exe",
        "RTSS.exe",
        "obs64.exe",
        "Medal.exe",
        "MedalEncoder.exe",
    ):
        assert canonical_overlay in ALWAYS_SAFE_LAUNCH_KILLSET, canonical_overlay


def test_never_kill_includes_anti_cheat_and_launchers() -> None:
    for image in (
        "EasyAntiCheat.exe",
        "BEService.exe",
        "vgc.exe",
        "Steam.exe",
        "Battle.net.exe",
        "Agent.exe",
        "EpicGamesLauncher.exe",
        # ABSO itself
        "python.exe",
        "powershell.exe",
        # Windows infrastructure
        "explorer.exe",
        "dwm.exe",
    ):
        assert image.lower() in NEVER_KILL_IMAGES, image


def test_always_safe_and_opt_in_are_disjoint() -> None:
    always = {name.lower() for name in ALWAYS_SAFE_LAUNCH_KILLSET}
    opt_in = {name.lower() for name in OPT_IN_LAUNCH_KILLSET}
    assert always.isdisjoint(opt_in), "Process must appear in exactly one tier"


def test_neither_killset_overlaps_never_kill_protection() -> None:
    always = {name.lower() for name in ALWAYS_SAFE_LAUNCH_KILLSET}
    opt_in = {name.lower() for name in OPT_IN_LAUNCH_KILLSET}
    assert always.isdisjoint(NEVER_KILL_IMAGES)
    assert opt_in.isdisjoint(NEVER_KILL_IMAGES)


def test_sweep_result_to_dict_round_trips_lists() -> None:
    janitor = ProcessJanitor()
    with patch.object(ProcessJanitor, "_is_process_running", return_value=False):
        result = janitor.sweep(["unused.exe"])

    data = result.to_dict()
    assert data["attempted"] == ["unused.exe"]
    assert data["not_running"] == ["unused.exe"]
    assert data["stopped"] == []
    assert data["changed"] is False
