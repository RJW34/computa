"""Productivity profiles.

Two siblings:
- ``productivity``     : SDR baseline. Turns Windows HDR / Auto HDR off so a
                         prior HDR gaming profile does not leak into daily
                         desktop work. Suitable for any panel.
- ``productivity-hdr`` : Opt-in HDR/OLED variant. Forces Windows HDR + WCG +
                         ACM off + native ICC for users on OLED / Mini-LED who
                         want the HDR desktop look applied via ABSO.

Both profiles target multi-monitor coding and browsing work:
- system responsiveness, smooth scrolling, snappy app launching
- background services intentionally left running
- VRR on for smooth scrolling
- no aggressive latency tuning (no LLM, no Prefer Max Performance)
- no power-plan switching (PowerSettingsHandler intentionally excluded)
- no mouse-feel changes (MouseSettingsHandler intentionally excluded)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abso.profiles.base import BaseProfile
from abso.profiles.profile_bases import (
    NEUTRAL_VIBRANCE,
    SDR_WIDE_GAMUT_VIBRANCE,
    merged_handler_settings,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


_PRODUCTIVITY_EXECUTABLES: list[str] = [
    "Code.exe",            # VS Code
    "devenv.exe",          # Visual Studio
    "chrome.exe",          # Chrome
    "firefox.exe",         # Firefox
    "msedge.exe",          # Edge
    "WindowsTerminal.exe",  # Windows Terminal
    "idea64.exe",          # IntelliJ IDEA
]


class _ProductivityBaseProfile(BaseProfile):
    """Shared productivity defaults for the SDR + HDR siblings.

    Subclasses only need to override the HDR/color block.
    """

    @property
    def optimization_target(self) -> str:
        return "productivity"

    @property
    def executable_hints(self) -> list[str]:
        return list(_PRODUCTIVITY_EXECUTABLES)

    @property
    def nvidia_profile_name(self) -> str | None:
        # SDR + HDR siblings share executable hints, so each must finalize a
        # distinct, stable NVIDIA profile name (enforced by
        # test_overlapping_nvidia_profile_families_have_stable_driver_identity).
        # Subclasses override.
        return None

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.color import ColorProfileSettingsHandler
        from abso.settings.display_range import DisplayColorRangeHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        # Minimal handlers — no power handler (would switch power plans) and
        # no mouse handler (changing desktop mouse feel outside a game is out
        # of scope for a productivity profile).
        return [
            WindowsSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            GraphicsSettingsHandler(),
            ColorProfileSettingsHandler(),
            DisplayColorRangeHandler(),
        ]

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        """Settings every productivity sibling agrees on."""
        return {
            "WindowsSettingsHandler": {
                # Game features — keep enabled for compatibility.
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                # HAGS ON helps with smooth desktop compositing.
                "hags": True,
                "windowed_optimizations": True,
                # VRR ON for smooth scrolling.
                "vrr_optimize": True,
            },
            # PowerSettingsHandler intentionally excluded — keep current power plan.
            "RegistrySettingsHandler": {
                # Allow more background tasks — we want indexing, search, etc.
                "system_responsiveness": 20,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 2,
                    "scheduling_category": "Medium",
                },
            },
            "NvidiaSettingsHandler": {
                # Balanced — smooth visuals with adaptive vsync. No Low Latency
                # Mode and no Prefer Max Performance: productivity wants lower
                # heat/noise and default driver pacing, not latency-favoring
                # clocks.
                "low_latency_mode": "off",
                "power_management": "adaptive",
                "vsync": "adaptive",
                "max_frame_rate": "off",
                "shader_cache": "unlimited",
                "threaded_optimization": "auto",
                "vrr_app_override": "allow",
            },
            "GraphicsSettingsHandler": {
                # Keep FSO enabled — works well with modern apps.
                "disable_global_fso": False,
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        return merged_handler_settings(self, handler_name)


class ProductivityProfile(_ProductivityBaseProfile):
    """SDR productivity baseline - forces Windows HDR / Auto HDR off.

    HDR is an opinionated, monitor-specific setting. The default
    productivity profile is the SDR lane and explicitly returns Windows
    HDR/Auto HDR to off so an HDR gaming profile does not leak into daily
    desktop work. If you want the HDR/OLED productivity experience, use
    ``productivity-hdr`` instead.
    """

    @property
    def profile_id(self) -> str:
        return "productivity"

    @property
    def display_name(self) -> str:
        return "Desktop / Productivity"

    @property
    def description(self) -> str:
        return (
            "Multi-monitor browsing and coding (SDR). Keeps background "
            "services running, adaptive vsync, VRR for smooth scrolling. "
            "Turns Windows HDR off - use productivity-hdr for the HDR lane."
        )

    @property
    def is_sdr_only(self) -> bool:
        # Treat this as SDR for the linter so any future HDR-affecting
        # settings get rejected if accidentally added here.
        return True

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Productivity (SDR)"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        # SDR additions: explicit hdr=False so a previously-HDR profile apply
        # does NOT leak HDR-on state into this profile. ICC + vibrance follow
        # the SDR-on-wide-gamut compensation convention used by every other
        # SDR profile.
        return {
            "WindowsSettingsHandler": {
                "hdr": False,
                "auto_hdr": False,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": SDR_WIDE_GAMUT_VIBRANCE,
                "show_osd_guidance": True,
                "game_type": "productivity",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "=== DISPLAY SETTINGS ===",
                "setting": "HDR",
                "value": "OFF (this profile turns Windows HDR / Auto HDR off)",
                "reason": (
                    "ABSO's default productivity profile is the SDR desktop lane. "
                    "Use productivity-hdr if you want ABSO to enable HDR + WCG + "
                    "native ICC for an OLED/Mini-LED desktop."
                ),
            },
            {
                "category": "Display Settings",
                "setting": "Refresh Rate",
                "value": "Maximum available",
                "reason": "Higher refresh = smoother scrolling and cursor movement.",
            },
            {
                "category": "Display Settings",
                "setting": "Night Light",
                "value": "Scheduled (evening hours)",
                "reason": "Reduces blue light for late-night coding.",
            },
            {
                "category": "Multi-Monitor",
                "setting": "VRR / G-Sync",
                "value": "Enable for windowed and full screen mode",
                "reason": "Smooth scrolling in browsers and editors.",
            },
            {
                "category": "App Settings",
                "setting": "Hardware acceleration",
                "value": "ON in browsers and editors",
                "reason": "Enables GPU rendering for smoother scrolling.",
            },
        ]


class ProductivityHDRProfile(_ProductivityBaseProfile):
    """HDR productivity variant - OLED / Mini-LED with Windows HDR forced on.

    Use this when your primary is a wide-gamut HDR-capable panel and you
    want ABSO to assert the full HDR composition stack (HDR + WCG + native
    ICC + ACM off, paper-white at 200 nits). This matches the convention
    used by the gaming HDR profiles.
    """

    @property
    def profile_id(self) -> str:
        return "productivity-hdr"

    @property
    def display_name(self) -> str:
        return "Desktop / Productivity (HDR)"

    @property
    def description(self) -> str:
        return (
            "Multi-monitor browsing and coding with Windows HDR + WCG forced "
            "on for OLED / Mini-LED desktop comfort. SDR content composited "
            "into HDR surface."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Productivity (HDR)"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                # HDR enabled for OLED.
                "hdr": True,
                # Wide Color Gamut ON - required on Win11 24H2+ to pair with
                # HDR so SDR desktop content renders in OLED's wide gamut
                # rather than sRGB.
                "advanced_color": True,
                "auto_hdr": False,
                # Paper-white starting point under HDR on OLED. Driver
                # installs reset this slider; asserting it here keeps the SDR
                # desktop looking right on every profile apply.
                "sdr_white_level_nits": 200,
            },
            "GraphicsSettingsHandler": {
                "disable_auto_color_management": True,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": NEUTRAL_VIBRANCE,
                "show_osd_guidance": True,
                "game_type": "productivity",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "=== DISPLAY SETTINGS ===",
                "setting": "HDR",
                "value": "ON (this profile asserts it)",
                "reason": "OLED panels excel at HDR. Profile keeps it on at the OS level.",
            },
            {
                "category": "Display Settings",
                "setting": "SDR content brightness",
                "value": "200 nits baseline; tune to taste (240-280 if too dim)",
                "reason": (
                    "Settings > System > Display > HDR > SDR content brightness. "
                    "Driver installs reset this; the profile re-asserts 200 nits."
                ),
            },
            {
                "category": "Display Settings",
                "setting": "Refresh Rate",
                "value": "Maximum available",
                "reason": "Higher refresh = smoother scrolling and cursor movement.",
            },
            {
                "category": "Multi-Monitor",
                "setting": "Mixed refresh rate monitors",
                "value": "HAGS ON",
                "reason": "HAGS helps with mixed refresh multi-monitor setups.",
            },
            {
                "category": "Multi-Monitor",
                "setting": "VRR / G-Sync",
                "value": "Enable for windowed and full screen mode",
                "reason": "Smooth scrolling in browsers and editors.",
            },
            {
                "category": "OLED Care",
                "setting": "Screen timeout",
                "value": "5-10 minutes",
                "reason": "Prevent burn-in from static UI elements.",
            },
            {
                "category": "OLED Care",
                "setting": "Dark mode",
                "value": "Enable in Windows and apps",
                "reason": "Reduces OLED power draw and potential burn-in from bright backgrounds.",
            },
            {
                "category": "OLED Care",
                "setting": "Pixel refresh",
                "value": "Run periodically per monitor manufacturer",
                "reason": "Most OLED monitors have built-in pixel refresh cycles.",
            },
            {
                "category": "App Settings",
                "setting": "Hardware acceleration",
                "value": "ON in browsers and editors",
                "reason": "Enables GPU rendering for smoother scrolling.",
            },
        ]


# Back-compat alias for any caller still importing the old class name.
ProductivityOLEDProfile = ProductivityHDRProfile
