"""CrashDetector - Automatic rollback on game crash detection.

This module monitors game exits (via ``GameWatcher`` callbacks) and
determines whether the exit was a probable crash.  When a crash is
detected shortly after a profile was applied, it triggers an automatic
rollback to protect system stability.

Crash patterns are persisted in ``%LOCALAPPDATA%\\ABSO\\crash_history.json``
so that repeatedly-unstable profiles can be flagged before they are
applied again.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from abso.core.backup import BackupManager
    from abso.core.fallback_controller import FallbackController
    from abso.core.game_watcher import ProcessInfo
    from abso.core.stability_gate import StabilityGate

logger = logging.getLogger(__name__)

# Thresholds
_MIN_RUNTIME_SECONDS: float = 60.0
_PROFILE_APPLY_WINDOW = timedelta(minutes=5)
_CRASH_COUNT_UNSTABLE: int = 3

# Persistence path
_CRASH_HISTORY_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ABSO"
_CRASH_HISTORY_FILE = _CRASH_HISTORY_DIR / "crash_history.json"


@dataclass
class CrashRecord:
    """Single recorded crash event."""

    game_exe: str
    profile_id: str | None
    timestamp: str
    runtime_seconds: float
    auto_rolled_back: bool


@dataclass
class CrashHistory:
    """Persistent crash history container."""

    version: int = 1
    records: list[CrashRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "version": self.version,
            "records": [asdict(r) for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrashHistory:
        """Deserialize from a JSON dict."""
        history = cls(version=data.get("version", 1))
        for record_data in data.get("records", []):
            history.records.append(CrashRecord(**record_data))
        return history


class CrashDetector:
    """Detects game crashes and triggers automatic rollback.

    When a game process exits abnormally (runtime < 60s or non-zero exit
    code), and a profile was applied within the last 5 minutes, the
    detector will:

    1. Log the crash event.
    2. Persist a ``CrashRecord`` in crash history.
    3. Trigger ``backup_manager.restore_backup("latest")``.
    4. Flag the profile as unstable if 3+ crashes are recorded for the
       same game/profile combination.
    5. Invoke the optional notification callback.

    Args:
        backup_manager: ``BackupManager`` used for automatic rollback.
        stability_gate: Optional ``StabilityGate`` for reporting failures
            to its ``FallbackController``.
    """

    def __init__(
        self,
        backup_manager: BackupManager,
        stability_gate: StabilityGate | None = None,
    ) -> None:
        self._backup_manager = backup_manager
        self._stability_gate = stability_gate
        self._history = self._load_history()

        # Track the most recent profile application for the rollback
        # decision window.
        self._last_profile_id: str | None = None
        self._last_profile_applied_at: datetime | None = None

        # Optional notification callback (e.g. tray balloon notification).
        self._notify_callback: Callable[[str], Any] | None = None

    # -- public interface ---------------------------------------------------

    def set_notify_callback(self, callback: Callable[[str], Any]) -> None:
        """Register a callback for crash notifications.

        Args:
            callback: A callable that receives a human-readable message
                string (e.g. for a tray balloon tip).
        """
        self._notify_callback = callback

    def record_profile_apply(self, profile_id: str) -> None:
        """Record that a profile was just applied.

        This starts the 5-minute rollback window.

        Args:
            profile_id: The profile that was applied.
        """
        self._last_profile_id = profile_id
        self._last_profile_applied_at = datetime.now()
        logger.debug(
            "CrashDetector: profile apply recorded — %s at %s",
            profile_id,
            self._last_profile_applied_at.isoformat(),
        )

    def on_game_exit(
        self,
        process_info: ProcessInfo,
        exit_code: int | None = None,
    ) -> None:
        """Called by GameWatcher when a watched process exits.

        Evaluates whether the exit looks like a crash and takes
        appropriate action.

        Args:
            process_info: Information about the exited process.
            exit_code: Process exit code if available (``None`` when
                the watcher could not retrieve it).
        """
        runtime = (datetime.now() - process_info.start_time).total_seconds()
        game_exe = process_info.name.lower()

        is_crash = self._evaluate_crash(runtime, exit_code)

        if not is_crash:
            logger.debug(
                "Normal exit: %s (PID %d) ran for %.1fs, exit_code=%s",
                game_exe,
                process_info.pid,
                runtime,
                exit_code,
            )
            return

        # -- Crash detected -------------------------------------------------
        profile_id = self._resolve_profile_id(process_info)
        rolled_back = False

        logger.warning(
            "Probable crash detected: %s (PID %d) — runtime=%.1fs, "
            "exit_code=%s, profile=%s",
            game_exe,
            process_info.pid,
            runtime,
            exit_code,
            profile_id,
        )

        # Decide whether to auto-rollback.
        if profile_id and self._within_apply_window():
            rolled_back = self._auto_rollback(game_exe, profile_id)

        # Persist crash record.
        record = CrashRecord(
            game_exe=game_exe,
            profile_id=profile_id,
            timestamp=datetime.now().isoformat(),
            runtime_seconds=round(runtime, 1),
            auto_rolled_back=rolled_back,
        )
        self._history.records.append(record)
        self._save_history()

        # Check for repeated instability.
        if profile_id and self.is_profile_unstable(profile_id, game_exe):
            logger.error(
                "Profile '%s' flagged UNSTABLE for %s "
                "(%d+ crashes recorded)",
                profile_id,
                game_exe,
                _CRASH_COUNT_UNSTABLE,
            )
            self._report_to_stability_gate(game_exe, profile_id)

        # Notification callback.
        self._send_notification(game_exe, profile_id, rolled_back)

    def get_crash_history(
        self,
        game_exe: str | None = None,
    ) -> list[CrashRecord]:
        """Query persisted crash history.

        Args:
            game_exe: If provided, filter records to this executable
                (case-insensitive).  If ``None``, return all records.

        Returns:
            List of matching ``CrashRecord`` entries, newest first.
        """
        records = self._history.records
        if game_exe is not None:
            game_exe_lower = game_exe.lower()
            records = [r for r in records if r.game_exe == game_exe_lower]
        return list(reversed(records))

    def is_profile_unstable(self, profile_id: str, game_exe: str) -> bool:
        """Check whether a profile has caused repeated crashes for a game.

        Args:
            profile_id: The profile identifier to check.
            game_exe: The game executable name (case-insensitive).

        Returns:
            ``True`` if the profile has caused ``_CRASH_COUNT_UNSTABLE``
            or more crashes for the given game.
        """
        game_exe_lower = game_exe.lower()
        count = sum(
            1
            for r in self._history.records
            if r.game_exe == game_exe_lower and r.profile_id == profile_id
        )
        return count >= _CRASH_COUNT_UNSTABLE

    # -- internal helpers ---------------------------------------------------

    def _evaluate_crash(
        self,
        runtime_seconds: float,
        exit_code: int | None,
    ) -> bool:
        """Determine whether an exit event qualifies as a probable crash.

        A crash is diagnosed when *either* condition is met:
        - The process ran for less than ``_MIN_RUNTIME_SECONDS``.
        - A non-zero exit code was explicitly reported.
        """
        if exit_code is not None and exit_code != 0:
            return True
        if runtime_seconds < _MIN_RUNTIME_SECONDS:
            return True
        return False

    def _resolve_profile_id(self, process_info: ProcessInfo) -> str | None:
        """Determine which profile was active when the process ran."""
        if process_info.profile_id is not None:
            return process_info.profile_id
        return self._last_profile_id

    def _within_apply_window(self) -> bool:
        """Return ``True`` if a profile was applied within the rollback window."""
        if self._last_profile_applied_at is None:
            return False
        return (datetime.now() - self._last_profile_applied_at) <= _PROFILE_APPLY_WINDOW

    def _auto_rollback(self, game_exe: str, profile_id: str) -> bool:
        """Attempt to restore the latest backup.

        Returns:
            ``True`` if rollback succeeded.
        """
        logger.warning(
            "Auto-rollback triggered: %s crashed within apply window "
            "of profile '%s'",
            game_exe,
            profile_id,
        )

        try:
            restore_summary = self._backup_manager.restore_backup("latest")
            if restore_summary.complete:
                logger.info("Auto-rollback completed successfully")
                return True

            incomplete = restore_summary.failed_components + restore_summary.skipped_components
            handlers = ", ".join(item["handler"] for item in incomplete)
            logger.error("Auto-rollback incomplete for handlers: %s", handlers)
            return False
        except Exception:
            logger.error(
                "Auto-rollback FAILED for profile '%s'",
                profile_id,
                exc_info=True,
            )
            return False

    def _report_to_stability_gate(
        self,
        game_exe: str,
        profile_id: str,
    ) -> None:
        """If a StabilityGate with a FallbackController is available,
        report the crash pattern so future applications of this profile
        use safe fallback values.
        """
        if self._stability_gate is None:
            return

        fallback: FallbackController | None = getattr(
            self._stability_gate, "fallback_controller", None
        )
        if fallback is None:
            return

        try:
            fallback.record_failure(
                executable=game_exe,
                setting_path=f"CrashDetector.profile:{profile_id}",
                reason=(
                    f"Profile '{profile_id}' caused {_CRASH_COUNT_UNSTABLE}+ "
                    f"crashes for {game_exe}"
                ),
            )
        except Exception:
            logger.error(
                "Failed to report crash to FallbackController",
                exc_info=True,
            )

    def _send_notification(
        self,
        game_exe: str,
        profile_id: str | None,
        rolled_back: bool,
    ) -> None:
        """Invoke the notification callback if registered."""
        if self._notify_callback is None:
            return

        if rolled_back:
            message = (
                f"ABSO: {game_exe} crashed after applying '{profile_id}'. "
                f"Settings automatically rolled back."
            )
        elif profile_id:
            message = (
                f"ABSO: {game_exe} crashed (profile '{profile_id}' was active)."
            )
        else:
            message = f"ABSO: {game_exe} exited abnormally."

        try:
            self._notify_callback(message)
        except Exception:
            logger.error("Notification callback failed", exc_info=True)

    # -- persistence --------------------------------------------------------

    def _load_history(self) -> CrashHistory:
        """Load crash history from disk."""
        if not _CRASH_HISTORY_FILE.exists():
            logger.debug("No crash history file at %s", _CRASH_HISTORY_FILE)
            return CrashHistory()

        try:
            data = json.loads(_CRASH_HISTORY_FILE.read_text(encoding="utf-8"))
            history = CrashHistory.from_dict(data)
            logger.info(
                "Loaded crash history: %d records", len(history.records),
            )
            return history
        except (json.JSONDecodeError, OSError, TypeError, KeyError) as exc:
            logger.error("Failed to load crash history: %s", exc)
            return CrashHistory()

    def _save_history(self) -> None:
        """Persist crash history to disk."""
        try:
            _CRASH_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            _CRASH_HISTORY_FILE.write_text(
                json.dumps(self._history.to_dict(), indent=2),
                encoding="utf-8",
            )
            logger.debug("Saved crash history to %s", _CRASH_HISTORY_FILE)
        except OSError as exc:
            logger.error("Failed to save crash history: %s", exc)
