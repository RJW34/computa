"""Fortnite profiles."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import (
    ReflexShooterBaseProfile,
    fso_overrides,
    merge_settings_map,
)


class _FortniteBaseProfile(ReflexShooterBaseProfile):
    """Shared Fortnite profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return [
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe",
        ]

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Competitive Fortnite runs exclusive-fullscreen (fullscreen_mode=0 in
        # GameUserSettings.ini). Disable FSO per-exe so Windows doesn't shunt
        # the shipping binary into the composited borderless path and steal
        # FPS from the Reflex/DX12 presentation path.
        return fso_overrides(self.executable_hints)

    @property
    def nvidia_binding_executables(self) -> list[str]:
        # executable_hints is broad (the shipping binary plus its EAC/BE
        # anti-cheat bootstrapper variants) for process detection. NVIDIA DRS
        # binding should target only the real rendering process, so strict VRR
        # binding proof doesn't chase the anti-cheat launcher names.
        return ["FortniteClient-Win64-Shipping.exe"]

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Fortnite"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        return [
            "Fortnite - HDR",
            "Fortnite (Streaming)",
            "Fortnite (Streaming HDR)",
        ]

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    def get_handlers(self):
        from abso.settings.fortnite_config import FortniteConfigHandler

        return [*super().get_handlers(), FortniteConfigHandler()]

    def _shared_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                # Honor the "No Sync" label at the driver level. The inherited
                # ReflexShooter base preset is reflex_game, which sets no
                # vrr_app_override and therefore leaves G-SYNC/VRR to the user's
                # global NVCP toggle. reflex_no_sync explicitly forces VRR off
                # (vrr_app_override=force_off + vsync_tear_control=disable) like
                # the OW2/Deadlock no-sync siblings, while still keeping driver
                # LLM off so in-game Reflex owns the render queue.
                "preset": "reflex_no_sync",
            },
            "FortniteConfigHandler": {
                "fullscreen_mode": 0,
                "vsync": False,
                "frame_rate_limit": 0,
            },
        }

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(self._shared_overrides(), self._variant_overrides())

    def _common_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": "Matches the competitive no-sync path this profile actually applies.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off",
                "reason": "Keep sync latency out of the path for this Reflex-first profile.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost — set the in-game toggle manually; profile requests driver LLM Off",
                "reason": "Applying this profile requests NVIDIA driver LLM Off for native Reflex queue control. Fortnite's Reflex toggle lives in Fortnite's settings and there is no stable config key to write it from outside; manually flip 'NVIDIA Reflex Low Latency' to 'On + Boost' in the game once.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Limit",
                "value": "Unlimited",
                "reason": "This is the explicit no-sync Fortnite lane, not a VRR cap profile.",
            },
            {
                "category": "Graphics",
                "setting": "Rendering Mode",
                "value": "DirectX 12",
                "reason": "This profile is built around Fortnite's DX12 path for Reflex and modern presentation behavior.",
            },
            {
                "category": "Graphics",
                "setting": "Multithreaded Rendering",
                "value": "On",
                "reason": "Better CPU utilization and more stable frame delivery in stacked endgames.",
            },
            {
                "category": "Graphics",
                "setting": "3D Resolution / DLSS",
                "value": "100% or DLSS Performance if GPU-bound",
                "reason": "Keep frame times stable first; use DLSS only when needed to hold target FPS.",
            },
            {
                "category": "Graphics",
                "setting": "Motion Blur",
                "value": "Off",
                "reason": "Reduces visual noise and preserves snap-tracking clarity.",
            },
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Endgame effects spikes matter more than visual richness in the competitive lane.",
            },
            {
                "category": "Content",
                "setting": "High Resolution Textures",
                "value": "Off",
                "reason": "Avoids streaming hitches and unnecessary VRAM churn.",
            },
        ]


