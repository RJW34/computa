"""Windows gaming settings handler."""

from __future__ import annotations

import ctypes
import logging
import time
import winreg
from ctypes import wintypes
from typing import Any

from abso.core.models import Issue
from abso.settings import MONITOR_DATA_STORE_KEY as _MONITOR_DATA_STORE_KEY
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# Windows display mode constants
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000
ENUM_CURRENT_SETTINGS = -1
DISP_CHANGE_SUCCESSFUL = 0
CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002

# SetDisplayConfig flags. Combination used to re-apply the currently-saved
# database — forces DWM to re-read MonitorDataStore after a silent-no-op
# SET_HDR_STATE on Win11 25H2+, which otherwise leaves the live path in SDR
# even though HDREnabled=1 in the registry.
_SDC_TOPOLOGY_INTERNAL = 0x00000001
_SDC_TOPOLOGY_CLONE = 0x00000002
_SDC_TOPOLOGY_EXTEND = 0x00000004
_SDC_TOPOLOGY_EXTERNAL = 0x00000008
_SDC_USE_DATABASE_CURRENT = (
    _SDC_TOPOLOGY_INTERNAL | _SDC_TOPOLOGY_CLONE | _SDC_TOPOLOGY_EXTEND | _SDC_TOPOLOGY_EXTERNAL
)
_SDC_APPLY = 0x00000080

# CCD API constants for HDR control
QDC_ONLY_ACTIVE_PATHS = 0x00000002
DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9
DISPLAYCONFIG_DEVICE_INFO_SET_ADVANCED_COLOR_STATE = 10
DISPLAYCONFIG_DEVICE_INFO_GET_SDR_WHITE_LEVEL = 11  # SDR paper white under HDR
# Windows 11 24H2+ introduced new types that separate HDR from WCG (Wide Color Gamut).
# Type 10 now toggles WCG on 24H2, NOT HDR. Use type 16 for HDR on 24H2+.
DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO_2 = 15  # 24H2+
DISPLAYCONFIG_DEVICE_INFO_SET_HDR_STATE = 16  # 24H2+
DISPLAYCONFIG_DEVICE_INFO_SET_WCG_STATE = 17  # 24H2+
DISPLAYCONFIG_DEVICE_INFO_SET_SDR_WHITE_LEVEL = 18  # SDR content brightness slider

DISPLAYCONFIG_ADVANCED_COLOR_MODE_SDR = 0
DISPLAYCONFIG_ADVANCED_COLOR_MODE_WCG = 1
DISPLAYCONFIG_ADVANCED_COLOR_MODE_HDR = 2

# SDR white level is stored/transmitted in units of nits * 1000 / 80:
#   nits  -> SDRWhiteLevel
#    80   ->      1000   (minimum, ≈ Windows slider 0 on most displays)
#   200   ->      2500
#   300   ->      3750
#   480   ->      6000   (≈ Windows slider max on most displays)
SDR_WHITE_LEVEL_UNITS_PER_NIT = 1000 / 80  # 12.5


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.UINT),
        ("size", wintypes.UINT),
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
    ]


class DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO(ctypes.Structure):
    """Query structure for advanced color (HDR) info per display target.

    The 'value' field is a bitfield:
      bit 0: advancedColorSupported
      bit 1: advancedColorEnabled
      bit 2: wideColorEnforced
      bit 3: advancedColorForceDisabled
    """

    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("value", wintypes.UINT),
        ("colorEncoding", wintypes.UINT),
        ("bitsPerColorChannel", wintypes.UINT),
    ]


class DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO_2(ctypes.Structure):
    """Win11 advanced color info with explicit HDR/WCG split.

    The legacy type-9 struct only reports generic "advanced color" support and
    activity. Win11's type-15 struct separates HDR user intent from the active
    compositor mode, which avoids reporting WCG as HDR or missing a user-enabled
    HDR toggle that is not currently active on the wire.
    """

    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("value", wintypes.UINT),
        ("colorEncoding", wintypes.UINT),
        ("bitsPerColorChannel", wintypes.UINT),
        ("activeColorMode", wintypes.UINT),
    ]


class DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE(ctypes.Structure):
    """Set structure for toggling advanced color (HDR) per display target.

    The 'value' field is a bitfield:
      bit 0: enableAdvancedColor (1=on, 0=off)
    """

    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("value", wintypes.UINT),
    ]


class DISPLAYCONFIG_SDR_WHITE_LEVEL_V1(ctypes.Structure):
    """SDR paper-white level, documented MSDN shape (24 bytes).

    Per the current Microsoft reference, the struct is just header +
    SDRWhiteLevel. Most Win11 builds accept this shape for both GET (type
    11) and SET (type 18).
    """

    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("SDRWhiteLevel", wintypes.ULONG),
    ]


class DISPLAYCONFIG_SDR_WHITE_LEVEL_V2(ctypes.Structure):
    """SDR paper-white level with a trailing finalValue flag (28 bytes).

    Some Win11 build/driver combinations reject the 24-byte V1 and only
    accept this 28-byte variant — it matches the layout used by
    community tools like HDRTray/SpecialK's HDR switcher. We try V1 first
    and fall back to V2 on struct-size errors.
    """

    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("SDRWhiteLevel", wintypes.ULONG),
        ("finalValue", wintypes.BOOL),
    ]


# Keep an alias for any external imports that still reference the old name.
DISPLAYCONFIG_SDR_WHITE_LEVEL = DISPLAYCONFIG_SDR_WHITE_LEVEL_V2


class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("statusFlags", wintypes.UINT),
    ]


class DISPLAYCONFIG_RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", wintypes.UINT), ("Denominator", wintypes.UINT)]


class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("outputTechnology", wintypes.UINT),
        ("rotation", wintypes.UINT),
        ("scaling", wintypes.UINT),
        ("refreshRate", DISPLAYCONFIG_RATIONAL),
        ("scanLineOrdering", wintypes.UINT),
        ("targetAvailable", wintypes.BOOL),
        ("statusFlags", wintypes.UINT),
    ]


class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    _fields_ = [
        ("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
        ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
        ("flags", wintypes.UINT),
    ]


class DEVMODE(ctypes.Structure):
    """Windows DEVMODE structure for display settings."""

    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", ctypes.c_ulong),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", ctypes.c_ulong),
        ("dmDisplayFixedOutput", ctypes.c_ulong),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_ulong),
        ("dmPelsWidth", ctypes.c_ulong),
        ("dmPelsHeight", ctypes.c_ulong),
        ("dmDisplayFlags", ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
        ("dmICMMethod", ctypes.c_ulong),
        ("dmICMIntent", ctypes.c_ulong),
        ("dmMediaType", ctypes.c_ulong),
        ("dmDitherType", ctypes.c_ulong),
        ("dmReserved1", ctypes.c_ulong),
        ("dmReserved2", ctypes.c_ulong),
        ("dmPanningWidth", ctypes.c_ulong),
        ("dmPanningHeight", ctypes.c_ulong),
    ]


