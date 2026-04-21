"""Rivals of Aether 2 G-SYNC / VRR profiles.

Two variants:
- Rivals2GSyncProfile: General-purpose G-SYNC (tear-free low latency)
- Rivals2OnlineGSyncProfile: Rollback-safe G-SYNC (online play with VRR)

Key difference from OW2 G-SYNC: Rivals 2 does NOT have NVIDIA Reflex,
so we use the ``vrr_fighting_game`` preset (LLM "on") instead of
``reflex_gsync`` (LLM "off").
"""

from __future__ import annotations

from typing import Any

from abso.profiles.profile_bases import Rivals2BaseProfile


class Rivals2GSyncProfile(Rivals2BaseProfile):
    """Low latency VRR profile for Rivals of Aether 2.

    Tear-free output via G-SYNC with VSync as safety net.
    Uses ``vrr_fighting_game`` preset (LLM on, VSync on, VRR allow).
    """

    @property
    def allow_dual_limiter(self) -> bool:
        # Rivals 2 GameUserSettings.ini is known to be rewritten by the game
        # on exit, so ABSO keeps the NVIDIA driver cap as a safety net in
        # addition to the in-game cap. Both resolve to refresh - 3.
        return True

    @property
    def profile_id(self) -> str:
        return "rivals2-gsync"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - Offline GSYNC"

    @property
    def description(self) -> str:
        return "Low latency VRR profile (G-SYNC ON, VSync safety net)"

    @property
    def optimization_target(self) -> str:
        return "low_latency_vrr"

    @property
    def is_online_profile(self) -> bool:
        return False

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def include_nvidia_notifications(self) -> bool:
        return True

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "max_refresh_rate": True,
            },
            "NvidiaSettingsHandler": {
                # vrr_fighting_game: LLM on, VSync on (safety net), VRR allow,
                # threaded opt on, max perf power, shader cache unlimited
                "preset": "vrr_fighting_game",
                # Auto-detect refresh rate and cap at refresh-3 for G-SYNC headroom
                "auto_vrr_fps_cap": True,
                # Ensure G-SYNC is enabled globally
                "global_vrr_mode": "fullscreen_only",
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,  # Exclusive fullscreen for best VRR
                "vsync": False,  # In-game VSync OFF (NVCP handles sync)
                "raw_input": True,
                "auto_vrr_fps_cap": True,
                "hdr_output": False,
            },
            "NvidiaNotificationHandler": {
                "disable_notifications": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "=== G-SYNC PROFILE ===",
                "setting": "Overview",
                "value": "G-SYNC ON, VSync ON (NVCP), FPS cap at refresh-3",
                "reason": (
                    "Tear-free low-latency VRR profile. VSync acts as safety net only — "
                    "never activates with FPS capped below refresh rate. "
                    "For 300Hz: cap at 297. For 240Hz: cap at 237. For 144Hz: cap at 141."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Set up G-SYNC",
                "value": "Enable G-SYNC, G-SYNC Compatible: ON",
                "reason": "Display > Set up G-SYNC. Check 'Enable G-SYNC' and 'Enable for full screen mode'.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical sync",
                "value": "On",
                "reason": (
                    "Manage 3D Settings. Acts as SAFETY NET only with G-SYNC. "
                    "With FPS capped below refresh, VSync never engages."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": (
                    "Reduces render queue depth. Limited effect in DX12/UE5 but 'On' is correct "
                    "(not 'Off' — Rivals 2 has no Reflex). If stuttering occurs, try 'Off' or "
                    "set Pre-Rendered Frames to 2 via Nvidia Profile Inspector."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "Refresh rate - 3 (auto-set by ABSO)",
                "reason": (
                    "ABSO auto-detects your refresh rate and caps at refresh-3. "
                    "Keeps G-SYNC active and VSync from engaging."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "Display Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Required for proper G-SYNC behavior. Borderless adds compositor latency.",
            },
            {
                "category": "In-Game Video",
                "setting": "V-SYNC",
                "value": "Off",
                "reason": "ALWAYS disable in-game VSync with G-SYNC. NVCP VSync handles sync.",
            },
            {
                "category": "In-Game Video",
                "setting": "Frame Rate Cap",
                "value": "Refresh rate - 3 (e.g., 297 for 300Hz)",
                "reason": (
                    "Must cap below refresh for G-SYNC to work properly. "
                    "In-game limiter has lower latency than NVCP/RTSS limiters."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "NVIDIA Reflex",
                "value": "Not available",
                "reason": (
                    "Rivals 2 does not implement NVIDIA Reflex. LLM 'On' is set via NVCP instead. "
                    "This is different from OW2/Fortnite where Reflex handles queue control."
                ),
            },
        ]


class Rivals2OnlineGSyncProfile(Rivals2BaseProfile):
    """Rollback-safe G-SYNC profile for Rivals 2 online play.

    Same G-SYNC setup as the general profile but with stability constraints
    for SnapNet rollback netcode. Threaded optimization forced off to prevent
    UE5 driver contention.
    """

    @property
    def allow_dual_limiter(self) -> bool:
        # Same rationale as Rivals2GSyncProfile: UE5 rewrites
        # GameUserSettings.ini on exit, so ABSO keeps the driver cap as a
        # safety net alongside the in-game cap. Both resolve to refresh - 3.
        return True

    @property
    def profile_id(self) -> str:
        return "rivals2-online-gsync"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - Online GSYNC"

    @property
    def description(self) -> str:
        return "Rollback-safe VRR profile (G-SYNC ON, stability-focused)"

    @property
    def optimization_target(self) -> str:
        return "stable_online_vrr"

    @property
    def is_online_profile(self) -> bool:
        return True

    @property
    def allows_aggressive_settings(self) -> bool:
        return False

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def include_nvidia_notifications(self) -> bool:
        return True

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "max_refresh_rate": True,
            },
            "NvidiaSettingsHandler": {
                "preset": "vrr_fighting_game",
                "auto_vrr_fps_cap": True,
                "global_vrr_mode": "fullscreen_only",
                # Override preset default — UE5 driver contention risk with rollback
                "threaded_optimization": "off",
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,
                "vsync": False,
                "raw_input": True,
                "auto_vrr_fps_cap": True,
                "hdr_output": False,
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 2,  # Conservative (not aggressive) for online stability
                "io_priority": 2,
            },
            "NvidiaNotificationHandler": {
                "disable_notifications": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "=== ONLINE G-SYNC PROFILE ===",
                "setting": "Overview",
                "value": "G-SYNC ON, Rollback-Safe, Stability-Focused",
                "reason": (
                    "Tear-free VRR for online play. Stability constraints applied for "
                    "SnapNet rollback netcode. Threaded optimization OFF to prevent "
                    "UE5 driver contention during rollback recovery."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Set up G-SYNC",
                "value": "Enable G-SYNC, G-SYNC Compatible: ON",
                "reason": "Display > Set up G-SYNC. Check 'Enable G-SYNC' and 'Enable for full screen mode'.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical sync",
                "value": "On (safety net)",
                "reason": "NVCP VSync as safety net only. Never engages with FPS capped below refresh.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Threaded Optimization",
                "value": "Off",
                "reason": "OFF — prevents UE5 driver contention that can destabilize rollback timing.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On (NOT Ultra)",
                "reason": (
                    "Ultra can cause frame pacing issues and overrides FPS caps. "
                    "'On' reduces queue depth safely for online play."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "Display Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Required for proper G-SYNC behavior.",
            },
            {
                "category": "In-Game Video",
                "setting": "V-SYNC",
                "value": "Off",
                "reason": "NVCP VSync handles sync. In-game VSync must be off with G-SYNC.",
            },
            {
                "category": "In-Game Video",
                "setting": "Frame Rate Cap",
                "value": "Refresh rate - 3",
                "reason": "Keeps G-SYNC active. Use in-game cap for lowest limiter latency.",
            },
            {
                "category": "Validation",
                "setting": "Expected Behavior",
                "value": "Tear-free, stable frametimes, no rollback dropouts",
                "reason": "G-SYNC smooths frame delivery. Conservative priority prevents timing contention.",
            },
        ]


