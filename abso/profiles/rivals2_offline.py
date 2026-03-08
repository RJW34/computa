"""Rivals of Aether 2 - OFFLINE / TRAINING profile.

Target: Training mode, local versus, CPU matches, replay review.
NO network rollback timing considerations.

Goals:
- Maximum frame pacing precision
- Minimum end-to-end latency
- Aggressive timing assumptions allowed

NVCP Settings (per-game for Rivals2.exe):
- V-Sync: OFF (no sync for minimum latency)
- Low Latency Mode: ON (Ultra has no effect in DX12/UE5)
- Max Frame Rate: OFF (uncapped)
- Power Management: Prefer Maximum Performance
- Threaded Optimization: OFF (UE5 driver contention)
- G-SYNC: OFF (no sync overhead)

External Tools: RTSS, frame pacing hooks ALLOWED.
"""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import Rivals2BaseProfile


class Rivals2OfflineProfile(Rivals2BaseProfile):
    """Optimization profile for Rivals 2 OFFLINE / TRAINING play.

    Aggressive low-latency profile for:
    - Training mode
    - Local versus
    - CPU matches
    - Replay review

    NOT suitable for online play - rollback netcode requires different timing.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-offline"

    @property
    def display_name(self) -> str:
        return "Rivals 2: Offline / Training"

    @property
    def description(self) -> str:
        return "Maximum latency reduction for training/local play (NOT for online)"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency_offline"

    @property
    def executable_hints(self) -> list[str]:
        return super().executable_hints

    # === Validation Metadata Overrides ===

    @property
    def is_online_profile(self) -> bool:
        """This is explicitly an OFFLINE profile - no rollback protection needed."""
        return False

    @property
    def is_sdr_only(self) -> bool:
        """Rivals 2 is SDR-only."""
        return True

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Rivals 2 uses DirectX 12 (UE5)."""
        return "dx12"

    @property
    def allows_aggressive_settings(self) -> bool:
        """Offline profiles allow aggressive latency settings."""
        return True

    @property
    def include_nvidia_notifications(self) -> bool:
        return True

    @property
    def include_rivals2_config(self) -> bool:
        return True

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        """Aggressive low-latency settings for offline play."""
        return {
            "WindowsSettingsHandler": {
                "max_refresh_rate": True,
            },
            "PowerSettingsHandler": {
                "processor_min_state": 100,
            },
            "NvidiaSettingsHandler": {
                # Rivals 2 is DX12/UE5 — LLM Ultra has no effect (DX9/DX11 only).
                # Use LLM ON for pre-render queue reduction where it works.
                "low_latency_mode": "on",
                "power_management": "prefer_max_performance",
                "vsync": "off",  # No sync — minimum latency, accept tearing
                "vsync_tear_control": "disable",
                "vrr_app_override": "force_off",  # No G-Sync overhead
                "max_frame_rate": "off",  # Uncapped
                "shader_cache": "unlimited",
                "threaded_optimization": "off",  # OFF — UE5 driver contention
                "triple_buffering": "off",
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,  # Exclusive fullscreen for lowest latency
                "vsync": False,  # In-game VSync OFF
                "raw_input": True,  # Best input latency
            },
            "NvidiaNotificationHandler": {
                "disable_notifications": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for OFFLINE play."""
        return [
            {
                "category": "=== OFFLINE PROFILE ===",
                "setting": "Use Case",
                "value": "Training, Local VS, CPU, Replays",
                "reason": "This profile is for OFFLINE play only. Use ONLINE profile for matchmaking.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "G-SYNC",
                "value": "Off",
                "reason": "No sync overhead for minimum latency. Tearing is acceptable offline.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical Sync",
                "value": "Off",
                "reason": "No sync — minimum latency path.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": (
                    "Reduces pre-render queue to 1 frame. Ultra has no effect in DX12/UE5 "
                    "(only works in DX9/DX11)."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "Off (uncapped)",
                "reason": "No artificial limiting. Use in-game limiter if needed.",
            },
            {
                "category": "In-Game Settings",
                "setting": "V-Sync",
                "value": "OFF",
                "reason": "Native engine frame pacing, driver handles sync.",
            },
            {
                "category": "External Tools",
                "setting": "RTSS",
                "value": "ALLOWED",
                "reason": "External limiters and frame pacing hooks are permitted for offline.",
            },
            {
                "category": "Validation",
                "setting": "Expected Behavior",
                "value": "Uncapped FPS, no sync overhead",
                "reason": "FPS should run uncapped without hitching. Tearing is expected.",
            },
        ]

