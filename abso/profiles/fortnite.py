"""Fortnite profiles."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import (
    ReflexShooterBaseProfile,
    fso_overrides,
    merge_settings_map,
    preserve_baseline_system_policy,
)

_STREAMING_WINDOWED_VRR_OVERRIDES: dict[str, dict[str, Any]] = {
    "WindowsSettingsHandler": {
        "windowed_optimizations": True,
        "vrr_optimize": True,
    },
    "GraphicsSettingsHandler": {
        "disable_global_fso": False,
    },
    "NvidiaSettingsHandler": {
        "global_vrr_mode": "fullscreen_and_windowed",
    },
    "FortniteConfigHandler": {
        "fullscreen_mode": 1,
        # NVIDIA's G-SYNC + Reflex guidance calls for in-game VSync on the
        # windowed path. Keep one explicit FPS limiter: the driver VRR cap.
        # https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/
        "vsync": True,
        "auto_vrr_fps_cap": False,
        "frame_rate_limit": 0,
    },
    "ProcessPriorityHandler": {
        "cpu_priority": 2,
        "io_priority": 2,
    },
}


class _FortniteBaseProfile(ReflexShooterBaseProfile):
    """Shared Fortnite profile defaults."""

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        settings = preserve_baseline_system_policy(super()._base_settings())
        # Allow the normal Windows presentation path. A fullscreen selection
        # does not prove exclusive presentation or a benefit from disabling FSO.
        settings["GraphicsSettingsHandler"]["disable_global_fso"] = False
        settings["FortniteConfigHandler"] = {"require_reflex": True}
        return settings

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
        return fso_overrides(self.executable_hints, disabled=False)

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
                "value": "Fullscreen",
                "reason": "Matches the game's fullscreen selection; the saved enum does not prove exclusive scanout or a latency advantage.",
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
                "value": "On or On + Boost (choose manually)",
                "reason": "Driver LLM is Off so native Reflex controls the queue. ABSO reads the saved Reflex choice but never writes it. Boost keeps GPU clocks higher at a power cost; compare it with On for this workload.",
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
                "value": "Compare Performance (DX12) with DirectX 12 manually",
                "reason": "Epic recommends Performance mode for competitive play. Standard DX12 offers different graphics/upscaling options; compare frame times and image quality, then restart if prompted. ABSO preserves the renderer.",
            },
            {
                "category": "Graphics",
                "setting": "Multithreaded Rendering",
                "value": "On",
                "reason": "Use the game's default when this option is available; a local frame-time benefit has not been measured.",
            },
            {
                "category": "Graphics",
                "setting": "3D Resolution / DLSS",
                "value": "100%; compare DLSS Quality when available and GPU-bound",
                "reason": "Upscaling trades image detail for rendering cost. Start with Quality on supported RTX hardware, then compare lower presets only if needed; available options depend on the renderer.",
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
                "reason": "Reduces optional texture storage and memory demand; it does not guarantee removal of streaming hitches.",
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
            "Keeps driver LLM off for Reflex; choose Reflex On or On + Boost in-game."
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
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Windows HDR Off",
                "reason": "Windows output stays SDR; Fortnite's saved HDR and calibration values are preserved.",
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
            "Windows HDR Fortnite profile with a no-sync latency path. "
            "Keeps driver LLM off for manual Reflex; native game HDR is unverified."
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
                # Windows SDR brightness preference; not proof of native HDR
                # or a calibrated peak-luminance value for every display.
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
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Windows HDR On; native game HDR unverified",
                "reason": "ABSO sets Windows HDR and preserves Fortnite's HDR/calibration values. A saved UE HDR key does not establish native HDR output; Auto HDR and RTX HDR are not enabled by this lane.",
            },
            *self._common_in_game_settings(),
        ]


class FortniteGSyncHDRProfile(_FortniteBaseProfile):
    """Fortnite fullscreen-selection G-SYNC lane with Windows HDR.

    The driver owns the explicit refresh-minus-three ceiling; the engine uses
    Unlimited. Native HDR and actual exclusive/VRR presentation need runtime
    evidence. The existing mixed-refresh compatibility gate remains in place.
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
            "Windows HDR Fortnite G-SYNC lane with driver VSync and a "
            "refresh - 3 driver cap; native FPS is Unlimited. Choose Reflex "
            "On or On + Boost in-game. Native game HDR is unverified."
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
        # Mixed-refresh fallback remains the no-sync HDR lane; overlay-blocked
        # applies use the dedicated streaming sibling below.
        return "fortnite-hdr"

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        return "fortnite-gsync-hdr-capture"

    @property
    def allow_dual_limiter(self) -> bool:
        return False

    def _shared_overrides(self) -> dict[str, dict[str, Any]]:
        # Replace the no-sync base contract (reflex_no_sync / uncapped) with the
        # G-SYNC one. Reflex still owns the render queue (driver LLM off), but
        # VRR is enabled with NVCP VSync as the safety net and a refresh - 3 cap.
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                # Auto-detect refresh and cap below it for G-SYNC headroom.
                "auto_vrr_fps_cap": True,
                # Existing fullscreen VRR policy; a saved mode is not runtime proof.
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
                # Fortnite's UI uses discrete limits. Do not force a custom
                # native297 merely because it is used by another game.
                "auto_vrr_fps_cap": False,
                "frame_rate_limit": 0,
            },
        }

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": True,
                "advanced_color": True,  # Win11 24H2+ WCG pairing
                "auto_hdr": False,
                # Windows SDR brightness preference; not proof of native HDR
                # or a calibrated peak-luminance value for every display.
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
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": "Matches this lane's fullscreen VRR policy. Confirm actual G-SYNC engagement in-game; the saved mode does not prove exclusive presentation.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off (in-game)",
                "reason": "This lane uses driver VSync with its fullscreen VRR policy. The borderless Streaming lanes instead enable in-game VSync; runtime engagement still needs checking.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On or On + Boost (choose manually)",
                "reason": "Driver LLM is Off. ABSO checks the saved Reflex choice without changing it; Boost keeps clocks higher at a power cost and is not proven best for this workload.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Limit",
                "value": "Unlimited in-game; driver cap at refresh - 3",
                "reason": "The driver owns the explicit ceiling (297 at 300Hz); Fortnite's engine stays Unlimited. Reflex may pace lower. Neither the saved cap nor this checklist proves runtime VRR engagement.",
            },
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Windows HDR On; native game HDR unverified",
                "reason": "ABSO preserves the game's HDR and calibration settings. Windows HDR does not prove Fortnite native HDR; this lane does not enable Auto HDR or RTX HDR.",
            },
            {
                "category": "Graphics",
                "setting": "Rendering Mode",
                "value": "Compare Performance (DX12) with DirectX 12 manually",
                "reason": "Epic recommends Performance mode for competitive play; standard DX12 offers different graphics/upscaling choices. Compare frame times and image quality; ABSO preserves the renderer.",
            },
            {
                "category": "Graphics",
                "setting": "Multithreaded Rendering",
                "value": "On",
                "reason": "Use the game's default when available; no local frame-time improvement has been established.",
            },
            {
                "category": "Graphics",
                "setting": "3D Resolution / DLSS",
                "value": "100%; compare DLSS Quality when available and GPU-bound",
                "reason": "Trade image detail for rendering cost only when needed. Supported upscalers depend on the selected renderer.",
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
                "reason": "Reduces optional texture storage and memory demand; removing it is not a guaranteed stutter fix.",
            },
        ]


