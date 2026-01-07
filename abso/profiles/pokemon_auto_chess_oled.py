"""Pokemon Auto Chess profile - OLED variant."""

from __future__ import annotations

from typing import Any

from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile


class PokemonAutoChessOLEDProfile(PokemonAutoChessProfile):
    """Optimization profile for Pokemon Auto Chess on OLED monitors.

    Identical to the standard profile but keeps HDR enabled.
    OLED panels have negligible HDR processing overhead.
    """

    @property
    def profile_id(self) -> str:
        return "pokemon-auto-chess-oled"

    @property
    def display_name(self) -> str:
        return "Pokemon Auto Chess (OLED)"

    @property
    def description(self) -> str:
        return "WebGL optimization for OLED monitors with HDR preserved"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings, overriding HDR to stay enabled for OLED."""
        settings = super().get_settings(handler_name)

        if handler_name == "WindowsSettingsHandler":
            settings = settings.copy()
            settings["hdr"] = True
            # Auto HDR OFF - WebGL is SDR content, Auto HDR causes washed-out colors
            settings["auto_hdr"] = False

        return settings
