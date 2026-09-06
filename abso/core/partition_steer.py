"""Session core-partition steering: game -> fast cores, background -> the rest.

Implements the two-sided core split popularized by CPU-partitioning tools
(Process Lasso, CPUSetSetter, Game-Optimizer): while a game runs, the game and
its descendants are biased toward the "fast" side of the machine (P-cores on
Intel hybrid, the V-Cache CCD on AMD X3D) and a curated list of background
apps (OBS, browsers, Discord, Spotify) is biased toward the other side --
at full clock speed, unlike EcoQoS throttling, so capture/encode tools keep
their performance while freeing the fast cores for the game.

Mechanism is soft ``SetProcessDefaultCpuSets`` steering only: hard affinity is
never touched, threads still spill under load, and the minimal
``PROCESS_SET_LIMITED_INFORMATION`` right keeps this anti-cheat-benign. CPU
Sets are NOT inherited by child processes, so the steerer re-sweeps every
poll: late-spawned game children and background apps are picked up within one
poll period.

State is per-process and runtime-only (the OS clears it at process exit).
A small JSON journal records steered PIDs so a crashed governor's leftovers
can be cleared on the next session start instead of lingering until the
steered processes exit.

Nothing here runs until the cpu-balance governor wires it for a game session;
enablement is profile-driven (``BaseProfile.cpu_partition_policy``) with
``abso.yaml`` ``cpu_sets`` overrides.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from pathlib import Path

from abso.core import cpu_sets
from abso.core.cpu_sets import CorePartition
from abso.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

# Hard floor: never steer core OS infrastructure regardless of any configured
# list. Everything else is protected structurally (game subtree, game image
# names, explicit curated lists) rather than by name.
NEVER_STEER_IMAGES: frozenset[str] = frozenset(
    name.lower()
    for name in (
        "system",
        "registry",
        "idle",
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
        "winlogon.exe",
        "services.exe",
        "lsass.exe",
        "svchost.exe",
        "dwm.exe",
        "audiodg.exe",
        "fontdrvhost.exe",
    )
)

# Default background-steer targets for gaming lanes: heavy multi-process apps
# that commonly stay open during play and steal fast-core time. These run at
# FULL speed on the background side -- this is placement, not throttling -- so
# voice (Discord) and music (Spotify) stay glitch-free.
DEFAULT_BACKGROUND_STEER_IMAGES: tuple[str, ...] = (
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "opera_gx.exe",
    "discord.exe",
    "spotify.exe",
    "slack.exe",
    "wallpaper32.exe",
    "wallpaper64.exe",
)

# Additional targets for capture-safe lanes: the encoders that those lanes
# deliberately keep alive. NVENC offloads the encode to the GPU, so their CPU
# work (composition, UI, muxing) is comfortably served by full-speed
# background cores. Deliberately excludes overlay/peripheral tools (RTSS,
# G HUB, NVIDIA Share) whose in-game hooks or input paths should follow
# system scheduling.
CAPTURE_BACKGROUND_STEER_IMAGES: tuple[str, ...] = (
    "obs64.exe",
    "obs32.exe",
    "Medal.exe",
    "MedalEncoder.exe",
)


def default_journal_path() -> Path:
    """Journal location inside the installed app-data dir."""
    from abso.core.app_paths import app_data_dir

    return app_data_dir() / "partition-steer.journal"


class PartitionSteerer:
    """Two-sided CPU Sets steering for one game session.

    Every :meth:`sweep` steers the game process and its descendants toward the
    partition's game side and any running background-list image toward the
    background side. :meth:`release_all` clears everything it steered.

    Dependencies are injected so the decision logic is fully unit-testable
    without touching real processes.
    """

    def __init__(
        self,
        game_pid: int,
        partition: CorePartition,
        background_images: Iterable[str] = (),
        *,
        never_steer: Iterable[str] | None = None,
        steer: Callable[[int, tuple[int, ...]], bool] | None = None,
        clear: Callable[[int], bool] | None = None,
        journal_path: Path | None = None,
    ) -> None:
        self._game_pid = game_pid
        self._partition = partition
        self._background = {name.lower() for name in background_images}
        never = NEVER_STEER_IMAGES if never_steer is None else {n.lower() for n in never_steer}
        self._never_steer = frozenset(never)
        self._steer = steer or (lambda pid, ids: cpu_sets.steer_process_to_sets(pid, ids))
        self._clear = clear or (lambda pid: cpu_sets.clear_process_cpu_sets(pid))
        self._journal_path = journal_path
        # pid -> image name, so the journal doubles as a session status
        # artifact (the tray reads it to log what was steered where).
        self._steered_game: dict[int, str] = {}
        self._steered_background: dict[int, str] = {}
        # Image names belonging to the game itself (learned from the live
        # process list). Protects the browser-game case: if the "game" is
        # chrome.exe, other chrome.exe processes must never be pushed to the
        # background side even when chrome.exe is on the background list.
        self._game_image_names: set[str] = set()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def partition(self) -> CorePartition:
        return self._partition

    @property
    def steered_game_pids(self) -> frozenset[int]:
        return frozenset(self._steered_game)

    @property
    def steered_background_pids(self) -> frozenset[int]:
        return frozenset(self._steered_background)

    @property
    def steered_background_images(self) -> tuple[str, ...]:
        """Distinct image names currently steered to the background side."""
        return tuple(sorted({n for n in self._steered_background.values() if n}))

    # ------------------------------------------------------------------
    # Core sweep
    # ------------------------------------------------------------------
    @staticmethod
    def compute_descendants(parent_map: dict[int, int], root: int) -> frozenset[int]:
        """Every PID whose parent chain leads back to ``root``."""
        children: dict[int, list[int]] = {}
        for pid, ppid in parent_map.items():
            children.setdefault(ppid, []).append(pid)
        descendants: set[int] = set()
        stack = list(children.get(root, []))
        while stack:
            pid = stack.pop()
            if pid in descendants or pid == root:
                continue
            descendants.add(pid)
            stack.extend(children.get(pid, []))
        return frozenset(descendants)

    def sweep(self, processes: list[tuple[int, str, int]]) -> tuple[int, int]:
        """Steer the game subtree and background images. Returns newly-steered
        ``(game_count, background_count)``.

        ``processes`` is the toolhelp snapshot as ``(pid, image, parent_pid)``.
        """
        parent_map = {pid: ppid for pid, _name, ppid in processes}
        names = {pid: name for pid, name, _ppid in processes}
        descendants = self.compute_descendants(parent_map, self._game_pid)
        game_side = {self._game_pid} | descendants

        game_name = names.get(self._game_pid)
        if game_name:
            self._game_image_names.add(game_name.lower())

        newly_game = 0
        if self._partition.has_game_side:
            for pid in game_side:
                if pid in self._steered_game or pid <= 4:
                    continue
                if self._steer(pid, self._partition.game_ids):
                    self._steered_game[pid] = names.get(pid, "")
                    newly_game += 1

        newly_background = 0
        if self._partition.has_background_side and self._background:
            for pid, name, _ppid in processes:
                if pid in self._steered_background or pid in self._steered_game:
                    continue
                if not self._should_steer_background(pid, name, game_side):
                    continue
                if self._steer(pid, self._partition.background_ids):
                    self._steered_background[pid] = name
                    newly_background += 1

        if newly_game or newly_background:
            self._write_journal()
        return newly_game, newly_background

    def _should_steer_background(self, pid: int, name: str, game_side: set[int]) -> bool:
        if pid <= 4 or pid in game_side:
            return False
        name_lower = name.lower()
        if name_lower in self._never_steer or name_lower in self._game_image_names:
            return False
        return name_lower in self._background

    def steer_extra(self, pid: int, name: str) -> bool:
        """Steer one heavy process to the background side (auto-detect path).

        Applies the same structural guards as the list-based sweep; the caller
        is responsible for CPU-threshold/sustain qualification and for its own
        exclusion policy (anti-cheat, protected images, foreground).
        """
        if not self._partition.has_background_side:
            return False
        if pid in self._steered_background or pid in self._steered_game:
            return False
        name_lower = name.lower()
        if pid <= 4 or pid == self._game_pid:
            return False
        if name_lower in self._never_steer or name_lower in self._game_image_names:
            return False
        if self._steer(pid, self._partition.background_ids):
            self._steered_background[pid] = name
            self._write_journal()
            return True
        return False

    # ------------------------------------------------------------------
    # Release / crash recovery
    # ------------------------------------------------------------------
    def release_all(self) -> None:
        """Clear CPU Sets on every process this steerer touched."""
        for pid in list(self._steered_game) + list(self._steered_background):
            try:
                self._clear(pid)
            except Exception as exc:  # a vanished PID is fine
                logger.debug("clear cpu sets for pid %d failed: %s", pid, exc)
        self._steered_game.clear()
        self._steered_background.clear()
        self._delete_journal()

    def _write_journal(self) -> None:
        if self._journal_path is None:
            return
        try:
            atomic_write_json(
                self._journal_path,
                {
                    "game_pid": self._game_pid,
                    "kind": self._partition.kind,
                    "game_sets": len(self._partition.game_ids),
                    "background_sets": len(self._partition.background_ids),
                    "game": {str(pid): name for pid, name in sorted(self._steered_game.items())},
                    "background": {
                        str(pid): name
                        for pid, name in sorted(self._steered_background.items())
                    },
                },
            )
        except Exception as exc:
            logger.debug("partition-steer journal write failed: %s", exc)

    def _delete_journal(self) -> None:
        if self._journal_path is None:
            return
        try:
            self._journal_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.debug("partition-steer journal delete failed: %s", exc)

    @classmethod
    def recover_stale_journal(
        cls,
        journal_path: Path,
        *,
        clear: Callable[[int], bool] | None = None,
    ) -> int:
        """Clear CPU Sets left behind by a crashed session's journal.

        Returns the number of PIDs cleared. A recycled PID only has its (most
        likely unset) default CPU Sets cleared, which reverts it to system
        scheduling -- the safe direction.
        """
        try:
            if not journal_path.exists():
                return 0
            data = json.loads(journal_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("partition-steer journal unreadable: %s", exc)
            data = {}
        clear_fn = clear or (lambda pid: cpu_sets.clear_process_cpu_sets(pid))
        cleared = 0
        for key in ("game", "background"):
            entries = data.get(key) or []
            # Both journal shapes: {pid: name} maps and legacy pid lists.
            pids = entries.keys() if isinstance(entries, dict) else entries
            for pid in pids:
                try:
                    if clear_fn(int(pid)):
                        cleared += 1
                except Exception as exc:
                    logger.debug("stale clear for pid %r failed: %s", pid, exc)
        try:
            journal_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.debug("stale journal delete failed: %s", exc)
        if cleared:
            logger.info("Cleared stale CPU Set steering for %d process(es)", cleared)
        return cleared
