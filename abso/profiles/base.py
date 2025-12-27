"""Base profile class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class BaseProfile(ABC):
    """Abstract base class for game optimization profiles.

    Each game profile defines:
    - Target settings for each settings handler
    - In-game settings recommendations
    - Game-specific logic (e.g., executable detection)
    """

    @property
    @abstractmethod
    def profile_id(self) -> str:
        """Unique identifier for the profile."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of the profile."""
        pass

    @property
    @abstractmethod
    def optimization_target(self) -> str:
        """What this profile optimizes for (e.g., 'minimum_latency')."""
        pass

    @property
    @abstractmethod
    def executable_hints(self) -> list[str]:
        """Executable names to identify the game."""
        pass

    @abstractmethod
    def get_handlers(self) -> list[SettingsHandler]:
        """Get settings handlers used by this profile.

        Returns:
            List of SettingsHandler instances.
        """
        pass

    @abstractmethod
    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings for a specific handler.

        Args:
            handler_name: Name of the handler class.

        Returns:
            Settings dictionary for that handler.
        """
        pass

    def has_in_game_settings(self) -> bool:
        """Check if this profile has in-game settings recommendations.

        Returns:
            True if there are in-game recommendations.
        """
        return len(self.get_in_game_settings()) > 0

    @abstractmethod
    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get in-game settings recommendations.

        Returns:
            List of dicts with 'category', 'setting', 'value', 'reason' keys.
        """
        pass

    def generate_in_game_report(self) -> str:
        """Generate markdown report of in-game settings.

        Returns:
            Markdown formatted string.
        """
        lines = [
            f"# {self.display_name} - In-Game Settings",
            "",
            f"**Optimization Target:** {self.optimization_target}",
            "",
            "These settings should be configured within the game itself.",
            "",
        ]

        settings = self.get_in_game_settings()
        if not settings:
            lines.append("*No specific in-game settings recommendations.*")
            return "\n".join(lines)

        # Group by category
        categories: dict[str, list[dict[str, str]]] = {}
        for s in settings:
            cat = s.get("category", "General")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(s)

        for category, cat_settings in categories.items():
            lines.append(f"## {category}")
            lines.append("")

            for s in cat_settings:
                lines.append(f"- **{s['setting']}:** {s['value']}")
                if s.get("reason"):
                    lines.append(f"  - *{s['reason']}*")

            lines.append("")

        return "\n".join(lines)
