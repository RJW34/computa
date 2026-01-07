"""Call of Duty: Black Ops 7 profile - OLED variant."""

from __future__ import annotations

from typing import Any

from abso.profiles.cod_bo7 import CodBo7Profile


class CodBo7OLEDProfile(CodBo7Profile):
    """Optimization profile for Call of Duty: Black Ops 7 on OLED monitors.

    Identical to the standard CoD BO7 profile but keeps HDR enabled.
    OLED panels have negligible HDR processing overhead.
    """

    @property
    def profile_id(self) -> str:
        return "cod-bo7-oled"

    @property
    def display_name(self) -> str:
        return "Call of Duty: Black Ops 7 (OLED)"

    @property
    def description(self) -> str:
        return "Low latency for OLED monitors with HDR preserved"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings, overriding HDR to stay enabled for OLED."""
        settings = super().get_settings(handler_name)

        if handler_name == "WindowsSettingsHandler":
            settings = settings.copy()
            settings["hdr"] = True
            # Auto HDR OFF - game has native HDR, Auto HDR not needed
            settings["auto_hdr"] = False

        return settings
