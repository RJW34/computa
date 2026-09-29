"""Rivals of Aether 2 no-sync profiles for online play and training.

No VRR/VSync; tearing is accepted. A bounded native render cap (300 at
300 Hz) is retained as a starting policy, not a rollback requirement or
measured optimum. Driver queue control stays On; Reflex is not assumed.
"""

from __future__ import annotations

from typing import Any, Literal

from abso.core.vrr import FIGHTING_60HZ_NOSYNC_CAP_POLICY
from abso.profiles.profile_bases import Rivals2BaseProfile, merge_settings_map


class Rivals2NoSyncProfile(Rivals2BaseProfile):
    """One no-sync lane for ranked, unranked, and offline training."""

    @property
    def profile_id(self) -> str:
        return "rivals2-nosync"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - No Sync"

    @property
    def description(self) -> str:
        return "No-sync lane with a bounded native FPS cap; tearing accepted"

    @property
    def optimization_target(self) -> str:
        return "stable_online"

    @property
    def is_sdr_only(self) -> bool:
        return True

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Steam's published PC requirements list DirectX 11 for Rivals 2."""
        return "dx11"

    @property
    def allows_aggressive_settings(self) -> bool:
        """Do not opt into aggressive presets for this lane."""
        return False

    @property
    def include_nvidia_notifications(self) -> bool:
        return True

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        """No-sync settings; native limiter owns the render cap."""
        return {
            "WindowsSettingsHandler": {
                "max_refresh_rate": True,  # Set display to max refresh rate for current resolution
            },
            "NvidiaSettingsHandler": {
                "low_latency_mode": "on",  # Starting policy for DX11; compare before tuning.
                "power_management": "prefer_max_performance",
                "vsync": "off",  # This lane accepts tearing.
                "vsync_tear_control": "disable",  # Explicit tear control off with VSync OFF
                "vrr_app_override": "force_off",  # OFF for the no-sync path
                "global_vrr_mode": "off",  # Enforce global VRR off for clean no-sync transitions
                "max_frame_rate": "off",  # No driver cap - the in-game limiter owns pacing
                "shader_cache": "on",
                "threaded_optimization": "auto",  # OGL control; no proven DX11 gain.
                "triple_buffering": "off",  # OFF - irrelevant without VSync
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,  # Request fullscreen; actual presentation is unverified.
                "vsync": False,  # No synchronization on this lane.
                # Retain the bounded render-cap policy (300 at 300 Hz).
                # Multiples of 60 are not required for correct simulation and
                # no frame-time benefit has been measured for this policy.
                "auto_vrr_fps_cap": True,
                "vrr_cap_policy": FIGHTING_60HZ_NOSYNC_CAP_POLICY,
                "hdr_output": False,
            },
            "NvidiaNotificationHandler": {
                "disable_notifications": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for the no-sync lane."""
        return [
            {
                "category": "=== NO SYNC PROFILE ===",
                "setting": "Use Case",
                "value": "Ranked, Unranked, Training, Local VS, Replays",
                "reason": (
                    "One no-sync lane for online play and offline training. "
                    "Actual latency and frame pacing require measurement."
                ),
            },
            {
                "category": "Pacing policy",
                "setting": "Limiter selection",
                "value": "One native cap; no VRR or VSync",
                "reason": (
                    "This lane conservatively avoids competing pacing controls. "
                    "The 60-multiple cap is a heuristic; netcode or latency improvement is unmeasured."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "G-SYNC / VRR",
                "value": "OFF",
                "reason": (
                    "This lane disables VRR and accepts tearing. Use a G-SYNC "
                    "lane if you prefer synchronized variable-refresh presentation."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical Sync",
                "value": "OFF",
                "reason": "This lane accepts tearing. Visibility of tearing depends on the display, frame rate, and scene.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Threaded Optimization",
                "value": "Auto",
                "reason": (
                    "This NVIDIA setting is exposed as OGL_THREAD_CONTROL. "
                    "A frame-time benefit on Rivals 2's DX11 path has not been established."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": "Driver queue-control starting point for DX11. Compare frame times and latency; no mode is proven best on this PC.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "DISABLED",
                "reason": "No driver-level cap — the in-game limiter owns pacing.",
            },
            {
                "category": "In-Game Settings",
                "setting": "V-Sync",
                "value": "OFF",
                "reason": "This no-sync lane accepts tearing in exchange for avoiding VSync backpressure.",
            },
            {
                "category": "In-Game Settings",
                "setting": "Frame Rate Cap",
                "value": "Multiple of 60 at/below refresh (auto-set: 300 @ 300Hz)",
                "reason": (
                    "The retained render-budget policy uses multiples of 60, but an "
                    "integer frames-per-tick cadence is not a simulation requirement. "
                    "No local latency or rollback benefit has been measured."
                ),
            },
            {
                "category": "External Tools",
                "setting": "RTSS / Frame Limiters",
                "value": "DISABLED",
                "reason": "Avoid adding another cap to the limiter already selected by the profile. This is a pacing policy, not proof that external limiters break netcode.",
            },
            {
                "category": "Monitoring",
                "setting": "Overlays",
                "value": "Stopped by this profile at launch",
                "reason": "This lane stops capture and overlay tools, including RTSS. Use the capture-safe sibling when those apps must remain running.",
            },
            *self._rivals2_overlay_guidance(),
            {
                "category": "Validation",
                "setting": "Expected Behavior",
                "value": "Check frame pacing, tearing, and online responsiveness",
                "reason": "VRR is off in this lane. Saved configuration cannot guarantee online or rendering performance.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Rivals 2 manual: disable RTSS/external FPS caps; keep in-game "
            "V-Sync Off. ABSO sets the in-game cap to the largest multiple of "
            "60 at your refresh (e.g. 300 @ 300 Hz)."
        ]


class Rivals2NoSyncHDRProfile(Rivals2NoSyncProfile):
    """No-sync Rivals 2 lane with Windows HDR composition enabled."""

    @property
    def profile_id(self) -> str:
        return "rivals2-nosync-hdr"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - No Sync HDR"

    @property
    def description(self) -> str:
        return (
            "No-sync Rivals 2 lane with Windows HDR composition. "
            "Tearing is accepted; native game HDR output stays off."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._settings_overrides(),
            self.HDR_WINDOWS_COMPOSITION_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [*self._rivals2_hdr_guidance(), *super().get_in_game_settings()]