class FortniteProfile(_FortniteBaseProfile):
    """Fortnite SDR competitive profile."""

    @property
    def profile_id(self) -> str:
        return "fortnite"

    @property
    def display_name(self) -> str:
        return "Fortnite - SDR"

    @property
    def description(self) -> str:
        return (
            "Competitive SDR Fortnite profile with a no-sync latency path. "
            "Keeps driver LLM off for Reflex; enable Reflex On + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": False,
                "auto_hdr": False,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 45,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "FortniteConfigHandler": {
                # SDR lane: HDR output off. The config handler writes
                # HDRDisplayOutputNits unconditionally, but Fortnite ignores the
                # nits value when bUseHDRDisplayOutput is false, so setting it
                # here would only write an inert INI line (matches the Marvel
                # Rivals SDR cleanup).
                "hdr_output": False,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Off",
                "reason": "This variant intentionally stays on the SDR path.",
            },
            *self._common_in_game_settings(),
        ]


class FortniteHDRProfile(_FortniteBaseProfile):
    """Fortnite HDR competitive profile."""

    @property
    def profile_id(self) -> str:
        return "fortnite-hdr"

    @property
    def display_name(self) -> str:
        return "Fortnite - HDR"

    @property
    def description(self) -> str:
        return (
            "Competitive Fortnite HDR profile with a no-sync latency path. "
            "Keeps driver LLM off for Reflex; enable Reflex On + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": True,
                "advanced_color": True,  # Win11 24H2+ WCG pairing
                "auto_hdr": False,
                # Paper-white ≈ 200 nits under HDR on OLED / Mini-LED.
                # Driver installs reset this slider; asserting it here
                # restores the correct SDR-in-HDR tone-mapping.
                "sdr_white_level_nits": 200,
            },
            "GraphicsSettingsHandler": {
                # Assert ACM off so Windows can't silently clamp wide-gamut
                # to sRGB after a driver re-enumeration.
                "disable_auto_color_management": True,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "FortniteConfigHandler": {
                "hdr_output": True,
                "hdr_nits": 1000,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "On",
                "reason": "Use Fortnite's native HDR output path in GameUserSettings.ini when the installed build and display path support HDR.",
            },
            {
                "category": "Display",
                "setting": "HDR Peak Brightness / Nits",
                "value": "Start at 1000 nits or match your display peak",
                "reason": "Keep Windows HDR and Fortnite's native HDR output aligned.",
            },
            *self._common_in_game_settings(),
        ]


