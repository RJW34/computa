"""Overwatch 2 profiles."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import ReflexShooterBaseProfile


class _Overwatch2BaseProfile(ReflexShooterBaseProfile):
    """Shared Overwatch 2 profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return ["Overwatch.exe"]

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        # Overwatch 2 uses DX11 in most competitive configurations.
        return "dx11"

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
                # Ensure global G-SYNC is enabled before launching OW2.
                "global_vrr_mode": "fullscreen_only",
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
