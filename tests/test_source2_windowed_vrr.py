"""Source 2 VRR lanes must wire all three windowed G-SYNC enablers.

Source 2 presents through DXGI flip: CS2's and Deadlock's "Fullscreen" and
"Fullscreen Windowed" both resolve to hardware independent flip, and there is
no legacy exclusive-fullscreen mode for the driver to detect. Both families
originally shipped the strict exclusive-fullscreen contract —
``global_vrr_mode = fullscreen_only`` with the Windows windowed-VRR flags off
and FSO disabled per-exe. That combination asks the driver to engage VRR only
in a mode the game never enters while switching off the enablers the flip path
depends on, so G-SYNC silently never engaged.

Same failure shape as the OW2 150-fps incident (docs/CODEX_HANDOFF_OW2_150FPS.md):
lose independent flip and windowed G-SYNC cannot engage.
"""

from __future__ import annotations

import pytest

# Canonical import order (mirrors the other profile tests).
import abso.main  # noqa: F401
from abso.profiles.counter_strike_2 import (
    CounterStrike2GSyncHDRCaptureProfile,
    CounterStrike2GSyncHDRProfile,
    CounterStrike2GSyncProfile,
    CounterStrike2HDRProfile,
    CounterStrike2Profile,
)
from abso.profiles.deadlock import (
    DeadlockGSyncHDRProfile,
    DeadlockGSyncProfile,
    DeadlockHDRProfile,
    DeadlockProfile,
)

# (profile class, bound executables that must stay on the flip path)
SOURCE2_VRR_PROFILES = [
    (CounterStrike2GSyncProfile, ["cs2.exe"]),
    (CounterStrike2GSyncHDRProfile, ["cs2.exe"]),
    (CounterStrike2GSyncHDRCaptureProfile, ["cs2.exe"]),
    (DeadlockGSyncProfile, ["project8.exe", "deadlock.exe"]),
    (DeadlockGSyncHDRProfile, ["project8.exe", "deadlock.exe"]),
]

SOURCE2_NO_SYNC_PROFILES = [
    CounterStrike2Profile,
    CounterStrike2HDRProfile,
    DeadlockProfile,
    DeadlockHDRProfile,
]


@pytest.mark.parametrize(("profile_cls", "executables"), SOURCE2_VRR_PROFILES)
def test_source2_vrr_lane_declares_all_three_windowed_vrr_enablers(
    profile_cls, executables
) -> None:
    profile = profile_cls()

    nvidia = profile.get_settings("NvidiaSettingsHandler")
    assert nvidia.get("global_vrr_mode") == "fullscreen_and_windowed", (
        f"{profile.profile_id} restricts driver VRR to a fullscreen mode "
        "Source 2 never enters"
    )
    # The per-app override must still allow VRR for the bound executable,
    # otherwise switching in from a no-sync lane (force_off) leaves G-SYNC
    # disabled for the game regardless of the global mode.
    assert nvidia.get("vrr_app_override") == "allow"

    windows = profile.get_settings("WindowsSettingsHandler")
    assert windows.get("windowed_optimizations") is True, (
        f"{profile.profile_id} is missing SwapEffectUpgradeEnable"
    )
    assert windows.get("vrr_optimize") is True, (
        f"{profile.profile_id} is missing VRROptimizeEnable"
    )


@pytest.mark.parametrize(("profile_cls", "executables"), SOURCE2_VRR_PROFILES)
def test_source2_vrr_lane_keeps_the_flip_path_intact(profile_cls, executables) -> None:
    """FSO must stay enabled — globally and per-exe — on the VRR lanes.

    Disabling FSO cannot buy exclusive fullscreen here (Source 2 has none), and
    it removes the optimized composited path that independent flip rides on.
    """
    profile = profile_cls()

    graphics = profile.get_settings("GraphicsSettingsHandler")
    assert graphics.get("disable_global_fso") is False, (
        f"{profile.profile_id} kills the global FSO path windowed VRR needs"
    )

    registry = profile.get_settings("RegistrySettingsHandler")
    for exe in executables:
        assert profile.fullscreen_optimizations_per_exe[exe] is False, (
            f"{profile.profile_id} still disables FSO for {exe}"
        )
        assert registry["fullscreen_optimizations"][exe] is False


@pytest.mark.parametrize(("profile_cls", "executables"), SOURCE2_VRR_PROFILES)
def test_source2_vrr_lane_guidance_matches_the_display_path(
    profile_cls, executables
) -> None:
    """In-game guidance must not tell the user to pick a VRR-less mode."""
    profile = profile_cls()

    display_rows = [
        row
        for row in profile.get_in_game_settings()
        if row.get("setting") == "Display Mode"
    ]
    assert display_rows, f"{profile.profile_id} has no Display Mode guidance"
    for row in display_rows:
        assert "Windowed" in row["value"], (
            f"{profile.profile_id} still recommends an exclusive-fullscreen mode"
        )


@pytest.mark.parametrize(("profile_cls", "executables"), SOURCE2_VRR_PROFILES)
def test_source2_vrr_lane_resolves_to_vrr_allow(profile_cls, executables) -> None:
    """The effective per-app override survives NVIDIA preset resolution."""
    from abso.settings.nvidia import NvidiaSettingsHandler

    profile = profile_cls()
    resolved = NvidiaSettingsHandler()._resolve_requested_nvidia_settings(
        profile.get_settings("NvidiaSettingsHandler")
    )
    assert resolved.get("vrr_app_override") == "allow", profile.profile_id


@pytest.mark.parametrize("profile_cls", SOURCE2_NO_SYNC_PROFILES)
def test_source2_no_sync_lanes_keep_vrr_off(profile_cls) -> None:
    """The fix must not leak VRR into the deterministic no-sync lanes."""
    from abso.settings.nvidia import NvidiaSettingsHandler

    nvidia = profile_cls().get_settings("NvidiaSettingsHandler")
    assert nvidia.get("global_vrr_mode") == "off"
    # The per-app force_off arrives via the reflex_no_sync preset, so resolve
    # the preset the way apply does rather than reading the declared map.
    resolved = NvidiaSettingsHandler()._resolve_requested_nvidia_settings(nvidia)
    assert resolved.get("vrr_app_override") == "force_off"


@pytest.mark.parametrize(("profile_cls", "executables"), SOURCE2_VRR_PROFILES)
def test_source2_vrr_lane_keeps_its_overlay_policy(profile_cls, executables) -> None:
    """Moving off fullscreen_only must not relax the overlay/binding contract.

    ``BaseProfile`` derives the overlay-free gate and the exact-NVIDIA-binding
    requirement from ``uses_fullscreen_only_vrr_path``. These lanes no longer
    satisfy that derivation, so they must declare both explicitly — except the
    capture lane, which drops the overlay gate by design.
    """
    profile = profile_cls()

    assert profile.uses_fullscreen_only_vrr_path is False
    assert profile.requires_exact_nvidia_binding is True, profile.profile_id

    expected_overlay_free = not profile.is_capture_safe
    assert (
        profile.display_path_requirements.require_overlay_free_path
        is expected_overlay_free
    ), profile.profile_id
    assert profile.auto_disable_blocking_overlays is expected_overlay_free
