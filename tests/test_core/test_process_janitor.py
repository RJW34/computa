"""Tests for ProcessJanitor (launch-time sanitizer)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.core.overlay_policy import OVERLAY_PROCESS_IMAGES
from abso.core.process_janitor import (
    ALWAYS_SAFE_LAUNCH_KILLSET,
    NEVER_KILL_IMAGES,
    OPT_IN_LAUNCH_KILLSET,
    LaunchKillset,
    ProcessJanitor,
)


@patch.object(ProcessJanitor, "_stop_process_image")
@patch.object(ProcessJanitor, "_snapshot_running_images")
def test_janitor_stops_running_images(mock_snapshot, mock_stop) -> None:
    janitor = ProcessJanitor()
    mock_snapshot.return_value = frozenset({"medal.exe", "gamebar.exe"})
    mock_stop.return_value = True

    result = janitor.sweep(["Medal.exe", "GameBar.exe", "NahimicService.exe"])

    assert sorted(result.attempted) == ["GameBar.exe", "Medal.exe", "NahimicService.exe"]
    assert sorted(result.stopped) == ["GameBar.exe", "Medal.exe"]
    assert sorted(result.not_running) == ["NahimicService.exe"]
    assert result.failed == []
    assert result.changed is True


@patch.object(ProcessJanitor, "_snapshot_running_images", return_value=frozenset())
@patch.object(ProcessJanitor, "_is_process_running", return_value=False)
def test_janitor_skips_protected_images(mock_is_running, mock_snapshot) -> None:
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
@patch.object(ProcessJanitor, "_snapshot_running_images")
def test_janitor_dry_run_does_not_invoke_taskkill(mock_snapshot, mock_stop) -> None:
    janitor = ProcessJanitor()
    mock_snapshot.return_value = frozenset({"medal.exe"})

    result = janitor.sweep(["Medal.exe"], dry_run=True)

    mock_stop.assert_not_called()
    assert result.stopped == []
    assert "Would stop Medal.exe" in result.notices[0]


def test_janitor_deduplicates_case_insensitive_input() -> None:
    janitor = ProcessJanitor()

    with patch.object(ProcessJanitor, "_snapshot_running_images", return_value=frozenset()):
        result = janitor.sweep(["Medal.exe", "medal.exe", "MEDAL.EXE"])

    # Same image, only one attempt.
    assert len(result.attempted) == 1


@patch("abso.core.process_janitor.subprocess.run")
def test_janitor_uses_one_tasklist_call_for_the_whole_killset(mock_run) -> None:
    """A sweep must not spawn one tasklist per image.

    The launch sanitizer re-sweeps for the life of a gaming session, so
    per-image probes turn a ~60-image killset into ~60 process spawns per
    tick. Exactly one snapshot must answer the pre-kill gate for all of them.
    """
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    janitor = ProcessJanitor()

    images = [f"Background{index}.exe" for index in range(60)]
    result = janitor.sweep(images)

    assert mock_run.call_count == 1
    assert mock_run.call_args.args[0] == ["tasklist", "/FO", "CSV", "/NH"]
    assert sorted(result.not_running) == sorted(images)


@patch.object(ProcessJanitor, "_stop_process_image", return_value=True)
@patch.object(ProcessJanitor, "_query_process_running", return_value=True)
@patch.object(ProcessJanitor, "_snapshot_running_images", return_value=None)
def test_janitor_falls_back_to_per_image_query_when_snapshot_fails(
    mock_snapshot, mock_query, mock_stop
) -> None:
    """An unusable bulk snapshot must not read as 'nothing is running'."""
    janitor = ProcessJanitor()

    result = janitor.sweep(["Medal.exe"])

    mock_query.assert_called_once_with("Medal.exe")
    assert result.stopped == ["Medal.exe"]
    assert result.not_running == []


@patch.object(ProcessJanitor, "_stop_process_image", return_value=False)
@patch.object(ProcessJanitor, "_query_process_running", return_value=True)
@patch.object(
    ProcessJanitor, "_snapshot_running_images", return_value=frozenset({"stubbornprocess.exe"})
)
def test_janitor_records_failures_when_taskkill_cannot_stop_image(
    mock_snapshot, mock_query, mock_stop
) -> None:
    janitor = ProcessJanitor()

    result = janitor.sweep(["StubbornProcess.exe"])

    assert result.failed == ["StubbornProcess.exe"]
    assert any("could not stop StubbornProcess.exe" in w for w in result.warnings)


@patch.object(ProcessJanitor, "_stop_process_image", return_value=False)
@patch.object(ProcessJanitor, "_query_process_running", return_value=None)
@patch.object(
    ProcessJanitor, "_snapshot_running_images", return_value=frozenset({"stubbornprocess.exe"})
)
def test_janitor_unverifiable_kill_is_failure_not_success(
    mock_snapshot, mock_query, mock_stop
) -> None:
    """If tasklist cannot confirm the kill, do not claim a success."""
    janitor = ProcessJanitor()

    result = janitor.sweep(["StubbornProcess.exe"])

    assert result.stopped == []
    assert result.failed == ["StubbornProcess.exe"]


@patch.object(ProcessJanitor, "_stop_process_image", return_value=False)
@patch.object(ProcessJanitor, "_query_process_running", return_value=False)
@patch.object(
    ProcessJanitor, "_snapshot_running_images", return_value=frozenset({"racyprocess.exe"})
)
def test_janitor_confirmed_gone_after_failed_kill_is_stopped(
    mock_snapshot, mock_query, mock_stop
) -> None:
    """A failed taskkill but a positively-confirmed absent image is a stop.

    The post-kill re-check stays a live per-image query: the pre-sweep
    snapshot predates the taskkill and cannot answer whether it landed.
    """
    janitor = ProcessJanitor()

    result = janitor.sweep(["RacyProcess.exe"])

    mock_query.assert_called_once_with("RacyProcess.exe")
    assert result.stopped == ["RacyProcess.exe"]
    assert result.failed == []


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
    for canonical_overlay in OVERLAY_PROCESS_IMAGES:
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


@patch("abso.core.process_janitor.subprocess.run")
def test_is_process_running_uses_exact_tasklist_image_name(mock_subprocess_run) -> None:
    mock_subprocess_run.return_value = MagicMock(
        returncode=0,
        stdout='"notmedal.exe","1111","Console","1","10000 K"\n',
    )

    janitor = ProcessJanitor()

    assert janitor._is_process_running("Medal.exe") is False
