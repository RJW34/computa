"""Fortnite GameUserSettings.ini handler."""

from __future__ import annotations

import os
from pathlib import Path

from abso.settings.ue_game_user_settings import UEGameUserSettingsHandler


class FortniteConfigHandler(UEGameUserSettingsHandler):
    """Enforce Fortnite display settings from GameUserSettings.ini."""

    is_critical_verify = True

    TARGET_SECTION_NAME = "/Script/FortniteGame.FortGameUserSettings"
    MUTABLE_SETTINGS_TO_INI = {
        "fullscreen_mode": "PreferredFullscreenMode",
        "vsync": "bUseVSync",
        "frame_rate_limit": "FrameRateLimit",
        "hdr_output": "bUseHDRDisplayOutput",
        "hdr_nits": "HDRDisplayOutputNits",
    }
    MIRROR_FULLSCREEN_MODE_KEYS = ("LastConfirmedFullscreenMode",)

    def _get_config_dir(self) -> Path | None:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None

        candidate = Path(local_appdata) / "FortniteGame" / "Saved" / "Config" / "WindowsClient"
        if candidate.is_dir():
            return candidate
        return None
