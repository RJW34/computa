"""Overwatch 2 profiles."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import DisplayPathRequirements
from abso.profiles.profile_bases import (
    ReflexShooterBaseProfile,
    fso_overrides,
    merge_settings_map,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler

_logger = logging.getLogger(__name__)


class _Overwatch2BaseProfile(ReflexShooterBaseProfile):
    """Shared Overwatch 2 profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return ["Overwatch.exe"]

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        # Overwatch 2 uses DX11 in most competitive configurations.
        return "dx11"

    # ------------------------------------------------------------------
    # Dual-install Overwatch.exe discovery (Battle.net + Steam coexistence)
    # ------------------------------------------------------------------
    #
    # Users routinely have both a Battle.net OW2 install and a Steam OW2
    # install (different account regions, shared accounts, etc). They each
    # spawn an Overwatch.exe process from a DIFFERENT full path. Some of
    # the per-exe registry-based handlers we use match by name (IFEO,
    # NVIDIA profile_name binding) and naturally cover both. But the
    # AppCompatFlags\Layers FSO-disable token is matched by Windows on
    # the FULL PATH at process creation - a bare "Overwatch.exe" value
    # name is registered but doesn't apply.
    #
    # get_settings() must stay deterministic for snapshots and tray catalog
    # generation, so the profile declares only the stable executable name.
    # At apply/verify time resolve_runtime_settings() expands that entry to
    # any Battle.net and Steam paths visible on the current PC.

    @staticmethod
    def _battle_net_overwatch_path() -> str | None:
        """Resolve Battle.net's Overwatch install path.

        Tries (in order):
          1. Windows Uninstall registry entry written by Battle.net's installer,
             which is the canonical source and is present on every modern
             Battle.net install (DisplayIcon points right at Overwatch.exe).
          2. Legacy Blizzard Entertainment\\Overwatch InstallPath value, kept
             as a fallback for older / non-standard installs.
        """
        try:
            import winreg
        except ImportError:
            return None

        # 1) Uninstall key (canonical): DisplayIcon or InstallLocation
        for hive, sub in (
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Overwatch",
            ),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Overwatch",
            ),
        ):
            try:
                with winreg.OpenKey(hive, sub) as key:
                    # DisplayIcon is usually a literal Overwatch.exe path
                    try:
                        icon = winreg.QueryValueEx(key, "DisplayIcon")[0]
                        if icon and Path(icon).exists() and icon.lower().endswith("overwatch.exe"):
                            return str(Path(icon))
                    except OSError:
                        pass
                    # Fallback to InstallLocation + standard subdir
                    try:
                        install_location = winreg.QueryValueEx(key, "InstallLocation")[0]
                        for candidate in (
                            Path(install_location) / "_retail_" / "Overwatch.exe",
                            Path(install_location) / "Overwatch.exe",
                        ):
                            if candidate.exists():
                                return str(candidate)
                    except OSError:
                        pass
            except OSError:
                continue

        # 2) Legacy Blizzard Entertainment\\Overwatch InstallPath
        for hive, sub in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Blizzard Entertainment\Overwatch"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Blizzard Entertainment\Overwatch"),
        ):
            try:
                with winreg.OpenKey(hive, sub) as key:
                    install_path = winreg.QueryValueEx(key, "InstallPath")[0]
                    for candidate in (
                        Path(install_path) / "_retail_" / "Overwatch.exe",
                        Path(install_path) / "Overwatch.exe",
                    ):
                        if candidate.exists():
                            return str(candidate)
            except OSError:
                continue
        return None

    @staticmethod
    def _steam_libraries() -> list[Path]:
        """Return all Steam library roots known to the local Steam install."""
        libs: list[Path] = []
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam_path = Path(winreg.QueryValueEx(key, "SteamPath")[0])
                if steam_path.exists():
                    libs.append(steam_path)
                vdf = steam_path / "steamapps" / "libraryfolders.vdf"
                if vdf.exists():
                    text = vdf.read_text(encoding="utf-8", errors="ignore")
                    for match in re.finditer(r'"path"\s+"([^"]+)"', text):
                        candidate = Path(match.group(1).replace(r"\\", "\\"))
                        if candidate.exists() and candidate not in libs:
                            libs.append(candidate)
        except (OSError, ImportError):
            pass
        return libs

    @classmethod
    def _steam_overwatch_paths(cls) -> list[str]:
        """Find Overwatch.exe inside any Steam library."""
        hits: list[str] = []
        for lib in cls._steam_libraries():
            for sub in ("Overwatch 2", "Overwatch"):
                for candidate in (
                    lib / "steamapps" / "common" / sub / "_retail_" / "Overwatch.exe",
                    lib / "steamapps" / "common" / sub / "Overwatch.exe",
                ):
                    if candidate.exists():
                        hits.append(str(candidate))
        return hits

    @classmethod
    def _overwatch_install_paths(cls) -> list[str]:
        """All Overwatch.exe install paths visible on this machine, de-duplicated."""
        paths: list[str] = []
        bnet = cls._battle_net_overwatch_path()
        if bnet:
            paths.append(bnet)
        for steam_path in cls._steam_overwatch_paths():
            if steam_path not in paths:
                paths.append(steam_path)
        if paths:
            _logger.info("OW2 install paths discovered: %s", paths)
        return paths

    def _fso_dict(self, *, disabled: bool) -> dict[str, bool]:
        """Build the deterministic profile FSO declaration."""
        return fso_overrides(self.executable_hints, disabled=disabled)

    @staticmethod
    def _windowed_vrr_windows_settings() -> dict[str, Any]:
        """Windows flags required for OW2's modern borderless G-SYNC path."""
        return {
            "windowed_optimizations": True,
            "vrr_optimize": True,
        }

    @staticmethod
    def _borderless_ow2_settings() -> dict[str, Any]:
        """OW2 Settings_v0.ini keys for borderless/windowed fullscreen."""
        return {
            "window_mode": 1,
            "fullscreen_window": False,
            "fullscreen_window_enabled": False,
            "windowed_fullscreen": True,
        }

    def resolve_runtime_settings(
        self,
        handler_name: str,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        """Expand OW2 FSO settings to local install paths at apply/verify time."""
        if handler_name != "RegistrySettingsHandler":
            return settings

        raw_fso = settings.get("fullscreen_optimizations")
        if not isinstance(raw_fso, dict):
            return settings

        if "Overwatch.exe" not in raw_fso:
            return settings

        merged = settings.copy()
        expanded = {
            str(exe): bool(disabled)
            for exe, disabled in raw_fso.items()
            if isinstance(exe, str) and exe.strip()
        }
        desired_state = expanded["Overwatch.exe"]
        for full_path in self._overwatch_install_paths():
            expanded.setdefault(full_path, desired_state)
        merged["fullscreen_optimizations"] = expanded
        return merged

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.ow2_config import OW2ConfigHandler

        handlers = super().get_handlers()
        handlers.append(OW2ConfigHandler())
        return handlers

    @property
    def allow_dual_limiter(self) -> bool:
        # The native file is rewritten by OW2; a matching driver ceiling
        # remains a fallback if the game's saved cap drifts. Reflex controls
        # runtime pacing independently and may cap below both ceilings.
        return True

    @staticmethod
    def _ow2_gsync_driver_cap_settings() -> dict[str, Any]:
        """Static VRR safety ceiling; do not persist an observed Reflex cap."""
        return {
            "auto_vrr_fps_cap": True,
            "vrr_cap_policy": "refresh_minus_3",
        }

    @staticmethod
    def _ow2_gsync_engine_cap_settings() -> dict[str, Any]:
        """Use refresh - 3 in the native file and verify the manual Reflex step.

        NVIDIA documents Reflex pacing below refresh with G-SYNC + V-SYNC.
        It does not prescribe persisting 276 for every 300 Hz OW2 setup:
        https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/
        """
        return {
            "auto_vrr_fps_cap": True,
            "vrr_cap_policy": "refresh_minus_3",
            "expected_reflex_mode": 2,
        }

    @staticmethod
    def _ow2_gsync_cap_guidance() -> dict[str, str]:
        return {
            "category": "Display",
            "setting": "Frame Rate Cap",
            "value": "Auto static ceiling: refresh - 3 (297 at 300 Hz)",
            "reason": (
                "The saved native and driver caps are fallback ceilings, not a target FPS. "
                "With G-SYNC, VSync and Reflex active, runtime FPS may be lower; while it is, "
                "the higher saved ceilings do not limit it. A reading such as 276 is not "
                "itself saved-cap drift or a universal Reflex target. An added performance "
                "benefit from redundant caps has not been established."
            ),
        }

    @staticmethod
    def _custom_render_scale_guidance() -> dict[str, str]:
        return {
            "category": "Graphics",
            "setting": "Custom Render Scale",
            "value": "100% baseline; test 80-90% only if GPU-bound",
            "reason": (
                "ABSO keeps native internal resolution for clarity and consistent aim feel. "
                "Lower values can raise FPS on GPU-bound systems, but they are a manual "
                "quality tradeoff, not a universal latency win."
            ),
        }

    @staticmethod
    def _graphics_detail_guidance() -> list[dict[str, str]]:
        """Separate managed effects quality from manual visual preferences."""
        return [
            {
                "category": "Graphics",
                "setting": "Effects Detail",
                "value": "Low",
                "reason": "ABSO sets the saved effects detail to Low as a performance starting point.",
            },
            {
                "category": "Graphics",
                "setting": "Shadow Detail",
                "value": "Off or Low — choose manually",
                "reason": (
                    "Choose the shadow detail you prefer. Low is a visual preference, "
                    "not a demonstrated performance improvement over Off. ABSO preserves this choice."
                ),
            },
            {
                "category": "Graphics",
                "setting": "Local Reflections",
                "value": "Off — set manually",
                "reason": (
                    "Optional performance starting point that removes local reflections. "
                    "ABSO preserves this choice; saved-setting verification does not check it."
                ),
            },
            {
                "category": "Graphics",
                "setting": "Damage FX",
                "value": "Low — set manually",
                "reason": (
                    "Manual visual starting point; ABSO does not write or verify this option. "
                    "No FPS improvement is claimed without measurement."
                ),
            },
        ]

    @staticmethod
    def _ow2_gsync_post_apply_notes() -> list[str]:
        return [
            (
                "OW2 manual: set NVIDIA Reflex to Enabled + Boost; keep Dynamic Render Scale Off "
                "and Custom Render Scale 100% unless GPU-bound."
            ),
            (
                "OW2 saved cap: refresh - 3 (297 at 300 Hz) is a fallback ceiling. "
                "Reflex may pace runtime FPS below it; a lower reading alone is not saved-cap drift. "
                "This does not promise 297 FPS or a fixed 276 FPS Reflex target."
            ),
        ]

    def _base_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                # Keep HDR disabled by default to avoid SDR/HDR tone-mapping bugs.
                "hdr": False,
            },
            "OW2ConfigHandler": {
                "window_mode": 0,  # Fullscreen (Exclusive)
                "fullscreen_window": False,
                "fullscreen_window_enabled": True,
                "windowed_fullscreen": False,
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
        return merge_settings_map(self._base_overrides(), self._variant_overrides())


class Overwatch2Profile(_Overwatch2BaseProfile):
    """Overwatch 2 no-sync SDR profile.

    Latency-focused SDR path. Explicitly disables VRR/G-SYNC per-app so
    behavior is deterministic even when users have global VRR enabled. For
    the HDR counterpart see :class:`Overwatch2NoSyncHDRProfile`.
    """

    @property
    def profile_id(self) -> str:
        return "overwatch2"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - No Sync SDR"

    @property
    def description(self) -> str:
        return "Latency-focused no-sync SDR profile (VSync OFF, VRR OFF). Enable Reflex On + Boost in-game."

    @property
    def is_sdr_only(self) -> bool:
        # Explicit SDR variant. HDR is handled by Overwatch2NoSyncHDRProfile.
        return True

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Force true exclusive fullscreen at the OS layer so Windows cannot
        # silently shunt Overwatch into the composited FSO borderless path
        # if the in-game WindowMode ever drifts back to 1. Full launcher
        # paths are expanded only at apply/verify time so snapshots stay stable.
        return self._fso_dict(disabled=True)

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                # In-game Reflex ON + Boost: uncapped no-sync goes GPU-bound in
                # team fights, where native Reflex can reduce queue latency.
                # Boost tradeoffs still require comparison on this machine.
                # Driver preset keeps LLM off so the engine owns the queue,
                # and disables VSync + VRR for pure no-sync.
                "preset": "reflex_no_sync",
                # Use NVIDIA's predefined OW2 profile to avoid executable binding conflicts.
                "profile_name": "Overwatch 2",
                # Enforce global no-sync state for deterministic No-SYNC profile transitions.
                "global_vrr_mode": "off",
            },
            "OW2ConfigHandler": {
                # No-sync: exclusive fullscreen for cleanest presentation path.
                "window_mode": 0,
                # Uncapped no-sync path (600 = OW2 max).
                "frame_rate_cap": 600,
                # Verify confirms the manual in-game Reflex step (On + Boost).
                # Native Reflex handles render-queue backpressure; compare
                # latency and FPS on this setup when choosing Boost.
                "expected_reflex_mode": 2,
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
                "reason": "No-sync mode avoids the VSync/VRR queueing path and accepts tearing.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex",
                "value": "Enabled + Boost — set the in-game toggle manually",
                "reason": (
                    "Reflex reduces render-queue latency, especially when GPU-bound. "
                    "Boost keeps GPU clocks elevated and may increase power use or "
                    "reduce FPS; compare Enabled alone on this machine."
                ),
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Uncapped (600)",
                "reason": "No-sync profile: uncapped FPS reduces frame time when the game can sustain it.",
            },
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": (
                    "Requests the game's lower-buffering path. Its interaction with "
                    "Reflex should be checked with frame-time and latency measurements."
                ),
            },
            {
                "category": "Graphics",
                "setting": "Dynamic Render Scale",
                "value": "Off",
                "reason": "Avoid frametime variance from dynamic scaling.",
            },
            self._custom_render_scale_guidance(),
            *self._graphics_detail_guidance(),
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            (
                "OW2 manual: Dynamic Render Scale Off, Custom Render Scale 100%; "
                "try 80-90 only if GPU-bound. Set NVIDIA Reflex to Enabled + Boost "
                "and compare Enabled alone if Boost reduces performance."
            )
        ]


