"""Overwatch 2 profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import DisplayPathRequirements
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
            "OW2ConfigHandler": {
                "window_mode": 0,  # Fullscreen (Exclusive)
                "vsync": False,  # Off
                "reduce_buffering": True,  # On
                "dynamic_render_scale": False,  # Off (UseGPUScale)
                "dynamic_render_scale_v2": False,  # Off (DynamicRenderScale current key)
                "render_scale": 0,  # 100%
                "upscaling": False,  # Disabled
                "triple_buffering": False,  # Off
                "hdr": False,  # Off - prevents blown-out SDR from OW2 internal HDR pipeline
                "gfx_preset": 1,  # Low
                "effects_quality": 1,  # Low
                "texture_detail": 1,  # Low
                "model_quality": 1,  # Low
                "aa_detail": 0,  # Off
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
        return "Minimum latency no-sync profile (Reflex OFF, VSync OFF, VRR OFF)"

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                # In-game Reflex OFF (GPU not saturated at 1440p Low).
                # Driver preset disables LLM + VSync + VRR for pure no-sync.
                "preset": "reflex_no_sync",
                # Use NVIDIA's predefined OW2 profile to avoid executable binding conflicts.
                "profile_name": "Overwatch 2",
                # Enforce global no-sync state for deterministic No-SYNC profile transitions.
                "global_vrr_mode": "off",
            },
            "OW2ConfigHandler": {
                # No-sync: exclusive fullscreen for cleanest presentation path.
                "window_mode": 0,
                # Uncapped for minimum latency (600 = OW2 max).
                "frame_rate_cap": 600,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": "No-sync: exclusive fullscreen avoids compositor overhead. FPS cap difference only matters under VRR.",
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
                "value": "Off (high-end GPU) / On+Boost (mid-range GPU)",
                "reason": (
                    "On a high-end GPU at 1440p Low, the GPU is not saturated - Reflex "
                    "throttles CPU frame submission without benefit, costing about 60 FPS. "
                    "Higher uncapped FPS means lower latency than Reflex queue management. "
                    "If your GPU is saturated (GPU usage above 90%), switch to On+Boost instead."
                ),
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Uncapped (600)",
                "reason": "No-sync profile: maximum FPS equals minimum click-to-pixel latency.",
            },
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": (
                    "Essential with Reflex OFF - limits pre-render buffer to 1 frame. "
                    "Only mechanism keeping render queue shallow."
                ),
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

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        return DisplayPathRequirements(require_overlay_free_path=True)

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        return "overwatch2-gsync-capture"

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "GraphicsSettingsHandler": {
                "disable_mpo": False,
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                # Use NVIDIA's predefined OW2 profile to avoid executable binding conflicts.
                "profile_name": "Overwatch 2",
                # Enforce VRR-safe cap automatically (refresh-3) to keep VSync as safety net.
                "auto_vrr_fps_cap": True,
                # This profile is intentionally fullscreen-only. If we ever add a
                # borderless OW2 VRR profile, it needs a different VRR path.
                "global_vrr_mode": "fullscreen_only",
            },
            "ColorProfileSettingsHandler": {
                # Slightly below neutral (50) to compensate for DCI-P3 oversaturation in SDR.
                "digital_vibrance": 45,
            },
            "OW2ConfigHandler": {
                # Set in-game cap to refresh - 3 so OW2 and NVCP agree on the VRR target.
                "auto_vrr_fps_cap": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": (
                    "This profile is tuned for fullscreen-only G-SYNC. "
                    "Do not switch to borderless/windowed mode after launch."
                ),
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
                "value": "Auto (refresh - 3)",
                "reason": "Set by ABSO to keep NVCP VSync from engaging while preserving VRR.",
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

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        return DisplayPathRequirements(require_overlay_free_path=True)

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        return "overwatch2-gsync-hdr-capture"

    def _base_overrides(self) -> dict[str, dict[str, Any]]:
        base = super()._base_overrides()
        base.update({
            "WindowsSettingsHandler": {
                "hdr": True,
                "auto_hdr": False,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "OW2ConfigHandler": {
                **base.get("OW2ConfigHandler", {}),
                "hdr": True,  # Native HDR - OW2 handles tone mapping for OLED/Mini-LED
            },
        })
        return base

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "GraphicsSettingsHandler": {
                "disable_mpo": False,
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Overwatch 2",
                "auto_vrr_fps_cap": True,
                "global_vrr_mode": "fullscreen_only",
            },
            "OW2ConfigHandler": {
                # Set in-game cap to refresh - 3 so OW2 and NVCP agree on the VRR target.
                "auto_vrr_fps_cap": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": (
                    "This profile is tuned for fullscreen-only G-SYNC. "
                    "Do not switch to borderless/windowed mode after launch."
                ),
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
                "value": "Auto (refresh - 3)",
                "reason": "Set by ABSO to keep NVCP VSync from engaging while preserving VRR.",
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


class Overwatch2GSyncCaptureProfile(_Overwatch2BaseProfile):
    """Capture-safe Overwatch 2 VRR profile.

    Uses the borderless/windowed G-SYNC path so Medal/Discord/OBS-style
    overlays can coexist with VRR more predictably than the strict
    fullscreen-exclusive esports path.
    """

    @property
    def profile_id(self) -> str:
        return "overwatch2-gsync-capture"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - GSYNC Capture-Safe"

    @property
    def description(self) -> str:
        return "Borderless/windowed VRR path for clipping, overlays, and capture apps"

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "windowed_optimizations": True,
                "vrr_optimize": True,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
                "disable_mpo": False,
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Overwatch 2",
                "auto_vrr_fps_cap": True,
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "ColorProfileSettingsHandler": {
                "digital_vibrance": 45,
            },
            "OW2ConfigHandler": {
                "window_mode": 1,
                "auto_vrr_fps_cap": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Borderless / Windowed Fullscreen",
                "reason": (
                    "Capture-safe path: keeps Medal/Discord/OBS overlays compatible while "
                    "using the windowed G-SYNC path. Use the strict fullscreen profile if "
                    "you want the absolute lowest latency and no overlays."
                ),
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off (in-game)",
                "reason": "Use NVCP VSync as the VRR safety net; keep in-game VSync off.",
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
                "value": "Auto (refresh - 3)",
                "reason": "Set by ABSO for stable windowed G-SYNC behavior below refresh.",
            },
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": "Maintains low queue depth without fighting the capture-safe path.",
            },
            {
                "category": "Graphics",
                "setting": "Dynamic Render Scale",
                "value": "Off",
                "reason": "Avoid frame pacing swings while recording/clipping.",
            },
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Minimizes frame spikes during heavy team fights and capture load.",
            },
        ]


class Overwatch2GSyncHDRCaptureProfile(_Overwatch2BaseProfile):
    """Capture-safe HDR Overwatch 2 VRR profile."""

    @property
    def profile_id(self) -> str:
        return "overwatch2-gsync-hdr-capture"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - GSYNC HDR Capture-Safe"

    @property
    def description(self) -> str:
        return "Borderless/windowed HDR VRR path for clipping, overlays, and capture apps"

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
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "OW2ConfigHandler": {
                **base.get("OW2ConfigHandler", {}),
                "hdr": True,
            },
        })
        return base

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "windowed_optimizations": True,
                "vrr_optimize": True,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
                "disable_mpo": False,
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Overwatch 2",
                "auto_vrr_fps_cap": True,
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "OW2ConfigHandler": {
                "window_mode": 1,
                "auto_vrr_fps_cap": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Borderless / Windowed Fullscreen",
                "reason": (
                    "Capture-safe HDR path: keeps Medal/Discord/OBS overlays compatible while "
                    "using windowed G-SYNC. Use the strict HDR profile only when overlays are off."
                ),
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off (in-game)",
                "reason": "Use NVCP VSync as the VRR safety net; keep in-game VSync off.",
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
                "value": "Auto (refresh - 3)",
                "reason": "Set by ABSO for stable windowed G-SYNC behavior below refresh.",
            },
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": "Maintains low queue depth without fighting the capture-safe path.",
            },
            {
                "category": "Display",
                "setting": "HDR Mode",
                "value": "On",
                "reason": "Native HDR output for OLED/Mini-LED displays on the capture-safe path.",
            },
            {
                "category": "Display",
                "setting": "HDR Paper White Nits",
                "value": "~200 (calibrate to taste)",
                "reason": "Controls SDR-content brightness under HDR.",
            },
            {
                "category": "Display",
                "setting": "HDR Max Display Brightness",
                "value": "Match monitor peak",
                "reason": "Set to your display's actual peak brightness for correct tone mapping.",
            },
            {
                "category": "Graphics",
                "setting": "Dynamic Render Scale",
                "value": "Off",
                "reason": "Avoid frame pacing swings while recording/clipping.",
            },
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Minimizes frame spikes during heavy team fights and capture load.",
            },
        ]
