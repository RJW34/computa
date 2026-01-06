"""Rivals of Aether 2 profile - OLED variant."""

from __future__ import annotations

from typing import Any

from abso.profiles.rivals2 import Rivals2Profile


class Rivals2OLEDProfile(Rivals2Profile):
    """Optimization profile for Rivals of Aether 2 on OLED monitors.

    Identical to the standard Rivals 2 profile but keeps HDR enabled.

    OLED rationale:
    - OLED panels have no backlight processing overhead for HDR
    - HDR tone mapping happens in GPU, not the panel
    - Input lag difference between SDR/HDR is negligible on OLED (~0-1ms)
    - HDR provides better colors and peak brightness on capable panels

    Use this profile if you have an OLED monitor (LG UltraGear, Alienware, etc.)
    and prefer HDR visual quality without meaningful latency penalty.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-oled"

    @property
    def display_name(self) -> str:
        return "Rivals of Aether 2 (OLED)"

    @property
    def description(self) -> str:
        return "Ultra-low latency for OLED monitors with HDR preserved"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings, overriding HDR to stay enabled for OLED."""
        settings = super().get_settings(handler_name)

        # Override HDR settings for OLED - keep HDR enabled
        if handler_name == "WindowsSettingsHandler":
            settings = settings.copy()
            settings["hdr"] = True
            settings["auto_hdr"] = True

        return settings