class WindowsSettingsHandler(SettingsHandler):
    """Handles Windows gaming-related settings.

    Manages:
    - Game Mode
    - Game Bar / Game DVR
    - Hardware-Accelerated GPU Scheduling (HAGS)
    - VBS / Memory Integrity
    - HDR / Auto HDR
    - Display refresh rate optimization
    """

    is_critical_verify = True

    # Registry paths
    GAME_BAR_KEY = r"Software\Microsoft\GameBar"
    GAME_DVR_KEY = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
    GRAPHICS_DRIVERS_KEY = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
    VBS_KEY = (
        r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity"
    )
    # HDR registry path (per-monitor, but this is the global toggle)
    DISPLAY_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\VideoSettings"
    # Per-monitor color state (ACM, HDR, WCG, SDR white level) lives here.
    MONITOR_DATA_STORE_KEY = _MONITOR_DATA_STORE_KEY
    DIRECTX_USER_GLOBAL_SETTINGS_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
    DIRECTX_FLAG_NAMES = {
        "auto_hdr": "AutoHDREnable",
        "windowed_optimizations": "SwapEffectUpgradeEnable",
        "vrr_optimize": "VRROptimizeEnable",
    }

    # DWM refresh propagation; tunable for slow systems.
    _DWM_REFRESH_WAIT_SECONDS: float = 0.5

    @staticmethod
    def _bool_matches(value: Any, target: bool) -> bool:
        """Return True only when a detected boolean value is known and matches."""
        return value is not None and bool(value) == bool(target)

    @staticmethod
    def _nits_matches(value: Any, target: float, *, tolerance: float = 1.0) -> bool:
        """Return True when a detected SDR paper-white value already matches."""
        try:
            return abs(float(value) - float(target)) <= tolerance
        except (TypeError, ValueError):
            return False

    @classmethod
    def _advanced_color_matches(
        cls,
        current: dict[str, Any],
        target_advanced_color: bool,
        target_hdr: bool,
        *,
        manage_hdr_intent: bool = True,
    ) -> bool:
        """Check whether live/readback state already matches the WCG+HDR target."""
        if not cls._bool_matches(current.get("advanced_color"), target_advanced_color):
            return False
        if not manage_hdr_intent:
            return True

        hdr_values = [
            value for value in (current.get("hdr"), current.get("hdr_active")) if value is not None
        ]
        if not hdr_values:
            return not bool(target_hdr)
        return all(bool(value) == bool(target_hdr) for value in hdr_values)

    def detect(self) -> dict[str, Any]:
        """Detect current Windows gaming settings."""
        refresh_info = self._get_refresh_rate_info()
        hdr_state = self._get_hdr_state_summary()
        sdr_white = self._get_sdr_white_level()
        advanced_color = self._get_advanced_color()
        directx_flags = self._get_directx_flags()
        return {
            "game_mode": self._get_game_mode(),
            "game_bar": self._get_game_bar(),
            "game_dvr": self._get_game_dvr(),
            "hags": self._get_hags(),
            "vbs": self._get_vbs(),
            "hdr": hdr_state["any_enabled"] if hdr_state["available"] else None,
            "hdr_active": hdr_state.get("any_active") if hdr_state["available"] else None,
            "hdr_capable_count": hdr_state["hdr_capable_count"] if hdr_state["available"] else None,
            "hdr_enabled_count": hdr_state["hdr_enabled_count"] if hdr_state["available"] else None,
            "hdr_active_count": (
                hdr_state.get("hdr_active_count") if hdr_state["available"] else None
            ),
            "hdr_per_target": hdr_state.get("per_target") if hdr_state["available"] else None,
            "auto_hdr": directx_flags.get("auto_hdr"),
            "advanced_color": advanced_color.get("any_enabled"),
            "advanced_color_per_monitor": advanced_color.get("per_monitor"),
            "windowed_optimizations": directx_flags.get("windowed_optimizations"),
            "vrr_optimize": directx_flags.get("vrr_optimize"),
            "refresh_rate": refresh_info.get("current"),
            "max_refresh_rate": refresh_info.get("max"),
            "available_refresh_rates": refresh_info.get("available"),
            "sdr_white_level_nits": sdr_white.get("min_nits"),
            "sdr_white_level_per_target": sdr_white.get("per_target"),
        }

    @staticmethod
    def _add_hdr_summary(current: dict[str, Any], hdr_state: dict[str, Any]) -> None:
        """Add HDR summary keys in the same shape returned by detect()."""
        if hdr_state.get("available"):
            current.update(
                {
                    "hdr": hdr_state.get("any_enabled"),
                    "hdr_active": hdr_state.get("any_active"),
                    "hdr_capable_count": hdr_state.get("hdr_capable_count"),
                    "hdr_enabled_count": hdr_state.get("hdr_enabled_count"),
                    "hdr_active_count": hdr_state.get("hdr_active_count"),
                    "hdr_per_target": hdr_state.get("per_target"),
                }
            )
        else:
            current.update(
                {
                    "hdr": None,
                    "hdr_active": None,
                    "hdr_capable_count": None,
                    "hdr_enabled_count": None,
                    "hdr_active_count": None,
                    "hdr_per_target": None,
                }
            )

    def _detect_for_apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Detect only the current values needed to apply the requested keys.

        Full ``detect()`` enumerates DisplayConfig, HDR, WCG, SDR white level,
        refresh rate, and several registry-backed flags. Applying one already
        active registry flag should not query every display subsystem first.
        """
        current: dict[str, Any] = {}

        if "game_mode" in settings:
            current["game_mode"] = self._get_game_mode()
        if "game_bar" in settings:
            current["game_bar"] = self._get_game_bar()
        if "game_dvr" in settings:
            current["game_dvr"] = self._get_game_dvr()
        if "hags" in settings:
            current["hags"] = self._get_hags()
        if "vbs" in settings:
            current["vbs"] = self._get_vbs()

        directx_keys = set(self.DIRECTX_FLAG_NAMES).intersection(settings)
        if directx_keys:
            directx_flags = self._get_directx_flags()
            for key in directx_keys:
                current[key] = directx_flags.get(key)

        if "advanced_color" in settings:
            advanced_color = self._get_advanced_color()
            current["advanced_color"] = advanced_color.get("any_enabled")
            current["advanced_color_per_monitor"] = advanced_color.get("per_monitor")
            self._add_hdr_summary(current, self._get_hdr_state_summary())

        if settings.get("sdr_white_level_nits") is not None:
            sdr_white = self._get_sdr_white_level()
            current["sdr_white_level_nits"] = sdr_white.get("min_nits")
            current["sdr_white_level_per_target"] = sdr_white.get("per_target")

        if "refresh_rate" in settings or settings.get("max_refresh_rate") is True:
            refresh_info = self._get_refresh_rate_info()
            current["refresh_rate"] = refresh_info.get("current")
            current["max_refresh_rate"] = refresh_info.get("max")
            current["available_refresh_rates"] = refresh_info.get("available")

        return current

    def _detect_for_verify(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Detect only the current values needed to verify requested keys."""
        current = self._detect_for_apply(settings)
        if "hdr" in settings and "hdr" not in current:
            self._add_hdr_summary(current, self._get_hdr_state_summary())
        return current

    def audit(self) -> list[Issue]:
        """Audit Windows settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check Game Mode
        if not current.get("game_mode"):
            issues.append(
                Issue(
                    title="Game Mode is disabled",
                    severity="warning",
                    current_value="Disabled",
                    optimal_value="Enabled",
                    explanation="Game Mode prioritizes gaming processes and reduces background activity.",
                    category="windows",
                )
            )

        # Check Game Bar/DVR (should be disabled for performance)
        if current.get("game_bar"):
            issues.append(
                Issue(
                    title="Game Bar is enabled",
                    severity="info",
                    current_value="Enabled",
                    optimal_value="Disabled",
                    explanation="Game Bar can add slight overhead. Disable unless you use its features.",
                    category="windows",
                )
            )

        if current.get("game_dvr"):
            issues.append(
                Issue(
                    title="Background recording is enabled",
                    severity="warning",
                    current_value="Enabled",
                    optimal_value="Disabled",
                    explanation="Background recording impacts performance even when not actively recording.",
                    category="windows",
                )
            )

        # VBS surfacing. ABSO does NOT advertise a universal "disable for
        # FPS" recommendation: independent testing shows VBS/HVCI can cost
        # measurable performance in some gaming configurations (Tom's
        # Hardware, Neowin), but disabling VBS reduces Windows' security
        # posture (Credential Guard, Memory Integrity) and is a tradeoff
        # users must make explicitly. ABSO's opt-in max-performance flow
        # (see ``abso.settings.vbs_optin``) is the only path that disables
        # VBS; the audit output just reports current state.
        if current.get("vbs"):
            issues.append(
                Issue(
                    title="VBS / Memory Integrity is enabled",
                    severity="info",
                    current_value="Enabled",
                    optimal_value="Enabled (security tradeoff; opt-in disable available)",
                    explanation=(
                        "VBS/Memory Integrity adds a virtualization layer that can cost "
                        "gaming performance depending on hardware and workload. "
                        "This audit has not measured that cost. Disabling it is "
                        "a security tradeoff: VBS protects credentials, kernel memory "
                        "integrity, and hypervisor-protected code integrity. ABSO does "
                        "not silently disable VBS. If you want to trade security for "
                        "performance, use the explicit opt-in max-performance flow; it "
                        "requires a reboot and provides a reversible restore path."
                    ),
                    category="windows",
                )
            )

        # Refresh rate check
        current_hz = current.get("refresh_rate")
        max_hz = current.get("max_refresh_rate")
        if current_hz and max_hz and current_hz < max_hz:
            issues.append(
                Issue(
                    title="Display not running at maximum refresh rate",
                    severity="warning",
                    current_value=f"{current_hz} Hz",
                    optimal_value=f"{max_hz} Hz",
                    explanation=(
                        f"Your monitor supports up to {max_hz} Hz but is currently set to {current_hz} Hz. "
                        "Higher refresh rates provide smoother gameplay and lower input latency."
                    ),
                    category="windows",
                )
            )

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply Windows gaming settings.

        Only sets requires_reboot=True if we actually change HAGS or VBS.
        If values already match, no reboot is needed.

        Returns detailed per-setting success/failure information.
        """
        requires_reboot = False
        errors: list[str] = []
        applied: list[str] = []
        changed_keys: list[str] = []

        # Get only the current values needed to check if we're changing anything.
        current = self._detect_for_apply(settings)

        # Apply each setting individually with error tracking
        if "game_mode" in settings:
            try:
                target = bool(settings["game_mode"])
                if self._bool_matches(current.get("game_mode"), target):
                    applied.append(f"Game Mode: already {'enabled' if target else 'disabled'}")
                else:
                    self._set_game_mode(target)
                    changed_keys.append("game_mode")
                    applied.append(f"Game Mode: {'enabled' if target else 'disabled'}")
            except Exception as e:
                errors.append(f"Game Mode: {e}")

        if "game_bar" in settings:
            try:
                target = bool(settings["game_bar"])
                if self._bool_matches(current.get("game_bar"), target):
                    applied.append(f"Game Bar: already {'enabled' if target else 'disabled'}")
                else:
                    self._set_game_bar(target)
                    changed_keys.append("game_bar")
                    applied.append(f"Game Bar: {'enabled' if target else 'disabled'}")
            except Exception as e:
                errors.append(f"Game Bar: {e}")

        if "game_dvr" in settings:
            try:
                target = bool(settings["game_dvr"])
                if self._bool_matches(current.get("game_dvr"), target):
                    applied.append(f"Game DVR: already {'enabled' if target else 'disabled'}")
                else:
                    self._set_game_dvr(target)
                    changed_keys.append("game_dvr")
                    applied.append(f"Game DVR: {'enabled' if target else 'disabled'}")
            except Exception as e:
                errors.append(f"Game DVR: {e}")

        if "hags" in settings:
            try:
                target = settings["hags"]
                current_hags = current.get("hags")
                # Only set requires_reboot if we can detect current value AND it differs
                if self._bool_matches(current_hags, target):
                    applied.append(f"HAGS: already {'enabled' if target else 'disabled'}")
                else:
                    if current_hags is not None and current_hags != target:
                        requires_reboot = True
                    self._set_hags(target)
                    changed_keys.append("hags")
                    applied.append(f"HAGS: {'enabled' if target else 'disabled'}")
            except Exception as e:
                errors.append(f"HAGS: {e}")

        if "vbs" in settings:
            try:
                target = settings["vbs"]
                current_vbs = current.get("vbs")
                if self._bool_matches(current_vbs, target):
                    applied.append(f"VBS: already {'enabled' if target else 'disabled'}")
                else:
                    if current_vbs is None:
                        # Detection failed — conservatively assume reboot needed
                        requires_reboot = True
                    elif current_vbs != target:
                        requires_reboot = True
                    self._set_vbs(target)
                    changed_keys.append("vbs")
                    applied.append(f"VBS: {'enabled' if target else 'disabled'}")
            except Exception as e:
                errors.append(f"VBS: {e}")

        # HDR and Wide Color Gamut (AdvancedColorEnabled) are coupled on
        # Win11 24H2+: setting HDR alone leaves SDR content rendering in
        # sRGB gamut on wide-gamut displays (classic washed-out desktop).
        # When a profile sets either, funnel both through a single refresh
        # cycle so DWM re-reads MonitorDataStore once with the intended
        # final state instead of flickering twice.
        hdr_handled_by_refresh = False
        if "advanced_color" in settings:
            manage_hdr_intent = "hdr" in settings
            target_advanced_color = bool(settings["advanced_color"])
            live_hdr_summary_for_refresh: dict[str, Any] | None = None
            if manage_hdr_intent:
                target_hdr = bool(settings["hdr"])
                hdr_handled_by_refresh = True
            else:
                # Preserve current live HDR state; we only flip WCG.
                current_hdr_active = current.get("hdr_active")
                if current_hdr_active is None:
                    live_hdr_summary_for_refresh = self._get_hdr_state_summary()
                    target_hdr = bool(
                        live_hdr_summary_for_refresh.get("any_active")
                        if live_hdr_summary_for_refresh.get("available")
                        else False
                    )
                else:
                    target_hdr = bool(current_hdr_active)
                    current_hdr_enabled = current.get("hdr")
                    live_hdr_summary_for_refresh = {
                        "available": True,
                        "any_active": target_hdr,
                        "any_enabled": (
                            bool(current_hdr_enabled)
                            if current_hdr_enabled is not None
                            else target_hdr
                        ),
                    }

            state_note = (
                f"Wide Color Gamut: {'on' if target_advanced_color else 'off'}"
                f" + HDR: {'on' if target_hdr else 'off'}"
            )
            if self._advanced_color_matches(
                current,
                target_advanced_color,
                target_hdr,
                manage_hdr_intent=manage_hdr_intent,
            ):
                applied.append(f"{state_note} (already correct)")
            else:
                try:
                    refresh_kwargs: dict[str, Any] = {
                        "manage_hdr_intent": manage_hdr_intent,
                    }
                    if live_hdr_summary_for_refresh is not None:
                        refresh_kwargs["live_hdr_summary"] = live_hdr_summary_for_refresh
                    refresh_result = self._set_advanced_color_with_refresh(
                        target_advanced_color,
                        target_hdr,
                        **refresh_kwargs,
                    )
                except Exception as e:
                    errors.append(f"Advanced color refresh crashed: {e}")
                else:
                    if refresh_result.get("applied_count", 0) > 0:
                        changed_keys.append("advanced_color")
                        if "hdr" in settings:
                            changed_keys.append("hdr")
                        applied.append(
                            f"{state_note} (written to "
                            f"{refresh_result['applied_count']} monitor(s))"
                        )
                    elif refresh_result.get("skipped_count", 0) > 0:
                        applied.append(f"{state_note} (already correct)")
                    # WCG errors are surfaced as notes, never as handler errors:
                    # cosmetic setting must never roll a profile back.
                    for err in refresh_result.get("errors", []):
                        applied.append(f"Advanced color: warning ({err})")
                    for err in refresh_result.get("critical_errors", []):
                        errors.append(str(err))

        if "hdr" in settings and not hdr_handled_by_refresh:
            hdr_result = self._set_hdr(settings["hdr"])
            if hdr_result["success"]:
                if hdr_result.get("changed"):
                    changed_keys.append("hdr")
                if settings["hdr"]:
                    hdr_capable_count = int(hdr_result.get("hdr_capable_count", 0) or 0)
                    hdr_enabled_count = int(hdr_result.get("hdr_enabled_count", 0) or 0)
                    hdr_active_count = int(
                        hdr_result.get("hdr_active_count", hdr_enabled_count) or 0
                    )
                    if hdr_capable_count <= 0:
                        errors.append("HDR: no HDR-capable active displays were detected")
                    elif hdr_active_count <= 0:
                        errors.append(
                            "HDR: enable requested, but Windows reported 0 active HDR displays "
                            f"({hdr_enabled_count} target(s) have Use HDR enabled)"
                        )
                    else:
                        applied.append(
                            f"HDR: active on {hdr_active_count} monitor(s) "
                            f"({hdr_enabled_count} with Use HDR enabled)"
                        )
                else:
                    applied.append("HDR: disabled on all monitors")
            else:
                for err in hdr_result.get("errors", []):
                    errors.append(f"HDR: {err}")

        if "auto_hdr" in settings:
            target_auto_hdr = bool(settings["auto_hdr"])
            if self._bool_matches(current.get("auto_hdr"), target_auto_hdr):
                applied.append(f"Auto HDR: already {'enabled' if target_auto_hdr else 'disabled'}")
            else:
                auto_hdr_result = self._set_auto_hdr(target_auto_hdr)
                if auto_hdr_result["success"]:
                    changed_keys.append("auto_hdr")
                    applied.append(f"Auto HDR: {'enabled' if target_auto_hdr else 'disabled'}")
                else:
                    errors.append(f"Auto HDR: {auto_hdr_result.get('error', 'Unknown error')}")

        if "sdr_white_level_nits" in settings:
            requested_nits = settings["sdr_white_level_nits"]
            if requested_nits is None:
                pass  # Explicit opt-out, skip silently.
            else:
                try:
                    nits_value = float(requested_nits)
                except (TypeError, ValueError) as e:
                    # Bad value in a profile is a profile authoring bug —
                    # surface as an applied-note, not a handler failure.
                    applied.append(
                        f"SDR content brightness: skipped (invalid value "
                        f"{requested_nits!r}: {e})"
                    )
                else:
                    if self._nits_matches(
                        current.get("sdr_white_level_nits"),
                        nits_value,
                    ):
                        applied.append(
                            f"SDR content brightness: already {round(nits_value, 1)} nits"
                        )
                    else:
                        sdr_result = self._set_sdr_white_level(nits_value)
                        if sdr_result["applied_count"] > 0:
                            changed_keys.append("sdr_white_level_nits")
                            applied.append(
                                f"SDR content brightness: {sdr_result['requested_nits']} nits "
                                f"on {sdr_result['applied_count']} HDR monitor(s)"
                            )
                        if sdr_result["skipped_count"] > 0 and sdr_result["applied_count"] == 0:
                            # All targets either SDR or declined the op — not an
                            # error, just a notice. SDR white level is cosmetic
                            # and never fails the handler.
                            applied.append(
                                f"SDR content brightness: skipped "
                                f"({sdr_result['skipped_count']} target(s) not HDR "
                                "or not SDR-white-level-settable)"
                            )
                        for warn in sdr_result.get("warnings", []):
                            # Surface unusual statuses as applied-notes so the
                            # tray UI sees them, but do NOT append to errors[] —
                            # a cosmetic slider must not roll back a profile.
                            applied.append(f"SDR content brightness: warning ({warn})")

        if "windowed_optimizations" in settings:
            target = bool(settings["windowed_optimizations"])
            if self._bool_matches(current.get("windowed_optimizations"), target):
                state = "enabled" if target else "disabled"
                applied.append(f"Windowed Optimizations: already {state}")
            else:
                wo_result = self._set_windowed_optimizations(target)
                if wo_result["success"]:
                    changed_keys.append("windowed_optimizations")
                    state = "enabled" if target else "disabled"
                    applied.append(f"Windowed Optimizations: {state}")
                else:
                    errors.append(
                        f"Windowed Optimizations: {wo_result.get('error', 'Unknown error')}"
                    )

        if "vrr_optimize" in settings:
            target = bool(settings["vrr_optimize"])
            if self._bool_matches(current.get("vrr_optimize"), target):
                applied.append(f"VRR Optimize: already {'enabled' if target else 'disabled'}")
            else:
                vrr_result = self._set_vrr_optimize(target)
                if vrr_result["success"]:
                    changed_keys.append("vrr_optimize")
                    applied.append(f"VRR Optimize: {'enabled' if target else 'disabled'}")
                else:
                    errors.append(f"VRR Optimize: {vrr_result.get('error', 'Unknown error')}")

        if "refresh_rate" in settings:
            try:
                target_hz = int(settings["refresh_rate"])
                current_hz = current.get("refresh_rate")
                if current_hz is not None and int(current_hz) == target_hz:
                    applied.append(f"Refresh Rate: already {target_hz} Hz")
                else:
                    self._set_refresh_rate(target_hz)
                    changed_keys.append("refresh_rate")
                    applied.append(f"Refresh Rate: {target_hz} Hz")
            except Exception as e:
                errors.append(f"Refresh Rate: {e}")

        if settings.get("max_refresh_rate") is True:
            try:
                current_hz = current.get("refresh_rate")
                max_hz = current.get("max_refresh_rate")
                if current_hz is not None and max_hz is not None and int(current_hz) >= int(max_hz):
                    applied.append(f"Refresh Rate: already at maximum ({current_hz} Hz)")
                else:
                    self._set_max_refresh_rate()
                    changed_keys.append("refresh_rate")
                    applied.append("Refresh Rate: set to maximum")
            except Exception as e:
                errors.append(f"Max Refresh Rate: {e}")

        # Log summary
        if applied:
            logger.info(f"Windows settings applied: {', '.join(applied)}")
        if errors:
            logger.warning(f"Windows settings errors: {', '.join(errors)}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": requires_reboot,
            "applied": applied,
            "changed": bool(changed_keys),
            "changed_keys": changed_keys,
            "failed": errors,
        }

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify requested Windows settings against live/readback state.

        This covers both reboot-gated settings and immediately visible display
        state, so HDR profile swaps cannot silently pass verification when the
        live display path remains SDR.
        """
        current = self._detect_for_verify(settings)
        results = {"all_active": True, "settings": {}}

        if "game_mode" in settings:
            target = bool(settings["game_mode"])
            current_val = current.get("game_mode")
            is_active = current_val is None or bool(current_val) == target
            results["settings"]["game_mode"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "game_bar" in settings:
            target = bool(settings["game_bar"])
            current_val = current.get("game_bar")
            is_active = current_val is None or bool(current_val) == target
            results["settings"]["game_bar"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "game_dvr" in settings:
            target = bool(settings["game_dvr"])
            current_val = current.get("game_dvr")
            is_active = current_val is None or bool(current_val) == target
            results["settings"]["game_dvr"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "hags" in settings:
            target = settings["hags"]
            current_val = current.get("hags")
            # If we can't detect, assume it's active (can't prove otherwise)
            is_active = current_val is None or current_val == target
            results["settings"]["hags"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "vbs" in settings:
            target = settings["vbs"]
            current_val = current.get("vbs")
            # If we can't detect, assume it's active (can't prove otherwise)
            is_active = current_val is None or current_val == target
            results["settings"]["vbs"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "hdr" in settings:
            target = bool(settings["hdr"])
            current_val = current.get("hdr")
            active_val = current.get("hdr_active")
            # Verify gates on the live compositor mode (what the user sees and
            # what apps query). The per-monitor "Use HDR" user_enabled bit is
            # reported alongside for diagnostics but never gates the result —
            # it can persist on secondary HDR-capable targets that aren't on
            # the active path.
            if active_val is not None:
                is_active = bool(active_val) == target
            elif current_val is not None:
                is_active = bool(current_val) == target
            else:
                is_active = not target
            current_report: Any
            if (
                active_val is not None
                and current_val is not None
                and bool(active_val) != bool(current_val)
            ):
                current_report = {
                    "user_enabled": bool(current_val),
                    "active": bool(active_val),
                }
            elif current_val is not None:
                current_report = bool(current_val)
            elif active_val is not None:
                current_report = {
                    "user_enabled": "undetectable",
                    "active": bool(active_val),
                }
            else:
                current_report = "undetectable"
            results["settings"]["hdr"] = {
                "target": target,
                "current": current_report,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "auto_hdr" in settings:
            target = bool(settings["auto_hdr"])
            current_val = current.get("auto_hdr")
            if current_val is None:
                is_active = not target
            else:
                is_active = bool(current_val) == target
            results["settings"]["auto_hdr"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "advanced_color" in settings:
            target = bool(settings["advanced_color"])
            current_val = current.get("advanced_color")
            if current_val is None:
                is_active = not target
            else:
                is_active = bool(current_val) == target
            results["settings"]["advanced_color"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if settings.get("sdr_white_level_nits") is not None:
            try:
                target_nits = float(settings["sdr_white_level_nits"])
            except (TypeError, ValueError):
                target_nits = None
            current_nits = current.get("sdr_white_level_nits")
            is_active = (
                target_nits is not None
                and current_nits is not None
                and abs(float(current_nits) - target_nits) <= 1.0
            )
            results["settings"]["sdr_white_level_nits"] = {
                "target": (
                    target_nits if target_nits is not None else settings["sdr_white_level_nits"]
                ),
                "current": current_nits if current_nits is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "windowed_optimizations" in settings:
            target = bool(settings["windowed_optimizations"])
            current_val = current.get("windowed_optimizations")
            is_active = current_val is None or bool(current_val) == target
            results["settings"]["windowed_optimizations"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "vrr_optimize" in settings:
            target = bool(settings["vrr_optimize"])
            current_val = current.get("vrr_optimize")
            is_active = current_val is None or bool(current_val) == target
            results["settings"]["vrr_optimize"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "refresh_rate" in settings:
            target_hz: int | None
            try:
                target_hz = int(settings["refresh_rate"])
            except (TypeError, ValueError):
                target_hz = None
            current_hz = current.get("refresh_rate")
            try:
                current_hz_int = int(current_hz) if current_hz is not None else None
            except (TypeError, ValueError):
                current_hz_int = None
            is_active = (
                target_hz is not None
                and current_hz_int is not None
                and current_hz_int == target_hz
            )
            if current_hz_int is None:
                is_active = True
            results["settings"]["refresh_rate"] = {
                "target": target_hz if target_hz is not None else settings["refresh_rate"],
                "current": current_hz_int if current_hz_int is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if settings.get("max_refresh_rate") is True:
            current_hz = current.get("refresh_rate")
            max_hz = current.get("max_refresh_rate")
            try:
                current_hz_int = int(current_hz) if current_hz is not None else None
                max_hz_int = int(max_hz) if max_hz is not None else None
            except (TypeError, ValueError):
                current_hz_int = None
                max_hz_int = None
            is_active = (
                current_hz_int is None
                or max_hz_int is None
                or current_hz_int >= max_hz_int
            )
            results["settings"]["max_refresh_rate"] = {
                "target": "maximum",
                "current": (
                    {
                        "refresh_rate": current_hz_int,
                        "max_refresh_rate": max_hz_int,
                    }
                    if current_hz_int is not None and max_hz_int is not None
                    else "undetectable"
                ),
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        return results

    def backup(self) -> dict[str, Any]:
        """Backup current Windows gaming settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Windows gaming settings from backup."""
        result = self.apply(data)
        return result.get("success", False)

    # Private helper methods

    def _get_game_mode(self) -> bool | None:
        """Get Game Mode status."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.GAME_BAR_KEY, 0, winreg.KEY_READ)
            try:
                value = winreg.QueryValueEx(key, "AutoGameModeEnabled")[0]
                return bool(value)
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Game Mode: {e}")
            return None

    def _set_game_mode(self, enabled: bool) -> None:
        """Set Game Mode status."""
        if not isinstance(enabled, int):
            logger.warning(
                f"Skipping registry write for Game Mode: expected int, got {type(enabled).__name__}"
            )
            return
        value = 1 if enabled else 0
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, self.GAME_BAR_KEY, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            winreg.SetValueEx(key, "AllowAutoGameMode", 0, winreg.REG_DWORD, value)
            winreg.SetValueEx(key, "AutoGameModeEnabled", 0, winreg.REG_DWORD, value)

    def _get_game_bar(self) -> bool | None:
        """Get Game Bar status."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.GAME_BAR_KEY, 0, winreg.KEY_READ)
            try:
                value = winreg.QueryValueEx(key, "UseNexusForGameBarEnabled")[0]
                return bool(value)
            except FileNotFoundError:
                return True  # Default is enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Game Bar: {e}")
            return None

    def _set_game_bar(self, enabled: bool) -> None:
        """Set Game Bar status."""
        if not isinstance(enabled, int):
            logger.warning(
                f"Skipping registry write for Game Bar: expected int, got {type(enabled).__name__}"
            )
            return
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, self.GAME_BAR_KEY, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            winreg.SetValueEx(
                key, "UseNexusForGameBarEnabled", 0, winreg.REG_DWORD, 1 if enabled else 0
            )

    def _get_game_dvr(self) -> bool | None:
        """Get Game DVR (background recording) status."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.GAME_DVR_KEY, 0, winreg.KEY_READ)
            try:
                value = winreg.QueryValueEx(key, "AppCaptureEnabled")[0]
                return bool(value)
            except FileNotFoundError:
                return True  # Default is enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Game DVR: {e}")
            return None

    def _set_game_dvr(self, enabled: bool) -> None:
        """Set Game DVR status."""
        if not isinstance(enabled, int):
            logger.warning(
                f"Skipping registry write for Game DVR: expected int, got {type(enabled).__name__}"
            )
            return
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, self.GAME_DVR_KEY, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            winreg.SetValueEx(key, "AppCaptureEnabled", 0, winreg.REG_DWORD, 1 if enabled else 0)

    def _get_hags(self) -> bool | None:
        """Get Hardware-Accelerated GPU Scheduling status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, self.GRAPHICS_DRIVERS_KEY, 0, winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "HwSchMode")[0]
                return value == 2  # 1 = Off, 2 = On
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get HAGS: {e}")
            return None

    def _set_hags(self, enabled: bool) -> None:
        """Set Hardware-Accelerated GPU Scheduling status."""
        if not isinstance(enabled, int):
            logger.warning(
                f"Skipping registry write for HAGS: expected int, got {type(enabled).__name__}"
            )
            return
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, self.GRAPHICS_DRIVERS_KEY, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            winreg.SetValueEx(key, "HwSchMode", 0, winreg.REG_DWORD, 2 if enabled else 1)

    def _get_vbs(self) -> bool | None:
        """Get VBS / Memory Integrity status."""
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.VBS_KEY, 0, winreg.KEY_READ)
            try:
                value = winreg.QueryValueEx(key, "Enabled")[0]
                return bool(value)
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get VBS: {e}")
            return None

    def _set_vbs(self, enabled: bool) -> None:
        """Set VBS / Memory Integrity status."""
        if not isinstance(enabled, int):
            logger.warning(
                f"Skipping registry write for VBS: expected int, got {type(enabled).__name__}"
            )
            return
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, self.VBS_KEY, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            winreg.SetValueEx(key, "Enabled", 0, winreg.REG_DWORD, 1 if enabled else 0)

    @staticmethod
    def _get_active_display_targets() -> list[tuple[_LUID, int]]:
        """Enumerate active display targets via QueryDisplayConfig.

        Returns:
            List of (adapterId, targetId) tuples for each active display.
        """
        user32 = ctypes.windll.user32
        num_paths = wintypes.UINT()
        num_modes = wintypes.UINT()

        status = user32.GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(num_paths),
            ctypes.byref(num_modes),
        )
        if status != 0 or num_paths.value == 0:
            return []

        paths = (DISPLAYCONFIG_PATH_INFO * num_paths.value)()
        # We only need paths, not modes, but the API requires the modes buffer
        modes_buf = (ctypes.c_byte * (num_modes.value * 64))()

        status = user32.QueryDisplayConfig(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(num_paths),
            paths,
            ctypes.byref(num_modes),
            modes_buf,
            None,
        )
        if status != 0:
            return []

        targets: list[tuple[_LUID, int]] = []
        for i in range(num_paths.value):
            t = paths[i].targetInfo
            targets.append((t.adapterId, t.id))
        return targets

    def _is_monitor_hdr_capable(self, monitor_id: str) -> bool:
        """Check if a monitor supports HDR via Windows registry/CCD API.

        Args:
            monitor_id: Monitor hardware identifier (e.g., "GSM784C_12345").

        Returns:
            True if the monitor is detected to support HDR.
        """
        # HDR capability detected via generic Windows CCD/registry API (works for all monitors)
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                rf"SYSTEM\CurrentControlSet\Enum\DISPLAY\{monitor_id}\Device Parameters",
                0,
                winreg.KEY_READ,
            )
            try:
                value, _ = winreg.QueryValueEx(key, "AdvancedColorSupported")
                return bool(value)
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    def _get_target_hdr_info(self, adapter_id: Any, target_id: int) -> dict[str, Any] | None:
        """Read HDR/WCG state for one active display target.

        Prefer Win11's type-15 query because it has explicit HDR user intent
        and active color mode fields. Fall back to legacy type 9 on older
        builds where "advanced color enabled" was the only available signal.
        """
        user32 = ctypes.windll.user32

        info2 = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO_2()
        info2.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO_2
        info2.header.size = ctypes.sizeof(info2)
        info2.header.adapterId = adapter_id
        info2.header.id = target_id
        status2 = user32.DisplayConfigGetDeviceInfo(ctypes.byref(info2))
        if status2 == 0:
            value = int(info2.value)
            active_mode = int(info2.activeColorMode)
            return {
                "api": "advanced_color_info_2",
                "adapter_low_part": int(adapter_id.LowPart),
                "adapter_high_part": int(adapter_id.HighPart),
                "target_id": int(target_id),
                "raw_value": value,
                "advanced_color_supported": bool(value & 0x01),
                "advanced_color_active": bool(value & 0x02),
                "advanced_color_limited_by_policy": bool(value & 0x08),
                "hdr_supported": bool(value & 0x10),
                "hdr_user_enabled": bool(value & 0x20),
                "wcg_supported": bool(value & 0x40),
                "wcg_user_enabled": bool(value & 0x80),
                "active_color_mode": active_mode,
                "hdr_active": active_mode == DISPLAYCONFIG_ADVANCED_COLOR_MODE_HDR,
            }

        legacy = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
        legacy.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO
        legacy.header.size = ctypes.sizeof(legacy)
        legacy.header.adapterId = adapter_id
        legacy.header.id = target_id
        status = user32.DisplayConfigGetDeviceInfo(ctypes.byref(legacy))
        if status != 0:
            return None

        # Legacy Windows exposed "advanced color" as the HDR path. We cannot
        # distinguish user intent from active compositor mode here, so both
        # fields intentionally carry the same best-effort signal.
        value = int(legacy.value)
        enabled = bool(value & 0x02)
        return {
            "api": "advanced_color_info_legacy",
            "adapter_low_part": int(adapter_id.LowPart),
            "adapter_high_part": int(adapter_id.HighPart),
            "target_id": int(target_id),
            "raw_value": value,
            "advanced_color_supported": bool(value & 0x01),
            "advanced_color_active": enabled,
            "advanced_color_limited_by_policy": bool(value & 0x08),
            "hdr_supported": bool(value & 0x01),
            "hdr_user_enabled": enabled,
            "wcg_supported": None,
            "wcg_user_enabled": None,
            "active_color_mode": None,
            "hdr_active": enabled,
        }

    def _get_hdr_state_summary(self) -> dict[str, Any]:
        """Summarize active-target HDR capability, intent, and live mode."""
        summary: dict[str, Any] = {
            "available": False,
            "hdr_capable_count": 0,
            "hdr_enabled_count": 0,
            "hdr_active_count": 0,
            "any_enabled": False,
            "any_active": False,
            "per_target": [],
        }

        try:
            targets = self._get_active_display_targets()
            if not targets:
                return summary

            summary["available"] = True
            for adapter_id, target_id in targets:
                info = self._get_target_hdr_info(adapter_id, target_id)
                if info is None:
                    continue

                summary["per_target"].append(info)
                if info.get("hdr_supported"):
                    summary["hdr_capable_count"] += 1
                if info.get("hdr_user_enabled"):
                    summary["hdr_enabled_count"] += 1
                if info.get("hdr_active"):
                    summary["hdr_active_count"] += 1

            summary["any_enabled"] = summary["hdr_enabled_count"] > 0
            summary["any_active"] = summary["hdr_active_count"] > 0
            return summary
        except Exception as e:
            logger.debug(f"HDR state summary failed: {e}")
            return summary

    @staticmethod
    def _display_target_key(adapter_id: Any, target_id: int) -> tuple[int, int, int]:
        """Return a stable key for matching active display targets to CCD info."""
        return (int(adapter_id.LowPart), int(adapter_id.HighPart), int(target_id))

    @staticmethod
    def _hdr_info_key(info: dict[str, Any]) -> tuple[int, int, int] | None:
        """Return the target key from a `_get_target_hdr_info` row when present."""
        try:
            return (
                int(info["adapter_low_part"]),
                int(info["adapter_high_part"]),
                int(info["target_id"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @classmethod
    def _hdr_info_by_target(
        cls,
        summary: dict[str, Any],
    ) -> dict[tuple[int, int, int], dict[str, Any]]:
        """Index active-target HDR info rows when the summary carries identities."""
        indexed: dict[tuple[int, int, int], dict[str, Any]] = {}
        for info in summary.get("per_target") or []:
            if not isinstance(info, dict):
                continue
            key = cls._hdr_info_key(info)
            if key is not None:
                indexed[key] = info
        return indexed

    @staticmethod
    def _should_send_hdr_set_to_target(
        *,
        enabled: bool,
        info: dict[str, Any] | None,
    ) -> bool:
        """Skip known SDR-only targets while preserving unknown-target fallback."""
        if info is None:
            return True
        if bool(info.get("hdr_supported")):
            return True
        return not enabled and (
            bool(info.get("hdr_active")) or bool(info.get("hdr_user_enabled"))
        )

    def _get_hdr(self) -> bool | None:
        """Get Windows HDR status using the CCD DisplayConfig API.

        Queries each active display target for advanced color (HDR) state.
        Returns True if ANY monitor has HDR enabled, False if all off, None if unavailable.
        """
        summary = self._get_hdr_state_summary()
        if not summary["available"]:
            return None
        return bool(summary["any_enabled"])

    def _get_registry_hdr_enabled_per_monitor(self) -> dict[str, bool]:
        """Read HDREnabled from every MonitorDataStore entry.

        The registry is the authoritative pre-apply source of truth for HDR
        state on Win11 24H2+. The legacy DisplayConfig GET (type 9) bit 1
        on 24H2+ reflects WCG (advanced color), NOT HDR specifically —
        checking it to decide "HDR already in target state" produces false
        positives when WCG is on but HDR is off (or vice versa).
        """
        out: dict[str, bool] = {}
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MONITOR_DATA_STORE_KEY,
                0,
                winreg.KEY_READ,
            ) as root:
                i = 0
                while True:
                    try:
                        mid = winreg.EnumKey(root, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, mid, 0, winreg.KEY_READ) as sub:
                            try:
                                v = winreg.QueryValueEx(sub, "HDREnabled")[0]
                                out[mid] = bool(v)
                            except FileNotFoundError:
                                pass  # Monitor has no HDR state key; not HDR-capable
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug("HDREnabled enumeration failed: %s", exc)
        return out

    def _set_hdr(self, enabled: bool) -> dict[str, Any]:
        """Set Windows HDR state using the active-display compositor mode as truth.

        Design:
            1. Read the live active-target state with type 15 when available.
               Registry MonitorDataStore contains historical monitors, so it
               cannot decide whether the current display path is already right.
            2. Issue DisplayConfigSetDeviceInfo with type 16
               (SET_HDR_STATE) per target, falling back to type 10
               (SET_ADVANCED_COLOR_STATE) on pre-24H2 builds.
            3. Verify the live active color mode. If SET_HDR_STATE silently
               no-opped (known Win11 25H2 behavior), write registry intent and
               kick SetDisplayConfig so DWM re-reads the display database.

        Success criterion is the user-perceived state — the active compositor
        mode on the live path. The ``user_enabled`` ("Use HDR") registry bit
        can stay set on a secondary HDR-capable target that isn't currently
        in HDR mode. That is not a failure; report it as a notice.

        Returns the standard ``success / hdr_capable_count / hdr_enabled_count
        / errors`` dict used by apply()'s logging.
        """
        result: dict[str, Any] = {
            "success": True,
            "hdr_capable_count": 0,
            "hdr_enabled_count": 0,
            "errors": [],
            "changed": False,
        }

        live_before = self._get_hdr_state_summary()
        result["hdr_capable_count"] = live_before.get("hdr_capable_count", 0)
        result["hdr_enabled_count"] = live_before.get("hdr_enabled_count", 0)
        result["hdr_active_count"] = live_before.get(
            "hdr_active_count", result["hdr_enabled_count"]
        )

        if (
            live_before.get("available")
            and live_before.get("hdr_capable_count", 0) > 0
            and bool(live_before.get("any_active")) == enabled
        ):
            logger.debug(
                "HDR active mode already %s on the live display path; skipping SET",
                "on" if enabled else "off",
            )
            return result

        # Step 2: SET_HDR_STATE per active target. We don't short-circuit on
        # registry state here — MonitorDataStore contains inactive historical
        # displays and can disagree with the target that is actually connected.
        result["changed"] = True
        try:
            targets = self._get_active_display_targets()
            if not targets:
                result["errors"].append("No active display targets found")
                result["success"] = False
                return result

            user32 = ctypes.windll.user32
            hdr_info_by_target = self._hdr_info_by_target(live_before)
            selected_targets: list[tuple[Any, int]] = []
            skipped_targets: list[dict[str, Any]] = []

            for adapter_id, target_id in targets:
                info = hdr_info_by_target.get(self._display_target_key(adapter_id, target_id))
                if self._should_send_hdr_set_to_target(enabled=enabled, info=info):
                    selected_targets.append((adapter_id, target_id))
                    continue

                skipped_targets.append(
                    {
                        "target_id": int(target_id),
                        "reason": "hdr_not_supported",
                    }
                )

            if skipped_targets:
                result["skipped_targets"] = skipped_targets

            if not selected_targets:
                result["errors"].append("No HDR-capable active display targets found")
                result["success"] = False
                return result

            for adapter_id, target_id in selected_targets:
                try:
                    set_success = False
                    state = DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE()
                    state.header.type = DISPLAYCONFIG_DEVICE_INFO_SET_HDR_STATE
                    state.header.size = ctypes.sizeof(state)
                    state.header.adapterId = adapter_id
                    state.header.id = target_id
                    state.value = 1 if enabled else 0

                    status = user32.DisplayConfigSetDeviceInfo(ctypes.byref(state))
                    if status == 0:
                        set_success = True
                    else:
                        # Pre-24H2 fallback
                        state.header.type = DISPLAYCONFIG_DEVICE_INFO_SET_ADVANCED_COLOR_STATE
                        status = user32.DisplayConfigSetDeviceInfo(ctypes.byref(state))
                        if status == 0:
                            set_success = True

                    if not set_success:
                        msg = (
                            f"DisplayConfigSetDeviceInfo failed for target "
                            f"{target_id}: error {status}"
                        )
                        logger.error(msg)
                        result["errors"].append(msg)
                        result["success"] = False
                    else:
                        logger.info(
                            "HDR %s for display target %s",
                            "enabled" if enabled else "disabled",
                            target_id,
                        )
                except Exception as exc:
                    msg = f"Failed to set HDR for target {target_id}: {exc}"
                    logger.error(msg)
                    result["errors"].append(msg)
                    result["success"] = False
        except Exception as exc:
            msg = f"Failed to set HDR: {exc}"
            logger.error(msg)
            result["errors"].append(msg)
            result["success"] = False

        time.sleep(self._DWM_REFRESH_WAIT_SECONDS)

        # Final live-state verification. The registry/MonitorDataStore values
        # can be force-written by the silent-no-op fallback, so they are not
        # a reliable signal that HDR actually lit up on the wire. Query the
        # live DisplayConfig API instead — this is what the compositor and
        # apps see, and what the user perceives as "HDR is on / off".
        live_summary = self._get_hdr_state_summary()
        live_enabled_count = live_summary.get("hdr_enabled_count", 0)
        live_active_count = live_summary.get("hdr_active_count", live_enabled_count)
        live_capable_count = live_summary.get("hdr_capable_count", 0)
        result["hdr_enabled_count"] = live_enabled_count
        result["hdr_active_count"] = live_active_count
        result["hdr_capable_count"] = live_capable_count

        # The live active compositor mode is what the user perceives and what
        # apps see. The user_enabled registry bit can persist on secondary
        # HDR-capable monitors that aren't currently on the active path; that
        # is informational only, never a failure.
        live_active_matches_target = bool(live_summary.get("any_active")) == enabled
        live_user_enabled_matches_target = bool(live_summary.get("any_enabled")) == enabled

        if live_capable_count > 0 and not live_active_matches_target:
            # Registry can already contain HDREnabled=1 from a previous
            # stale apply while the live path is still SDR (or vice versa).
            # SET_HDR_STATE can silently no-op in that case. Write the intended
            # HDREnabled value and ask DWM to re-read the display database
            # before declaring a failure.
            logger.warning(
                "HDR active mode did not match target after SET_HDR_STATE "
                "(target=%s, user_enabled_count=%s, active_count=%s). "
                "Writing registry intent and kicking SetDisplayConfig.",
                enabled,
                live_enabled_count,
                live_active_count,
            )
            self._write_hdr_enabled_registry(enabled)
            if self._kick_display_config_database_reapply():
                time.sleep(self._DWM_REFRESH_WAIT_SECONDS)
                live_summary = self._get_hdr_state_summary()
                live_enabled_count = live_summary.get("hdr_enabled_count", 0)
                live_active_count = live_summary.get("hdr_active_count", live_enabled_count)
                live_capable_count = live_summary.get("hdr_capable_count", 0)
                result["hdr_enabled_count"] = live_enabled_count
                result["hdr_active_count"] = live_active_count
                result["hdr_capable_count"] = live_capable_count
                live_active_matches_target = bool(live_summary.get("any_active")) == enabled
                live_user_enabled_matches_target = bool(live_summary.get("any_enabled")) == enabled
                if live_active_matches_target:
                    result.setdefault("notices", []).append(
                        "HDR live state recovered after SetDisplayConfig " "database re-apply"
                    )

        if enabled and live_capable_count > 0 and live_active_count == 0:
            # Desired HDR ON, monitors report capable, but live state is SDR
            # everywhere. Every user-mode API path was tried; surface as a
            # real failure with actionable guidance.
            msg = (
                "HDR could not be activated on the live display path "
                f"({live_capable_count} HDR-capable target(s) detected, "
                f"{live_enabled_count} target(s) have Use HDR enabled, "
                "0 currently in HDR active mode). The OS-side registry intent has "
                "been written. Open Windows Settings -> Display and toggle "
                "'Use HDR' on for the HDR-capable monitor, then re-apply "
                "this profile. (Known Win11 25H2 quirk: SET_HDR_STATE can "
                "silently no-op on stale display-path state; manual UI "
                "toggle bypasses it.)"
            )
            logger.error(msg)
            result["errors"].append(msg)
            result["success"] = False
        elif not enabled and live_active_count > 0:
            # Desired HDR OFF, but the compositor is still in HDR active mode.
            # This is a real failure: the user's screen would still look HDR.
            msg = (
                "HDR disable was requested, but Windows still reports "
                f"{live_active_count} target(s) in HDR active mode."
            )
            logger.error(msg)
            result["errors"].append(msg)
            result["success"] = False
        elif not live_user_enabled_matches_target and live_capable_count > 0:
            # Compositor is in the requested mode, but the per-monitor "Use HDR"
            # registry bit is stuck (typically a secondary HDR-capable target
            # the user hasn't manually toggled). Surface as a notice — the
            # user-perceived display state matches the request.
            result.setdefault("notices", []).append(
                f"HDR {'enable' if enabled else 'disable'} active on the live "
                f"display path, but {live_enabled_count} target(s) still report "
                "'Use HDR' enabled at the OS level. This is cosmetic only — "
                "toggle 'Use HDR' off for that monitor in Windows Settings if "
                "you want it fully cleared."
            )

        return result

    def _kick_display_config_database_reapply(self) -> bool:
        """Ask DWM to re-read the saved display database after registry HDR writes."""
        try:
            kick_status = ctypes.windll.user32.SetDisplayConfig(
                0, None, 0, None, _SDC_APPLY | _SDC_USE_DATABASE_CURRENT
            )
            if kick_status != 0:
                logger.warning(
                    "SetDisplayConfig kick returned non-zero status %s; live "
                    "HDR re-apply may still need a manual refresh-rate cycle.",
                    kick_status,
                )
                return False
            logger.info(
                "SetDisplayConfig database re-apply succeeded; DWM should "
                "pick up HDREnabled within a few hundred ms."
            )
            return True
        except Exception as kick_exc:
            logger.warning("SetDisplayConfig kick failed: %s", kick_exc)
            return False

    # =========================================================================
    # SDR content brightness under HDR (Windows 11 "SDR content brightness" slider)
    # =========================================================================

    def _get_sdr_white_level(self) -> dict[str, Any]:
        """Read the SDR paper-white nits value for every active target.

        Returns a dict with:
            available: bool — CCD API reachable at all
            per_target: list of {target_id, nits, hdr_enabled, struct_variant}
            any_hdr_enabled: bool
            min_nits / max_nits: summary across HDR-on targets, or None

        Only HDR-enabled targets have meaningful values; SDR targets are
        skipped because SDR white level is not exposed when HDR is off.

        Tries the 24-byte V1 struct first (matches current MSDN docs),
        falls back to the 28-byte V2 struct used by community tools.
        """
        out: dict[str, Any] = {
            "available": False,
            "per_target": [],
            "any_hdr_enabled": False,
            "min_nits": None,
            "max_nits": None,
        }

        try:
            targets = self._get_active_display_targets()
            if not targets:
                return out

            out["available"] = True
            values: list[float] = []

            for adapter_id, target_id in targets:
                # Need to know HDR state to decide whether the level is valid.
                target_hdr = self._get_target_hdr_info(adapter_id, target_id)
                hdr_enabled = bool(target_hdr and target_hdr.get("hdr_active"))

                if not hdr_enabled:
                    out["per_target"].append(
                        {
                            "target_id": target_id,
                            "nits": None,
                            "hdr_enabled": False,
                            "struct_variant": None,
                        }
                    )
                    continue

                nits_val, variant = self._read_sdr_white_level_raw(adapter_id, target_id)
                if nits_val is None:
                    out["per_target"].append(
                        {
                            "target_id": target_id,
                            "nits": None,
                            "hdr_enabled": True,
                            "struct_variant": None,
                        }
                    )
                    continue

                values.append(nits_val)
                out["per_target"].append(
                    {
                        "target_id": target_id,
                        "nits": round(nits_val, 1),
                        "hdr_enabled": True,
                        "struct_variant": variant,
                    }
                )

            out["any_hdr_enabled"] = any(t["hdr_enabled"] for t in out["per_target"])
            if values:
                out["min_nits"] = round(min(values), 1)
                out["max_nits"] = round(max(values), 1)
            return out
        except Exception as e:
            logger.debug(f"Get SDR white level failed: {e}")
            return out

    def _read_sdr_white_level_raw(
        self,
        adapter_id: Any,
        target_id: int,
    ) -> tuple[float | None, str | None]:
        """Try V1 (24 bytes) then V2 (28 bytes) to read SDR white level.

        Returns (nits, "v1"|"v2") on success, (None, None) when both shapes
        fail. Caching which variant worked lets SET use the same one.
        """
        user32 = ctypes.windll.user32
        for variant_label, struct_cls in (
            ("v1", DISPLAYCONFIG_SDR_WHITE_LEVEL_V1),
            ("v2", DISPLAYCONFIG_SDR_WHITE_LEVEL_V2),
        ):
            level = struct_cls()
            level.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SDR_WHITE_LEVEL
            level.header.size = ctypes.sizeof(struct_cls)
            level.header.adapterId = adapter_id
            level.header.id = target_id
            status = user32.DisplayConfigGetDeviceInfo(ctypes.byref(level))
            if status == 0:
                nits = level.SDRWhiteLevel / SDR_WHITE_LEVEL_UNITS_PER_NIT
                return nits, variant_label
            logger.debug(
                "GET_SDR_WHITE_LEVEL %s for target %s: status=%s",
                variant_label,
                target_id,
                status,
            )
        return None, None

    # Windows Win32 error codes we classify as "target refuses this op" —
    # treated as skipped per target, not as an apply-breaking error.
    # Windows does not always accept SDR_WHITE_LEVEL writes on every
    # target even when the advanced-color GET reports HDR on, e.g. on
    # Win11 24H2+ where WCG/HDR were split, or on secondary/clone paths.
    _SDR_WHITE_LEVEL_SKIP_ERRORS = frozenset(
        {
            31,  # ERROR_GEN_FAILURE
            50,  # ERROR_NOT_SUPPORTED
            87,  # ERROR_INVALID_PARAMETER — driver declined this target
            1168,  # ERROR_NOT_FOUND
        }
    )

    def _set_sdr_white_level(self, nits: float) -> dict[str, Any]:
        """Set the Windows "SDR content brightness" slider to ``nits``.

        Best-effort across every active target. Writes to HDR-on targets
        that accept the call, silently skips SDR targets, and classifies
        "driver refused this op" Win32 errors (87, 50, 31, 1168) as
        skipped rather than failed. Any other status code is reported as
        a warning but still does NOT flip ``success`` — SDR white level is
        cosmetic and must not break a profile apply.

        Returns a dict:
            success: always True unless the whole operation crashed
            requested_nits: clamped value we tried
            applied_count: targets that actually took the write
            skipped_count: targets that are SDR / declined the op
            warnings: human-readable notes from unusual non-fatal statuses
        """
        # Clamp to a sane range. Windows rejects <80 and the usable ceiling
        # on most displays is 480. Per-profile callers can still request any
        # value; we just avoid writing values the API will refuse.
        if nits < 80:
            nits = 80
        if nits > 480:
            nits = 480

        result: dict[str, Any] = {
            "success": True,
            "requested_nits": nits,
            "applied_count": 0,
            "skipped_count": 0,
            "warnings": [],
        }

        try:
            targets = self._get_active_display_targets()
            if not targets:
                result["warnings"].append("No active display targets found")
                return result

            encoded = int(round(nits * SDR_WHITE_LEVEL_UNITS_PER_NIT))

            for adapter_id, target_id in targets:
                # Skip monitors with HDR off — the SET call will fail and there
                # is no slider to move on an SDR output.
                target_hdr = self._get_target_hdr_info(adapter_id, target_id)
                if not (target_hdr and target_hdr.get("hdr_active")):
                    result["skipped_count"] += 1
                    continue

                # Probe which struct shape this target accepts. Some Win11
                # builds/drivers require V1 (24 bytes, no finalValue); others
                # require V2 (28 bytes, with finalValue). The cached probe
                # from the GET path would be faster but less reliable across
                # reboots, so we re-probe per SET for correctness.
                set_status = self._write_sdr_white_level(adapter_id, target_id, encoded)

                if set_status == 0:
                    result["applied_count"] += 1
                    continue

                unsigned_status = set_status & 0xFFFFFFFF if set_status < 0 else set_status

                if unsigned_status in self._SDR_WHITE_LEVEL_SKIP_ERRORS:
                    result["skipped_count"] += 1
                    logger.debug(
                        "SDR_WHITE_LEVEL declined for target %s (Win32 error %s) — skipped",
                        target_id,
                        set_status,
                    )
                    continue

                # Unknown non-zero status: log a warning, but keep going and
                # still report success=True. We would rather leave a monitor
                # at its current paper-white than trigger a profile rollback.
                warning = (
                    f"SetDeviceInfo(SDR_WHITE_LEVEL) returned unexpected "
                    f"status {set_status} for target {target_id}; left unchanged"
                )
                logger.warning(warning)
                result["warnings"].append(warning)
        except Exception as e:
            # Any crash in the SDR white level path is logged but still
            # treated as best-effort: the rest of the profile apply is far
            # more important than the HDR paper-white slider.
            logger.warning("SDR white level set crashed: %s", e)
            result["warnings"].append(f"SDR white level set crashed: {e}")

        return result

    def _write_sdr_white_level(
        self,
        adapter_id: Any,
        target_id: int,
        encoded_value: int,
    ) -> int:
        """Write SDR white level with struct-variant probing + verify-after-write.

        The Win11 SDR_WHITE_LEVEL API has a nasty silent-failure mode: the
        SET can return success (status=0) even when Windows did not commit
        the value. The ``finalValue`` field in the V2 28-byte struct exists
        precisely to distinguish "commit this" from "preview only" — without
        it, some builds accept the call but persist nothing.

        Strategy:
        1. Try V2 (28 bytes, finalValue=1) — the shape community tools use
           and the one that actually commits on recent Win11.
        2. After any status=0 SET, immediately GET and confirm the read-back
           matches the requested value (±1 unit for floating-point rounding).
           A "successful" SET that doesn't change the value is treated as
           a silent failure and falls through to the next variant.
        3. V1 (24 bytes) as fallback for older/odd Win11 builds.

        Returns 0 only when the value actually landed and verified; otherwise
        returns the last meaningful Win32 status code.
        """
        user32 = ctypes.windll.user32
        last_status = 0

        attempts = (
            ("v2", DISPLAYCONFIG_SDR_WHITE_LEVEL_V2, True),  # commit-shape
            ("v1", DISPLAYCONFIG_SDR_WHITE_LEVEL_V1, False),  # docs-shape fallback
        )

        for label, struct_cls, has_final_value in attempts:
            level = struct_cls()
            level.header.type = DISPLAYCONFIG_DEVICE_INFO_SET_SDR_WHITE_LEVEL
            level.header.size = ctypes.sizeof(struct_cls)
            level.header.adapterId = adapter_id
            level.header.id = target_id
            level.SDRWhiteLevel = encoded_value
            if has_final_value:
                level.finalValue = 1

            status = user32.DisplayConfigSetDeviceInfo(ctypes.byref(level))
            last_status = status
            logger.debug(
                "SET_SDR_WHITE_LEVEL %s for target %s: status=%s",
                label,
                target_id,
                status,
            )
            if status != 0:
                continue

            # Win11 quirk: some builds accept both struct shapes but persist neither.
            readback_nits, _variant = self._read_sdr_white_level_raw(adapter_id, target_id)
            if readback_nits is None:
                # Can't verify — trust the status and move on.
                return 0

            requested_nits = encoded_value / SDR_WHITE_LEVEL_UNITS_PER_NIT
            # Encoded value is integer; allow a 1-unit (≈0.08 nit) tolerance.
            if abs(readback_nits - requested_nits) <= 0.1:
                return 0

            logger.debug(
                "SDR_WHITE_LEVEL %s SET returned 0 but readback=%.1f nits "
                "differs from requested %.1f nits — silent commit failure, "
                "trying next variant",
                label,
                readback_nits,
                requested_nits,
            )
            # Pretend this was a struct-size-ish failure so the caller's
            # SKIP_ERRORS set doesn't prematurely short-circuit.
            last_status = 87  # ERROR_INVALID_PARAMETER

        return last_status

    # =========================================================================
    # Wide Color Gamut (AdvancedColorEnabled) — Win11 24H2+ split-color-stack
    # =========================================================================

    def _get_advanced_color(self) -> dict[str, Any]:
        """Read AdvancedColorEnabled across every MonitorDataStore entry + live DWM.

        On Win11 24H2+ the old combined "advanced color" was split:
            HDREnabled            -- HDR10 tone mapping
            AdvancedColorEnabled  -- Wide Color Gamut (WCG) for SDR content

        ABSO's HDR profiles set ``hdr`` only. On 24H2+ that produces a
        washed-out SDR-inside-HDR look on wide-gamut displays because WCG
        is left off. This reader surfaces per-monitor state so the UI/audit
        can flag the mismatch.
        """
        result: dict[str, Any] = {
            "any_enabled": False,
            "per_monitor": {},  # keyed by registry monitor_id
        }
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MONITOR_DATA_STORE_KEY,
                0,
                winreg.KEY_READ,
            ) as root:
                i = 0
                while True:
                    try:
                        monitor_id = winreg.EnumKey(root, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, monitor_id, 0, winreg.KEY_READ) as sub:
                            try:
                                value = winreg.QueryValueEx(sub, "AdvancedColorEnabled")[0]
                                result["per_monitor"][monitor_id] = bool(value)
                                if value:
                                    result["any_enabled"] = True
                            except FileNotFoundError:
                                # Key not present yet — default off.
                                result["per_monitor"][monitor_id] = False
                    except Exception as exc:
                        logger.debug("WCG read for %s failed: %s", monitor_id, exc)
        except Exception as exc:
            logger.debug("Enumerate MonitorDataStore for WCG: %s", exc)
        return result

    def _set_advanced_color(self, enabled: bool) -> dict[str, Any]:
        """Write AdvancedColorEnabled per-monitor in MonitorDataStore.

        Registry write ONLY. For the value to reach DWM's live compositor
        the caller must cycle HDR via SET_HDR_STATE — see
        ``_set_advanced_color_with_refresh`` for the combined sequence.
        """
        value = 1 if enabled else 0
        result: dict[str, Any] = {
            "success": True,
            "applied_count": 0,
            "skipped_count": 0,
            "errors": [],
        }

        monitor_ids: list[str] = []
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MONITOR_DATA_STORE_KEY,
                0,
                winreg.KEY_READ,
            ) as root:
                i = 0
                while True:
                    try:
                        monitor_ids.append(winreg.EnumKey(root, i))
                        i += 1
                    except OSError:
                        break
        except Exception as exc:
            result["success"] = False
            result["errors"].append(f"Enumerate MonitorDataStore: {exc}")
            return result

        for mid in monitor_ids:
            sub_path = f"{self.MONITOR_DATA_STORE_KEY}\\{mid}"
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    sub_path,
                    0,
                    winreg.KEY_ALL_ACCESS,
                ) as sub:
                    try:
                        current = winreg.QueryValueEx(sub, "AdvancedColorEnabled")[0]
                    except FileNotFoundError:
                        current = None
                    if current == value:
                        result["skipped_count"] += 1
                        continue
                    winreg.SetValueEx(sub, "AdvancedColorEnabled", 0, winreg.REG_DWORD, value)
                    result["applied_count"] += 1
            except PermissionError as exc:
                result["errors"].append(f"{mid}: permission denied ({exc})")
                result["success"] = False
            except Exception as exc:
                # Partial failures are logged but don't break the whole op.
                result["errors"].append(f"{mid}: {exc}")
        return result

    def _write_hdr_enabled_registry(self, enabled: bool) -> dict[str, Any]:
        """Persist HDREnabled per-monitor so a DWM re-init reads our intent.

        SET_HDR_STATE writes this too on success, but on Win11 builds where
        SET silently no-ops we still want the registry to be correct so the
        upcoming HDR-cycle re-init picks up the intended state.
        """
        value = 1 if enabled else 0
        result: dict[str, Any] = {"applied_count": 0, "skipped_count": 0}
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MONITOR_DATA_STORE_KEY,
                0,
                winreg.KEY_READ,
            ) as root:
                monitor_ids: list[str] = []
                i = 0
                while True:
                    try:
                        monitor_ids.append(winreg.EnumKey(root, i))
                        i += 1
                    except OSError:
                        break
        except Exception:
            return result

        for mid in monitor_ids:
            sub_path = f"{self.MONITOR_DATA_STORE_KEY}\\{mid}"
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    sub_path,
                    0,
                    winreg.KEY_ALL_ACCESS,
                ) as sub:
                    try:
                        current_hdr = winreg.QueryValueEx(sub, "HDREnabled")[0]
                    except FileNotFoundError:
                        continue  # Monitor not HDR-capable at registry level
                    # Only rewrite when target differs so we don't bump modify
                    # time on monitors that aren't HDR-capable.
                    if current_hdr != value:
                        winreg.SetValueEx(sub, "HDREnabled", 0, winreg.REG_DWORD, value)
                        result["applied_count"] += 1
                    else:
                        result["skipped_count"] += 1
            except Exception:
                continue
        return result

    def _set_advanced_color_with_refresh(
        self,
        target_advanced_color: bool,
        target_hdr: bool,
        *,
        manage_hdr_intent: bool = True,
        live_hdr_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write WCG/HDR registry intent + cycle HDR to force DWM re-read.

        On Win11 24H2+ MonitorDataStore writes do not propagate to the DWM
        compositor until HDR re-enumerates. The sequence that's been
        verified to work on build 26200 is:
            1. HDR OFF via SET_HDR_STATE        (compositor tears down HDR)
            2. write AdvancedColorEnabled + HDREnabled registry values
            3. short sleep so DWM finishes releasing the old path
            4. HDR ON via SET_HDR_STATE (when target_hdr=True)
               — DWM re-initializes the HDR pipeline, reading the fresh
                 MonitorDataStore values
            5. if target_hdr is False, skip step 4 (leave HDR off)

        Returns a dict {success, applied_count, skipped_count, errors[],
        cycle_ran, final_state}.
        """
        result: dict[str, Any] = {
            "success": True,
            "applied_count": 0,
            "skipped_count": 0,
            "errors": [],
            "critical_errors": [],
            "cycle_ran": False,
            "final_state": {},
        }

        # Pre-check live HDR state: if HDR is already in target state on the
        # live path, skip the off-on cycle entirely. Win11 25H2 SET_HDR_STATE
        # is asymmetric — the OFF command tends to be honored even when the
        # subsequent ON silently no-ops, which would leave the user with HDR
        # actively turned OFF as a side effect of an apply that was supposed
        # to be a no-op. Only cycle when we genuinely need to flip HDR.
        live_pre = (
            live_hdr_summary
            if live_hdr_summary is not None
            else self._get_hdr_state_summary()
        )
        live_hdr_on = bool(live_pre.get("any_active"))
        skip_hdr_cycle = (not manage_hdr_intent) or live_hdr_on == bool(target_hdr)
        if not manage_hdr_intent:
            logger.info(
                "WCG-only refresh will not write HDR intent or cycle HDR; "
                "preserving live HDR active state (%s).",
                "on" if live_hdr_on else "off",
            )
        if skip_hdr_cycle:
            logger.info(
                "HDR live state already matches target (%s); WCG refresh "
                "will skip the HDR off/on cycle to avoid asymmetric SET "
                "no-op damage on Win11 25H2.",
                "on" if target_hdr else "off",
            )
        else:
            # Step 1: HDR OFF.
            #
            # When target_hdr=True this is a transient teardown to release the
            # compositor's HDR pipeline so DWM re-reads MonitorDataStore on the
            # subsequent step-4 enable. Step 2 will overwrite the HDR registry
            # intent regardless, so a stuck per-monitor user_enabled bit during
            # the teardown is not load-bearing — surface as informational only.
            #
            # When target_hdr=False this step IS the final state. A failure to
            # leave the compositor in SDR is a real failure: escalate.
            step1_is_final = not target_hdr
            try:
                hdr_off_result = self._set_hdr(False)
                if not hdr_off_result.get("success", False):
                    if step1_is_final:
                        result["success"] = False
                        for err in hdr_off_result.get("errors", []) or []:
                            result["critical_errors"].append(f"HDR disable: {err}")
                    else:
                        for err in hdr_off_result.get("errors", []) or []:
                            result["errors"].append(f"HDR teardown: {err}")
            except Exception as exc:
                logger.warning("HDR OFF during WCG refresh failed: %s", exc)
                if step1_is_final:
                    result["success"] = False
                    result["critical_errors"].append(f"HDR disable crashed: {exc}")
                else:
                    result["errors"].append(f"HDR teardown crashed: {exc}")

        # Step 2: write WCG + HDR registry intent while compositor is quiescent.
        adv_result = self._set_advanced_color(target_advanced_color)
        result["applied_count"] += adv_result["applied_count"]
        result["skipped_count"] += adv_result["skipped_count"]
        for err in adv_result.get("errors", []):
            result["errors"].append(f"WCG write: {err}")
        if not adv_result["success"]:
            result["success"] = False

        hdr_registry_result = (
            self._write_hdr_enabled_registry(target_hdr) if manage_hdr_intent else None
        )

        if not manage_hdr_intent:
            result["cycle_ran"] = False
            result["final_state"] = {
                "advanced_color_registry_any_enabled": target_advanced_color,
                "hdr_any_enabled": live_pre.get("any_enabled"),
                "hdr_any_active": live_pre.get("any_active"),
            }
            return result

        hdr_registry_changed = (
            isinstance(hdr_registry_result, dict)
            and int(hdr_registry_result.get("applied_count", 0) or 0) > 0
        )
        if skip_hdr_cycle and adv_result.get("applied_count", 0) == 0 and not hdr_registry_changed:
            result["cycle_ran"] = False
            result["final_state"] = {
                "advanced_color_registry_any_enabled": target_advanced_color,
                "hdr_any_enabled": live_pre.get("any_enabled"),
                "hdr_any_active": live_pre.get("any_active"),
            }
            return result

        # Step 3: give DWM a moment to finish its OFF path. 0.5s was
        # measured sufficient on Win11 25H2 — 2s was overcautious.
        time.sleep(self._DWM_REFRESH_WAIT_SECONDS)

        # Step 4: HDR ON (if intended) — but only if we actually cycled OFF
        # in step 1. If HDR was already in target state, calling SET_HDR_STATE
        # again here would risk the silent-no-op leaving live state stuck.
        if skip_hdr_cycle:
            result["cycle_ran"] = False  # skipped — live state was already correct
        elif target_hdr:
            try:
                hdr_on_result = self._set_hdr(True)
                if not hdr_on_result.get("success", False):
                    result["success"] = False
                    for err in hdr_on_result.get("errors", []) or []:
                        result["critical_errors"].append(f"HDR enable: {err}")
                result["cycle_ran"] = True
            except Exception as exc:
                logger.warning("HDR ON during WCG refresh failed: %s", exc)
                result["success"] = False
                result["critical_errors"].append(f"HDR enable crashed: {exc}")
        else:
            result["cycle_ran"] = True  # cycle = off-only when HDR intended off

        # Step 5: verify final state via live DisplayConfig GET. This is
        # best-effort reporting — we don't fail the handler on verification
        # mismatches because some targets have silent-commit quirks.
        time.sleep(self._DWM_REFRESH_WAIT_SECONDS)
        final_advanced = self._get_advanced_color()
        final_hdr = self._get_hdr_state_summary()
        result["final_state"] = {
            "advanced_color_registry_any_enabled": final_advanced.get("any_enabled"),
            "hdr_any_enabled": final_hdr.get("any_enabled"),
            "hdr_any_active": final_hdr.get("any_active"),
        }
        return result

    def _get_auto_hdr(self) -> bool | None:
        """Get Windows Auto HDR status (Windows 11 only).

        Auto HDR is controlled by AutoHDREnable in DirectXUserGlobalSettings.
        NOTE: SwapEffectUpgradeEnable is a DIFFERENT setting (windowed optimizations).
        """
        return self._get_directx_flag(self.DIRECTX_FLAG_NAMES["auto_hdr"])

    def _set_auto_hdr(self, enabled: bool) -> dict[str, Any]:
        """Set Windows Auto HDR status (Windows 11 only).

        Auto HDR converts SDR games to HDR automatically.
        For competitive gaming, this should typically be disabled.
        Uses AutoHDREnable flag (not SwapEffectUpgradeEnable which is windowed optimizations).
        """
        return self._set_directx_flag(
            self.DIRECTX_FLAG_NAMES["auto_hdr"],
            enabled,
            "Auto HDR",
        )

    def _get_windowed_optimizations(self) -> bool | None:
        """Get 'Optimizations for windowed games' status (Windows 11).

        Controlled by SwapEffectUpgradeEnable in DirectXUserGlobalSettings.
        When enabled, Windows upgrades DX10/DX11 swap chains to flip model
        in windowed/borderless mode. Can cause stutter on 24H2.
        """
        return self._get_directx_flag(self.DIRECTX_FLAG_NAMES["windowed_optimizations"])

    def _set_windowed_optimizations(self, enabled: bool) -> dict[str, Any]:
        """Set 'Optimizations for windowed games' (Windows 11).

        For competitive gaming, this should typically be DISABLED — the
        DX10/DX11 swap chain upgrade can introduce frame pacing stutter,
        especially on Windows 11 24H2 with G-SYNC borderless.

        Also sets SwapEffectUpgradeCache DWORD for full effect.
        """
        result = self._set_directx_flag(
            self.DIRECTX_FLAG_NAMES["windowed_optimizations"],
            enabled,
            "Windowed Optimizations",
        )

        # Also set the cache DWORD that Windows checks
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\DirectX\GraphicsSettings",
                0,
                winreg.KEY_ALL_ACCESS,
            )
            try:
                winreg.SetValueEx(
                    key, "SwapEffectUpgradeCache", 0, winreg.REG_DWORD, 1 if enabled else 0
                )
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            try:
                key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\DirectX\GraphicsSettings",
                )
                try:
                    winreg.SetValueEx(
                        key, "SwapEffectUpgradeCache", 0, winreg.REG_DWORD, 1 if enabled else 0
                    )
                finally:
                    winreg.CloseKey(key)
            except Exception as e:
                logger.debug(f"Failed to set SwapEffectUpgradeCache: {e}")
        except Exception as e:
            logger.debug(f"Failed to set SwapEffectUpgradeCache: {e}")

        return result

    # --- Shared DirectX flag helpers ---

    @classmethod
    def _parse_directx_flags(cls, value: Any) -> dict[str, bool]:
        """Parse DirectXUserGlobalSettings into ABSO setting names."""
        by_flag = dict.fromkeys(cls.DIRECTX_FLAG_NAMES.values(), False)
        for token in (part.strip() for part in str(value).split(";")):
            name, sep, flag_value = token.partition("=")
            if sep != "=" or name not in by_flag:
                continue
            cleaned = flag_value.strip()
            if cleaned in {"0", "1"}:
                by_flag[name] = cleaned == "1"

        return {
            setting_name: bool(by_flag[flag_name])
            for setting_name, flag_name in cls.DIRECTX_FLAG_NAMES.items()
        }

    def _get_directx_flags(self) -> dict[str, bool | None]:
        """Read all DirectXUserGlobalSettings flags with one registry query."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.DIRECTX_USER_GLOBAL_SETTINGS_KEY,
                0,
                winreg.KEY_READ,
            )
            try:
                value = winreg.QueryValueEx(key, "DirectXUserGlobalSettings")[0]
                return self._parse_directx_flags(value)
            except FileNotFoundError:
                return dict.fromkeys(self.DIRECTX_FLAG_NAMES, None)
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get DirectXUserGlobalSettings: {e}")
            return dict.fromkeys(self.DIRECTX_FLAG_NAMES, None)

    def get_windowed_vrr_flags(self) -> dict[str, bool | None]:
        """Return just the borderless/windowed-VRR DirectX flags.

        Light read (one registry query, no monitor/HDR probes), used by the
        post-apply VRR-enabler reconciliation in :mod:`abso.core.vrr_reconcile`.
        Keys: ``windowed_optimizations`` (SwapEffectUpgradeEnable) and
        ``vrr_optimize`` (VRROptimizeEnable).
        """
        flags = self._get_directx_flags()
        return {
            "windowed_optimizations": flags.get("windowed_optimizations"),
            "vrr_optimize": flags.get("vrr_optimize"),
        }

    def _get_directx_flag(self, flag_name: str) -> bool | None:
        """Read a flag from DirectXUserGlobalSettings semicolon-delimited string."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.DIRECTX_USER_GLOBAL_SETTINGS_KEY,
                0,
                winreg.KEY_READ,
            )
            try:
                value = winreg.QueryValueEx(key, "DirectXUserGlobalSettings")[0]
                parsed = self._parse_directx_flags(value)
                setting_name = next(
                    (
                        candidate
                        for candidate, candidate_flag in self.DIRECTX_FLAG_NAMES.items()
                        if candidate_flag == flag_name
                    ),
                    None,
                )
                if setting_name is None:
                    return None
                return parsed[setting_name]
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get {flag_name}: {e}")
            return None

    @classmethod
    def _directx_settings_with_flag(
        cls,
        current: Any | None,
        flag_name: str,
        enabled: bool,
    ) -> str:
        """Return DirectXUserGlobalSettings with normalized ABSO-owned flags."""
        val = "1" if enabled else "0"
        tracked_names = set(cls.DIRECTX_FLAG_NAMES.values())
        tracked_values = dict.fromkeys(cls.DIRECTX_FLAG_NAMES.values(), "0")
        unknown_tokens: list[str] = []

        if current is not None:
            for token in (part.strip() for part in str(current).split(";")):
                if not token:
                    continue
                name, sep, token_value = token.partition("=")
                if sep == "=" and name in tracked_names:
                    cleaned = token_value.strip()
                    if cleaned in {"0", "1"}:
                        tracked_values[name] = cleaned
                    continue
                unknown_tokens.append(token)

        tracked_values[flag_name] = val
        tracked_tokens = [f"{name}={tracked_values[name]}" for name in cls.DIRECTX_FLAG_NAMES.values()]
        return ";".join([*unknown_tokens, *tracked_tokens])

    def _set_directx_flag(self, flag_name: str, enabled: bool, display_name: str) -> dict[str, Any]:
        """Set a flag in DirectXUserGlobalSettings semicolon-delimited string."""
        result: dict[str, Any] = {"success": True, "error": None}

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.DIRECTX_USER_GLOBAL_SETTINGS_KEY,
                0,
                winreg.KEY_ALL_ACCESS,
            )
            try:
                current = winreg.QueryValueEx(key, "DirectXUserGlobalSettings")[0]
                new_value = self._directx_settings_with_flag(current, flag_name, enabled)
                winreg.SetValueEx(key, "DirectXUserGlobalSettings", 0, winreg.REG_SZ, new_value)
                logger.info(f"{display_name} set to {'enabled' if enabled else 'disabled'}")
            except FileNotFoundError:
                winreg.SetValueEx(
                    key,
                    "DirectXUserGlobalSettings",
                    0,
                    winreg.REG_SZ,
                    self._directx_settings_with_flag(None, flag_name, enabled),
                )
                logger.info(
                    f"{display_name} set to {'enabled' if enabled else 'disabled'} (created)"
                )
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            try:
                key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    self.DIRECTX_USER_GLOBAL_SETTINGS_KEY,
                )
                try:
                    winreg.SetValueEx(
                        key,
                        "DirectXUserGlobalSettings",
                        0,
                        winreg.REG_SZ,
                        self._directx_settings_with_flag(None, flag_name, enabled),
                    )
                finally:
                    winreg.CloseKey(key)
            except Exception as e:
                result = {"success": False, "error": f"Failed to create {display_name} key: {e}"}
        except Exception as e:
            result = {"success": False, "error": f"Failed to set {display_name}: {e}"}

        return result

    def _get_vrr_optimize(self) -> bool | None:
        """Get VRR Optimize for windowed games status (Windows 11).

        VRROptimizeEnable controls whether Windows applies VRR compositor
        optimizations. Counterintuitively, this can ADD latency even in
        exclusive fullscreen by keeping compositor logic in the path.
        """
        return self._get_directx_flag(self.DIRECTX_FLAG_NAMES["vrr_optimize"])

    def _set_vrr_optimize(self, enabled: bool) -> dict[str, Any]:
        """Set VRR Optimize for windowed games (Windows 11).

        Strict fullscreen/no-sync profiles keep this disabled.
        VRROptimizeEnable=1 keeps compositor logic in the path even in
        exclusive fullscreen, which may add latency.

        Returns:
            Dict with 'success' and optional 'error'.
        """
        return self._set_directx_flag(
            self.DIRECTX_FLAG_NAMES["vrr_optimize"],
            enabled,
            "VRR Optimize",
        )

    def _get_refresh_rate_info(self) -> dict[str, Any]:
        """Get current and available refresh rates for the primary display.

        Returns:
            Dictionary with 'current', 'max', and 'available' refresh rates.
        """
        result: dict[str, Any] = {
            "current": None,
            "max": None,
            "available": [],
        }

        try:
            user32 = ctypes.windll.user32

            # Get current display settings
            devmode = DEVMODE()
            devmode.dmSize = ctypes.sizeof(DEVMODE)

            if user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
                result["current"] = devmode.dmDisplayFrequency
                current_width = devmode.dmPelsWidth
                current_height = devmode.dmPelsHeight

                # Enumerate all available modes at current resolution
                available_rates: set[int] = set()
                mode_num = 0
                enum_devmode = DEVMODE()
                enum_devmode.dmSize = ctypes.sizeof(DEVMODE)

                while mode_num < 500 and user32.EnumDisplaySettingsW(
                    None, mode_num, ctypes.byref(enum_devmode)
                ):
                    # Only consider modes at current resolution
                    if (
                        enum_devmode.dmPelsWidth == current_width
                        and enum_devmode.dmPelsHeight == current_height
                        and enum_devmode.dmDisplayFrequency > 0
                    ):
                        available_rates.add(enum_devmode.dmDisplayFrequency)
                    mode_num += 1

                if available_rates:
                    result["available"] = sorted(available_rates)
                    result["max"] = max(available_rates)

        except Exception as e:
            logger.debug(f"Failed to get refresh rate info: {e}")

        return result

    def _set_refresh_rate(self, target_hz: int) -> None:
        """Set the display refresh rate.

        Args:
            target_hz: Target refresh rate in Hz.
        """
        try:
            user32 = ctypes.windll.user32

            # Get current settings
            devmode = DEVMODE()
            devmode.dmSize = ctypes.sizeof(DEVMODE)

            if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
                raise RuntimeError("Failed to get current display settings")

            # Check if already at target rate
            if devmode.dmDisplayFrequency == target_hz:
                logger.info(f"Display already at {target_hz} Hz")
                return

            # Set new refresh rate
            devmode.dmDisplayFrequency = target_hz
            devmode.dmFields = DM_DISPLAYFREQUENCY

            # Test if the mode is valid
            result = user32.ChangeDisplaySettingsW(ctypes.byref(devmode), CDS_TEST)
            if result != DISP_CHANGE_SUCCESSFUL:
                raise RuntimeError(
                    f"Display mode {target_hz} Hz is not supported (error: {result})"
                )

            # Apply the change
            result = user32.ChangeDisplaySettingsW(ctypes.byref(devmode), CDS_UPDATEREGISTRY)
            if result != DISP_CHANGE_SUCCESSFUL:
                raise RuntimeError(f"Failed to set display to {target_hz} Hz (error: {result})")

            logger.info(f"Display refresh rate set to {target_hz} Hz")

        except Exception as e:
            logger.error(f"Failed to set refresh rate: {e}")
            raise

    def _set_max_refresh_rate(self) -> None:
        """Set the display to its maximum supported refresh rate."""
        info = self._get_refresh_rate_info()
        max_hz = info.get("max")
        current_hz = info.get("current")

        if not max_hz:
            logger.warning("Could not determine maximum refresh rate")
            return

        if current_hz and current_hz >= max_hz:
            logger.info(
                f"Display already at or above maximum enumerated rate ({current_hz} Hz >= {max_hz} Hz)"
            )
            return

        logger.info(f"Setting display to maximum refresh rate: {max_hz} Hz (was {current_hz} Hz)")
        self._set_refresh_rate(max_hz)

    def optimize_for_gaming(
        self, primary_max: bool = True, secondary_low: bool = True
    ) -> dict[str, Any]:
        """Optimize multi-monitor setup for gaming.

        Strategy:
        - Primary monitor: Set to maximum refresh rate for best gaming experience
        - Secondary monitors: Lower to 60Hz to reduce GPU compositor load

        This reduces the GPU work for rendering the Windows desktop on secondary
        monitors, freeing up resources for gaming on the primary display.

        Args:
            primary_max: Set primary monitor to max refresh rate (default True)
            secondary_low: Set secondary monitors to 60Hz (default True)

        Returns:
            Dictionary with results for each display.
        """
        results: dict[str, Any] = {}

        try:
            user32 = ctypes.windll.user32

            # Enumerate all display devices
            display_num = 0
            while True:
                try:
                    # DISPLAY_DEVICE structure
                    class DISPLAY_DEVICE(ctypes.Structure):
                        _fields_ = [
                            ("cb", ctypes.c_ulong),
                            ("DeviceName", ctypes.c_wchar * 32),
                            ("DeviceString", ctypes.c_wchar * 128),
                            ("StateFlags", ctypes.c_ulong),
                            ("DeviceID", ctypes.c_wchar * 128),
                            ("DeviceKey", ctypes.c_wchar * 128),
                        ]

                    dd = DISPLAY_DEVICE()
                    dd.cb = ctypes.sizeof(DISPLAY_DEVICE)

                    if not user32.EnumDisplayDevicesW(None, display_num, ctypes.byref(dd), 0):
                        break

                    # Check if this is an active display
                    DISPLAY_DEVICE_ACTIVE = 0x00000001
                    DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004

                    if dd.StateFlags & DISPLAY_DEVICE_ACTIVE:
                        is_primary = bool(dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE)
                        device_name = dd.DeviceName

                        # Get current settings for this display
                        devmode = DEVMODE()
                        devmode.dmSize = ctypes.sizeof(DEVMODE)

                        if user32.EnumDisplaySettingsW(
                            device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)
                        ):
                            current_hz = devmode.dmDisplayFrequency
                            current_width = devmode.dmPelsWidth
                            current_height = devmode.dmPelsHeight

                            # Find available refresh rates at current resolution
                            available_rates: set[int] = set()
                            mode_num = 0
                            enum_devmode = DEVMODE()
                            enum_devmode.dmSize = ctypes.sizeof(DEVMODE)

                            while mode_num < 500 and user32.EnumDisplaySettingsW(
                                device_name, mode_num, ctypes.byref(enum_devmode)
                            ):
                                if (
                                    enum_devmode.dmPelsWidth == current_width
                                    and enum_devmode.dmPelsHeight == current_height
                                    and enum_devmode.dmDisplayFrequency > 0
                                ):
                                    available_rates.add(enum_devmode.dmDisplayFrequency)
                                mode_num += 1

                            if available_rates:
                                max_hz = max(available_rates)
                                min_hz = min(available_rates)

                                if is_primary and primary_max:
                                    # Primary: set to max
                                    if current_hz < max_hz:
                                        target_hz = max_hz
                                        self._set_display_refresh_rate(device_name, target_hz)
                                        results[device_name] = {
                                            "is_primary": True,
                                            "previous": current_hz,
                                            "new": target_hz,
                                            "action": "maximized",
                                        }
                                    else:
                                        results[device_name] = {
                                            "is_primary": True,
                                            "current": current_hz,
                                            "action": "already_max",
                                        }

                                elif not is_primary and secondary_low:
                                    # Secondary: set to 60Hz (or closest available)
                                    target_hz = 60 if 60 in available_rates else min_hz
                                    if current_hz != target_hz:
                                        self._set_display_refresh_rate(device_name, target_hz)
                                        results[device_name] = {
                                            "is_primary": False,
                                            "previous": current_hz,
                                            "new": target_hz,
                                            "action": "lowered",
                                        }
                                    else:
                                        results[device_name] = {
                                            "is_primary": False,
                                            "current": current_hz,
                                            "action": "already_low",
                                        }

                    display_num += 1

                except Exception as e:
                    logger.debug(f"Error processing display {display_num}: {e}")
                    display_num += 1

        except Exception as e:
            logger.error(f"Failed to optimize displays: {e}")
            results["error"] = str(e)

        return results

    def _set_display_refresh_rate(self, device_name: str, target_hz: int) -> None:
        """Set refresh rate for a specific display.

        Args:
            device_name: Display device name (e.g., '\\\\.\\DISPLAY1')
            target_hz: Target refresh rate in Hz.
        """
        try:
            user32 = ctypes.windll.user32

            devmode = DEVMODE()
            devmode.dmSize = ctypes.sizeof(DEVMODE)

            if not user32.EnumDisplaySettingsW(
                device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)
            ):
                raise RuntimeError(f"Failed to get settings for {device_name}")

            devmode.dmDisplayFrequency = target_hz
            devmode.dmFields = DM_DISPLAYFREQUENCY

            # Test the mode
            result = user32.ChangeDisplaySettingsExW(
                device_name, ctypes.byref(devmode), None, CDS_TEST, None
            )
            if result != DISP_CHANGE_SUCCESSFUL:
                raise RuntimeError(f"Mode {target_hz} Hz not supported for {device_name}")

            # Apply the change
            result = user32.ChangeDisplaySettingsExW(
                device_name, ctypes.byref(devmode), None, CDS_UPDATEREGISTRY, None
            )
            if result != DISP_CHANGE_SUCCESSFUL:
                raise RuntimeError(f"Failed to set {device_name} to {target_hz} Hz")

            logger.info(f"Set {device_name} to {target_hz} Hz")

        except Exception as e:
            logger.error(f"Failed to set refresh rate for {device_name}: {e}")
            raise
