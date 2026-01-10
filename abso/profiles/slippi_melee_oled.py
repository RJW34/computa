"""Slippi Melee profile - OLED variant."""

from __future__ import annotations

from typing import Any

from abso.profiles.slippi_melee import SlippiMeleeProfile


class SlippiMeleeOLEDProfile(SlippiMeleeProfile):
    """Optimization profile for Slippi Melee on OLED monitors.

    Melee (via Dolphin/Slippi) is SDR content - it does NOT support HDR natively.
    Enabling Windows HDR with SDR content causes washed-out colors.

    This OLED profile keeps HDR DISABLED for accurate colors.
    OLED panels still benefit from the other optimizations (low latency,
    instant pixel response, true blacks) without the HDR color issues.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee-oled"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee - Slippi (OLED)"

    @property
    def description(self) -> str:
        return "Ultra-low latency for OLED monitors (HDR disabled - game is SDR)"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings with HDR disabled since Melee is SDR only."""
        settings = super().get_settings(handler_name)

        # Melee is SDR - disable HDR to prevent washed-out colors
        if handler_name == "WindowsSettingsHandler":
            settings = settings.copy()
            settings["hdr"] = False
            settings["auto_hdr"] = False

        return settings
