"""Marvel Rivals GameUserSettings.ini handler."""

from __future__ import annotations

import os
from pathlib import Path

from abso.settings.ue_game_user_settings import UEGameUserSettingsHandler


class MarvelRivalsConfigHandler(UEGameUserSettingsHandler):
    """Enforce Marvel Rivals display settings from GameUserSettings.ini."""

    MUTABLE_SETTINGS_TO_INI = {
        "fullscreen_mode": "FullscreenMode",
        "vsync": "bUseVSync",
        "frame_rate_limit": "FrameRateLimit",
        "hdr_output": "bUseHDRDisplayOutput",
        "hdr_nits": "HDRDisplayOutputNits",
        "nvidia_reflex": "bNvidiaReflex",
    }
    BOOL_SETTINGS = UEGameUserSettingsHandler.BOOL_SETTINGS | frozenset({"nvidia_reflex"})
    MIRROR_FULLSCREEN_MODE_KEYS = ("LastConfirmedFullscreenMode", "PreferredFullscreenMode")

    def _get_config_dir(self) -> Path | None:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None

        candidate = Path(local_appdata) / "Marvel" / "Saved" / "Config" / "Windows"
        if candidate.is_dir():
            return candidate
        return None
