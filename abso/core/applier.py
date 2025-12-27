"""Profile application engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from abso.profiles.base import BaseProfile
from abso.profiles.slippi_melee import SlippiMeleeProfile
from abso.profiles.cod_bo7 import CodBo7Profile
from abso.profiles.diablo4 import Diablo4Profile
from abso.profiles.rivals2 import Rivals2Profile
from abso.core.exceptions import (
    ProfileNotFoundError,
    ProfileApplyError,
    SettingsApplyError,
)

logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    """Result of applying a profile."""

    success: bool
    error: str | None = None
    requires_reboot: bool = False
    in_game_settings: bool = False
    applied_settings: list[str] = field(default_factory=list)
    failed_settings: list[str] = field(default_factory=list)


class ProfileApplier:
    """Applies game optimization profiles to the system."""

    # Registry of available profiles
    PROFILES: dict[str, type[BaseProfile]] = {
        "slippi-melee": SlippiMeleeProfile,
        "cod-bo7": CodBo7Profile,
        "diablo4": Diablo4Profile,
        "rivals2": Rivals2Profile,
    }

    def __init__(self) -> None:
        self._profiles: dict[str, BaseProfile] = {}

    def _get_profile(self, profile_name: str) -> BaseProfile:
        """Get or create a profile instance.

        Args:
            profile_name: Name of the profile.

        Returns:
            Profile instance.

        Raises:
            ValueError: If profile not found.
        """
        if profile_name not in self._profiles:
            profile_class = self.PROFILES.get(profile_name)
            if not profile_class:
                available = ", ".join(self.PROFILES.keys())
                raise ProfileNotFoundError(
                    f"Unknown profile: {profile_name}",
                    details=f"Available profiles: {available}"
                )
            self._profiles[profile_name] = profile_class()

        return self._profiles[profile_name]

    def apply_profile(self, profile_name: str) -> ApplyResult:
        """Apply a game optimization profile.

        Args:
            profile_name: Name of the profile to apply.

        Returns:
            ApplyResult with status and details.
        """
        try:
            profile = self._get_profile(profile_name)
        except ProfileNotFoundError as e:
            return ApplyResult(success=False, error=str(e))

        applied: list[str] = []
        failed: list[str] = []
        requires_reboot = False

        # Apply each settings category
        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__

            try:
                result = handler.apply(profile.get_settings(handler_name))

                if result.get("success", False):
                    applied.append(handler_name)
                    if result.get("requires_reboot", False):
                        requires_reboot = True
                else:
                    failed.append(f"{handler_name}: {result.get('error', 'Unknown error')}")

            except PermissionError as e:
                logger.error(f"Permission denied applying {handler_name}: {e}")
                failed.append(f"{handler_name}: Permission denied - {e}")
            except OSError as e:
                logger.error(f"OS error applying {handler_name}: {e}")
                failed.append(f"{handler_name}: OS error - {e}")
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Configuration error applying {handler_name}: {e}")
                failed.append(f"{handler_name}: Configuration error - {e}")

        success = len(failed) == 0
        error = "; ".join(failed) if failed else None

        return ApplyResult(
            success=success,
            error=error,
            requires_reboot=requires_reboot,
            in_game_settings=profile.has_in_game_settings(),
            applied_settings=applied,
            failed_settings=failed,
        )

    def generate_report(self, profile_name: str, output_dir: Path) -> Path:
        """Generate in-game settings report for a profile.

        Args:
            profile_name: Name of the profile.
            output_dir: Directory to save the report.

        Returns:
            Path to the generated report.

        Raises:
            ValueError: If profile not found.
        """
        profile = self._get_profile(profile_name)

        report_path = output_dir / f"{profile_name}_settings.md"
        report_content = profile.generate_in_game_report()

        report_path.write_text(report_content, encoding="utf-8")

        return report_path

    def list_profiles(self) -> list[dict[str, Any]]:
        """List all available profiles.

        Returns:
            List of profile info dicts.
        """
        profiles = []

        for name, profile_class in self.PROFILES.items():
            profile = profile_class()
            profiles.append({
                "id": name,
                "display_name": profile.display_name,
                "description": profile.description,
                "optimization_target": profile.optimization_target,
            })

        return profiles
