"""Fortnite GameUserSettings.ini handler."""

from __future__ import annotations

import os
from pathlib import Path

from abso.settings.ue_game_user_settings import UEGameUserSettingsHandler


class FortniteConfigHandler(UEGameUserSettingsHandler):
    """Enforce Fortnite display settings from GameUserSettings.ini."""

    is_critical_verify = True

    TARGET_SECTION_NAME = "/Script/FortniteGame.FortGameUserSettings"
    # Fortnite uses the stock Unreal EWindowMode enum for its fullscreen mode:
    #   0 = Fullscreen, 1 = Windowed Fullscreen (borderless), 2 = Windowed.
    # Fortnite stores it ONLY as PreferredFullscreenMode (+ the mirrored
    # LastConfirmedFullscreenMode) - there is no plain `FullscreenMode` key, so
    # this handler must NOT inherit the generic key. Verified 2026-06-19 against
    # a live install (was on 1 / Windowed Fullscreen) and a competitive
    # community config (PreferredFullscreenMode=0). ABSO targets 0 (Fullscreen)
    # for the lowest-latency presentation path, which is the competitive norm.
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
