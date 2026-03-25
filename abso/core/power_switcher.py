"""Per-process power plan switching.

Switches the system power plan to Ultimate Performance when a game
launches and restores the previous plan when the game exits.
Uses a state file for crash recovery.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Common power plan GUIDs
PLAN_GUIDS: dict[str, str] = {
    "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    # Ultimate Performance is created dynamically; GUID varies per machine
}


@dataclass
class PowerSwitcherState:
    pre_game_plan_guid: str | None = None
    game_plan_name: str | None = None
    game_exe: str | None = None


class PowerSwitcher:
    """Orchestrates power plan switching on game lifecycle events."""

    def __init__(self, state_dir: Path | None = None) -> None:
        if state_dir is None:
            state_dir = Path.cwd()
        self._state_file = state_dir / ".power_switcher_state.json"

    def get_active_plan_guid(self) -> str | None:
        """Get GUID of the currently active power plan via powercfg.

        Parses the output of ``powercfg /getactivescheme`` which looks like:
            Power Scheme GUID: 381b4222-...  (Balanced)

        Returns:
            The active plan GUID string, or ``None`` on failure.
        """
        try:
            result = subprocess.run(
                ["powercfg", "/getactivescheme"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning("powercfg /getactivescheme failed: %s", result.stderr.strip())
                return None

            # Expected format: "Power Scheme GUID: <guid>  (<name>)"
            for token in result.stdout.split():
                # GUIDs are 36 chars with hyphens (8-4-4-4-12)
                if len(token) == 36 and token.count("-") == 4:
                    return token.lower()

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.error("Failed to query active power plan: %s", exc)

        return None

    def set_active_plan(self, guid: str) -> bool:
        """Set the active power plan by GUID.

        Args:
            guid: The power plan GUID to activate.

        Returns:
            ``True`` if the plan was set successfully.
        """
        try:
            result = subprocess.run(
                ["powercfg", "/setactive", guid],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.error("powercfg /setactive %s failed: %s", guid, result.stderr.strip())
                return False
            logger.info("Active power plan set to %s", guid)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.error("Failed to set active power plan %s: %s", guid, exc)
            return False

    def find_plan_guid(self, name: str) -> str | None:
        """Find a power plan GUID by name (case-insensitive partial match).

        Checks the well-known ``PLAN_GUIDS`` dictionary first, then parses
        the output of ``powercfg /list`` for a matching description.

        Args:
            name: Full or partial name of the power plan.

        Returns:
            The matching GUID string, or ``None`` if not found.
        """
        name_lower = name.lower().replace(" ", "_")

        # Check well-known plans first
        for key, guid in PLAN_GUIDS.items():
            if name_lower == key or name_lower in key:
                return guid

        # Parse powercfg /list output
        try:
            result = subprocess.run(
                ["powercfg", "/list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning("powercfg /list failed: %s", result.stderr.strip())
                return None

            # Each line looks like:
            # Power Scheme GUID: 381b4222-...  (Balanced)
            # or with * for active plan
            for line in result.stdout.splitlines():
                if name.lower() in line.lower():
                    for token in line.split():
                        if len(token) == 36 and token.count("-") == 4:
                            return token.lower()

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.error("Failed to enumerate power plans: %s", exc)

        return None

    def on_game_start(self, plan_name: str, game_exe: str = "") -> bool:
        """Switch to gaming power plan and save current plan for restoration.

        Args:
            plan_name: Name of the target power plan (e.g. ``"Ultimate Performance"``).
            game_exe: Optional executable name for logging/state tracking.

        Returns:
            ``True`` if the power plan was switched successfully.
        """
        current_guid = self.get_active_plan_guid()
        if current_guid is None:
            logger.error("Cannot determine current power plan; aborting switch")
            return False

        target_guid = self.find_plan_guid(plan_name)
        if target_guid is None:
            logger.error("Power plan '%s' not found on this system", plan_name)
            return False

        if current_guid == target_guid:
            logger.info("Already on '%s' plan; no switch needed", plan_name)
            return True

        # Save state before switching
        state = PowerSwitcherState(
            pre_game_plan_guid=current_guid,
            game_plan_name=plan_name,
            game_exe=game_exe,
        )
        self._save_state(state)

        if not self.set_active_plan(target_guid):
            self._clear_state()
            return False

        logger.info(
            "Switched power plan to '%s' for %s (was %s)",
            plan_name,
            game_exe or "game",
            current_guid,
        )
        return True

    def on_game_exit(self) -> bool:
        """Restore pre-game power plan.

        Reads the saved state file and restores the power plan that was
        active before the game started. Cleans up the state file afterward.

        Returns:
            ``True`` if the plan was restored (or no restoration was needed).
        """
        state = self._load_state()
        if state is None:
            logger.debug("No power switcher state found; nothing to restore")
            return True

        if state.pre_game_plan_guid is None:
            logger.warning("State file present but no pre-game GUID recorded")
            self._clear_state()
            return False

        success = self.set_active_plan(state.pre_game_plan_guid)
        if success:
            logger.info(
                "Restored power plan to %s after %s exited",
                state.pre_game_plan_guid,
                state.game_exe or "game",
            )
        else:
            logger.error(
                "Failed to restore power plan to %s",
                state.pre_game_plan_guid,
            )

        self._clear_state()
        return success

    def recover_from_crash(self) -> bool:
        """Restore power plan if state file exists from a previous crash.

        Called on tray startup. If a state file exists it means a previous
        session did not exit cleanly, so we restore the saved plan and
        clean up.

        Returns:
            ``True`` if recovery succeeded or was not needed.
        """
        if not self._state_file.exists():
            return True

        logger.warning(
            "Power switcher state file found — recovering from unclean shutdown"
        )
        return self.on_game_exit()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self, state: PowerSwitcherState) -> None:
        """Write state to JSON file."""
        try:
            self._state_file.write_text(
                json.dumps(asdict(state), indent=2),
                encoding="utf-8",
            )
            logger.debug("Saved power switcher state to %s", self._state_file)
        except OSError as exc:
            logger.error("Failed to save power switcher state: %s", exc)

    def _load_state(self) -> PowerSwitcherState | None:
        """Read state from JSON file, return ``None`` if not found."""
        if not self._state_file.exists():
            return None
        try:
            data: dict[str, Any] = json.loads(
                self._state_file.read_text(encoding="utf-8")
            )
            return PowerSwitcherState(**data)
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.error("Failed to load power switcher state: %s", exc)
            return None

    def _clear_state(self) -> None:
        """Delete state file."""
        try:
            if self._state_file.exists():
                self._state_file.unlink()
                logger.debug("Cleared power switcher state file")
        except OSError as exc:
            logger.error("Failed to delete power switcher state file: %s", exc)