class Overwatch2NoSyncHDRProfile(Overwatch2Profile):
    """Overwatch 2 no-sync HDR profile.

    Same no-sync contract as
    :class:`Overwatch2Profile`, but with OW2's native HDR pipeline enabled
    for OLED / Mini-LED displays. VRR remains off per the no-sync policy:
    HDR here is a color/dynamic-range decision, not a sync decision.
    """

    @property
    def profile_id(self) -> str:
        return "overwatch2-hdr"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - No Sync HDR"

    @property
    def description(self) -> str:
        return (
            "Latency-focused no-sync HDR profile (VSync OFF, VRR OFF). Enable Reflex On + Boost in-game. "
            "Native HDR for OLED / Mini-LED displays."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _base_overrides(self) -> dict[str, dict[str, Any]]:
        # Start from the shared OW2 base, then flip the two HDR knobs and add
        # a native ICC color profile. We deliberately keep every other no-sync
        # behavior identical to the SDR variant.
        base = super()._base_overrides()
        ow2_base = dict(base.get("OW2ConfigHandler", {}))
        ow2_base["hdr"] = True  # Native HDR tone mapping in-engine
        base["OW2ConfigHandler"] = ow2_base
        base["WindowsSettingsHandler"] = {
            "hdr": True,
            "advanced_color": True,  # WCG on — required on Win11 24H2+ split stack
            "auto_hdr": False,  # OW2 has native HDR; don't layer Auto HDR on top
            # Paper-white ≈ 200 nits under HDR on OLED / Mini-LED. Driver
            # installs reset this slider; asserting it here restores the
            # correct SDR-in-HDR tone-mapping on every profile apply.
            "sdr_white_level_nits": 200,
        }
        base["ColorProfileSettingsHandler"] = {
            "icc_profile": "native",
            "digital_vibrance": 50,
            "show_osd_guidance": True,
            "game_type": "competitive_fps",
        }
        # Disable Auto Color Management on wide-gamut displays. Windows 11
        # 24H2+ can silently re-enable ACM after display re-enumeration
        # (NVIDIA driver installs trigger this), producing a washed-out
        # clamped-to-sRGB desktop. Gaming HDR profiles want un-clamped.
        existing_graphics = dict(base.get("GraphicsSettingsHandler", {}))
        existing_graphics["disable_auto_color_management"] = True
        base["GraphicsSettingsHandler"] = existing_graphics
        return base

    def get_in_game_settings(self) -> list[dict[str, str]]:
        # Start from the SDR no-sync guidance, then append HDR-specific
        # calibration rows so the user has one authoritative list.
        entries = list(super().get_in_game_settings())
        entries.extend(
            [
                {
                    "category": "Display",
                    "setting": "HDR Mode",
                    "value": "On",
                    "reason": "Native HDR output for OLED / Mini-LED displays.",
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
            ]
        )
        return entries


class Overwatch2GSyncProfile(_Overwatch2BaseProfile):
    """Overwatch 2 G-SYNC profile.

    VRR profile with native Reflex, NVCP VSync as a safety net, and matching
    refresh - 3 static caps. Reflex may dynamically pace below the ceiling.

    Runs the same borderless windowed flip path as the capture-safe sibling;
    the differences are overlay handling and game process priority. This lane kills
    overlay/capture apps (OBS, Medal, RTSS, Steam/Discord overlays, NVIDIA
    Share) at apply and game launch for frame-time headroom, and requires an
    overlay-free display path at apply time. The Discord app itself is
    never killed, so Discord screen sharing keeps working here — use the
    capture-safe sibling only when you want overlay/capture *apps* kept alive.
    """

    @property
    def profile_id(self) -> str:
        return "overwatch2-gsync"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - GSYNC SDR"

    @property
    def description(self) -> str:
        return (
            "Low latency VRR profile (VSync safety net, G-SYNC ON). "
            "Kills overlay/capture apps (OBS, Medal, RTSS, overlays) at launch "
            "for frame-time headroom; Discord screen share still works."
        )

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Overlay-free G-SYNC uses OW2's faster modern borderless flip path on
        # this Win11/Reflex setup. Clear any stale FSO-disable entry left by
        # the former exclusive profile so Windows can use the optimized path.
        # Full launcher paths are expanded only at apply/verify time.
        return self._fso_dict(disabled=False)

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
            "WindowsSettingsHandler": self._windowed_vrr_windows_settings(),
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
                "disable_mpo": False,
                # Assert ACM off to match the SDR capture sibling — otherwise
                # switching between the strict and capture SDR lanes flips ACM
                # state. Win11 24H2+ can silently re-enable ACM after display
                # re-enumeration, clamping wide-gamut SDR to sRGB.
                "disable_auto_color_management": True,
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                # Use NVIDIA's predefined OW2 profile to avoid executable binding conflicts.
                "profile_name": "Overwatch 2",
                # Static safety ceiling (297 FPS at 300 Hz).
                **self._ow2_gsync_driver_cap_settings(),
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "ColorProfileSettingsHandler": {
                # Slightly below neutral (50) to compensate for DCI-P3 oversaturation in SDR.
                "digital_vibrance": 45,
            },
            "OW2ConfigHandler": {
                **self._borderless_ow2_settings(),
                # Match the driver safety ceiling; Reflex may pace below it.
                **self._ow2_gsync_engine_cap_settings(),
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Borderless / Windowed Fullscreen",
                "reason": (
                    "This profile uses the same Win11 borderless G-SYNC path as the "
                    "Streaming sibling, but keeps capture and overlay processes out for lower "
                    "frame-time noise."
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
                "setting": "NVIDIA Reflex",
                "value": "Enabled + Boost — set the in-game toggle manually",
                "reason": "Enable native Reflex for queue control; the profile requests driver LLM Off. With G-SYNC and VSync active, Reflex may pace below the static cap. ABSO cannot safely write the Reflex toggle; verify it in-game. Boost can cost power or FPS, so compare Enabled alone if needed.",
            },
            self._ow2_gsync_cap_guidance(),
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
            self._custom_render_scale_guidance(),
            *self._graphics_detail_guidance(),
        ]

    def get_post_apply_notes(self) -> list[str]:
        return self._ow2_gsync_post_apply_notes()


class Overwatch2GSyncHDRProfile(_Overwatch2BaseProfile):
    """Overwatch 2 G-SYNC + HDR profile.

    Tear-free low-latency VRR with native HDR enabled. Designed for
    HDR-capable monitors (OLED, Mini-LED). Uses native color space
    instead of sRGB clamp.

    OW2's HDR implementation works well on OLED with proper in-game
    calibration (Paper White Nits, Max Nits). Auto HDR is disabled
    since OW2 has native HDR support.

    Same borderless windowed flip path as the HDR capture-safe sibling; the
    differences are overlay handling and game process priority. This lane kills overlay/capture apps
    at apply and game launch and requires an overlay-free display path. The
    Discord app itself is never killed, so Discord screen sharing keeps
    working here.
    """

    @property
    def profile_id(self) -> str:
        return "overwatch2-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - GSYNC HDR"

    @property
    def description(self) -> str:
        return (
            "Tear-free low latency VRR with native HDR (OLED/Mini-LED). "
            "Kills overlay/capture apps at launch for frame-time headroom; "
            "Discord screen share still works."
        )

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Native HDR on this Win11/Reflex setup is faster on OW2's modern
        # borderless flip path than on the former exclusive/fullscreen-only
        # lane. Clear stale FSO-disable entries so the optimized path can
        # engage after switching away from old strict builds.
        # Full launcher paths are expanded only at apply/verify time.
        return self._fso_dict(disabled=False)

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
        base.update(
            {
                "WindowsSettingsHandler": {
                    "hdr": True,
                    "advanced_color": True,  # Win11 24H2+ WCG pairing
                    "auto_hdr": False,
                    # Paper-white ≈ 200 nits under HDR on OLED / Mini-LED.
                    # Driver installs reset this slider; asserting it here
                    # restores the correct SDR-in-HDR tone-mapping.
                    "sdr_white_level_nits": 200,
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
            }
        )
        return base

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": self._windowed_vrr_windows_settings(),
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
                "disable_mpo": False,
                # Assert ACM off — see _base_overrides comment.
                "disable_auto_color_management": True,
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Overwatch 2",
                # Static safety ceiling (297 FPS at 300 Hz).
                **self._ow2_gsync_driver_cap_settings(),
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "OW2ConfigHandler": {
                **self._borderless_ow2_settings(),
                # Match the driver safety ceiling; Reflex may pace below it.
                # To override, set
                # ``profile_overrides.overwatch2-gsync-hdr.ow2_config`` in
                # abso.yaml: ``auto_vrr_fps_cap: false`` plus an explicit
                # ``frame_rate_cap: <int>``.
                **self._ow2_gsync_engine_cap_settings(),
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Borderless / Windowed Fullscreen",
                "reason": (
                    "This profile uses the same Win11 borderless HDR G-SYNC path as the "
                    "Streaming sibling, but keeps capture and overlay processes out for lower "
                    "frame-time noise."
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
                "setting": "NVIDIA Reflex",
                "value": "Enabled + Boost — set the in-game toggle manually",
                "reason": "Enable native Reflex for queue control; the profile requests driver LLM Off. With G-SYNC and VSync active, Reflex may pace below the static cap. ABSO cannot safely write the Reflex toggle; verify it in-game. Boost can cost power or FPS, so compare Enabled alone if needed.",
            },
            self._ow2_gsync_cap_guidance(),
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
            self._custom_render_scale_guidance(),
            *self._graphics_detail_guidance(),
        ]

    def get_post_apply_notes(self) -> list[str]:
        return self._ow2_gsync_post_apply_notes()


class Overwatch2GSyncCaptureProfile(_Overwatch2BaseProfile):
    """Capture-safe Overwatch 2 VRR profile.

    Same borderless windowed G-SYNC flip path as the strict
    :class:`Overwatch2GSyncProfile`, with Normal game CPU/I/O priority and
    capture retention. This lane keeps the capture / overlay / peripheral stack
    (OBS, Medal, RTSS, Steam/Discord overlays, NVIDIA Share, G HUB, iCUE)
    alive at apply and game launch, and skips the strict lane's
    overlay-free display-path gate. Note: Discord screen sharing works on
    BOTH lanes (the Discord app is never killed anywhere); pick this lane
    when you want overlay/capture apps themselves left running.
    """

    @property
    def is_capture_safe(self) -> bool:
        # The whole point of this lane: keep the capture / overlay /
        # peripheral stack alive. BaseProfile.launch_process_killset
        # filters CAPTURE_ALLOWED_IMAGES out of the killset when this
        # returns True so Medal, Discord overlay helpers, RTSS, OBS,
        # NVIDIA Share / Overlay, G HUB, and iCUE are not stopped.
        return True

    @property
    def profile_id(self) -> str:
        return "overwatch2-gsync-capture"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - GSYNC SDR Streaming"

    @property
    def description(self) -> str:
        return (
            "Borderless SDR G-SYNC streaming lane that preserves OBS, Medal, "
            "RTSS, and overlays and keeps game CPU/I/O priority at Normal so "
            "capture is not starved."
        )

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Capture lane intentionally runs the borderless FSO path. Clear any
        # per-exe FSO-disable flag a previous exclusive profile may have left
        # behind, so borderless G-SYNC can engage cleanly. Cleared for both
        # Full launcher paths are expanded only at apply/verify time.
        return self._fso_dict(disabled=False)

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": self._windowed_vrr_windows_settings(),
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
                "disable_mpo": False,
                # SDR capture lane still wants ACM off — OBS/capture clients
                # expect un-clamped source colors for their own color pipeline.
                "disable_auto_color_management": True,
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Overwatch 2",
                **self._ow2_gsync_driver_cap_settings(),
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "ColorProfileSettingsHandler": {
                "digital_vibrance": 45,
            },
            "OW2ConfigHandler": {
                **self._borderless_ow2_settings(),
                # Static native ceiling plus a manual Reflex verification step.
                **self._ow2_gsync_engine_cap_settings(),
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 2,
                "io_priority": 2,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Borderless / Windowed Fullscreen",
                "reason": (
                    "Streaming path: uses the borderless G-SYNC presentation "
                    "path while keeping OBS, Medal, RTSS, and overlays available."
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
                "setting": "NVIDIA Reflex",
                "value": "Enabled + Boost — set the in-game toggle manually",
                "reason": "Enable native Reflex for queue control; the profile requests driver LLM Off. With G-SYNC and VSync active, Reflex may pace below the static cap. ABSO cannot safely write the Reflex toggle; verify it in-game. Boost can cost power or FPS, so compare Enabled alone if needed.",
            },
            self._ow2_gsync_cap_guidance(),
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": "Maintains low queue depth on the streaming presentation path.",
            },
            {
                "category": "Graphics",
                "setting": "Dynamic Render Scale",
                "value": "Off",
                "reason": "Avoid frame pacing swings while recording/clipping.",
            },
            self._custom_render_scale_guidance(),
            *self._graphics_detail_guidance(),
        ]

    def get_post_apply_notes(self) -> list[str]:
        return self._ow2_gsync_post_apply_notes()


class Overwatch2GSyncHDRCaptureProfile(_Overwatch2BaseProfile):
    """Capture-safe HDR Overwatch 2 VRR profile.

    Same borderless windowed HDR G-SYNC path as the strict
    :class:`Overwatch2GSyncHDRProfile`, with Normal game CPU/I/O priority and
    capture retention — see :class:`Overwatch2GSyncCaptureProfile` for the contract.
    """

    @property
    def is_capture_safe(self) -> bool:
        # See Overwatch2GSyncCaptureProfile.is_capture_safe.
        return True

    @property
    def profile_id(self) -> str:
        return "overwatch2-gsync-hdr-capture"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - GSYNC HDR Streaming"

    @property
    def description(self) -> str:
        return (
            "Borderless HDR G-SYNC streaming lane that preserves OBS, Medal, "
            "RTSS, and overlays and keeps game CPU/I/O priority at Normal so "
            "capture is not starved."
        )

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # HDR capture lane: intentionally borderless FSO. Clear any stale FSO
        # disable left by a prior exclusive-HDR apply so the composited HDR
        # path can engage without fighting an OS-level exclusive lock.
        # Full launcher paths are expanded only at apply/verify time.
        return self._fso_dict(disabled=False)

    def _base_overrides(self) -> dict[str, dict[str, Any]]:
        base = super()._base_overrides()
        base.update(
            {
                "WindowsSettingsHandler": {
                    "hdr": True,
                    "advanced_color": True,  # Win11 24H2+ WCG pairing
                    "auto_hdr": False,
                    # Match the strict-HDR lane's paper-white.
                    "sdr_white_level_nits": 200,
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
            }
        )
        return base

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": self._windowed_vrr_windows_settings(),
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
                "disable_mpo": False,
                # HDR capture lane still wants ACM off to keep un-clamped
                # wide-gamut going to the capture source.
                "disable_auto_color_management": True,
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Overwatch 2",
                **self._ow2_gsync_driver_cap_settings(),
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "OW2ConfigHandler": {
                **self._borderless_ow2_settings(),
                # Static native ceiling plus a manual Reflex verification step.
                **self._ow2_gsync_engine_cap_settings(),
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 2,
                "io_priority": 2,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Borderless / Windowed Fullscreen",
                "reason": (
                    "Streaming HDR path: uses the borderless HDR G-SYNC "
                    "presentation path while keeping OBS, Medal, RTSS, and "
                    "overlays available."
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
                "setting": "NVIDIA Reflex",
                "value": "Enabled + Boost — set the in-game toggle manually",
                "reason": "Enable native Reflex for queue control; the profile requests driver LLM Off. With G-SYNC and VSync active, Reflex may pace below the static cap. ABSO cannot safely write the Reflex toggle; verify it in-game. Boost can cost power or FPS, so compare Enabled alone if needed.",
            },
            self._ow2_gsync_cap_guidance(),
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": "Maintains low queue depth on the streaming presentation path.",
            },
            {
                "category": "Display",
                "setting": "HDR Mode",
                "value": "On",
                "reason": "Native HDR output for OLED/Mini-LED displays on the streaming path.",
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
            self._custom_render_scale_guidance(),
            *self._graphics_detail_guidance(),
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            *self._ow2_gsync_post_apply_notes(),
            "Streaming color: default to SDR Streaming for an SDR destination. "
            "Use HDR Streaming only when OBS/output color space or tone mapping "
            "is already intentionally configured; ABSO does not change OBS settings.",
        ]
