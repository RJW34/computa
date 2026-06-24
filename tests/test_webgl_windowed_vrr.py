"""WebGL lanes must wire all three borderless/windowed G-SYNC enablers.

Windowed G-SYNC needs (1) the NVIDIA global VRR mode set to
``fullscreen_and_windowed`` AND (2) the two Windows windowed-VRR flags. The
WebGL auto-battler lanes previously set only the Windows flags, so the driver
global VRR mode was never reconciled and windowed G-SYNC could silently fail to
engage when switching in from a no-sync profile.
"""

from __future__ import annotations

import pytest

# Canonical import order (mirrors the other profile tests).
import abso.main  # noqa: F401
from abso.profiles.pacdeluxe import PACDeluxeProfile
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile


@pytest.mark.parametrize("profile_cls", [PokemonAutoChessProfile, PACDeluxeProfile])
def test_webgl_lane_declares_all_three_windowed_vrr_enablers(profile_cls) -> None:
    profile = profile_cls()

    nvidia = profile.get_settings("NvidiaSettingsHandler")
    assert nvidia.get("global_vrr_mode") == "fullscreen_and_windowed", (
        f"{profile.profile_id} is missing the NVIDIA global VRR mode enabler"
    )
    # The per-app override must still allow VRR for the bound app.
    assert nvidia.get("vrr_app_override") == "allow"

    windows = profile.get_settings("WindowsSettingsHandler")
    assert windows.get("windowed_optimizations") is True
    assert windows.get("vrr_optimize") is True
