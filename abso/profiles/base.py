"""Base profile class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class BaseProfile(ABC):
    """Abstract base class for game optimization profiles.

    Each game profile defines:
    - Target settings for each settings handler
    - In-game settings recommendations
    - Game-specific logic (e.g., executable detection)

    Validation Metadata (optional overrides):
    - is_online_profile: Whether this profile is for online/rollback gameplay
    - is_emulator_profile: Whether this is for an emulator (fixed framerate)
    - requires_reflex: Whether the game uses NVIDIA Reflex
    - is_sdr_only: Whether the game is SDR-only (no HDR support)
    - network_scope: What network optimizations are allowed
    - graphics_api: Primary graphics API (dx11, dx12, vulkan)
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

    # === Optional Validation Metadata ===
    # Subclasses can override these for more precise validation

    @property
    def is_online_profile(self) -> bool:
        """Whether this profile is for online/rollback gameplay.

        When True, RollbackGuard will enforce stricter settings.
        Default: Inferred from optimization_target.
        """
        return self.optimization_target in {
            "stable_online",
            "online",
            "ranked",
            "matchmaking",
        }

    @property
    def is_emulator_profile(self) -> bool:
        """Whether this is an emulator profile (fixed framerate).

        Emulator profiles running at fixed framerates (e.g., 60fps)
        don't benefit from VRR and should disable G-Sync.
        Default: Inferred from executable hints.
        """
        emulator_exes = {
            "dolphin.exe", "slippi dolphin.exe",
            "ryujinx.exe", "ryujinx.ava.exe", "ryujinx.headless.sdl2.exe",
            "yuzu.exe", "cemu.exe", "rpcs3.exe",
        }
        return any(
            exe.lower() in emulator_exes
            for exe in self.executable_hints
        )

    @property
    def requires_reflex(self) -> bool:
        """Whether the game uses NVIDIA Reflex.

        When True, driver LLM should be OFF to avoid conflicts.
        Default: False (override in profiles with Reflex support).
        """
        return False

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        """Whether profile should only run when VRR/G-SYNC support is confirmed.

        Use this for VRR-dependent profiles that should fail fast when the
        monitor stack is not reporting VRR capability.
        """
        return False

    @property
    def is_sdr_only(self) -> bool:
        """Whether the game is SDR-only (no native HDR).

        When True, HDR should be disabled to prevent washed-out colors.
        Default: Inferred from profile characteristics.
        """
        # Emulators are typically SDR
        if self.is_emulator_profile:
            return True

        # Check for known SDR games
        sdr_indicators = {"rivals", "melee", "slippi"}
        name_lower = self.display_name.lower()
        return any(ind in name_lower for ind in sdr_indicators)

    @property
    def network_scope(self) -> Literal["full", "limited", "none"]:
        """What network optimizations are allowed.

        - "full": Allow all network optimizations (Nagle disable, TCP tuning)
        - "limited": Only safe optimizations (no Nagle disable)
        - "none": Use OS defaults

        Default: Inferred from optimization_target.
        """
        if self.optimization_target in {
            "minimum_latency",
            "minimum_latency_offline",
            "low_latency_high_fps",
            "stable_online",
        }:
            return "full"
        if self.optimization_target in {"balanced"}:
            return "limited"
        return "none"

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Primary graphics API used by the game/emulator.

        Used to determine HAGS compatibility and LLM effectiveness.
        Default: "unknown" (override in profiles with known API).
        """
        return "unknown"

    @property
    def allows_aggressive_settings(self) -> bool:
        """Whether this profile allows aggressive gated settings.

        When False, StabilityGate will use safe fallbacks.
        Default: Based on optimization_target.
        """
        return self.optimization_target in {
            "minimum_latency",
            "minimum_latency_offline",
        }

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
