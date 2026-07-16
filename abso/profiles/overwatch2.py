"""Overwatch 2 profiles."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from abso.core.vrr import OW2_REFLEX_GSYNC_CAP_POLICY
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
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Overwatch"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Overwatch"),
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
        # OW2's G-SYNC variants deliberately layer a DRIVER v3 cap
        # (authoritative render pacer, 276 @ 300 Hz) with an in-game cap parked
        # ABOVE it (refresh - 3). OW2's engine cap governs simulation cadence,
        # not render pacing (CapFrameX per-frame testing, Oct 2025), and two
        # limiters fighting at the same value is the failure mode that
        # collapsed 1% lows under Reflex. Staggered caps still catch each
        # other when Settings_v0.ini drifts — OW2 rewrites the INI on exit and
        # on multi-monitor changes. The no-sync variant sets neither cap, so
        # this opt-in is harmless there.
        return True

    @staticmethod
    def _ow2_gsync_driver_cap_settings() -> dict[str, Any]:
        """Driver v3 FRL cap — the authoritative limiter on the G-SYNC lanes.

        Resolves to 276 @ 300 Hz (~8% below refresh). The policy name predates
        the Reflex-off switch (2026-07): the same frame-time-margin math that
        matched Reflex's auto cap is also the right ULL/G-SYNC headroom, so
        the cap VALUE is unchanged — only which limiter owns pacing changed.
        """
        return {
            "auto_vrr_fps_cap": True,
            "vrr_cap_policy": OW2_REFLEX_GSYNC_CAP_POLICY,
        }

    @staticmethod
    def _ow2_gsync_engine_cap_settings() -> dict[str, Any]:
        """In-game cap parked ABOVE the driver cap (refresh - 3 = 297 @ 300 Hz).

        OW2's engine cap only steadies simulation cadence; the driver v3 cap
        does the render pacing. Keeping them staggered stops limiter fights —
        per-frame CapFrameX testing (Oct 2025) showed in-game Reflex plus an
        active reachable cap collapsing 1% lows to ~half the average, which is
        why these lanes also expect the in-game Reflex toggle OFF.
        """
        return {
            "auto_vrr_fps_cap": True,
            "vrr_cap_policy": "refresh_minus_3",
            # Verify surfaces the manual in-game Reflex toggle (Off) as a
            # non-blocking step; ABSO cannot safely write the INI key.
            "expected_reflex_mode": 0,
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
    def _ow2_gsync_post_apply_notes() -> list[str]:
        return [
            (
                "OW2 manual: set NVIDIA Reflex to Off (driver ULL Ultra + the "
                "v3 cap own pacing on this lane); keep Dynamic Render Scale Off "
                "and Custom Render Scale 100% unless GPU-bound."
            )
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
        return "Latency-focused no-sync SDR profile (Reflex OFF, VSync OFF, VRR OFF)"

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
                # team fights, which is Reflex's measured win case (per-frame
                # OW2 testing shows no fps cost; CPU-bound lulls are neutral).
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
                # Uncapped play is where Reflex's backpressure removal pays;
                # its capped-lane pacing problems do not apply here.
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
                "setting": "NVIDIA Reflex Low Latency",
                "value": "Enabled + Boost — set the in-game toggle manually",
                "reason": (
                    "Uncapped no-sync play goes GPU-bound in team fights - exactly where "
                    "per-frame OW2 testing shows Reflex removes render-queue backpressure "
                    "at no measured fps cost; CPU-bound lulls are neutral. Reflex's pacing "
                    "problems only appear when it fights a reachable frame cap (the G-SYNC "
                    "lanes' scenario), which never happens on this uncapped lane."
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
                    "Redundant while Reflex is Enabled (Reflex supersedes it, per-frame "
                    "testing shows no difference) but harmless - and it keeps the render "
                    "queue shallow if Reflex is ever toggled off."
                ),
            },
            {
                "category": "Graphics",
                "setting": "Dynamic Render Scale",
                "value": "Off",
                "reason": "Avoid frametime variance from dynamic scaling.",
            },
            self._custom_render_scale_guidance(),
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Improves frame-time consistency in team fights.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            (
                "OW2 manual: Dynamic Render Scale Off, Custom Render Scale 100%; "
                "try 80-90 only if GPU-bound. Set NVIDIA Reflex to Enabled + Boost "
                "(uncapped no-sync is Reflex's measured win case)."
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
            "Latency-focused no-sync HDR profile (Reflex OFF, VSync OFF, VRR OFF). "
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

    Tear-free low-latency VRR profile. Driver ULL Ultra + a staggered driver
    v3 / in-game cap pair own the pacing (in-game Reflex OFF per per-frame
    CapFrameX findings), with NVCP VSync as safety net and per-app VRR enabled.

    Runs the same borderless windowed flip path as the capture-safe sibling;
    the difference is overlay handling, not the display path. This lane kills
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
                "preset": "ull_gsync",
                # Use NVIDIA's predefined OW2 profile to avoid executable binding conflicts.
                "profile_name": "Overwatch 2",
                # Driver v3 cap is the authoritative render pacer; the policy
                # resolves to 276 FPS on the reference 300 Hz path.
                **self._ow2_gsync_driver_cap_settings(),
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "ColorProfileSettingsHandler": {
                # Slightly below neutral (50) to compensate for DCI-P3 oversaturation in SDR.
                "digital_vibrance": 45,
            },
            "OW2ConfigHandler": {
                **self._borderless_ow2_settings(),
                # In-game cap parks ABOVE the driver cap (297 vs 276 @ 300 Hz)
                # and the in-game Reflex toggle is expected OFF — see
                # _ow2_gsync_engine_cap_settings for the measured rationale.
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
                    "This profile uses the same fast Win11 borderless G-SYNC path as "
                    "capture-safe, but keeps capture and overlay processes out for lower "
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
                "setting": "NVIDIA Reflex Low Latency",
                "value": "Off — ABSO already set driver LLM to Ultra; flip the in-game toggle to finish",
                "reason": "Per-frame CapFrameX testing (Oct 2025, RTX 4070 + G-SYNC) shows OW2's Reflex limiter fighting a reachable frame cap: identical average fps but 1% lows collapse to ~half the average with 2-10 ms frametime variance. Driver ULL Ultra + the driver v3 cap hold a flat frametime line instead. OW2's Reflex toggle is not safely writable from outside; manually set 'NVIDIA Reflex Low Latency' to 'Off' in Overwatch 2's Video settings once.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Auto staggered caps: driver v3 at 276, in-game at 297 (@300Hz; both scale by refresh)",
                "reason": "The NVIDIA driver v3 limiter (276 @ 300 Hz, ~8% under refresh) is the authoritative render pacer; the in-game cap parks at refresh - 3 (297) ABOVE it because OW2's engine cap only steadies simulation cadence. Staggering stops limiter fights — the failure mode behind Reflex's 1%-low collapse. No-sync OW2 lanes remain uncapped at 600.",
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
            self._custom_render_scale_guidance(),
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Reduces frame-time spikes during heavy ability usage.",
            },
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
    difference is overlay handling only. This lane kills overlay/capture apps
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
        base.update({
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
        })
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
                "preset": "ull_gsync",
                "profile_name": "Overwatch 2",
                # Driver v3 cap is the authoritative render pacer; the policy
                # resolves to 276 FPS on the reference 300 Hz path.
                **self._ow2_gsync_driver_cap_settings(),
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "OW2ConfigHandler": {
                **self._borderless_ow2_settings(),
                # In-game cap parks ABOVE the driver cap (297 vs 276 @ 300 Hz)
                # and the in-game Reflex toggle is expected OFF — see
                # _ow2_gsync_engine_cap_settings for the measured rationale.
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
                    "This profile uses the same fast Win11 borderless HDR G-SYNC path as "
                    "capture-safe, but keeps capture and overlay processes out for lower "
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
                "setting": "NVIDIA Reflex Low Latency",
                "value": "Off — ABSO already set driver LLM to Ultra; flip the in-game toggle to finish",
                "reason": "Per-frame CapFrameX testing (Oct 2025, RTX 4070 + G-SYNC) shows OW2's Reflex limiter fighting a reachable frame cap: identical average fps but 1% lows collapse to ~half the average with 2-10 ms frametime variance. Driver ULL Ultra + the driver v3 cap hold a flat frametime line instead. OW2's Reflex toggle is not safely writable from outside; manually set 'NVIDIA Reflex Low Latency' to 'Off' in Overwatch 2's Video settings once.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Auto staggered caps: driver v3 at 276, in-game at 297 (@300Hz; both scale by refresh)",
                "reason": "The NVIDIA driver v3 limiter (276 @ 300 Hz, ~8% under refresh) is the authoritative render pacer; the in-game cap parks at refresh - 3 (297) ABOVE it because OW2's engine cap only steadies simulation cadence. Staggering stops limiter fights — the failure mode behind Reflex's 1%-low collapse. No-sync OW2 lanes remain uncapped at 600.",
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
            self._custom_render_scale_guidance(),
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Reduces frame-time spikes during heavy ability usage.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return self._ow2_gsync_post_apply_notes()


class Overwatch2GSyncCaptureProfile(_Overwatch2BaseProfile):
    """Capture-safe Overwatch 2 VRR profile.

    Same borderless windowed G-SYNC flip path and settings payload as the
    strict :class:`Overwatch2GSyncProfile`; the difference is overlay
    handling. This lane keeps the capture / overlay / peripheral stack
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
        return "Overwatch 2 - GSYNC SDR Capture-Safe"

    @property
    def description(self) -> str:
        return (
            "Same VRR path as GSYNC SDR, but keeps OBS/Medal/RTSS and "
            "overlays alive at launch instead of killing them"
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
                "preset": "ull_gsync",
                "profile_name": "Overwatch 2",
                **self._ow2_gsync_driver_cap_settings(),
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "ColorProfileSettingsHandler": {
                "digital_vibrance": 45,
            },
            "OW2ConfigHandler": {
                **self._borderless_ow2_settings(),
                # Staggered caps + in-game Reflex expected OFF — see
                # _ow2_gsync_engine_cap_settings for the measured rationale.
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
                    "Capture-safe path: uses the same fast Win11 borderless G-SYNC path "
                    "as the overlay-free profile, while keeping Medal/Discord/OBS "
                    "overlays compatible."
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
                "value": "Off — ABSO already set driver LLM to Ultra; flip the in-game toggle to finish",
                "reason": "Per-frame CapFrameX testing (Oct 2025, RTX 4070 + G-SYNC) shows OW2's Reflex limiter fighting a reachable frame cap: identical average fps but 1% lows collapse to ~half the average with 2-10 ms frametime variance. Driver ULL Ultra + the driver v3 cap hold a flat frametime line instead. OW2's Reflex toggle is not safely writable from outside; manually set 'NVIDIA Reflex Low Latency' to 'Off' in Overwatch 2's Video settings once.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Auto staggered caps: driver v3 at 276, in-game at 297 (@300Hz; both scale by refresh)",
                "reason": "The NVIDIA driver v3 limiter (276 @ 300 Hz, ~8% under refresh) is the authoritative render pacer; the in-game cap parks at refresh - 3 (297) ABOVE it because OW2's engine cap only steadies simulation cadence. Staggering stops limiter fights — the failure mode behind Reflex's 1%-low collapse. No-sync OW2 lanes remain uncapped at 600.",
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
            self._custom_render_scale_guidance(),
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Reduces frame-time spikes during heavy team fights and capture load.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return self._ow2_gsync_post_apply_notes()


class Overwatch2GSyncHDRCaptureProfile(_Overwatch2BaseProfile):
    """Capture-safe HDR Overwatch 2 VRR profile.

    Same borderless windowed HDR G-SYNC path as the strict
    :class:`Overwatch2GSyncHDRProfile`; the difference is overlay handling
    only — see :class:`Overwatch2GSyncCaptureProfile` for the contract.
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
        return "Overwatch 2 - GSYNC HDR Capture-Safe"

    @property
    def description(self) -> str:
        return (
            "Same HDR VRR path as GSYNC HDR, but keeps OBS/Medal/RTSS and "
            "overlays alive at launch instead of killing them"
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
        base.update({
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
        })
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
                "preset": "ull_gsync",
                "profile_name": "Overwatch 2",
                **self._ow2_gsync_driver_cap_settings(),
                "global_vrr_mode": "fullscreen_and_windowed",
            },
            "OW2ConfigHandler": {
                **self._borderless_ow2_settings(),
                # Staggered caps + in-game Reflex expected OFF — see
                # _ow2_gsync_engine_cap_settings for the measured rationale.
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
                    "Capture-safe HDR path: uses the same fast Win11 borderless HDR "
                    "G-SYNC path as the overlay-free profile, while keeping "
                    "Medal/Discord/OBS overlays compatible."
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
                "value": "Off — ABSO already set driver LLM to Ultra; flip the in-game toggle to finish",
                "reason": "Per-frame CapFrameX testing (Oct 2025, RTX 4070 + G-SYNC) shows OW2's Reflex limiter fighting a reachable frame cap: identical average fps but 1% lows collapse to ~half the average with 2-10 ms frametime variance. Driver ULL Ultra + the driver v3 cap hold a flat frametime line instead. OW2's Reflex toggle is not safely writable from outside; manually set 'NVIDIA Reflex Low Latency' to 'Off' in Overwatch 2's Video settings once.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Auto staggered caps: driver v3 at 276, in-game at 297 (@300Hz; both scale by refresh)",
                "reason": "The NVIDIA driver v3 limiter (276 @ 300 Hz, ~8% under refresh) is the authoritative render pacer; the in-game cap parks at refresh - 3 (297) ABOVE it because OW2's engine cap only steadies simulation cadence. Staggering stops limiter fights — the failure mode behind Reflex's 1%-low collapse. No-sync OW2 lanes remain uncapped at 600.",
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
            self._custom_render_scale_guidance(),
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Reduces frame-time spikes during heavy team fights and capture load.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return self._ow2_gsync_post_apply_notes()
