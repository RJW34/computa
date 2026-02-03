"""Rivals of Aether 2 - ONLINE / MATCHMAKING profile.

Target: Ranked matchmaking, unranked online play, any rollback-enabled session.
Rollback netcode behavior is AUTHORITATIVE for this profile.

Per rollback.md canonical spec:
- Optimization Class: Rollback-Safe Low Latency
- Priority: Frame pacing stability > absolute latency

Goals:
- Deterministic stability for rollback netcode
- Prevent timing contention
- Preserve rollback recovery elasticity

NVCP Settings (per-game for Rivals2.exe):
- V-Sync: OFF (rollback is timing-sensitive, not tear-sensitive)
- G-SYNC / VRR: OFF (no VRR for online)
- Low Latency Mode: ON (NOT Ultra!)
- Max Frame Rate: OFF (no external limiters)
- Threaded Optimization: OFF (UE5 driver contention)
- Power Management: Prefer Maximum Performance

External Tools: RTSS, frame pacing hooks DISABLED.

EXPLICIT PROHIBITIONS (per canonical spec):
- LLM = Ultra (can cause frame pacing issues, overrides FPS caps)
- Fast Sync (incompatible with rollback)
- G-SYNC / VRR (adds ~2-5ms latency overhead)
- External FPS caps
- Refresh-minus-X logic
- Ultimate Performance plan (need scheduler headroom)
- Injection tools (RTSS)

Canonical one-line definition:
> Exclusive fullscreen + no sync + uncapped FPS + NV LLM ON (not Ultra) + HAGS ON + High Performance plan + no overlays
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class Rivals2OnlineProfile(BaseProfile):
    """Optimization profile for Rivals 2 ONLINE / MATCHMAKING play.

    Conservative stability-focused profile for:
    - Ranked matchmaking
    - Unranked online play
    - Any rollback-enabled session

    Prioritizes rollback netcode stability over raw latency reduction.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-online"

    @property
    def display_name(self) -> str:
        return "Rivals 2: Online / Matchmaking"

    @property
    def description(self) -> str:
        return "Stable rollback-safe settings for online play (prioritizes stability)"

    @property
    def optimization_target(self) -> str:
        return "stable_online"

    @property
    def executable_hints(self) -> list[str]:
        return [
            "Rivals2-Win64-Shipping.exe",
            "RivalsofAether2.exe",
            "Rivals2.exe",
        ]

    # === Validation Metadata Overrides ===

    @property
    def is_online_profile(self) -> bool:
        """This is explicitly an online rollback profile."""
        return True

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
        """Online profiles should NOT use aggressive settings."""
        return False

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.cnm import CNMSettingsHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.mouse import MouseSettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.services import ServicesSettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        return [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            NetworkSettingsHandler(),
            MouseSettingsHandler(),
            GraphicsSettingsHandler(),
            ServicesSettingsHandler(),
            MemorySettingsHandler(),
            ProcessPriorityHandler(self.executable_hints),
            CNMSettingsHandler(),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get stable, rollback-safe settings for online play.

        CRITICAL: These settings prioritize rollback netcode stability.
        Do NOT use aggressive latency settings for online play.
        """
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,  # Hardware Accelerated GPU Scheduling
                "hdr": False,  # Rivals 2 is SDR
                "auto_hdr": False,
                "vrr_optimize": False,  # Windows VRR OFF
                "max_refresh_rate": True,  # Set display to max refresh rate for current resolution
            },
            "PowerSettingsHandler": {
                # High performance but not "ultimate" - preserve scheduler elasticity
                "ensure_ultimate_performance": False,
                "active_plan": "high_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
                "disable_core_parking": True,
            },
            "RegistrySettingsHandler": {
                "system_responsiveness": 10,
                "network_throttling": 0xFFFFFFFF,
                "win32_priority_separation": 0x2A,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    "sfio_priority": "High",
                },
                # CONSERVATIVE: No forced sub-0.5ms timers
                # Do not remove scheduler elasticity
            },
            "NvidiaSettingsHandler": {
                # ONLINE profile: Conservative settings for rollback stability
                # Per rollback.md canonical spec - frame pacing stability > absolute latency
                "low_latency_mode": "on",  # ON, NOT Ultra! (Ultra can cause frame pacing issues, overrides FPS caps)
                "power_management": "prefer_max_performance",
                "vsync": "off",  # OFF - rollback netcode is timing-sensitive, not tear-sensitive
                "vsync_tear_control": "disable",  # Explicit tear control off with VSync OFF
                "gsync": "off",  # OFF - VRR adds ~2-5ms latency overhead
                "max_frame_rate": "off",  # Uncapped — no external limiters for online play
                "shader_cache": "unlimited",
                "threaded_optimization": "off",  # OFF - UE5 driver contention
                "triple_buffering": "off",  # OFF - irrelevant without VSync
                "game_name": "Rivals 2 Online",
            },
            "NetworkSettingsHandler": {
                "disable_nagle": True,
                "preset": "gaming",
            },
            "MouseSettingsHandler": {
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": True,
                "disable_mpo": False,  # MPO enabled for VRR
            },
            "ServicesSettingsHandler": {
                "preset": "gaming",
            },
            "MemorySettingsHandler": {
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            },
            "ProcessPriorityHandler": {
                "gpu_priority": 8,
                "cpu_priority": 2,  # Normal-High (not aggressive)
                "io_priority": 2,
            },
            "CNMSettingsHandler": {
                "action": "stop",
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for ONLINE play."""
        return [
            {
                "category": "=== ONLINE PROFILE ===",
                "setting": "Use Case",
                "value": "Ranked, Unranked, Rollback Sessions",
                "reason": "This profile prioritizes STABILITY for rollback netcode.",
            },
            {
                "category": "=== EXPLICIT PROHIBITIONS ===",
                "setting": "DO NOT USE",
                "value": "LLM Ultra, Fast VSync, External FPS Caps, Refresh-3 Logic",
                "reason": "These cause rollback timing failures at 300Hz. Stability > latency online.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "G-SYNC / VRR",
                "value": "OFF",
                "reason": "VRR OFF for online - adds ~2-5ms latency overhead.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical Sync",
                "value": "OFF",
                "reason": "OFF - rollback netcode is timing-sensitive, high-refresh tearing is negligible.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Threaded Optimization",
                "value": "OFF",
                "reason": "OFF - prevents UE5 driver contention issues.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": "ON (not Ultra) - Ultra can cause frame pacing issues and overrides FPS caps.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "DISABLED",
                "reason": "No external FPS cap — uncapped for online play.",
            },
            {
                "category": "In-Game Settings",
                "setting": "V-Sync",
                "value": "OFF",
                "reason": "Native engine timing must remain authoritative.",
            },
            {
                "category": "External Tools",
                "setting": "RTSS / Frame Limiters",
                "value": "DISABLED",
                "reason": "External limiters cause limiter contention with rollback. Disable all.",
            },
            {
                "category": "Monitoring",
                "setting": "Overlays",
                "value": "ALLOWED (read-only)",
                "reason": "Monitoring overlays are fine, but no frame pacing intervention.",
            },
            {
                "category": "Validation",
                "setting": "Expected Behavior",
                "value": "Minor frametime variance OK, no persistent VRR dropouts",
                "reason": "Rollback resync frames must not cause cascading frame loss.",
            },
        ]
