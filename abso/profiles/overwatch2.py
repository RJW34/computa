"""Overwatch 2 profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.profile_bases import ReflexShooterBaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class _Overwatch2BaseProfile(ReflexShooterBaseProfile):
    """Shared Overwatch 2 profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return ["Overwatch.exe"]

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        # Overwatch 2 uses DX11 in most competitive configurations.
        return "dx11"

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.ow2_config import OW2ConfigHandler

        handlers = super().get_handlers()
        handlers.append(OW2ConfigHandler())
        return handlers

    def _base_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                # Keep HDR disabled by default to avoid SDR/HDR tone-mapping bugs.
                "hdr": False,
            },
            "GraphicsSettingsHandler": {
                # Keep MPO enabled unless explicitly troubleshooting compositor issues.
                "disable_mpo": False,
            },
            "OW2ConfigHandler": {
                "window_mode": 0,               # Fullscreen
                "vsync": False,                  # Off
                "reduce_buffering": True,        # On
                "dynamic_render_scale": False,   # Off
                "render_scale": 0,               # 100%
                "upscaling": False,              # Disabled
                "triple_buffering": False,       # Off
                "hdr": False,                    # Off — prevents blown-out SDR from OW2 internal HDR pipeline
                "gfx_preset": 1,                 # Low
                "effects_quality": 1,            # Low
                "texture_detail": 1,             # Low
                "model_quality": 1,              # Low
                "aa_detail": 0,                  # Off
                "show_fps": True,
                "show_latency": True,
            },
        }

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        merged = self._base_overrides()
        for handler, values in self._variant_overrides().items():
            if handler not in merged:
                merged[handler] = {}
            merged[handler].update(values)
        return merged


class Overwatch2Profile(_Overwatch2BaseProfile):
    """Overwatch 2 no-sync profile.

    This is the absolute minimum-latency variant. It explicitly disables VRR/G-SYNC
    per-app so behavior is deterministic even when users have global VRR enabled.
    """

    @property
    def profile_id(self) -> str:
        return "overwatch2"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - No-Sync"

    @property
    def description(self) -> str:
        return "Minimum latency no-sync profile (Reflex, VSync OFF, VRR OFF)"

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                # Reflex handles queueing; keep driver queue options and VRR deterministic.
                "preset": "reflex_no_sync",
                # Use NVIDIA's predefined OW2 profile to avoid executable binding conflicts.
                "profile_name": "Overwatch 2",
                # Enforce global no-sync state for deterministic No-SYNC profile transitions.
                "global_vrr_mode": "off",
            },
            "OW2ConfigHandler": {
                # No-sync: uncapped / high fixed cap for minimum latency.
                "frame_rate_cap": 400,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": "Lowest-latency presentation path.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off",
                "reason": "No-sync mode removes sync queueing latency.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "Enabled + Boost",
                "reason": "Use native Reflex; keep driver LLM off.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Uncapped or high fixed cap",
                "reason": "No-sync profile prioritizes minimum click-to-pixel latency.",
            },
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": "Reduces render queue depth in-engine.",
            },
            {
                "category": "Graphics",
                "setting": "Dynamic Render Scale",
                "value": "Off",
                "reason": "Avoid frametime variance from dynamic scaling.",
            },
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Improves frame-time consistency in team fights.",
            },
        ]