class _FortniteGSyncCaptureBase(FortniteGSyncHDRProfile):
    """Shared capture-compatible Fortnite G-SYNC presentation contract."""

    @property
    def is_capture_safe(self) -> bool:
        return True

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        return None

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> None:
        return None

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        return fso_overrides(self.executable_hints, disabled=False)

    @property
    def allow_dual_limiter(self) -> bool:
        return False

    def _shared_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._shared_overrides(),
            _STREAMING_WINDOWED_VRR_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        # Graphics and Reflex remain manual: their current UI choices were
        # observed, but their serialized keys are not a stable write contract.
        # These starting points do not promise a particular FPS on every PC.
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Windowed Fullscreen (borderless)",
                "reason": "ABSO sets the windowed G-SYNC path and keeps OBS, Medal, RTSS, and overlays available.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "On (in-game)",
                "reason": "NVIDIA recommends in-game VSync for windowed G-SYNC with Reflex. The driver FPS cap stays below refresh.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On or On + Boost (choose manually)",
                "reason": "ABSO leaves driver LLM off and only reads the saved Reflex choice. Reflex may pace below the driver cap; compare Boost's power cost and latency on the actual workload.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Limit",
                "value": "Unlimited in-game; driver cap at refresh - 3",
                "reason": "ABSO clears the engine cap and sets the NVIDIA VRR ceiling from the detected refresh rate, avoiding two matching explicit limiters.",
            },
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Windows HDR On; native game HDR unverified",
                "reason": "ABSO enables Windows HDR. It leaves the game's HDR output and brightness keys unchanged; those keys alone do not prove native HDR output.",
            },
            *[
                {"category": "Graphics", "setting": setting, "value": value, "reason": reason}
                for setting, value, reason in (
                    ("Rendering Mode", "DirectX 12; compare Performance (DX12) manually", "Standard DX12 supports the following quality/upscaling starting points. Performance mode reduces rendering features; compare it separately and restart if prompted. ABSO preserves the current renderer."),
                    ("Anti-Aliasing & Super Resolution", "NVIDIA DLSS Quality (set manually, when available)", "A clarity/performance starting point for supported RTX GPUs; use the game's supported alternatives on other hardware."),
                    ("Nanite Virtualized Geometry", "Off (set manually)", "Reduce geometry cost; change from the lobby because this option cannot be changed mid-match."),
                    ("Global Illumination", "Off (set manually)", "Disable Lumen lighting for this performance starting point; change from the lobby."),
                    ("Reflections", "Off (set manually)", "Disable Lumen and screen-space reflections to reduce rendering work."),
                    ("Hardware Ray Tracing", "Off (set manually)", "Changing hardware ray tracing requires a game restart."),
                    ("Shadows", "Off (set manually)", "Reduce rendering work and visual clutter."),
                    ("View Distance", "Medium (manual starting point)", "Balance scenery detail and performance; reduce to Near if more headroom is needed."),
                    ("Textures", "Medium (manual starting point)", "Balance image detail and memory use; adjust to the GPU's available memory."),
                    ("Effects / Post Processing", "Low / Low (set manually)", "Reduce effects cost while preserving room for capture."),
                    ("Dynamic 3D Resolution", "Off (set manually)", "Keep the chosen upscaling quality stable instead of chasing a dynamic resolution target."),
                    ("Frame Generation", "Off (set manually, if offered)", "Keep the baseline focused on rendered game frames and input responsiveness."),
                    ("Motion Blur", "Off (set manually)", "Keep camera motion and tracking clear."),
                )
            ],
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Fortnite streaming: Windowed Fullscreen, in-game VSync On, and "
            "Unlimited engine FPS with the NVIDIA refresh - 3 cap. Set Reflex "
            "On or On + Boost manually. OBS and overlays remain available.",
            "Graphics remain user-controlled: compare standard DX12 with "
            "Performance (DX12). For standard DX12, DLSS Quality, Medium "
            "textures/view distance and Low effects are starting points; "
            "reducing Nanite, lighting, ray tracing and shadows reduces rendering "
            "work. Restart after renderer or ray-tracing changes if prompted.",
        ]


