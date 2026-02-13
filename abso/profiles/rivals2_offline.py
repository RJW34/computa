"""Rivals of Aether 2 - OFFLINE / TRAINING profile.

Target: Training mode, local versus, CPU matches, replay review.
NO network rollback timing considerations.

Goals:
- Maximum frame pacing precision
- Minimum end-to-end latency
- Aggressive timing assumptions allowed

NVCP Settings (per-game for Rivals2.exe):
- V-Sync: FAST
- Low Latency Mode: ULTRA
- Max Frame Rate: ENABLED (Refresh - 3, e.g., 297 for 300Hz)
- Power Management: Prefer Maximum Performance
- Threaded Optimization: Auto

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
                # Custom settings for OFFLINE profile
                "low_latency_mode": "ultra",  # ULTRA for offline
                "power_management": "prefer_max_performance",
                "vsync": "fast",  # FAST V-Sync for offline
                "max_frame_rate": "297",  # Refresh - 3 (for 300Hz)
                "shader_cache": "unlimited",
                "threaded_optimization": "auto",  # Auto for Rivals 2
                "triple_buffering": "off",
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
                "setting": "Monitor Technology",
                "value": "G-SYNC",
                "reason": "Enable G-Sync for tear-free gameplay.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical Sync",
                "value": "Fast",
                "reason": "Fast V-Sync renders uncapped, discards incomplete frames.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "Ultra",
                "reason": "ULTRA for aggressive frame queue reduction in offline play.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "297 (Refresh - 3)",
                "reason": "Cap at refresh - 3 for G-Sync headroom. Adjust for your refresh rate.",
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
                "value": "Stable 297 FPS, no VRR disengagement",
                "reason": "FPS should hold at cap without oscillation or hitching.",
            },
        ]

