"""Hermetic tests for session core-partition steering.

No real CPU Set is touched: steer/clear callables are injected and journals
write to tmp_path only.
"""

from __future__ import annotations

import json
from pathlib import Path

from abso.core.cpu_sets import CorePartition
from abso.core.partition_steer import (
    CAPTURE_BACKGROUND_STEER_IMAGES,
    DEFAULT_BACKGROUND_STEER_IMAGES,
    NEVER_STEER_IMAGES,
    PartitionSteerer,
)

HYBRID = CorePartition(kind="hybrid", game_ids=(256, 257), background_ids=(300, 301))
GAME_ONLY = CorePartition(kind="hybrid", game_ids=(256,), background_ids=())
NO_SPLIT = CorePartition(kind="symmetric_multi_ccd")


class _Recorder:
    def __init__(self, fail_pids: set[int] | None = None) -> None:
        self.steered: list[tuple[int, tuple[int, ...]]] = []
        self.cleared: list[int] = []
        self._fail = fail_pids or set()

    def steer(self, pid: int, ids: tuple[int, ...]) -> bool:
        if pid in self._fail:
            return False
        self.steered.append((pid, tuple(ids)))
        return True

    def clear(self, pid: int) -> bool:
        self.cleared.append(pid)
        return True


def _steerer(
    partition: CorePartition = HYBRID,
    images: tuple[str, ...] = (),
    *,
    game_pid: int = 100,
    recorder: _Recorder | None = None,
    journal: Path | None = None,
) -> tuple[PartitionSteerer, _Recorder]:
    rec = recorder or _Recorder()
    steerer = PartitionSteerer(
        game_pid,
        partition,
        images,
        steer=rec.steer,
        clear=rec.clear,
        journal_path=journal,
    )
    return steerer, rec


class TestComputeDescendants:
    def test_walks_parent_chains(self) -> None:
        parent_map = {100: 1, 101: 100, 102: 101, 500: 1}
        assert PartitionSteerer.compute_descendants(parent_map, 100) == {101, 102}

    def test_cycle_safe(self) -> None:
        parent_map = {100: 101, 101: 100}
        assert PartitionSteerer.compute_descendants(parent_map, 100) == {101}


class TestGameSideSweep:
    def test_steers_game_and_descendants_to_game_ids(self) -> None:
        steerer, rec = _steerer()
        procs = [(100, "game.exe", 1), (101, "helper.exe", 100), (500, "other.exe", 1)]
        newly_game, newly_bg = steerer.sweep(procs)
        assert newly_game == 2
        assert newly_bg == 0
        assert set(rec.steered) == {(100, (256, 257)), (101, (256, 257))}

    def test_already_steered_not_repeated(self) -> None:
        steerer, rec = _steerer()
        procs = [(100, "game.exe", 1)]
        steerer.sweep(procs)
        steerer.sweep(procs)
        assert rec.steered == [(100, (256, 257))]

    def test_late_spawned_child_picked_up_next_sweep(self) -> None:
        steerer, rec = _steerer()
        steerer.sweep([(100, "game.exe", 1)])
        steerer.sweep([(100, "game.exe", 1), (101, "shader.exe", 100)])
        assert (101, (256, 257)) in rec.steered

    def test_failed_steer_retries_next_sweep(self) -> None:
        rec = _Recorder(fail_pids={101})
        steerer, _ = _steerer(recorder=rec)
        procs = [(100, "game.exe", 1), (101, "eac.exe", 100)]
        steerer.sweep(procs)
        assert steerer.steered_game_pids == {100}
        rec._fail.clear()
        steerer.sweep(procs)
        assert 101 in steerer.steered_game_pids

    def test_no_split_partition_is_total_noop(self) -> None:
        steerer, rec = _steerer(NO_SPLIT, ("chrome.exe",))
        assert steerer.sweep([(100, "game.exe", 1), (500, "chrome.exe", 1)]) == (0, 0)
        assert rec.steered == []


class TestBackgroundSweep:
    def test_listed_images_go_to_background_ids(self) -> None:
        steerer, rec = _steerer(HYBRID, ("chrome.exe", "obs64.exe"))
        procs = [
            (100, "game.exe", 1),
            (500, "Chrome.exe", 1),
            (600, "obs64.exe", 1),
            (700, "unrelated.exe", 1),
        ]
        newly_game, newly_bg = steerer.sweep(procs)
        assert newly_bg == 2
        assert (500, (300, 301)) in rec.steered
        assert (600, (300, 301)) in rec.steered
        assert all(pid != 700 for pid, _ in rec.steered)

    def test_game_subtree_never_background_steered(self) -> None:
        steerer, rec = _steerer(HYBRID, ("chrome.exe",))
        # The game spawned a chrome child (embedded browser) -> game side.
        procs = [(100, "game.exe", 1), (101, "chrome.exe", 100)]
        steerer.sweep(procs)
        assert (101, (256, 257)) in rec.steered
        assert (101, (300, 301)) not in rec.steered

    def test_game_image_name_protected_across_instances(self) -> None:
        # Browser game: the "game" is chrome.exe; a second chrome process that
        # is NOT in the visible subtree must still never go background.
        steerer, rec = _steerer(HYBRID, ("chrome.exe",), game_pid=100)
        procs = [(100, "chrome.exe", 1), (500, "chrome.exe", 2)]
        steerer.sweep(procs)
        assert (500, (300, 301)) not in rec.steered

    def test_never_steer_floor(self) -> None:
        steerer, rec = _steerer(HYBRID, ("dwm.exe", "svchost.exe"))
        steerer.sweep([(100, "game.exe", 1), (900, "dwm.exe", 1), (901, "svchost.exe", 1)])
        assert all(pid not in (900, 901) for pid, _ in rec.steered)

    def test_no_background_side_skips_background(self) -> None:
        steerer, rec = _steerer(GAME_ONLY, ("chrome.exe",))
        steerer.sweep([(100, "game.exe", 1), (500, "chrome.exe", 1)])
        assert rec.steered == [(100, (256,))]


