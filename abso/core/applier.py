"""Profile application engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from abso.core.config import ConfigManager
from abso.core.exceptions import (
    ProfileNotFoundError,
)
from abso.profiles.base import BaseProfile
from abso.profiles.cod_bo7 import CodBo7Profile
from abso.profiles.cod_bo7_oled import CodBo7OLEDProfile
from abso.profiles.diablo4 import Diablo4Profile
from abso.profiles.diablo4_oled import Diablo4OLEDProfile
from abso.profiles.pacdeluxe import PACDeluxeProfile
from abso.profiles.pacdeluxe_oled import PACDeluxeOLEDProfile
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile
from abso.profiles.pokemon_auto_chess_oled import PokemonAutoChessOLEDProfile
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.rivals2_oled import Rivals2OLEDProfile
from abso.profiles.slippi_melee import SlippiMeleeProfile
from abso.profiles.slippi_melee_oled import SlippiMeleeOLEDProfile

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
        "slippi-melee-oled": SlippiMeleeOLEDProfile,
        "rivals2": Rivals2Profile,
        "rivals2-oled": Rivals2OLEDProfile,
        "cod-bo7": CodBo7Profile,
        "cod-bo7-oled": CodBo7OLEDProfile,
        "diablo4": Diablo4Profile,
        "diablo4-oled": Diablo4OLEDProfile,
        "pokemon-auto-chess": PokemonAutoChessProfile,
        "pokemon-auto-chess-oled": PokemonAutoChessOLEDProfile,
        "pacdeluxe": PACDeluxeProfile,
        "pacdeluxe-oled": PACDeluxeOLEDProfile,
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

        # Load configuration for overrides and disabled handlers
        config_manager = ConfigManager()
        profile_overrides = config_manager.get_profile_overrides(profile_name)

        applied: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []
        requires_reboot = False

        # Apply each settings category
        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__

            # Skip disabled handlers
            if config_manager.is_handler_disabled(handler_name):
                logger.info(f"Skipping disabled handler: {handler_name}")
                skipped.append(handler_name)
                continue

            try:
                # Get base settings from profile
                settings = profile.get_settings(handler_name)

                # Merge with user overrides from config
                if profile_overrides:
                    settings = self._merge_overrides(
                        settings, handler_name, profile_overrides
                    )

                # Inject game info for per-game Nvidia profiles
                if handler_name == "NvidiaSettingsHandler":
                    settings["executables"] = profile.executable_hints
                    settings["game_name"] = profile.display_name

                result = handler.apply(settings)

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

        if skipped:
            logger.info(f"Skipped handlers (disabled in config): {', '.join(skipped)}")

        return ApplyResult(
            success=success,
            error=error,
            requires_reboot=requires_reboot,
            in_game_settings=profile.has_in_game_settings(),
            applied_settings=applied,
            failed_settings=failed,
        )

    def _merge_overrides(
        self,
        settings: dict[str, Any],
        handler_name: str,
        overrides: Any,
    ) -> dict[str, Any]:
        """Merge profile settings with user overrides from config.

        Args:
            settings: Base settings from profile.
            handler_name: Name of the handler class.
            overrides: ProfileOverrides object from config.

        Returns:
            Merged settings dictionary.
        """
        # Map handler names to override attribute names
        handler_to_attr = {
            "NvidiaSettingsHandler": "nvidia",
            "WindowsSettingsHandler": "windows",
            "NetworkSettingsHandler": "network",
            "PowerSettingsHandler": "power",
            "TimerSettingsHandler": "timer",
            "MouseSettingsHandler": "mouse",
        }

        attr_name = handler_to_attr.get(handler_name)
        if not attr_name:
            return settings

        # Get handler-specific overrides
        handler_overrides = getattr(overrides, attr_name, {})
        if not handler_overrides:
            return settings

        # Deep merge: overrides take precedence
        merged = settings.copy()
        merged.update(handler_overrides)
        logger.debug(f"Applied overrides for {handler_name}: {handler_overrides}")

        return merged

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

    def verify_profile(self, profile_name: str) -> dict[str, Any]:
        """Verify that a profile's reboot-requiring settings are active.

        This checks if settings that normally require a reboot are already
        in effect. Useful for determining if a reboot is actually needed
        after applying a profile.

        Args:
            profile_name: Name of the profile to verify.

        Returns:
            Dict with 'all_active' bool and per-handler verification results.
        """
        profile = self._get_profile(profile_name)

        results: dict[str, Any] = {
            "profile": profile_name,
            "all_active": True,
            "handlers": {},
        }

        # Check handlers that have reboot-requiring settings
        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__

            # Only check handlers that have verify_active method
            if not hasattr(handler, "verify_active"):
                continue

            settings = profile.get_settings(handler_name)
            if not settings:
                continue

            try:
                handler_result = handler.verify_active(settings)
                results["handlers"][handler_name] = handler_result

                if not handler_result.get("all_active", True):
                    results["all_active"] = False

            except Exception as e:
                logger.error(f"Error verifying {handler_name}: {e}")
                results["handlers"][handler_name] = {
                    "error": str(e),
                    "all_active": False,
                }
                results["all_active"] = False

        return results

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
