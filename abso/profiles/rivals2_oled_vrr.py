"""Rivals of Aether 2 profile - OLED with VRR/G-Sync variant."""

from __future__ import annotations

from typing import Any

from abso.profiles.rivals2_oled import Rivals2OLEDProfile


class Rivals2OLEDVRRProfile(Rivals2OLEDProfile):
    """Optimization profile for Rivals of Aether 2 on OLED with G-Sync/VRR.

    This profile prioritizes tear-free visuals with near-minimum latency.
    Uses G-Sync + VSync (NVCP) + 240 FPS cap for the optimal VRR experience.

    Tradeoff vs no-sync profile:
    - Adds ~2-5ms latency
    - Eliminates all tearing
    - Smoother visual experience

    Still keeps HDR DISABLED since Rivals 2 is an SDR game.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-oled-vrr"

    @property
    def display_name(self) -> str:
        return "Rivals of Aether 2 (OLED + G-Sync)"

    @property
    def description(self) -> str:
        return "Tear-free VRR gaming with near-minimum latency (HDR disabled - game is SDR)"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings with VRR/G-Sync optimizations."""
        settings = super().get_settings(handler_name)

        if handler_name == "NvidiaSettingsHandler":
            settings = settings.copy()
            # Switch to VRR preset instead of no-sync
            # This enables: G-Sync allowed, VSync ON (safety net), LLM On
            settings["preset"] = "vrr_fighting_game"

        return settings

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for VRR/G-Sync setup.

        This profile uses VRR as the PRIMARY configuration.
        """
        return [
            # =========================================================================
            # VRR SETUP (Primary for this profile)
            # =========================================================================
            {
                "category": "=== VRR/G-SYNC SETUP ===",
                "setting": "Overview",
                "value": "G-SYNC ON, V-SYNC ON (NVCP), 240 FPS in-game cap",
                "reason": (
                    "Tear-free gaming with near-minimum latency. Adds ~2-5ms vs no-sync "
                    "but eliminates all tearing. V-SYNC acts as safety net only - never "
                    "activates with FPS properly capped below refresh rate."
                ),
            },

            # --- MANUAL SETUP REQUIRED ---
            {
                "category": "MANUAL: NVIDIA Control Panel",
                "setting": "Set up G-SYNC (MUST DO MANUALLY)",
                "value": "Enable G-SYNC, G-SYNC Compatible: ON",
                "reason": (
                    "Display > Set up G-SYNC. Check 'Enable G-SYNC, G-SYNC Compatible' "
                    "and select 'Enable for full screen mode'. This is a GLOBAL setting "
                    "that cannot be automated per-game."
                ),
            },
            {
                "category": "MANUAL: Windows Settings",
                "setting": "Variable refresh rate",
                "value": "On",
                "reason": (
                    "Settings > System > Display > Graphics > Change default graphics settings. "
                    "Enable 'Variable refresh rate' for Windows VRR support."
                ),
            },

            # --- Automated by Profile ---
            {
                "category": "Nvidia Control Panel (Auto)",
                "setting": "Vertical sync",
                "value": "On",
                "reason": (
                    "Manage 3D Settings > Program Settings > Rivals2.exe. "
                    "Applied automatically by profile. Acts as SAFETY NET only with G-SYNC. "
                    "With FPS capped at 240 on 300Hz monitor, V-SYNC never engages."
                ),
            },
            {
                "category": "Nvidia Control Panel (Auto)",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": (
                    "Manage 3D Settings. Applied automatically by profile. "
                    "Reduces render queue depth. 'On' (not Ultra) to respect FPS caps. "
                    "If stuttering occurs, see Troubleshooting section."
                ),
            },
            {
                "category": "Nvidia Control Panel (Auto)",
                "setting": "Power management mode",
                "value": "Prefer maximum performance",
                "reason": "Applied automatically. Prevents GPU downclocking.",
            },
            {
                "category": "Nvidia Control Panel (Auto)",
                "setting": "Triple buffering",
                "value": "Off",
                "reason": "Applied automatically. Not needed with G-SYNC.",
            },

            # --- In-Game Settings ---
            {
                "category": "In-Game Video",
                "setting": "V-SYNC",
                "value": "Off (CRITICAL)",
                "reason": (
                    "ALWAYS disable in-game V-SYNC with G-SYNC. "
                    "NVCP V-SYNC handles sync as a safety net."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "Frame Rate Cap",
                "value": "297 (refresh rate - 3)",
                "reason": (
                    "MUST cap below refresh rate for G-SYNC to work properly. "
                    "For 300Hz monitor: set 297. For 240Hz: set 237. For 144Hz: set 141. "
                    "In-game limiters throttle at engine-level BEFORE frame calculation "
                    "(~0.5ms penalty vs ~2-4ms for NVCP/RTSS). Combined with faster scanout "
                    "at 297fps (3.37ms) vs 240fps (4.17ms), in-game 297 is optimal."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "Display Mode",
                "value": "Exclusive Fullscreen (preferred) or Borderless",
                "reason": (
                    "G-SYNC works in both modes on Windows 10/11 with recent drivers. "
                    "Exclusive fullscreen has slightly lower latency."
                ),
            },

            # --- Common Settings ---
            {
                "category": "In-Game Video",
                "setting": "Resolution Scale",
                "value": "100% (Native)",
                "reason": "Native resolution for sharpest visuals.",
            },
            {
                "category": "In-Game Video",
                "setting": "Motion Blur",
                "value": "Off",
                "reason": "Disable for competitive play - obscures visual clarity.",
            },
            {
                "category": "In-Game Video",
                "setting": "Anti-Aliasing",
                "value": "TAA (or disable if ghosting)",
                "reason": "UE5 uses TAA. Disable if it causes ghosting on fast movement.",
            },

            # --- Windows Settings ---
            {
                "category": "Windows Settings",
                "setting": "Refresh Rate",
                "value": "300Hz",
                "reason": (
                    "Settings > System > Display > Advanced display. "
                    "Keep at max refresh. With G-SYNC, scanout matches FPS (4.17ms at 240fps) "
                    "but higher refresh = lower minimum latency if FPS spikes."
                ),
            },

            # --- Troubleshooting ---
            {
                "category": "Troubleshooting",
                "setting": "If experiencing micro-stuttering",
                "value": "Adjust Low Latency Mode",
                "reason": (
                    "Low Latency Mode reduces the render queue, which CAN cause stuttering "
                    "on some systems. Try:\n"
                    "1. Set Low Latency Mode to 'Off' in NVCP\n"
                    "2. Use NPI to set 'Maximum Pre-Rendered Frames' to 2-3\n"
                    "These settings are hardware-dependent."
                ),
            },
            {
                "category": "Troubleshooting",
                "setting": "If G-SYNC not engaging",
                "value": "Check G-SYNC indicator",
                "reason": (
                    "NVCP > Display > Set up G-SYNC > 'Enable G-SYNC indicator'. "
                    "Verify indicator shows when game is running. If not:\n"
                    "1. Ensure FPS cap is BELOW refresh rate\n"
                    "2. Try Exclusive Fullscreen mode\n"
                    "3. Check that G-SYNC is enabled globally"
                ),
            },

            # --- Latency Comparison ---
            {
                "category": "Latency Info",
                "setting": "Expected latency vs no-sync",
                "value": "+2-5ms",
                "reason": (
                    "VRR setup adds ~2-5ms vs no-sync:\n"
                    "- G-SYNC processing: ~1-2ms\n"
                    "- Scanout at 240fps: 4.17ms vs 3.33ms at 300Hz no-sync\n\n"
                    "Trade-off: Completely tear-free visuals for slightly higher latency. "
                    "Many players prefer this for the smoother experience."
                ),
            },
            {
                "category": "Latency Info",
                "setting": "Why in-game 297 is optimal for 300Hz",
                "value": "Best of both worlds",
                "reason": (
                    "Per BlurBusters: In-game limiters throttle at ENGINE-LEVEL before frame "
                    "calculation, while NVCP/RTSS throttle AFTER frames are calculated.\n\n"
                    "| Method | Limiter Latency | Scanout | Net Result |\n"
                    "|--------|-----------------|---------|------------|\n"
                    "| In-game 297 | ~0.5ms | 3.37ms | LOWEST |\n"
                    "| In-game 240 | ~0.5ms | 4.17ms | +0.8ms |\n"
                    "| NVCP 297 | ~2-4ms | 3.37ms | +1.5-3.5ms |\n\n"
                    "Custom FPS cap (1-999) lets you use the fast in-game limiter at optimal 297fps."
                ),
            },
        ]
