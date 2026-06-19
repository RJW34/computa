"""Rivals of Aether 2 - OFFLINE / TRAINING profile.

Target: Training mode, local versus, CPU matches, replay review.
NO network rollback timing considerations.

Goals:
- Maximum frame pacing precision
- Latency-focused no-sync presentation
- Aggressive timing assumptions allowed

NVCP Settings (per-game for Rivals2.exe):
- V-Sync: OFF (no sync, tearing accepted)
- Low Latency Mode: ON (DX12/UE5 impact must be measured per driver/game)
- Max Frame Rate: OFF (uncapped)
- Power Management: Prefer Maximum Performance
- Threaded Optimization: OFF (UE5 driver contention)
- G-SYNC: OFF (no VRR queueing path)

External Tools: RTSS, frame pacing hooks ALLOWED.
"""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import Rivals2BaseProfile, merge_settings_map


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
        return "Rivals 2 - Offline No Sync"

    @property
    def description(self) -> str:
        return "Latency-focused no-sync profile for training/local play (NOT for online)"

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
                # Rivals 2 is DX12/UE5. Driver LLM impact is less deterministic
                # than DX11; use On rather than Ultra and measure locally.
                "low_latency_mode": "on",
                "power_management": "prefer_max_performance",
                "vsync": "off",  # No sync, accept tearing
                "vsync_tear_control": "disable",
                "vrr_app_override": "force_off",  # No G-Sync overhead
                "global_vrr_mode": "off",  # Enforce global VRR off for clean no-sync transitions
                "max_frame_rate": "off",  # Uncapped
                "shader_cache": "unlimited",
                "threaded_optimization": "off",  # OFF — UE5 driver contention
                "triple_buffering": "off",
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,  # Exclusive fullscreen no-sync path
                "vsync": False,  # In-game VSync OFF
                "raw_input": True,  # Best input latency
                "frame_rate_limit": 0,  # 0 = truly uncapped (UE); driver cap is also off
                "hdr_output": False,
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
                "reason": "Avoids the VRR queueing path. Tearing is acceptable offline.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical Sync",
                "value": "Off",
                "reason": "No-sync path: accepts tearing to avoid VSync queueing.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": (
                    "Driver LLM can reduce render queueing in supported paths. "
                    "DX12/UE5 behavior is game-controlled enough that ABSO does "
                    "not claim a fixed latency win."
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


class Rivals2OfflineHDRProfile(Rivals2OfflineProfile):
    """Offline no-sync Rivals 2 profile with Windows HDR composition enabled."""

    @property
    def profile_id(self) -> str:
        return "rivals2-offline-hdr"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - Offline No Sync HDR"

    @property
    def description(self) -> str:
        return (
            "Offline no-sync Rivals 2 profile with Windows HDR composition. "
            "Keeps the same latency knobs as the SDR lane; Rivals 2 native HDR output stays off."
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


