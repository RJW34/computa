"""OBS Streaming optimization profile.

Combines system-level optimizations (Windows, Power, NVIDIA) with
OBS-specific encoder settings for optimal streaming performance.
Designed for Twitch streaming at 1080p60 with minimal encoding overhead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class OBSStreamingProfile(BaseProfile):
    """Optimization profile for OBS streaming.

    Optimizes both system settings and OBS configuration for
    streaming to platforms like Twitch, YouTube, and Kick.

    Key optimizations:
    - NVENC encoder settings (CBR, proper bitrate, balanced preset)
    - Windows settings (Game Mode ON, HAGS OFF for NVENC stability)
    - Power plan (Ultimate Performance for consistent encoding)
    - Process priority (OBS gets encoding priority)
    - Output resolution scaling (1080p for quality/bitrate balance)
    """

    def __init__(
        self,
        target_bitrate: int = 6000,
        output_resolution: tuple[int, int] = (1920, 1080),
        encoder_preset: str = "p5",
    ) -> None:
        """Initialize streaming profile.

        Args:
            target_bitrate: Stream bitrate in kbps (default: 6000 for Twitch)
            output_resolution: Output resolution tuple (default: 1080p)
            encoder_preset: NVENC preset p1-p7 (default: p5 balanced)
        """
        self._target_bitrate = target_bitrate
        self._output_resolution = output_resolution
        self._encoder_preset = encoder_preset

    @property
    def profile_id(self) -> str:
        return "obs-streaming"

    @property
    def display_name(self) -> str:
        return "OBS Streaming (Twitch 1080p60)"

    @property
    def description(self) -> str:
        return "Optimized for streaming to Twitch at 1080p 60fps with minimal encoding overhead"

    @property
    def optimization_target(self) -> str:
        return "streaming_quality"

    @property
    def executable_hints(self) -> list[str]:
        return [
            "obs64.exe",
            "obs32.exe",
            "obs-browser.exe",
        ]

    @property
    def is_online_profile(self) -> bool:
        # Streaming is inherently online but doesn't use rollback netcode
        return False

    @property
    def requires_reflex(self) -> bool:
        # OBS doesn't use Reflex
        return False

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        # OBS uses DirectX 11 for composition
        return "dx11"

    @property
    def allows_aggressive_settings(self) -> bool:
        # Streaming prioritizes stability over aggressive latency
        return False

    @property
    def network_scope(self) -> Literal["full", "limited", "none"]:
        # Streaming needs stable network, not aggressive tuning
        return "limited"

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.obs import OBSSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        return [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            OBSSettingsHandler(),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                # Game Mode helps with encoding priority
                "game_mode": True,
                "game_bar": False,  # Not needed, adds overhead
                "game_dvr": False,  # OBS handles recording
                # HAGS OFF - can interfere with NVENC stability
                "hags": False,
                # VRR not relevant for streaming
                "vrr_optimize": False,
            },
            "PowerSettingsHandler": {
                # Ultimate performance for consistent encoding
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                # Prevent throttling during long streams
                "processor_max_performance": True,
                "processor_min_state": 100,
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
            },
            "RegistrySettingsHandler": {
                # Lower system responsiveness = more CPU for OBS
                "system_responsiveness": 10,
                # OBS process priority
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 2,  # Normal (OBS handles its own priority)
                    "scheduling_category": "Medium",
                },
            },
            "NvidiaSettingsHandler": {
                # Streaming-focused NVIDIA settings (explicit keys)
                "low_latency_mode": "off",  # OFF - avoids NVENC frame pacing issues
                "power_management": "prefer_max_performance",
                "shader_cache": "unlimited",
                "threaded_optimization": "on",
                "vsync": "off",
            },
            "OBSSettingsHandler": {
                # Stream encoder settings
                "stream_encoder": {
                    "rate_control": "CBR",
                    "bitrate": self._target_bitrate,
                    "preset": self._encoder_preset,
                    "multipass": "disabled",
                    "profile": "high",
                    "look-ahead": False,
                    "psycho_aq": True,
                },
                # Video output settings
                "video": {
                    "output_cx": self._output_resolution[0],
                    "output_cy": self._output_resolution[1],
                    "scale_type": "lanczos",
                },
                # Low latency for stream
                "low_latency": True,
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """OBS and streaming setup recommendations."""
        return [
            # =========================================================================
            # OBS ENCODER SETTINGS
            # =========================================================================
            {
                "category": "=== OBS ENCODER SETTINGS ===",
                "setting": "Output Mode",
                "value": "Advanced",
                "reason": "Advanced mode gives full control over encoder settings.",
            },
            {
                "category": "OBS Encoder",
                "setting": "Encoder",
                "value": "NVIDIA NVENC H.264 (new)",
                "reason": "Hardware encoding with minimal CPU impact. Use jim_nvenc for best performance.",
            },
            {
                "category": "OBS Encoder",
                "setting": "Rate Control",
                "value": "CBR (Constant Bit Rate)",
                "reason": "Required for streaming. VBR/CQP/Lossless won't work properly.",
            },
            {
                "category": "OBS Encoder",
                "setting": "Bitrate",
                "value": f"{self._target_bitrate} kbps",
                "reason": "Twitch recommends 6000 kbps for 1080p60. Max is ~8500 kbps for Partners.",
            },
            {
                "category": "OBS Encoder",
                "setting": "Preset",
                "value": "P5: Slow (Good Quality)",
                "reason": "Balanced quality/performance. P6-P7 are overkill and cause GPU spikes.",
            },
            {
                "category": "OBS Encoder",
                "setting": "Profile",
                "value": "high",
                "reason": "Best compression efficiency for streaming.",
            },
            {
                "category": "OBS Encoder",
                "setting": "Look-ahead",
                "value": "OFF",
                "reason": "Adds latency. Only useful for recordings.",
            },
            {
                "category": "OBS Encoder",
                "setting": "Psycho Visual Tuning",
                "value": "ON",
                "reason": "Improves perceived quality at same bitrate.",
            },
            {
                "category": "OBS Encoder",
                "setting": "Max B-frames",
                "value": "2",
                "reason": "Good balance of quality and encoding speed.",
            },
            {
                "category": "OBS Encoder",
                "setting": "Keyframe Interval",
                "value": "2 seconds",
                "reason": "Required by Twitch/YouTube for proper seeking.",
            },

            # =========================================================================
            # OBS VIDEO SETTINGS
            # =========================================================================
            {
                "category": "=== OBS VIDEO SETTINGS ===",
                "setting": "Base (Canvas) Resolution",
                "value": "Your monitor resolution",
                "reason": "Match your display for 1:1 capture quality.",
            },
            {
                "category": "OBS Video",
                "setting": "Output (Scaled) Resolution",
                "value": f"{self._output_resolution[0]}x{self._output_resolution[1]}",
                "reason": "1080p is the sweet spot for Twitch at 6000 kbps.",
            },
            {
                "category": "OBS Video",
                "setting": "Downscale Filter",
                "value": "Lanczos (Sharpened scaling, 36 samples)",
                "reason": "Best quality downscaling for streaming.",
            },
            {
                "category": "OBS Video",
                "setting": "FPS",
                "value": "60",
                "reason": "Standard for gaming streams. 30 FPS only for low-motion content.",
            },
            {
                "category": "OBS Video",
                "setting": "Color Format",
                "value": "NV12",
                "reason": "Standard for streaming. I444/I422 not supported by most platforms.",
            },

            # =========================================================================
            # OBS ADVANCED SETTINGS
            # =========================================================================
            {
                "category": "=== OBS ADVANCED SETTINGS ===",
                "setting": "Process Priority",
                "value": "Above Normal",
                "reason": "Settings > Advanced > Process Priority. Helps prevent dropped frames.",
            },
            {
                "category": "OBS Advanced",
                "setting": "Renderer",
                "value": "Direct3D 11",
                "reason": "Most stable renderer for Windows.",
            },
            {
                "category": "OBS Advanced",
                "setting": "Color Space",
                "value": "sRGB",
                "reason": "Standard for streaming. Rec. 709 also works.",
            },
            {
                "category": "OBS Advanced",
                "setting": "Color Range",
                "value": "Partial",
                "reason": "Full range can cause crushed blacks on some platforms.",
            },

            # =========================================================================
            # GAME CAPTURE TIPS
            # =========================================================================
            {
                "category": "=== GAME CAPTURE TIPS ===",
                "setting": "Capture Method",
                "value": "Game Capture (not Window/Display)",
                "reason": "Game Capture has lowest overhead and best compatibility.",
            },
            {
                "category": "Game Capture",
                "setting": "Anti-cheat Compatibility Hook",
                "value": "Enable if game uses anti-cheat",
                "reason": "Required for games like Valorant, Fortnite, Apex.",
            },
            {
                "category": "Game Capture",
                "setting": "Capture Cursor",
                "value": "ON for most games",
                "reason": "Viewers like seeing your cursor for context.",
            },
            {
                "category": "Game Capture",
                "setting": "Limit Capture Framerate",
                "value": "OFF",
                "reason": "Let OBS handle frame timing with its own logic.",
            },

            # =========================================================================
            # PERFORMANCE MONITORING
            # =========================================================================
            {
                "category": "=== PERFORMANCE MONITORING ===",
                "setting": "Stats Window",
                "value": "View > Stats (keep open while streaming)",
                "reason": "Monitor encoding lag, rendering lag, and dropped frames.",
            },
            {
                "category": "Performance",
                "setting": "Encoding Overloaded Warning",
                "value": "Should NEVER appear",
                "reason": "If you see this, lower preset (p5->p4) or resolution.",
            },
            {
                "category": "Performance",
                "setting": "GPU Usage While Streaming",
                "value": "< 90% recommended",
                "reason": "Leave headroom for NVENC. 100% GPU = dropped frames.",
            },
        ]


class OBSStreaming720pProfile(OBSStreamingProfile):
    """720p60 streaming profile for lower bandwidth connections."""

    def __init__(self) -> None:
        super().__init__(
            target_bitrate=4500,
            output_resolution=(1280, 720),
            encoder_preset="p5",
        )

    @property
    def profile_id(self) -> str:
        return "obs-streaming-720p"

    @property
    def display_name(self) -> str:
        return "OBS Streaming (720p60)"

    @property
    def description(self) -> str:
        return "Streaming at 720p 60fps - good for limited upload bandwidth"


class OBSStreaming1080pSlowProfile(OBSStreamingProfile):
    """1080p60 high quality profile using slower preset."""

    def __init__(self) -> None:
        super().__init__(
            target_bitrate=8000,
            output_resolution=(1920, 1080),
            encoder_preset="p6",  # Slower but higher quality
        )

    @property
    def profile_id(self) -> str:
        return "obs-streaming-hq"

    @property
    def display_name(self) -> str:
        return "OBS Streaming (1080p60 HQ)"

    @property
    def description(self) -> str:
        return "High quality streaming at 1080p - for Twitch Partners with transcoding"