class Overwatch2GSyncProfile(_Overwatch2BaseProfile):
    """Overwatch 2 G-SYNC profile.

    Tear-free low-latency VRR profile. Uses Reflex + NVCP VSync safety net and
    per-app VRR enabled.
    """

    @property
    def profile_id(self) -> str:
        return "overwatch2-gsync"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - GSYNC"

    @property
    def description(self) -> str:
        return "Low latency VRR profile (Reflex, VSync safety net, G-SYNC ON)"

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                # Use NVIDIA's predefined OW2 profile to avoid executable binding conflicts.
                "profile_name": "Overwatch 2",
                # Enforce VRR-safe cap automatically (refresh-3) to keep VSync as safety net.
                "auto_vrr_fps_cap": True,
                # Ensure global G-SYNC is enabled before launching OW2.
                "global_vrr_mode": "fullscreen_only",
            },
            "ColorProfileSettingsHandler": {
                # Slightly below neutral (50) to compensate for DCI-P3 oversaturation in SDR.
                "digital_vibrance": 45,
            },
            "OW2ConfigHandler": {
                # Remove any pre-existing in-game cap; NVCP auto_vrr_fps_cap handles the real limit.
                "frame_rate_cap": 400,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": "Best VRR behavior with lowest compositor overhead.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off (in-game)",
                "reason": "Use NVCP VSync as safety net; keep in-game VSync off.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "Enabled + Boost",
                "reason": "Native Reflex should own queue control.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Refresh rate - 3",
                "reason": "Keeps NVCP VSync from engaging while preserving VRR tear-free output.",
            },
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": "Maintains low queue depth in the render pipeline.",
            },
            {
                "category": "Graphics",
                "setting": "Dynamic Render Scale",
                "value": "Off",
                "reason": "Avoid large frame pacing oscillations.",
            },
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Minimizes frame spikes during heavy ability usage.",
            },
        ]


class Overwatch2GSyncHDRProfile(_Overwatch2BaseProfile):
    """Overwatch 2 G-SYNC + HDR profile.

    Tear-free low-latency VRR with native HDR enabled. Designed for
    HDR-capable monitors (OLED, Mini-LED). Uses native color space
    instead of sRGB clamp.

    OW2's HDR implementation works well on OLED with proper in-game
    calibration (Paper White Nits, Max Nits). Auto HDR is disabled
    since OW2 has native HDR support.
    """

    @property
    def profile_id(self) -> str:
        return "overwatch2-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - GSYNC HDR"

    @property
    def description(self) -> str:
        return "Tear-free low latency VRR with native HDR (OLED/Mini-LED)"

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    def _base_overrides(self) -> dict[str, dict[str, Any]]:
        base = super()._base_overrides()
        base.update({
            "WindowsSettingsHandler": {
                "hdr": True,
                "auto_hdr": False,
            },
            "GraphicsSettingsHandler": {
                "disable_mpo": False,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "OW2ConfigHandler": {
                **base.get("OW2ConfigHandler", {}),
                "hdr": True,  # Native HDR — OW2 handles tone mapping for OLED/Mini-LED
            },
        })
        return base

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Overwatch 2",
                "auto_vrr_fps_cap": True,
                "global_vrr_mode": "fullscreen_only",
            },
            "OW2ConfigHandler": {
                # Remove any pre-existing in-game cap; NVCP auto_vrr_fps_cap handles the real limit.
                "frame_rate_cap": 400,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": "Best VRR behavior with lowest compositor overhead.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off (in-game)",
                "reason": "Use NVCP VSync as safety net; keep in-game VSync off.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "Enabled + Boost",
                "reason": "Native Reflex should own queue control.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Refresh rate - 3",
                "reason": "Keeps NVCP VSync from engaging while preserving VRR tear-free output.",
            },
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": "Maintains low queue depth in the render pipeline.",
            },
            {
                "category": "Display",
                "setting": "HDR Mode",
                "value": "On",
                "reason": "Native HDR output for OLED/Mini-LED displays.",
            },
            {
                "category": "Display",
                "setting": "HDR Paper White Nits",
                "value": "~200 (calibrate to taste)",
                "reason": "Controls SDR-content brightness under HDR. ~200 nits is a good OLED starting point.",
            },
            {
                "category": "Display",
                "setting": "HDR Max Display Brightness",
                "value": "Match monitor peak (e.g. 1000+ nits OLED)",
                "reason": "Set to your display's actual peak brightness for correct tone mapping.",
            },
            {
                "category": "Display",
                "setting": "HDR UI Brightness",
                "value": "Adjust to taste",
                "reason": "OW2-specific slider for HUD brightness under HDR.",
            },
            {
                "category": "Graphics",
                "setting": "Dynamic Render Scale",
                "value": "Off",
                "reason": "Avoid large frame pacing oscillations.",
            },
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Minimizes frame spikes during heavy ability usage.",
            },
        ]
