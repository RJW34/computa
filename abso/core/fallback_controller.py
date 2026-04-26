"""FallbackController - Automatic reversion and failure persistence.

This module tracks runtime validation failures per-executable and persists
fallback decisions across reboots.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default state file location
DEFAULT_STATE_FILE = Path.home() / ".abso" / "fallback_state.json"


@dataclass
class FailureRecord:
    """Record of a runtime validation failure."""

    executable: str
    setting_path: str  # e.g., "WindowsSettingsHandler.hags"
    reason: str
    timestamp: str
    failure_count: int = 1


@dataclass
class FallbackState:
    """Persistent state for fallback decisions."""

    version: int = 1
    failures: dict[str, dict[str, FailureRecord]] = field(default_factory=dict)
    # Key: executable name, Value: dict of setting_path -> FailureRecord

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "version": self.version,
            "failures": {
                exe: {
                    path: asdict(record)
                    for path, record in records.items()
                }
                for exe, records in self.failures.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FallbackState:
        """Create from JSON dict."""
        state = cls(version=data.get("version", 1))

        failures_data = data.get("failures", {})
        for exe, records in failures_data.items():
            state.failures[exe] = {}
            for path, record_data in records.items():
                state.failures[exe][path] = FailureRecord(**record_data)

        return state


class FallbackController:
    """Manages fallback decisions and failure persistence.

    Fallback triggers:
    - Repeated runtime validation failures
    - Game crash during apply window
    - Severe frametime instability

    Persistence:
    - Stored per executable
    - Survives reboots
    - Overrideable only with explicit force flag
    """

    def __init__(
        self,
        state_file: Path | None = None,
        auto_load: bool = True,
    ) -> None:
        """Initialize FallbackController.

        Args:
            state_file: Path to state file. Defaults to ~/.abso/fallback_state.json
            auto_load: Whether to load state on init.
        """
        self.state_file = state_file or DEFAULT_STATE_FILE
        self.state = FallbackState()

        if auto_load:
            self.load()

    def load(self) -> bool:
        """Load state from disk.

        Returns:
            True if state was loaded, False if file doesn't exist or error.
        """
        if not self.state_file.exists():
            logger.debug(f"No fallback state file at {self.state_file}")
            return False

        try:
            if self.state_file.stat().st_size > 1024 * 1024:
                logger.warning("fallback state file unexpectedly large; ignoring")
                self.state = FallbackState()
                return False
        except OSError as e:
            logger.error(f"Failed to stat fallback state: {e}")
            return False

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.state = FallbackState.from_dict(data)
            logger.info(f"Loaded fallback state: {len(self.state.failures)} executables tracked")
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load fallback state: {e}")
            return False

    def save(self) -> bool:
        """Save state to disk.

        Returns:
            True if saved successfully.
        """
        try:
            # Ensure directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state.to_dict(), f, indent=2)
            logger.debug(f"Saved fallback state to {self.state_file}")
            return True
        except OSError as e:
            logger.error(f"Failed to save fallback state: {e}")
            return False

    def record_failure(
        self,
        executable: str,
        setting_path: str,
        reason: str,
    ) -> FailureRecord:
        """Record a runtime validation failure.

        Args:
            executable: Name of the game executable.
            setting_path: Handler.setting path (e.g., "WindowsSettingsHandler.hags")
            reason: Description of the failure.

        Returns:
            The created or updated FailureRecord.
        """
        executable = executable.lower()

        if executable not in self.state.failures:
            self.state.failures[executable] = {}

        existing = self.state.failures[executable].get(setting_path)

        if existing:
            existing.failure_count += 1
            existing.timestamp = datetime.now().isoformat()
            existing.reason = reason
            record = existing
        else:
            record = FailureRecord(
                executable=executable,
                setting_path=setting_path,
                reason=reason,
                timestamp=datetime.now().isoformat(),
            )
            self.state.failures[executable][setting_path] = record

        logger.warning(
            f"FallbackController: Recorded failure for {executable} "
            f"[{setting_path}]: {reason} (count: {record.failure_count})"
        )

        # Auto-save
        self.save()

        return record

    def get_failure(
        self,
        executable: str,
        setting_path: str,
    ) -> FailureRecord | None:
        """Get failure record for a specific setting.

        Args:
            executable: Name of the game executable.
            setting_path: Handler.setting path.

        Returns:
            FailureRecord if found, None otherwise.
        """
        executable = executable.lower()

        exe_failures = self.state.failures.get(executable, {})
        return exe_failures.get(setting_path)

    def get_all_failures(self, executable: str) -> dict[str, FailureRecord]:
        """Get all failure records for an executable.

        Args:
            executable: Name of the game executable.

        Returns:
            Dict of setting_path -> FailureRecord.
        """
        return self.state.failures.get(executable.lower(), {})

    def has_failures(self, executable: str) -> bool:
        """Check if an executable has any recorded failures.

        Args:
            executable: Name of the game executable.

        Returns:
            True if there are recorded failures.
        """
        return len(self.get_all_failures(executable)) > 0

    def clear_failure(
        self,
        executable: str,
        setting_path: str,
        force: bool = False,
    ) -> bool:
        """Clear a specific failure record.

        Args:
            executable: Name of the game executable.
            setting_path: Handler.setting path.
            force: Must be True to actually clear.

        Returns:
            True if cleared, False if not found or force not set.
        """
        if not force:
            logger.warning(
                "FallbackController: Cannot clear failure without force=True"
            )
            return False

        executable = executable.lower()

        if executable not in self.state.failures:
            return False

        if setting_path not in self.state.failures[executable]:
            return False

        del self.state.failures[executable][setting_path]

        # Clean up empty entries
        if not self.state.failures[executable]:
            del self.state.failures[executable]

        logger.info(
            f"FallbackController: Cleared failure for {executable} [{setting_path}]"
        )

        self.save()
        return True

    def clear_all_failures(
        self,
        executable: str,
        force: bool = False,
    ) -> int:
        """Clear all failure records for an executable.

        Args:
            executable: Name of the game executable.
            force: Must be True to actually clear.

        Returns:
            Number of failures cleared.
        """
        if not force:
            logger.warning(
                "FallbackController: Cannot clear failures without force=True"
            )
            return 0

        executable = executable.lower()

        if executable not in self.state.failures:
            return 0

        count = len(self.state.failures[executable])
        del self.state.failures[executable]

        logger.info(
            f"FallbackController: Cleared {count} failure(s) for {executable}"
        )

        self.save()
        return count

    def reset(self, force: bool = False) -> bool:
        """Reset all fallback state.

        Args:
            force: Must be True to actually reset.

        Returns:
            True if reset, False if force not set.
        """
        if not force:
            logger.warning(
                "FallbackController: Cannot reset without force=True"
            )
            return False

        self.state = FallbackState()
        self.save()

        logger.info("FallbackController: Reset all fallback state")
        return True

    def list_all(self) -> list[dict[str, Any]]:
        """List all tracked executables and their failures.

        Returns:
            List of dicts with executable info.
        """
        result = []
        for exe, failures in self.state.failures.items():
            result.append({
                "executable": exe,
                "failure_count": len(failures),
                "failures": [
                    {
                        "setting": path,
                        "reason": record.reason,
                        "count": record.failure_count,
                        "timestamp": record.timestamp,
                    }
                    for path, record in failures.items()
                ],
            })
        return result

    def should_use_fallback(
        self,
        executable: str,
        setting_path: str,
        threshold: int = 1,
    ) -> bool:
        """Check if a fallback should be used for a setting.

        Args:
            executable: Name of the game executable.
            setting_path: Handler.setting path.
            threshold: Number of failures before triggering fallback.

        Returns:
            True if fallback should be used.
        """
        record = self.get_failure(executable, setting_path)
        if not record:
            return False
        return record.failure_count >= threshold
