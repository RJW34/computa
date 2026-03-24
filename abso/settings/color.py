"""Color profile settings handler.

Manages per-game color configuration:
- ICC profile switching (sRGB vs native) via mscms.dll + registry
- NVIDIA digital vibrance via NVAPI display API
- Monitor OSD guidance (informational, shown once per monitor)

Color depth and encoding are read-only (detected via CCD DisplayConfig API,
reused from windows.py).
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import logging
import os
import winreg
from ctypes import c_int, c_uint, c_void_p, wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# ICC profile aliases -> actual filenames (shipped with Windows)
ICC_PROFILE_ALIASES: dict[str, str] = {
    "srgb": "sRGB Color Space Profile.icm",
}

# Windows color directory
COLOR_DIR = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "spool" / "drivers" / "color"

# Registry paths for ICC profile associations
# Per-monitor: HKCU\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ICM\ProfileAssociations\Display\{class_guid}\{index}
ICM_ASSOC_BASE = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ICM\ProfileAssociations\Display"
DISPLAY_CLASS_GUID = "{4d36e96e-e325-11ce-bfc1-08002be10318}"

# OSD acknowledgment file
OSD_ACK_DIR = Path.home() / ".abso"
OSD_ACK_FILE = OSD_ACK_DIR / "osd_acknowledged.json"

# NVAPI Digital Vibrance interface IDs
NVAPI_GET_DVC_INFO_EX = 0x0DBA0B04
NVAPI_SET_DVC_LEVEL_EX = 0x4A82C2B1
NVAPI_GET_DVC_INFO = 0x4085DE45
NVAPI_SET_DVC_LEVEL = 0x172409B4
NVAPI_ENUM_NVIDIA_DISPLAY_HANDLE = 0x9ABDD40D
NVAPI_GET_ASSOCIATED_NVIDIA_DISPLAY_NAME = 0x22A78B05
NVAPI_GET_ASSOCIATED_NVIDIA_DISPLAY_HANDLE = 0x35C29134
NVAPI_INITIALIZE = 0x0150E828

# DVC user-facing range (0-100, 50=default/no change)
DVC_USER_MIN = 0
DVC_USER_MAX = 100
DVC_USER_DEFAULT = 50
NVAPI_SHORT_STRING_MAX = 64

# CCD API constants (same as windows.py)
QDC_ONLY_ACTIVE_PATHS = 0x00000002
DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME = 1
DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9

# Color encoding names
COLOR_ENCODING_NAMES = {
    0: "RGB",
    1: "YCbCr444",
    2: "YCbCr422",
    3: "YCbCr420",
    4: "Intensity",
}


# =============================================================================
# CCD Structures (reuse pattern from windows.py)
# =============================================================================

class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.UINT),
        ("size", wintypes.UINT),
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
    ]


class _DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO(ctypes.Structure):
    _fields_ = [
        ("header", _DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("value", wintypes.UINT),
        ("colorEncoding", wintypes.UINT),
        ("bitsPerColorChannel", wintypes.UINT),
    ]


class _DISPLAYCONFIG_SOURCE_DEVICE_NAME(ctypes.Structure):
    _fields_ = [
        ("header", _DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("viewGdiDeviceName", ctypes.c_wchar * 32),
    ]


class _DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("statusFlags", wintypes.UINT),
    ]


class _DISPLAYCONFIG_RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", wintypes.UINT), ("Denominator", wintypes.UINT)]


class _DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("outputTechnology", wintypes.UINT),
        ("rotation", wintypes.UINT),
        ("scaling", wintypes.UINT),
        ("refreshRate", _DISPLAYCONFIG_RATIONAL),
        ("scanLineOrdering", wintypes.UINT),
        ("targetAvailable", wintypes.BOOL),
        ("statusFlags", wintypes.UINT),
    ]


class _DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    _fields_ = [
        ("sourceInfo", _DISPLAYCONFIG_PATH_SOURCE_INFO),
        ("targetInfo", _DISPLAYCONFIG_PATH_TARGET_INFO),
        ("flags", wintypes.UINT),
    ]


# =============================================================================
# DISPLAY_DEVICE structure for EnumDisplayDevices
# =============================================================================

class _DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", ctypes.c_wchar * 128),
        ("DeviceKey", ctypes.c_wchar * 128),
    ]


# =============================================================================
# NV_DISPLAY_DVC_INFO_EX structure for NVAPI digital vibrance
# =============================================================================

class _NV_DISPLAY_DVC_INFO(ctypes.Structure):
    """Legacy NvAPI_GetDVCInfo / NvAPI_SetDVCLevel struct (4 fields)."""
    _fields_ = [
        ("version", c_uint),
        ("currentLevel", c_int),
        ("minLevel", c_int),
        ("maxLevel", c_int),
    ]


class _NV_DISPLAY_DVC_INFO_EX(ctypes.Structure):
    """Extended NvAPI_GetDVCInfoEx / NvAPI_SetDVCLevelEx struct (5 fields)."""
    _fields_ = [
        ("version", c_uint),
        ("currentLevel", c_int),
        ("minLevel", c_int),
        ("maxLevel", c_int),
        ("defaultLevel", c_int),
    ]


# =============================================================================
# Helper functions
# =============================================================================

@dataclass
class DVCRange:
    """Hardware-reported digital vibrance range from NvAPI_GetDVCInfoEx."""
    min_level: int
    max_level: int
    default_level: int
    current_level: int


def _user_to_internal(user_level: int, hw: DVCRange) -> int:
    """Convert user-facing 0-100 to hardware internal level.

    Piecewise linear: user 0→hw.min, 50→hw.default, 100→hw.max.
    This respects the actual hardware range instead of assuming fixed bounds.
    """
    clamped = max(DVC_USER_MIN, min(DVC_USER_MAX, user_level))

    if clamped <= DVC_USER_DEFAULT:
        # Map [0..50] → [min..default]
        if DVC_USER_DEFAULT == 0:
            return hw.default_level
        t = clamped / DVC_USER_DEFAULT
        return round(hw.min_level + t * (hw.default_level - hw.min_level))
    else:
        # Map [50..100] → [default..max]
        span = DVC_USER_MAX - DVC_USER_DEFAULT
        if span == 0:
            return hw.max_level
        t = (clamped - DVC_USER_DEFAULT) / span
        return round(hw.default_level + t * (hw.max_level - hw.default_level))


def _internal_to_user(internal_level: int, hw: DVCRange) -> int:
    """Convert hardware internal level to user-facing 0-100.

    Piecewise linear inverse: hw.min→0, hw.default→50, hw.max→100.
    """
    if internal_level <= hw.default_level:
        span = hw.default_level - hw.min_level
        if span == 0:
            return DVC_USER_DEFAULT
        t = (internal_level - hw.min_level) / span
        return round(DVC_USER_MIN + t * DVC_USER_DEFAULT)
    else:
        span = hw.max_level - hw.default_level
        if span == 0:
            return DVC_USER_MAX
        t = (internal_level - hw.default_level) / span
        return round(DVC_USER_DEFAULT + t * (DVC_USER_MAX - DVC_USER_DEFAULT))


# =============================================================================
# Handler
# =============================================================================

class ColorProfileSettingsHandler(SettingsHandler):
    """Handles display color profile settings.

    Manages:
    - ICC profile switching (sRGB / native / custom) via mscms.dll + registry
    - NVIDIA digital vibrance via NVAPI display API
    - Monitor OSD guidance (informational, shown once per monitor model)

    Color depth and encoding are detected (read-only) via the CCD DisplayConfig
    API for informational purposes.
    """

    def __init__(self) -> None:
        self._nvapi: ctypes.WinDLL | None = None
        self._nvapi_initialized = False
        self._nvapi_query_func: Any = None
        self._interface_table: dict[str, Any] = {}
        self._mscms: ctypes.WinDLL | None = None

    # =========================================================================
    # SettingsHandler interface
    # =========================================================================

    def detect(self) -> dict[str, Any]:
        """Detect current color profile settings."""
        monitor_info = self._get_primary_monitor_info()
        color_info = self._get_display_color_info()

        return {
            "icc_profile": self._get_current_icc_profile(monitor_info),
            "digital_vibrance": self._get_digital_vibrance(),
            "color_depth_bits": color_info.get("bits_per_channel"),
            "color_encoding": color_info.get("encoding"),
            "monitor_device": monitor_info.get("device_name") if monitor_info else None,
            "monitor_id": monitor_info.get("monitor_id") if monitor_info else None,
        }

    def audit(self) -> list[Issue]:
        """Audit color settings for optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        vibrance = current.get("digital_vibrance")
        if vibrance is not None and vibrance != DVC_USER_DEFAULT:
            issues.append(Issue(
                title="NVIDIA digital vibrance is non-default",
                severity="info",
                current_value=f"{vibrance}%",
                optimal_value=f"{DVC_USER_DEFAULT}% (default)",
                explanation=(
                    "Digital vibrance is set to a non-default level. This may be intentional "
                    "for competitive games (boosted colors improve visibility) but should be "
                    "reset for color-accurate work."
                ),
                category="color",
            ))

        icc = current.get("icc_profile")
        if icc is None:
            issues.append(Issue(
                title="No ICC color profile detected",
                severity="info",
                current_value="None / default",
                optimal_value="sRGB Color Space Profile.icm (for gaming)",
                explanation=(
                    "No explicit ICC profile is set. For competitive gaming, sRGB ensures "
                    "consistent, standardized colors. For HDR/cinematic games, the monitor's "
                    "native profile is preferred."
                ),
                category="color",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply color profile settings.

        Settings dict shape:
            icc_profile: "srgb" | "native" | explicit filename
            digital_vibrance: 0-100 (50 = default/no change)
            show_osd_guidance: bool
            game_type: "competitive_fps" | "cinematic" | "emulator" | "productivity"

        Graceful degradation: if a subsystem (mscms, NVAPI) is unavailable,
        that subsystem is skipped — never fails the whole handler.
        """
        if not settings:
            return {"success": True, "error": None, "requires_reboot": False}

        # Apply user color preferences from abso.yaml (override profile defaults)
        try:
            from abso.core.config import get_config

            color_config = get_config().color
            if not color_config.manage_icc:
                settings.pop("icc_profile", None)
            elif color_config.icc_profile is not None:
                settings["icc_profile"] = color_config.icc_profile
            if not color_config.manage_vibrance:
                settings.pop("digital_vibrance", None)
            elif color_config.digital_vibrance is not None:
                settings["digital_vibrance"] = color_config.digital_vibrance
        except Exception:
            pass  # Config unavailable — use profile defaults

        errors: list[str] = []
        applied: list[str] = []
        skipped: list[str] = []

        # --- ICC Profile ---
        if "icc_profile" in settings:
            try:
                profile_alias = settings["icc_profile"]
                self._apply_icc_profile(profile_alias)
                applied.append(f"ICC profile: {profile_alias}")
            except FileNotFoundError as e:
                # Missing profile is a real error (user asked for something specific)
                logger.warning(f"Failed to set ICC profile: {e}")
                errors.append(f"ICC profile: {e}")
            except Exception as e:
                # mscms unavailable, can't identify monitor, registry failed, etc.
                # → graceful skip, not a handler failure
                logger.info(f"ICC profile not available, skipping: {e}")
                skipped.append(f"ICC profile: {e}")

        # --- Digital Vibrance ---
        if "digital_vibrance" in settings:
            level = settings["digital_vibrance"]
            try:
                self._set_digital_vibrance(level)
                applied.append(f"Digital vibrance: {level}%")
            except Exception as e:
                # NVAPI not available, no display handle, etc. → graceful skip
                logger.info(f"Digital vibrance not available, skipping: {e}")
                skipped.append(f"Digital vibrance: {e}")

        # --- OSD Guidance ---
        if settings.get("show_osd_guidance", False):
            game_type = settings.get("game_type", "competitive_fps")
            try:
                self._show_osd_guidance(game_type)
            except Exception as e:
                logger.debug(f"OSD guidance display failed: {e}")

        if skipped:
            logger.debug(f"Color subsystems skipped (not available): {skipped}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
            "applied": applied,
            "skipped": skipped,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current ICC profile and digital vibrance."""
        monitor_info = self._get_primary_monitor_info()
        return {
            "icc_profile": self._get_current_icc_profile(monitor_info),
            "digital_vibrance": self._get_digital_vibrance(),
            "monitor_class_index": monitor_info.get("class_index") if monitor_info else None,
        }

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore ICC profile and digital vibrance from backup.

        Graceful: unavailable subsystems are skipped, not treated as failures.
        Only real errors (subsystem available but operation failed) count.
        """
        try:
            errors = []

            icc = data.get("icc_profile")
            if icc is not None:
                try:
                    self._apply_icc_profile(icc)
                except FileNotFoundError as e:
                    logger.error(f"Failed to restore ICC profile: {e}")
                    errors.append(str(e))
                except Exception as e:
                    logger.info(f"ICC restore skipped (not available): {e}")

            vibrance = data.get("digital_vibrance")
            if vibrance is not None:
                try:
                    self._set_digital_vibrance(vibrance)
                except Exception as e:
                    logger.info(f"Vibrance restore skipped (not available): {e}")

            return len(errors) == 0

        except Exception as e:
            logger.error(f"Failed to restore color settings: {e}")
            return False

    # =========================================================================
    # ICC Profile Methods
    # =========================================================================

    def _get_primary_monitor_info(self) -> dict[str, Any] | None:
        """Get primary monitor device info via EnumDisplayDevicesW.

        Returns dict with:
            device_name: adapter device name (e.g. r'\\\\.\\DISPLAY1')
            class_index: registry subkey index for ICM associations
            monitor_id: monitor device ID string (e.g. 'GSM784...')
        """
        try:
            user32 = ctypes.windll.user32

            # Enumerate display adapters
            adapter_idx = 0
            while True:
                adapter = _DISPLAY_DEVICE()
                adapter.cb = ctypes.sizeof(_DISPLAY_DEVICE)

                if not user32.EnumDisplayDevicesW(None, adapter_idx, ctypes.byref(adapter), 0):
                    break

                # Check if this is the primary adapter (active + primary)
                is_active = bool(adapter.StateFlags & 0x1)  # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
                is_primary = bool(adapter.StateFlags & 0x4)  # DISPLAY_DEVICE_PRIMARY_DEVICE

                if is_active and is_primary:
                    # Get the child monitor device
                    monitor = _DISPLAY_DEVICE()
                    monitor.cb = ctypes.sizeof(_DISPLAY_DEVICE)

                    if user32.EnumDisplayDevicesW(adapter.DeviceName, 0, ctypes.byref(monitor), 0):
                        # Extract class index from DeviceKey
                        # DeviceKey looks like: \Registry\Machine\System\...\{guid}\XXXX
                        device_key = monitor.DeviceKey
                        class_index = device_key.rsplit("\\", 1)[-1] if "\\" in device_key else "0000"

                        return {
                            "device_name": adapter.DeviceName,
                            "class_index": class_index,
                            "monitor_id": monitor.DeviceID,
                            "monitor_string": monitor.DeviceString,
                        }

                adapter_idx += 1

        except Exception as e:
            logger.debug(f"Failed to get primary monitor info: {e}")

        return None

    def _get_current_icc_profile(self, monitor_info: dict[str, Any] | None = None) -> str | None:
        """Read the current active ICC profile from registry.

        The active SDR profile is the first entry in ICMProfile (REG_MULTI_SZ).
        """
        if monitor_info is None:
            monitor_info = self._get_primary_monitor_info()

        if not monitor_info:
            return None

        class_index = monitor_info.get("class_index", "0000")
        reg_path = f"{ICM_ASSOC_BASE}\\{DISPLAY_CLASS_GUID}\\{class_index}"

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                reg_path,
                0,
                winreg.KEY_READ,
            )
            try:
                value, reg_type = winreg.QueryValueEx(key, "ICMProfile")
                if reg_type == winreg.REG_MULTI_SZ and value:
                    # First entry is the active default profile
                    return value[0] if isinstance(value, list) and value else value
                if isinstance(value, str) and value:
                    return value
                return None
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.debug(f"Failed to read ICC profile from registry: {e}")
            return None

    def _resolve_profile_name(self, alias: str) -> str | None:
        """Resolve a profile alias to an actual filename.

        "srgb"    -> "sRGB Color Space Profile.icm"
        "native"  -> None (means remove/restore default)
        otherwise -> treat as literal filename
        """
        if alias == "native":
            return None

        resolved = ICC_PROFILE_ALIASES.get(alias.lower())
        if resolved:
            return resolved

        # Treat as literal filename
        return alias

    def _list_installed_profiles(self) -> list[str]:
        """List ICC profiles installed in the Windows color directory."""
        try:
            if COLOR_DIR.exists():
                return [
                    f.name for f in COLOR_DIR.iterdir()
                    if f.suffix.lower() in (".icm", ".icc")
                ]
        except Exception as e:
            logger.debug(f"Failed to list color profiles: {e}")
        return []

    def _apply_icc_profile(self, alias: str) -> None:
        """Apply an ICC profile by alias or filename.

        Tries mscms.dll WcsSetDefaultColorProfile first, falls back to
        direct registry write.
        """
        filename = self._resolve_profile_name(alias)

        if filename is None:
            # "native" -> remove explicit profile association
            self._remove_icc_profile()
            return

        # Verify profile exists
        profile_path = COLOR_DIR / filename
        if not profile_path.exists():
            raise FileNotFoundError(f"ICC profile not found: {profile_path}")

        # Try mscms.dll API first
        if self._set_icc_via_mscms(filename):
            logger.info(f"ICC profile set via mscms: {filename}")
            return

        # Fallback: direct registry write
        self._set_icc_via_registry(filename)
        logger.info(f"ICC profile set via registry: {filename}")

    def _set_icc_via_mscms(self, filename: str) -> bool:
        """Set ICC profile using mscms.dll WcsSetDefaultColorProfile."""
        try:
            if self._mscms is None:
                self._mscms = ctypes.WinDLL("mscms.dll")

            # WcsSetDefaultColorProfile(scope, deviceName, cptColorProfileType,
            #   cpstColorProfileSubType, dwProfileID, profileName)
            # scope: WCS_PROFILE_MANAGEMENT_SCOPE_CURRENT_USER = 1
            # cptColorProfileType: CPT_ICC = 1
            # cpstColorProfileSubType: CPST_RGB_WORKING_SPACE = 4 or CPST_NONE = 1
            func = self._mscms.WcsSetDefaultColorProfile
            func.argtypes = [
                wintypes.DWORD,    # scope
                ctypes.c_wchar_p,  # pDeviceName (None = default device)
                wintypes.DWORD,    # cptColorProfileType
                wintypes.DWORD,    # cpstColorProfileSubType
                wintypes.DWORD,    # dwProfileID
                ctypes.c_wchar_p,  # pProfileName
            ]
            func.restype = wintypes.BOOL

            result = func(
                1,         # WCS_PROFILE_MANAGEMENT_SCOPE_CURRENT_USER
                None,      # default display device
                1,         # CPT_ICC
                1,         # CPST_NONE (default)
                0,         # dwProfileID
                filename,  # profile filename
            )

            return bool(result)

        except (OSError, AttributeError) as e:
            logger.debug(f"mscms.dll ICC set failed: {e}")
            return False

    def _set_icc_via_registry(self, filename: str) -> None:
        """Set ICC profile via direct registry write (fallback)."""
        monitor_info = self._get_primary_monitor_info()
        if not monitor_info:
            raise RuntimeError("Cannot identify primary monitor for ICC profile")

        class_index = monitor_info.get("class_index", "0000")
        reg_path = f"{ICM_ASSOC_BASE}\\{DISPLAY_CLASS_GUID}\\{class_index}"

        try:
            key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                reg_path,
                0,
                winreg.KEY_ALL_ACCESS,
            )
            try:
                # Read existing profiles to preserve list
                existing: list[str] = []
                try:
                    value, _ = winreg.QueryValueEx(key, "ICMProfile")
                    if isinstance(value, list):
                        existing = [v for v in value if v]
                    elif isinstance(value, str) and value:
                        existing = [value]
                except FileNotFoundError:
                    pass

                # Put our profile first (active default), keep others
                new_list = [filename] + [p for p in existing if p != filename]
                winreg.SetValueEx(key, "ICMProfile", 0, winreg.REG_MULTI_SZ, new_list)

            finally:
                winreg.CloseKey(key)

        except Exception as e:
            raise RuntimeError(f"Failed to write ICC profile to registry: {e}") from e

    def _remove_icc_profile(self) -> None:
        """Remove explicit ICC profile association (restore monitor native)."""
        monitor_info = self._get_primary_monitor_info()
        if not monitor_info:
            logger.debug("Cannot identify primary monitor; skipping ICC removal")
            return

        class_index = monitor_info.get("class_index", "0000")
        reg_path = f"{ICM_ASSOC_BASE}\\{DISPLAY_CLASS_GUID}\\{class_index}"

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                reg_path,
                0,
                winreg.KEY_ALL_ACCESS,
            )
            try:
                winreg.DeleteValue(key, "ICMProfile")
            except FileNotFoundError:
                pass  # Already no profile set
            finally:
                winreg.CloseKey(key)

            logger.info("ICC profile association removed (native)")

        except FileNotFoundError:
            pass  # Registry key doesn't exist, nothing to remove
        except Exception as e:
            logger.debug(f"Failed to remove ICC profile: {e}")

    # =========================================================================
    # NVIDIA Digital Vibrance
    # =========================================================================

    def _init_nvapi(self) -> bool:
        """Initialize NVAPI for digital vibrance control."""
        if self._nvapi_initialized:
            return True

        try:
            system32 = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
            nvapi_path = system32 / "nvapi64.dll"
            if not nvapi_path.exists():
                logger.debug("nvapi64.dll not found")
                return False

            self._nvapi = ctypes.WinDLL(str(nvapi_path))

            # Get nvapi_QueryInterface
            self._nvapi_query_func = self._nvapi.nvapi_QueryInterface
            self._nvapi_query_func.restype = c_void_p
            self._nvapi_query_func.argtypes = [c_uint]

            # Initialize NVAPI
            init_ptr = self._nvapi_query_func(NVAPI_INITIALIZE)
            if not init_ptr:
                logger.debug("NvAPI_Initialize not found")
                return False

            init_func = ctypes.CFUNCTYPE(c_int)(init_ptr)
            status = init_func()
            if status != 0:
                logger.debug(f"NvAPI_Initialize failed: status={status}")
                return False

            self._nvapi_initialized = True
            return True

        except Exception as e:
            logger.debug(f"NVAPI init failed: {e}")
            return False

    def _nvapi_get_function(self, name: str, interface_id: int, restype: Any, argtypes: list[Any]) -> Any:
        """Get and cache an NVAPI function pointer."""
        if name in self._interface_table:
            return self._interface_table[name]

        if not self._nvapi_query_func:
            return None

        ptr = self._nvapi_query_func(interface_id)
        if not ptr:
            return None

        func_type = ctypes.CFUNCTYPE(restype, *argtypes)
        func = func_type(ptr)
        self._interface_table[name] = func
        return func

    @staticmethod
    def _normalize_display_name(name: str | None) -> str:
        """Normalize display names across Win32/NVAPI formats for matching."""
        if not name:
            return ""
        normalized = str(name).strip().upper().replace("/", "\\")
        while normalized.startswith("\\"):
            normalized = normalized[1:]
        normalized = normalized.replace(".\\", "")
        return normalized

    def _enumerate_nvidia_display_handles(self) -> list[c_int]:
        """Enumerate all available NVIDIA display handles."""
        handles: list[c_int] = []
        if not self._init_nvapi():
            return handles

        try:
            enum_func = self._nvapi_get_function(
                "NvAPI_EnumNvidiaDisplayHandle",
                NVAPI_ENUM_NVIDIA_DISPLAY_HANDLE,
                c_int,
                [c_uint, ctypes.POINTER(c_int)],
            )
            if not enum_func:
                return handles

            for index in range(16):
                handle = c_int(0)
                status = enum_func(index, ctypes.byref(handle))
                if status != 0:
                    break
                if handle.value != 0:
                    handles.append(handle)
        except Exception as e:
            logger.debug(f"Failed to enumerate NVIDIA display handles: {e}")

        return handles

    def _get_associated_nvidia_display_handle(self, device_name: str) -> c_int | None:
        """Map a Windows display device name to the matching NVIDIA display handle."""
        if not self._init_nvapi() or not device_name:
            return None

        normalized_target = self._normalize_display_name(device_name)

        # First try direct lookup from GDI device name -> NV display handle.
        try:
            assoc_func = self._nvapi_get_function(
                "NvAPI_GetAssociatedNvidiaDisplayHandle",
                NVAPI_GET_ASSOCIATED_NVIDIA_DISPLAY_HANDLE,
                c_int,
                [ctypes.c_char_p, ctypes.POINTER(c_int)],
            )
            if assoc_func:
                handle = c_int(0)
                status = assoc_func(device_name.encode("ascii", "ignore"), ctypes.byref(handle))
                if status == 0 and handle.value != 0:
                    return handle
        except Exception as e:
            logger.debug(f"NvAPI_GetAssociatedNvidiaDisplayHandle failed: {e}")

        # Fallback: enumerate handles and compare associated display names.
        try:
            name_func = self._nvapi_get_function(
                "NvAPI_GetAssociatedNvidiaDisplayName",
                NVAPI_GET_ASSOCIATED_NVIDIA_DISPLAY_NAME,
                c_int,
                [c_int, ctypes.POINTER(ctypes.c_char)],
            )
            if not name_func:
                return None

            for handle in self._enumerate_nvidia_display_handles():
                buffer = ctypes.create_string_buffer(NVAPI_SHORT_STRING_MAX)
                status = name_func(handle, buffer)
                if status != 0:
                    continue

                associated_name = buffer.value.decode("ascii", errors="ignore")
                if self._normalize_display_name(associated_name) == normalized_target:
                    return handle
        except Exception as e:
            logger.debug(f"NvAPI_GetAssociatedNvidiaDisplayName fallback failed: {e}")

        return None

    def _get_nvidia_display_handle(self) -> c_int | None:
        """Get NVIDIA display handle for the Windows primary display."""
        if not self._init_nvapi():
            return None

        try:
            monitor_info = self._get_primary_monitor_info()
            primary_device_name = monitor_info.get("device_name") if monitor_info else None
            if primary_device_name:
                associated = self._get_associated_nvidia_display_handle(primary_device_name)
                if associated is not None:
                    return associated

            handles = self._enumerate_nvidia_display_handles()
            if handles:
                return handles[0]

            return None

        except Exception as e:
            logger.debug(f"Failed to get NVIDIA display handle: {e}")
            return None

    def _get_dvc_range(self, handle: c_int) -> DVCRange | None:
        """Query the actual hardware DVC range from NVAPI.

        Returns the min/max/default/current levels reported by the driver,
        which vary by GPU and display.

        Tries NvAPI_GetDVCInfoEx first (includes defaultLevel), then falls
        back to the legacy NvAPI_GetDVCInfo (infers default as midpoint).
        """
        try:
            # Try Ex version first — reports defaultLevel directly
            get_func = self._nvapi_get_function(
                "NvAPI_GetDVCInfoEx",
                NVAPI_GET_DVC_INFO_EX,
                c_int,
                [c_int, c_uint, ctypes.POINTER(_NV_DISPLAY_DVC_INFO_EX)],
            )

            if get_func:
                info = _NV_DISPLAY_DVC_INFO_EX()
                info.version = ctypes.sizeof(_NV_DISPLAY_DVC_INFO_EX) | (1 << 16)

                status = get_func(handle, 0, ctypes.byref(info))
                if status == 0:
                    return DVCRange(
                        min_level=info.minLevel,
                        max_level=info.maxLevel,
                        default_level=info.defaultLevel,
                        current_level=info.currentLevel,
                    )

            # Fallback: legacy NvAPI_GetDVCInfo (4-field struct, no defaultLevel)
            # IMPORTANT: uses _NV_DISPLAY_DVC_INFO (not Ex!) — different struct size
            get_func_legacy = self._nvapi_get_function(
                "NvAPI_GetDVCInfo",
                NVAPI_GET_DVC_INFO,
                c_int,
                [c_int, c_uint, ctypes.POINTER(_NV_DISPLAY_DVC_INFO)],
            )

            if get_func_legacy:
                info_legacy = _NV_DISPLAY_DVC_INFO()
                info_legacy.version = ctypes.sizeof(_NV_DISPLAY_DVC_INFO) | (1 << 16)

                status = get_func_legacy(handle, 0, ctypes.byref(info_legacy))
                if status == 0:
                    # Legacy API has no defaultLevel — infer as midpoint.
                    # NVIDIA DVC range 0..N: 0=full desaturation, N=max boost,
                    # midpoint=normal/default colors (50% in NVCP slider).
                    inferred_default = (info_legacy.minLevel + info_legacy.maxLevel) // 2
                    return DVCRange(
                        min_level=info_legacy.minLevel,
                        max_level=info_legacy.maxLevel,
                        default_level=inferred_default,
                        current_level=info_legacy.currentLevel,
                    )

        except Exception as e:
            logger.debug(f"Failed to query DVC range: {e}")

        return None

    def _get_digital_vibrance(self) -> int | None:
        """Get current digital vibrance level (0-100, 50=default)."""
        if not self._init_nvapi():
            return None

        handle = self._get_nvidia_display_handle()
        if handle is None:
            return None

        hw = self._get_dvc_range(handle)
        if hw is None:
            return None

        return _internal_to_user(hw.current_level, hw)

    def _set_digital_vibrance(self, user_level: int) -> None:
        """Set digital vibrance level (0-100, 50=default).

        Queries the actual hardware range first, then converts the user-facing
        level to the correct internal value for this GPU+display combination.
        """
        if not self._init_nvapi():
            raise RuntimeError("NVAPI not available for digital vibrance")

        handle = self._get_nvidia_display_handle()
        if handle is None:
            raise RuntimeError("No NVIDIA display found")

        # Query actual hardware range — critical for correct conversion
        hw = self._get_dvc_range(handle)
        if hw is None:
            raise RuntimeError("Cannot query digital vibrance range from hardware")

        internal_level = _user_to_internal(user_level, hw)
        logger.debug(
            f"DVC conversion: user={user_level}% → internal={internal_level} "
            f"(hw range: {hw.min_level}..{hw.default_level}..{hw.max_level})"
        )

        # Prefer legacy NvAPI_SetDVCLevel (simpler, proven to match Get range)
        set_func_legacy = self._nvapi_get_function(
            "NvAPI_SetDVCLevel",
            NVAPI_SET_DVC_LEVEL,
            c_int,
            [c_int, c_uint, c_int],
        )

        if set_func_legacy:
            status = set_func_legacy(handle, 0, internal_level)
            if status == 0:
                logger.info(f"Digital vibrance set to {user_level}% (internal={internal_level})")
                return

        # Fallback: NvAPI_SetDVCLevelEx (newer API, struct-based)
        set_func = self._nvapi_get_function(
            "NvAPI_SetDVCLevelEx",
            NVAPI_SET_DVC_LEVEL_EX,
            c_int,
            [c_int, c_uint, ctypes.POINTER(_NV_DISPLAY_DVC_INFO_EX)],
        )

        if set_func:
            info = _NV_DISPLAY_DVC_INFO_EX()
            info.version = ctypes.sizeof(_NV_DISPLAY_DVC_INFO_EX) | (1 << 16)
            info.currentLevel = internal_level

            status = set_func(handle, 0, ctypes.byref(info))
            if status == 0:
                logger.info(f"Digital vibrance set to {user_level}% via Ex API")
                return

        raise RuntimeError("Failed to set digital vibrance (no working API)")

    # =========================================================================
    # Display Color Info (CCD API — read-only)
    # =========================================================================

    def _get_display_color_info(self) -> dict[str, Any]:
        """Get color depth and encoding for the primary display via CCD API."""
        result: dict[str, Any] = {
            "bits_per_channel": None,
            "encoding": None,
        }

        try:
            targets = self._get_active_display_targets()
            if not targets:
                return result

            monitor_info = self._get_primary_monitor_info()
            primary_device_name = monitor_info.get("device_name") if monitor_info else None
            selected = self._select_primary_target(
                targets=targets,
                primary_device_name=primary_device_name,
            )
            if not selected:
                return result

            info = _DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
            info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO
            info.header.size = ctypes.sizeof(info)
            info.header.adapterId = selected["adapter_id"]
            info.header.id = selected["target_id"]

            status = ctypes.windll.user32.DisplayConfigGetDeviceInfo(ctypes.byref(info))
            if status == 0:
                result["bits_per_channel"] = info.bitsPerColorChannel
                result["encoding"] = COLOR_ENCODING_NAMES.get(
                    info.colorEncoding, f"Unknown({info.colorEncoding})"
                )

        except Exception as e:
            logger.debug(f"CCD color info detection failed: {e}")

        return result

    @classmethod
    def _select_primary_target(
        cls,
        targets: list[dict[str, Any]],
        primary_device_name: str | None,
    ) -> dict[str, Any] | None:
        """Select CCD target matching the primary display device."""
        if not targets:
            return None

        normalized_primary = cls._normalize_display_name(primary_device_name)
        if normalized_primary:
            for target in targets:
                normalized_source = cls._normalize_display_name(target.get("source_device_name"))
                if normalized_source and normalized_source == normalized_primary:
                    return target

        return targets[0]

    @staticmethod
    def _get_source_device_name(adapter_id: _LUID, source_id: int) -> str | None:
        """Resolve CCD source to GDI device name (e.g. '\\\\.\\DISPLAY1')."""
        try:
            user32 = ctypes.windll.user32

            name_info = _DISPLAYCONFIG_SOURCE_DEVICE_NAME()
            name_info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
            name_info.header.size = ctypes.sizeof(name_info)
            name_info.header.adapterId = adapter_id
            name_info.header.id = source_id

            status = user32.DisplayConfigGetDeviceInfo(ctypes.byref(name_info))
            if status == 0 and name_info.viewGdiDeviceName:
                return str(name_info.viewGdiDeviceName)
        except Exception as e:
            logger.debug(f"Failed to resolve source device name for source_id={source_id}: {e}")

        return None

    @staticmethod
    def _get_active_display_targets() -> list[dict[str, Any]]:
        """Enumerate active display targets via QueryDisplayConfig."""
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

        paths = (_DISPLAYCONFIG_PATH_INFO * num_paths.value)()
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

        targets: list[dict[str, Any]] = []
        for i in range(num_paths.value):
            path = paths[i]
            source = path.sourceInfo
            target = path.targetInfo
            targets.append({
                "adapter_id": target.adapterId,
                "target_id": target.id,
                "source_id": source.id,
                "source_device_name": ColorProfileSettingsHandler._get_source_device_name(
                    source.adapterId,
                    source.id,
                ),
            })
        return targets

    # =========================================================================
    # Monitor OSD Guidance
    # =========================================================================

    def _show_osd_guidance(self, game_type: str) -> None:
        """Show monitor OSD recommendations if not previously acknowledged."""
        monitor_info = self._get_primary_monitor_info()
        if not monitor_info:
            return

        monitor_id = monitor_info.get("monitor_id", "")

        # Try to import OSD data
        try:
            from abso.data.monitor_osd import get_osd_recommendations
        except ImportError:
            logger.debug("Monitor OSD data module not available")
            return

        result = get_osd_recommendations(monitor_id, game_type)
        if result is None:
            return

        display_name, recommendations = result

        # Check if already acknowledged for this monitor
        if self._is_osd_acknowledged(monitor_id):
            return

        # Log recommendations (the CLI renderer will pick these up)
        logger.info(f"Monitor OSD recommendations for {display_name} ({game_type}):")
        for rec in recommendations:
            logger.info(f"  {rec.setting}: {rec.value} — {rec.reason}")

        # Mark as acknowledged
        self._acknowledge_osd(monitor_id)

    @staticmethod
    def _is_osd_acknowledged(monitor_id: str) -> bool:
        """Check if OSD guidance was already shown for this monitor."""
        # Extract model pattern from monitor ID (first 6 chars of the monitor portion)
        model_key = _extract_model_key(monitor_id)
        if not model_key:
            return False

        try:
            if OSD_ACK_FILE.exists():
                data = json.loads(OSD_ACK_FILE.read_text(encoding="utf-8"))
                return bool(data.get(model_key, False))
        except Exception:
            pass

        return False

    @staticmethod
    def _acknowledge_osd(monitor_id: str) -> None:
        """Mark OSD guidance as acknowledged for this monitor model."""
        model_key = _extract_model_key(monitor_id)
        if not model_key:
            return

        try:
            OSD_ACK_DIR.mkdir(parents=True, exist_ok=True)

            data: dict[str, bool] = {}
            if OSD_ACK_FILE.exists():
                with contextlib.suppress(Exception):
                    data = json.loads(OSD_ACK_FILE.read_text(encoding="utf-8"))

            data[model_key] = True
            OSD_ACK_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

        except Exception as e:
            logger.debug(f"Failed to save OSD acknowledgment: {e}")


def _extract_model_key(monitor_id: str) -> str | None:
    """Extract monitor model pattern from device ID string.

    Device IDs look like: MONITOR\\GSM7847\\{guid}...
    We extract the manufacturer+model portion (e.g. 'GSM7847').
    """
    if not monitor_id:
        return None

    parts = monitor_id.replace("/", "\\").split("\\")
    for part in parts:
        # Look for the manufacturer+model pattern (3 letters + digits)
        if len(part) >= 6 and part[:3].isalpha() and any(c.isdigit() for c in part[3:]):
            return part

    return None