class FortniteGSyncHDRProfile(_FortniteBaseProfile):
    """Fortnite G-SYNC + native HDR competitive profile.

    Tear-free low-latency VRR path for HDR-capable displays (OLED / Mini-LED).
    Unlike the no-sync Fortnite lanes, this keeps G-SYNC ON with NVCP VSync as
    the safety net and an auto refresh - 3 FPS cap (Blur Busters G-SYNC 101).
    Reflex still owns the render queue (driver LLM stays off); flip Fortnite's
    in-game NVIDIA Reflex to On + Boost once.

    Runs the same exclusive-fullscreen path as the SDR/HDR no-sync siblings
    (PreferredFullscreenMode=0); the difference is the sync model, not the
    presentation path. On a mixed-refresh multi-monitor desktop where strict
    fullscreen VRR can cause a secondary-monitor black flash, ABSO can fall
    back to the no-sync HDR lane via ``mixed_refresh_safe_fallback_profile_id``.
    """

    @property
    def profile_id(self) -> str:
        return "fortnite-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Fortnite - GSYNC HDR"

    @property
    def description(self) -> str:
        return (
            "Tear-free low-latency VRR Fortnite profile with native HDR "
            "(OLED / Mini-LED). G-SYNC ON + NVCP VSync safety net with a "
            "refresh - 3 cap; keeps driver LLM off for Reflex (enable Reflex "
            "On + Boost in-game)."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        # VRR-dependent lane: fail fast (or fall back) when the monitor stack
        # is not reporting confirmed G-SYNC/VRR capability.
        return True

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> str:
        # No overlay/capture borderless sibling exists for Fortnite, so on a
        # mixed-refresh desktop where strict fullscreen VRR risks a secondary
        # black flash, fall back to the no-sync HDR lane instead of the strict
        # G-SYNC path.
        return "fortnite-hdr"

    @property
    def allow_dual_limiter(self) -> bool:
        # Fortnite rewrites GameUserSettings.ini on exit, so ABSO layers the
        # in-game cap (authoritative, Blur Busters-preferred) with the NVIDIA
        # driver cap (safety net). Both resolve to refresh - 3, so the
        # effective cap stays deterministic if the INI drifts.
        return True

    def _shared_overrides(self) -> dict[str, dict[str, Any]]:
        # Replace the no-sync base contract (reflex_no_sync / uncapped) with the
        # G-SYNC one. Reflex still owns the render queue (driver LLM off), but
        # VRR is enabled with NVCP VSync as the safety net and a refresh - 3 cap.
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                # Auto-detect refresh and cap below it for G-SYNC headroom.
                "auto_vrr_fps_cap": True,
                # Enable G-SYNC for exclusive fullscreen (PreferredFullscreenMode=0).
                "global_vrr_mode": "fullscreen_only",
                # reflex_gsync already sets vrr_app_override=allow, but assert it
                # explicitly so a no-sync Fortnite lane (force_off) -> this lane
                # re-enables VRR deterministically instead of relying on the
                # global flip alone (symmetric with the Rivals 2 G-SYNC lanes).
                "vrr_app_override": "allow",
            },
            "FortniteConfigHandler": {
                "fullscreen_mode": 0,
                "vsync": False,
                # Write the in-game FrameRateLimit to refresh - 3 at apply time.
                "auto_vrr_fps_cap": True,
            },
        }

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": True,
                "advanced_color": True,  # Win11 24H2+ WCG pairing
                "auto_hdr": False,
                # Paper-white ≈ 200 nits under HDR on OLED / Mini-LED.
                # Driver installs reset this slider; asserting it here
                # restores the correct SDR-in-HDR tone-mapping.
                "sdr_white_level_nits": 200,
            },
            "GraphicsSettingsHandler": {
                # Assert ACM off so Windows can't silently clamp wide-gamut
                # to sRGB after a driver re-enumeration.
                "disable_auto_color_management": True,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "FortniteConfigHandler": {
                "hdr_output": True,
                "hdr_nits": 1000,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": "Exclusive fullscreen is the lowest-latency presentation path and the right match for this profile's fullscreen-only G-SYNC mode.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off (in-game)",
                "reason": "Leave VSync to NVIDIA Control Panel as the VRR safety net; keep the in-game toggle off so it never adds queueing latency.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost — set the in-game toggle manually; profile requests driver LLM Off",
                "reason": "Applying this profile requests NVIDIA driver LLM Off for native Reflex queue control. Fortnite's Reflex toggle lives in Fortnite's settings and there is no stable config key to write it from outside; manually flip 'NVIDIA Reflex Low Latency' to 'On + Boost' in the game once.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Limit",
                "value": "Auto (refresh - 3: e.g. 297 @ 300Hz, 237 @ 240Hz, 141 @ 144Hz)",
                "reason": "Set by ABSO to refresh - 3 (Blur Busters G-SYNC 101). Keeps G-SYNC active and prevents NVCP V-SYNC from engaging while preserving tear-free output.",
            },
            {
                "category": "Display",
                "setting": "HDR",
                "value": "On",
                "reason": "Use Fortnite's native HDR output path in GameUserSettings.ini when the installed build and display path support HDR.",
            },
            {
                "category": "Display",
                "setting": "HDR Peak Brightness / Nits",
                "value": "Start at 1000 nits or match your display peak",
                "reason": "Keep Windows HDR and Fortnite's native HDR output aligned.",
            },
            {
                "category": "Graphics",
                "setting": "Rendering Mode",
                "value": "DirectX 12",
                "reason": "This profile is built around Fortnite's DX12 path for Reflex and modern presentation behavior.",
            },
            {
                "category": "Graphics",
                "setting": "Multithreaded Rendering",
                "value": "On",
                "reason": "Better CPU utilization and more stable frame delivery in stacked endgames.",
            },
            {
                "category": "Graphics",
                "setting": "3D Resolution / DLSS",
                "value": "100% or DLSS Performance if GPU-bound",
                "reason": "Keep frame times stable first; use DLSS only when needed to hold the VRR cap.",
            },
            {
                "category": "Graphics",
                "setting": "Motion Blur",
                "value": "Off",
                "reason": "Reduces visual noise and preserves snap-tracking clarity.",
            },
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Endgame effects spikes matter more than visual richness in the competitive lane.",
            },
            {
                "category": "Content",
                "setting": "High Resolution Textures",
                "value": "Off",
                "reason": "Avoids streaming hitches and unnecessary VRAM churn.",
            },
        ]