class FortniteGSyncCaptureProfile(_FortniteGSyncCaptureBase):
    """Fortnite SDR streaming lane with borderless G-SYNC."""

    @property
    def profile_id(self) -> str:
        return "fortnite-gsync-capture"

    @property
    def display_name(self) -> str:
        return "Fortnite - GSYNC SDR Streaming"

    @property
    def description(self) -> str:
        return (
            "SDR capped G-SYNC lane on Fortnite's borderless path; preserves "
            "OBS, Medal, RTSS, and overlays and keeps game CPU/I/O priority at "
            "Normal. Uses in-game VSync and a driver cap; enable Reflex "
            "On or On + Boost manually."
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
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        patched: list[dict[str, str]] = []
        for row in super().get_in_game_settings():
            if row.get("setting") == "HDR Peak Brightness / Nits":
                continue
            if row.get("setting") == "HDR":
                row = {
                    **row,
                    "value": "Windows HDR Off",
                    "reason": "Windows output stays SDR; Fortnite's saved HDR and calibration values are preserved.",
                }
            patched.append(row)
        return patched


class FortniteGSyncHDRCaptureProfile(_FortniteGSyncCaptureBase):
    """Fortnite streaming lane with Windows HDR and borderless G-SYNC."""

    @property
    def profile_id(self) -> str:
        return "fortnite-gsync-hdr-capture"

    @property
    def display_name(self) -> str:
        return "Fortnite - GSYNC HDR Streaming"

    @property
    def description(self) -> str:
        return (
            "Windows HDR G-SYNC lane on Fortnite's borderless path; "
            "preserves OBS, Medal, RTSS, and overlays and keeps game CPU/I/O "
            "priority at Normal. Uses in-game VSync and a driver cap; enable "
            "Reflex On or On + Boost manually. Native game HDR is unverified."
        )

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        settings = super()._variant_overrides()
        # An accepted UE INI key does not establish Fortnite native HDR
        # support. Preserve the user's game HDR/calibration values; this lane
        # promises only the Windows HDR setting that ABSO can verify.
        settings.pop("FortniteConfigHandler", None)
        return settings

    def get_post_apply_notes(self) -> list[str]:
        return [
            *super().get_post_apply_notes(),
            "Streaming color: default to SDR Streaming for an SDR destination. "
            "Use HDR Streaming only when OBS/output color space or tone mapping "
            "is already intentionally configured; ABSO does not change OBS settings.",
        ]
