"""Rivals of Aether 2 profile - OLED variant."""

from __future__ import annotations

from typing import Any

from abso.profiles.rivals2 import Rivals2Profile


class Rivals2OLEDProfile(Rivals2Profile):
    """Optimization profile for Rivals of Aether 2 on OLED monitors.

    Rivals 2 is an SDR game - it does NOT support HDR natively.
    Enabling Windows HDR with SDR content causes washed-out colors.

    This OLED profile keeps HDR DISABLED for accurate colors.
    OLED panels still benefit from the other optimizations (low latency,
    fullscreen exclusive, etc.) without the HDR color issues.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-oled"

    @property
    def display_name(self) -> str:
        return "Rivals of Aether 2 (OLED)"

    @property
    def description(self) -> str:
        return "Ultra-low latency for OLED monitors (HDR disabled - game is SDR)"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings with HDR disabled since Rivals 2 is SDR only."""
        settings = super().get_settings(handler_name)

        # Rivals 2 is SDR - disable HDR to prevent washed-out colors
        if handler_name == "WindowsSettingsHandler":
            settings = settings.copy()
            settings["hdr"] = False
            settings["auto_hdr"] = False

        return settings