class TestSteerExtra:
    def test_steers_heavy_process(self) -> None:
        steerer, rec = _steerer()
        steerer.sweep([(100, "game.exe", 1)])
        assert steerer.steer_extra(700, "encoder.exe") is True
        assert (700, (300, 301)) in rec.steered

    def test_guards_apply(self) -> None:
        steerer, rec = _steerer()
        steerer.sweep([(100, "game.exe", 1)])
        assert steerer.steer_extra(100, "game.exe") is False  # the game
        assert steerer.steer_extra(4, "system", ) is False  # system pid
        assert steerer.steer_extra(900, "dwm.exe") is False  # never-steer
        assert steerer.steer_extra(901, "game.exe") is False  # game image name

    def test_no_background_side_declines(self) -> None:
        steerer, _ = _steerer(GAME_ONLY)
        assert steerer.steer_extra(700, "encoder.exe") is False


class TestReleaseAndJournal:
    def test_release_all_clears_both_sides(self, tmp_path) -> None:
        journal = tmp_path / "steer.journal"
        steerer, rec = _steerer(HYBRID, ("chrome.exe",), journal=journal)
        steerer.sweep([(100, "game.exe", 1), (500, "chrome.exe", 1)])
        assert journal.exists()
        steerer.release_all()
        assert set(rec.cleared) == {100, 500}
        assert steerer.steered_game_pids == frozenset()
        assert steerer.steered_background_pids == frozenset()
        assert not journal.exists()

    def test_journal_records_both_sides_with_metadata(self, tmp_path) -> None:
        journal = tmp_path / "steer.journal"
        steerer, _ = _steerer(HYBRID, ("chrome.exe",), journal=journal)
        steerer.sweep([(100, "game.exe", 1), (500, "chrome.exe", 1)])
        data = json.loads(journal.read_text(encoding="utf-8"))
        assert data["kind"] == "hybrid"
        assert data["game_sets"] == 2
        assert data["background_sets"] == 2
        assert data["game"] == {"100": "game.exe"}
        assert data["background"] == {"500": "chrome.exe"}

    def test_steered_background_images_property(self, tmp_path) -> None:
        steerer, _ = _steerer(HYBRID, ("chrome.exe", "obs64.exe"))
        steerer.sweep(
            [
                (100, "game.exe", 1),
                (500, "chrome.exe", 1),
                (501, "chrome.exe", 1),
                (600, "obs64.exe", 1),
            ]
        )
        assert steerer.steered_background_images == ("chrome.exe", "obs64.exe")

    def test_recover_stale_journal_clears_and_deletes(self, tmp_path) -> None:
        journal = tmp_path / "steer.journal"
        journal.write_text(
            json.dumps(
                {
                    "game_pid": 100,
                    "game": {"100": "game.exe", "101": "helper.exe"},
                    "background": {"500": "chrome.exe"},
                }
            ),
            encoding="utf-8",
        )
        cleared: list[int] = []
        count = PartitionSteerer.recover_stale_journal(
            journal, clear=lambda pid: cleared.append(pid) or True
        )
        assert count == 3
        assert set(cleared) == {100, 101, 500}
        assert not journal.exists()

    def test_recover_legacy_list_journal(self, tmp_path) -> None:
        journal = tmp_path / "steer.journal"
        journal.write_text(
            json.dumps({"game_pid": 100, "game": [100], "background": [500]}),
            encoding="utf-8",
        )
        cleared: list[int] = []
        count = PartitionSteerer.recover_stale_journal(
            journal, clear=lambda pid: cleared.append(pid) or True
        )
        assert count == 2
        assert set(cleared) == {100, 500}

    def test_recover_missing_journal_is_noop(self, tmp_path) -> None:
        assert PartitionSteerer.recover_stale_journal(tmp_path / "none.journal") == 0

    def test_recover_corrupt_journal_deletes(self, tmp_path) -> None:
        journal = tmp_path / "steer.journal"
        journal.write_text("{not json", encoding="utf-8")
        assert PartitionSteerer.recover_stale_journal(journal, clear=lambda pid: True) == 0
        assert not journal.exists()


class TestImageConstants:
    def test_capture_list_is_encoders_only(self) -> None:
        lowered = {i.lower() for i in CAPTURE_BACKGROUND_STEER_IMAGES}
        assert "obs64.exe" in lowered
        assert "rtss.exe" not in lowered  # overlay hooks stay unsteered
        assert "lghub.exe" not in lowered  # input path stays unsteered

    def test_default_list_never_overlaps_never_steer(self) -> None:
        assert not {
            i.lower() for i in DEFAULT_BACKGROUND_STEER_IMAGES
        } & NEVER_STEER_IMAGES
