"""NVAPI DRS (Driver Settings) integration for safe NVIDIA profile management.

This module provides direct access to NVIDIA's DRS API via ctypes, allowing
safe modification of individual per-game driver settings without wiping
the entire profile database (which NPI's import does).

Key capabilities:
- Create/modify per-game profiles
- Set G-Sync, Low Latency Mode, V-Sync, frame cap per-application
- Read current settings
- All changes are non-destructive (only modifies targeted settings)

Reference: NVAPI SDK documentation
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_char,
    c_int,
    c_uint,
    c_uint8,
    c_uint16,
    c_uint32,
    c_void_p,
    c_wchar,
    c_wchar_p,
    create_unicode_buffer,
    pointer,
    sizeof,
)
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# =============================================================================
# NVAPI Constants
# =============================================================================

NVAPI_MAX_PHYSICAL_GPUS = 64
NVAPI_SHORT_STRING_MAX = 64
NVAPI_LONG_STRING_MAX = 256
NVAPI_UNICODE_STRING_MAX = 2048
NVAPI_SETTING_MAX_VALUES = 100

# DRS-specific constants
NVDRS_GLOBAL_PROFILE_NAME = "Base Profile"


class NvAPIStatus(IntEnum):
    """NVAPI return status codes."""
    OK = 0
    ERROR = -1
    LIBRARY_NOT_FOUND = -2
    NO_IMPLEMENTATION = -3
    API_NOT_INITIALIZED = -4
    INVALID_ARGUMENT = -5
    NVIDIA_DEVICE_NOT_FOUND = -6
    END_ENUMERATION = -7
    INVALID_HANDLE = -8
    INCOMPATIBLE_STRUCT_VERSION = -9
    HANDLE_INVALIDATED = -10
    OPENGL_CONTEXT_NOT_CURRENT = -11
    INVALID_POINTER = -14
    NO_GL_EXPERT = -12
    INSTRUMENTATION_DISABLED = -13
    NO_GL_NSIGHT = -15
    EXPECTED_LOGICAL_GPU_HANDLE = -100
    EXPECTED_PHYSICAL_GPU_HANDLE = -101
    EXPECTED_DISPLAY_HANDLE = -102
    INVALID_COMBINATION = -103
    NOT_SUPPORTED = -104
    PORTID_NOT_FOUND = -105
    EXPECTED_UNATTACHED_DISPLAY_HANDLE = -106
    INVALID_PERF_LEVEL = -107
    DEVICE_BUSY = -108
    NV_PERSIST_FILE_NOT_FOUND = -109
    PERSIST_DATA_NOT_FOUND = -110
    EXPECTED_TV_DISPLAY = -111
    EXPECTED_TV_DISPLAY_ON_DCONNECTOR = -112
    NO_ACTIVE_SLI_TOPOLOGY = -113
    SLI_RENDERING_MODE_NOTALLOWED = -114
    EXPECTED_DIGITAL_FLAT_PANEL = -115
    ARGUMENT_EXCEED_MAX_SIZE = -116
    DEVICE_SWITCHING_NOT_ALLOWED = -117
    TESTING_CLOCKS_NOT_SUPPORTED = -118
    UNKNOWN_UNDERSCAN_CONFIG = -119
    TIMEOUT_RECONFIGURING_GPU_TOPO = -120
    DATA_NOT_FOUND = -121
    EXPECTED_ANALOG_DISPLAY = -122
    NO_VIDLINK = -123
    REQUIRES_REBOOT = -124
    INVALID_HYBRID_MODE = -125
    MIXED_TARGET_TYPES = -126
    SYSWOW64_NOT_SUPPORTED = -127
    IMPLICIT_SET_GPU_TOPOLOGY_CHANGE_NOT_ALLOWED = -128
    REQUEST_USER_TO_CLOSE_NON_MIGRATABLE_APPS = -129
    OUT_OF_MEMORY = -130
    WAS_STILL_DRAWING = -131
    FILE_NOT_FOUND = -132
    TOO_MANY_UNIQUE_STATE_OBJECTS = -133
    INVALID_CALL = -134
    D3D10_1_LIBRARY_NOT_FOUND = -135
    FUNCTION_NOT_FOUND = -136
    INVALID_USER_PRIVILEGE = -137
    EXPECTED_NON_PRIMARY_DISPLAY_HANDLE = -138
    EXPECTED_COMPUTE_GPU_HANDLE = -139
    STEREO_NOT_INITIALIZED = -140
    STEREO_REGISTRY_ACCESS_FAILED = -141
    STEREO_REGISTRY_PROFILE_TYPE_NOT_SUPPORTED = -142
    STEREO_REGISTRY_VALUE_NOT_SUPPORTED = -143
    STEREO_NOT_ENABLED = -144
    STEREO_NOT_TURNED_ON = -145
    STEREO_INVALID_DEVICE_INTERFACE = -146
    STEREO_PARAMETER_OUT_OF_RANGE = -147
    STEREO_FRUSTUM_ADJUST_MODE_NOT_SUPPORTED = -148
    TOPO_NOT_POSSIBLE = -149
    MODE_CHANGE_FAILED = -150
    D3D11_LIBRARY_NOT_FOUND = -151
    INVALID_ADDRESS = -152
    STRING_TOO_SMALL = -153
    MATCHING_DEVICE_NOT_FOUND = -154
    DRIVER_RUNNING = -155
    DRIVER_NOTRUNNING = -156
    ERROR_DRIVER_RELOAD_REQUIRED = -157
    SET_NOT_ALLOWED = -158
    ADVANCED_DISPLAY_TOPOLOGY_REQUIRED = -159
    SETTING_NOT_FOUND = -160
    SETTING_SIZE_TOO_LARGE = -161
    TOO_MANY_SETTINGS_IN_PROFILE = -162
    PROFILE_NOT_FOUND = -163
    PROFILE_NAME_IN_USE = -164
    PROFILE_NAME_EMPTY = -165
    EXECUTABLE_NOT_FOUND = -166
    EXECUTABLE_ALREADY_IN_USE = -167
    DATATYPE_MISMATCH = -168
    PROFILE_REMOVED = -169
    UNREGISTERED_RESOURCE = -170
    ID_OUT_OF_RANGE = -171
    DISPLAYCONFIG_VALIDATION_FAILED = -172
    DPMST_CHANGED = -173
    INSUFFICIENT_BUFFER = -174
    ACCESS_DENIED = -175
    MOSAIC_NOT_ACTIVE = -176
    SHARE_RESOURCE_RELOCATED = -177
    REQUEST_USER_TO_DISABLE_DWM = -178
    D3D_DEVICE_LOST = -179
    INVALID_CONFIGURATION = -180
    STEREO_HANDSHAKE_NOT_DONE = -181
    EXECUTABLE_PATH_IS_AMBIGUOUS = -182
    DEFAULT_STEREO_PROFILE_IS_NOT_DEFINED = -183
    DEFAULT_STEREO_PROFILE_DOES_NOT_EXIST = -184
    CLUSTER_ALREADY_EXISTS = -185
    DPMST_DISPLAY_ID_EXPECTED = -186
    INVALID_DISPLAY_ID = -187
    STREAM_IS_OUT_OF_SYNC = -188
    INCOMPATIBLE_AUDIO_DRIVER = -189
    VALUE_ALREADY_SET = -190
    TIMEOUT = -191
    GPU_WORKSTATION_FEATURE_INCOMPLETE = -192
    STEREO_INIT_ACTIVATION_NOT_DONE = -193
    SYNC_NOT_ACTIVE = -194
    SYNC_MASTER_NOT_FOUND = -195
    INVALID_SYNC_TOPOLOGY = -196
    ECID_SIGN_ALGO_UNSUPPORTED = -197
    ECID_KEY_VERIFICATION_FAILED = -198
    FIRMWARE_OUT_OF_DATE = -199
    FIRMWARE_REVISION_NOT_SUPPORTED = -200


class NvDRSSettingType(IntEnum):
    """DRS setting data types."""
    DWORD = 0
    BINARY = 1
    STRING = 2
    WSTRING = 3


class NvDRSSettingLocation(IntEnum):
    """DRS setting location."""
    CURRENT_PROFILE = 0
    GLOBAL_PROFILE = 1
    BASE_PROFILE = 2
    DEFAULT_PROFILE = 3


# =============================================================================
# NVAPI Structures
# =============================================================================

class NvAPI_ShortString(Structure):
    """Short string buffer."""
    _fields_ = [("value", c_char * NVAPI_SHORT_STRING_MAX)]


# NvAPI_UnicodeString is an array of uint16, not wchar
NvAPI_UnicodeString = c_uint16 * NVAPI_UNICODE_STRING_MAX


def MAKE_NVAPI_VERSION(struct: type, version: int) -> int:
    """Create NVAPI version field value."""
    return ctypes.sizeof(struct) | (version << 16)


class NVDRS_GPU_SUPPORT(Structure):
    """GPU support flags."""
    _fields_ = [("geforce", c_uint32, 1),
                ("quadro", c_uint32, 1),
                ("nvs", c_uint32, 1),
                ("reserved", c_uint32, 29)]


class NVDRS_BINARY_SETTING(Structure):
    """Binary setting value."""
    _fields_ = [
        ("valueLength", c_uint32),
        ("valueData", c_uint8 * 4096),
    ]


class NVDRS_SETTING_VALUE(ctypes.Union):
    """Setting value union."""
    _fields_ = [
        ("u32Value", c_uint32),
        ("binaryValue", NVDRS_BINARY_SETTING),
        ("wszValue", NvAPI_UnicodeString),
    ]


class NVDRS_SETTING(Structure):
    """DRS setting structure."""
    _fields_ = [
        ("version", c_uint32),
        ("settingName", NvAPI_UnicodeString),
        ("settingId", c_uint32),
        ("settingType", c_int),
        ("settingLocation", c_int),
        ("isCurrentPredefined", c_uint32),
        ("isPredefinedValid", c_uint32),
        ("predefinedValue", NVDRS_SETTING_VALUE),
        ("currentValue", NVDRS_SETTING_VALUE),
    ]


NVDRS_SETTING_VER = MAKE_NVAPI_VERSION(NVDRS_SETTING, 1)


class NVDRS_APPLICATION_V4(Structure):
    """DRS application structure (version 4)."""
    _fields_ = [
        ("version", c_uint32),
        ("isPredefined", c_uint32),
        ("appName", NvAPI_UnicodeString),
        ("userFriendlyName", NvAPI_UnicodeString),
        ("launcher", NvAPI_UnicodeString),
        ("fileInFolder", NvAPI_UnicodeString),
        ("isMetro", c_uint32),
        ("isCommandLine", c_uint32),
        ("commandLine", NvAPI_UnicodeString),
    ]


NVDRS_APPLICATION_VER4 = MAKE_NVAPI_VERSION(NVDRS_APPLICATION_V4, 4)


# Try earlier versions if V4 doesn't work
class NVDRS_APPLICATION_V3(Structure):
    """DRS application structure (version 3)."""
    _fields_ = [
        ("version", c_uint32),
        ("isPredefined", c_uint32),
        ("appName", NvAPI_UnicodeString),
        ("userFriendlyName", NvAPI_UnicodeString),
        ("launcher", NvAPI_UnicodeString),
        ("fileInFolder", NvAPI_UnicodeString),
    ]


NVDRS_APPLICATION_VER3 = MAKE_NVAPI_VERSION(NVDRS_APPLICATION_V3, 3)


class NVDRS_APPLICATION_V2(Structure):
    """DRS application structure (version 2)."""
    _fields_ = [
        ("version", c_uint32),
        ("isPredefined", c_uint32),
        ("appName", NvAPI_UnicodeString),
        ("userFriendlyName", NvAPI_UnicodeString),
        ("launcher", NvAPI_UnicodeString),
    ]


NVDRS_APPLICATION_VER2 = MAKE_NVAPI_VERSION(NVDRS_APPLICATION_V2, 2)


class NVDRS_APPLICATION_V1(Structure):
    """DRS application structure (version 1)."""
    _fields_ = [
        ("version", c_uint32),
        ("isPredefined", c_uint32),
        ("appName", NvAPI_UnicodeString),
        ("userFriendlyName", NvAPI_UnicodeString),
    ]


NVDRS_APPLICATION_VER1 = MAKE_NVAPI_VERSION(NVDRS_APPLICATION_V1, 1)


class NVDRS_PROFILE(Structure):
    """DRS profile structure."""
    _fields_ = [
        ("version", c_uint32),
        ("profileName", NvAPI_UnicodeString),
        ("gpuSupport", NVDRS_GPU_SUPPORT),
        ("isPredefined", c_uint32),
        ("numOfApps", c_uint32),
        ("numOfSettings", c_uint32),
    ]


NVDRS_PROFILE_VER = MAKE_NVAPI_VERSION(NVDRS_PROFILE, 1)


def _str_to_nvapi_unicode(s: str, arr: NvAPI_UnicodeString) -> None:
    """Convert Python string to NvAPI_UnicodeString array."""
    encoded = s.encode("utf-16-le")
    for i, byte_pair in enumerate(range(0, min(len(encoded), (NVAPI_UNICODE_STRING_MAX - 1) * 2), 2)):
        arr[i] = encoded[byte_pair] | (encoded[byte_pair + 1] << 8)
    # Null terminate
    arr[min(len(s), NVAPI_UNICODE_STRING_MAX - 1)] = 0


def _nvapi_unicode_to_str(arr: NvAPI_UnicodeString) -> str:
    """Convert NvAPI_UnicodeString array to Python string."""
    chars = []
    for val in arr:
        if val == 0:
            break
        chars.append(chr(val))
    return "".join(chars)


# =============================================================================
# NVAPI Function Signatures
# =============================================================================

# Handle types
NvDRSSessionHandle = c_void_p
NvDRSProfileHandle = c_void_p


# =============================================================================
# NVAPI DRS Wrapper Class
# =============================================================================

@dataclass
class NVAPISetting:
    """Represents an NVIDIA driver setting."""
    setting_id: int
    name: str
    value: int | str | bytes
    setting_type: NvDRSSettingType = NvDRSSettingType.DWORD


class NVAPIError(Exception):
    """NVAPI operation error."""
    def __init__(self, message: str, status: int | None = None):
        self.status = status
        self.status_name = NvAPIStatus(status).name if status is not None else "UNKNOWN"
        super().__init__(f"{message} (Status: {self.status_name}, Code: {status})")


class NVAPIDRS:
    """NVAPI DRS (Driver Settings) interface.

    Provides safe, non-destructive access to NVIDIA driver settings.
    Unlike NPI import, this modifies only the targeted settings.
    """

    def __init__(self):
        """Initialize NVAPI DRS interface."""
        self._nvapi: ctypes.CDLL | None = None
        self._session: NvDRSSessionHandle | None = None
        self._initialized = False
        self._interface_table: dict[str, Any] = {}

    def _find_nvapi_dll(self) -> Path | None:
        """Find nvapi64.dll location."""
        # Check System32 first (most common)
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        nvapi_path = system32 / "nvapi64.dll"
        if nvapi_path.exists():
            return nvapi_path

        # Check driver store
        driver_store = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "DriverStore" / "FileRepository"
        if driver_store.exists():
            for folder in driver_store.iterdir():
                if folder.is_dir() and folder.name.startswith("nv"):
                    nvapi_candidate = folder / "nvapi64.dll"
                    if nvapi_candidate.exists():
                        return nvapi_candidate

        return None

    def _query_interface(self, interface_id: int) -> c_void_p:
        """Query NVAPI interface by ID.

        NVAPI uses a query interface pattern where you pass an interface ID
        and get back a function pointer. The nvapi_QueryInterface function
        is the only exported function from nvapi64.dll.
        """
        if not self._nvapi:
            raise NVAPIError("NVAPI not loaded")

        if not hasattr(self, "_query_interface_func"):
            # Get nvapi_QueryInterface by name (it's the only export)
            self._query_interface_func = self._nvapi.nvapi_QueryInterface
            self._query_interface_func.restype = c_void_p
            self._query_interface_func.argtypes = [c_uint]

        ptr = self._query_interface_func(interface_id)
        if not ptr:
            raise NVAPIError(f"Interface 0x{interface_id:08X} not found", NvAPIStatus.FUNCTION_NOT_FOUND)
        return ptr

    def _get_function(self, name: str, interface_id: int, restype, argtypes) -> Any:
        """Get and cache an NVAPI function."""
        if name in self._interface_table:
            return self._interface_table[name]

        ptr = self._query_interface(interface_id)
        func_type = ctypes.CFUNCTYPE(restype, *argtypes)
        func = func_type(ptr)
        self._interface_table[name] = func
        return func

    def initialize(self) -> bool:
        """Initialize NVAPI.

        Returns:
            True if initialization succeeded.

        Raises:
            NVAPIError: If NVAPI cannot be loaded or initialized.
        """
        if self._initialized:
            return True

        # Find and load nvapi64.dll
        nvapi_path = self._find_nvapi_dll()
        if not nvapi_path:
            raise NVAPIError("nvapi64.dll not found", NvAPIStatus.LIBRARY_NOT_FOUND)

        try:
            self._nvapi = ctypes.WinDLL(str(nvapi_path))
        except OSError as e:
            raise NVAPIError(f"Failed to load nvapi64.dll: {e}", NvAPIStatus.LIBRARY_NOT_FOUND)

        # NvAPI_Initialize - interface ID 0x0150E828
        try:
            init_func = self._get_function(
                "NvAPI_Initialize",
                0x0150E828,
                c_int,
                []
            )
            status = init_func()
            if status != NvAPIStatus.OK:
                raise NVAPIError("NvAPI_Initialize failed", status)
        except Exception as e:
            raise NVAPIError(f"Failed to initialize NVAPI: {e}")

        self._initialized = True
        logger.info("NVAPI initialized successfully")
        return True

    def create_session(self) -> None:
        """Create a DRS session.

        Must be called before any DRS operations.
        """
        if not self._initialized:
            self.initialize()

        if self._session:
            return  # Already have a session

        # NvAPI_DRS_CreateSession - interface ID 0x0694D52E
        create_session = self._get_function(
            "NvAPI_DRS_CreateSession",
            0x0694D52E,
            c_int,
            [POINTER(NvDRSSessionHandle)]
        )

        session = NvDRSSessionHandle()
        status = create_session(byref(session))
        if status != NvAPIStatus.OK:
            raise NVAPIError("Failed to create DRS session", status)

        self._session = session
        logger.debug("DRS session created")

    def load_settings(self) -> None:
        """Load current driver settings into the session."""
        if not self._session:
            self.create_session()

        # NvAPI_DRS_LoadSettings - interface ID 0x375DBD6B
        load_settings = self._get_function(
            "NvAPI_DRS_LoadSettings",
            0x375DBD6B,
            c_int,
            [NvDRSSessionHandle]
        )

        status = load_settings(self._session)
        if status != NvAPIStatus.OK:
            raise NVAPIError("Failed to load DRS settings", status)

        logger.debug("DRS settings loaded")

    def save_settings(self) -> None:
        """Save modified settings back to the driver."""
        if not self._session:
            raise NVAPIError("No active DRS session")

        # NvAPI_DRS_SaveSettings - interface ID 0xFCBC7E14
        save_settings = self._get_function(
            "NvAPI_DRS_SaveSettings",
            0xFCBC7E14,
            c_int,
            [NvDRSSessionHandle]
        )

        status = save_settings(self._session)
        if status != NvAPIStatus.OK:
            raise NVAPIError("Failed to save DRS settings", status)

        logger.info("DRS settings saved")

    def destroy_session(self) -> None:
        """Destroy the DRS session and clean up."""
        if not self._session:
            return

        # NvAPI_DRS_DestroySession - interface ID 0xDAD9CFF8
        destroy_session = self._get_function(
            "NvAPI_DRS_DestroySession",
            0xDAD9CFF8,
            c_int,
            [NvDRSSessionHandle]
        )

        status = destroy_session(self._session)
        self._session = None

        if status != NvAPIStatus.OK:
            logger.warning(f"DRS session destroy returned status {status}")
        else:
            logger.debug("DRS session destroyed")

    def find_profile_by_name(self, profile_name: str) -> NvDRSProfileHandle | None:
        """Find a profile by name.

        Args:
            profile_name: Name of the profile to find.

        Returns:
            Profile handle or None if not found.
        """
        if not self._session:
            self.create_session()
            self.load_settings()

        # NvAPI_DRS_FindProfileByName - interface ID 0x7E4A9A0B
        find_profile = self._get_function(
            "NvAPI_DRS_FindProfileByName",
            0x7E4A9A0B,
            c_int,
            [NvDRSSessionHandle, c_wchar_p, POINTER(NvDRSProfileHandle)]
        )

        profile_handle = NvDRSProfileHandle()
        status = find_profile(self._session, profile_name, byref(profile_handle))

        if status == NvAPIStatus.PROFILE_NOT_FOUND:
            return None
        elif status != NvAPIStatus.OK:
            raise NVAPIError(f"Failed to find profile '{profile_name}'", status)

        return profile_handle

    def get_base_profile(self) -> NvDRSProfileHandle:
        """Get the base (global) profile handle.

        Returns:
            Handle to the base profile.
        """
        if not self._session:
            self.create_session()
            self.load_settings()

        # NvAPI_DRS_GetBaseProfile - interface ID 0xDA8466A0
        get_base = self._get_function(
            "NvAPI_DRS_GetBaseProfile",
            0xDA8466A0,
            c_int,
            [NvDRSSessionHandle, POINTER(NvDRSProfileHandle)]
        )

        profile_handle = NvDRSProfileHandle()
        status = get_base(self._session, byref(profile_handle))

        if status != NvAPIStatus.OK:
            raise NVAPIError("Failed to get base profile", status)

        return profile_handle

    def enumerate_profiles(self) -> list[dict[str, Any]]:
        """Enumerate all profiles in the system.

        Returns:
            List of profile info dicts with 'name', 'handle', 'is_predefined', 'num_apps'.
        """
        if not self._session:
            self.create_session()
            self.load_settings()

        # NvAPI_DRS_EnumProfiles - interface ID 0xBC371EE0
        enum_profiles = self._get_function(
            "NvAPI_DRS_EnumProfiles",
            0xBC371EE0,
            c_int,
            [NvDRSSessionHandle, c_uint32, POINTER(NvDRSProfileHandle)]
        )

        # NvAPI_DRS_GetProfileInfo - interface ID 0x61CD6FD6
        get_profile_info = self._get_function(
            "NvAPI_DRS_GetProfileInfo",
            0x61CD6FD6,
            c_int,
            [NvDRSSessionHandle, NvDRSProfileHandle, POINTER(NVDRS_PROFILE)]
        )

        profiles = []
        index = 0

        while True:
            profile_handle = NvDRSProfileHandle()
            status = enum_profiles(self._session, index, byref(profile_handle))

            if status == NvAPIStatus.END_ENUMERATION:
                break
            elif status != NvAPIStatus.OK:
                logger.debug(f"Profile enumeration stopped at index {index}: status {status}")
                break

            # Get profile info
            profile_info = NVDRS_PROFILE()
            profile_info.version = NVDRS_PROFILE_VER
            info_status = get_profile_info(self._session, profile_handle, byref(profile_info))

            if info_status == NvAPIStatus.OK:
                name = _nvapi_unicode_to_str(profile_info.profileName)
                profiles.append({
                    "name": name,
                    "handle": profile_handle,
                    "is_predefined": bool(profile_info.isPredefined),
                    "num_apps": profile_info.numOfApps,
                })

            index += 1

        return profiles

    def delete_profile(self, profile_handle: NvDRSProfileHandle) -> bool:
        """Delete a profile.

        Args:
            profile_handle: Handle to the profile to delete.

        Returns:
            True if deleted successfully.

        Note:
            Cannot delete predefined (NVIDIA system) profiles.
        """
        if not self._session:
            self.create_session()
            self.load_settings()

        # NvAPI_DRS_DeleteProfile - interface ID 0x17093206
        delete_profile = self._get_function(
            "NvAPI_DRS_DeleteProfile",
            0x17093206,
            c_int,
            [NvDRSSessionHandle, NvDRSProfileHandle]
        )

        status = delete_profile(self._session, profile_handle)

        if status == NvAPIStatus.OK:
            return True
        elif status == NvAPIStatus.PROFILE_NOT_FOUND:
            logger.warning("Profile not found for deletion")
            return False
        else:
            logger.error(f"Failed to delete profile: status {status}")
            return False

    def create_profile(self, profile_name: str) -> NvDRSProfileHandle:
        """Create a new profile.

        Args:
            profile_name: Name for the new profile.

        Returns:
            Handle to the created profile.
        """
        if not self._session:
            self.create_session()
            self.load_settings()

        # NvAPI_DRS_CreateProfile - interface ID 0xCC176068
        create_profile = self._get_function(
            "NvAPI_DRS_CreateProfile",
            0xCC176068,
            c_int,
            [NvDRSSessionHandle, POINTER(NVDRS_PROFILE), POINTER(NvDRSProfileHandle)]
        )

        profile_info = NVDRS_PROFILE()
        profile_info.version = NVDRS_PROFILE_VER
        _str_to_nvapi_unicode(profile_name, profile_info.profileName)
        profile_info.gpuSupport.geforce = 1
        profile_info.gpuSupport.quadro = 1
        profile_info.isPredefined = 0

        profile_handle = NvDRSProfileHandle()
        status = create_profile(self._session, byref(profile_info), byref(profile_handle))

        if status == NvAPIStatus.PROFILE_NAME_IN_USE:
            # Profile already exists, find it instead
            return self.find_profile_by_name(profile_name)
        elif status != NvAPIStatus.OK:
            raise NVAPIError(f"Failed to create profile '{profile_name}'", status)

        logger.info(f"Created profile: {profile_name}")
        return profile_handle

    def add_application_to_profile(
        self,
        profile_handle: NvDRSProfileHandle,
        app_name: str,
        friendly_name: str | None = None
    ) -> None:
        """Add an application (executable) to a profile.

        Args:
            profile_handle: Handle to the profile.
            app_name: Executable name (e.g., "game.exe").
            friendly_name: Optional display name.
        """
        if not self._session:
            raise NVAPIError("No active DRS session")

        # NvAPI_DRS_CreateApplication - interface ID 0x4347A9DE
        create_app = self._get_function(
            "NvAPI_DRS_CreateApplication",
            0x4347A9DE,
            c_int,
            [NvDRSSessionHandle, NvDRSProfileHandle, c_void_p]  # Use c_void_p for flexibility
        )

        # Try different application structure versions (newest first)
        app_structs = [
            (NVDRS_APPLICATION_V4, NVDRS_APPLICATION_VER4),
            (NVDRS_APPLICATION_V3, NVDRS_APPLICATION_VER3),
            (NVDRS_APPLICATION_V2, NVDRS_APPLICATION_VER2),
            (NVDRS_APPLICATION_V1, NVDRS_APPLICATION_VER1),
        ]

        last_status = None
        for app_class, app_version in app_structs:
            app_info = app_class()
            app_info.version = app_version
            _str_to_nvapi_unicode(app_name, app_info.appName)
            _str_to_nvapi_unicode(friendly_name or app_name, app_info.userFriendlyName)
            app_info.isPredefined = 0

            # Set additional fields if they exist
            if hasattr(app_info, 'launcher'):
                _str_to_nvapi_unicode("", app_info.launcher)
            if hasattr(app_info, 'fileInFolder'):
                _str_to_nvapi_unicode("", app_info.fileInFolder)
            if hasattr(app_info, 'isMetro'):
                app_info.isMetro = 0
            if hasattr(app_info, 'isCommandLine'):
                app_info.isCommandLine = 0
            if hasattr(app_info, 'commandLine'):
                _str_to_nvapi_unicode("", app_info.commandLine)

            status = create_app(self._session, profile_handle, byref(app_info))

            if status == NvAPIStatus.OK:
                logger.info(f"Added application to profile: {app_name} (using V{app_version >> 16})")
                return
            elif status == NvAPIStatus.EXECUTABLE_ALREADY_IN_USE:
                logger.debug(f"Application {app_name} already in a profile")
                return
            elif status == NvAPIStatus.INCOMPATIBLE_STRUCT_VERSION:
                last_status = status
                continue  # Try older version
            else:
                raise NVAPIError(f"Failed to add application '{app_name}'", status)

        # All versions failed - this can happen with newer drivers
        # Log at debug level - the higher-level code handles the fallback
        logger.debug(
            f"NVAPI app binding failed for '{app_name}' (driver struct version mismatch). "
            f"Falling back to NPI or manual instructions."
        )
        # Store the failure for reporting
        if not hasattr(self, '_app_binding_failures'):
            self._app_binding_failures = []
        self._app_binding_failures.append(app_name)

    def get_setting(
        self,
        profile_handle: NvDRSProfileHandle,
        setting_id: int
    ) -> int | None:
        """Get a DWORD setting value from a profile.

        Args:
            profile_handle: Handle to the profile.
            setting_id: The setting ID to read.

        Returns:
            Setting value or None if not set.
        """
        if not self._session:
            raise NVAPIError("No active DRS session")

        # NvAPI_DRS_GetSetting - interface ID 0x73BF8338
        get_setting = self._get_function(
            "NvAPI_DRS_GetSetting",
            0x73BF8338,
            c_int,
            [NvDRSSessionHandle, NvDRSProfileHandle, c_uint32, POINTER(NVDRS_SETTING)]
        )

        setting = NVDRS_SETTING()
        setting.version = NVDRS_SETTING_VER

        status = get_setting(self._session, profile_handle, setting_id, byref(setting))

        if status == NvAPIStatus.SETTING_NOT_FOUND:
            return None
        elif status != NvAPIStatus.OK:
            raise NVAPIError(f"Failed to get setting 0x{setting_id:08X}", status)

        return setting.currentValue.u32Value

    def set_setting(
        self,
        profile_handle: NvDRSProfileHandle,
        setting_id: int,
        value: int
    ) -> None:
        """Set a DWORD setting value in a profile.

        Args:
            profile_handle: Handle to the profile.
            setting_id: The setting ID to modify.
            value: The new value to set.
        """
        if not self._session:
            raise NVAPIError("No active DRS session")

        # NvAPI_DRS_SetSetting - interface ID 0x577DD202
        set_setting = self._get_function(
            "NvAPI_DRS_SetSetting",
            0x577DD202,
            c_int,
            [NvDRSSessionHandle, NvDRSProfileHandle, POINTER(NVDRS_SETTING)]
        )

        setting = NVDRS_SETTING()
        setting.version = NVDRS_SETTING_VER
        setting.settingId = setting_id
        setting.settingType = NvDRSSettingType.DWORD
        setting.currentValue.u32Value = value

        status = set_setting(self._session, profile_handle, byref(setting))

        if status != NvAPIStatus.OK:
            raise NVAPIError(f"Failed to set setting 0x{setting_id:08X} = {value}", status)

        logger.debug(f"Set setting 0x{setting_id:08X} = {value}")

    def delete_setting(
        self,
        profile_handle: NvDRSProfileHandle,
        setting_id: int
    ) -> None:
        """Delete a setting from a profile (revert to default).

        Args:
            profile_handle: Handle to the profile.
            setting_id: The setting ID to delete.
        """
        if not self._session:
            raise NVAPIError("No active DRS session")

        # NvAPI_DRS_DeleteProfileSetting - interface ID 0xE4A26362
        delete_setting = self._get_function(
            "NvAPI_DRS_DeleteProfileSetting",
            0xE4A26362,
            c_int,
            [NvDRSSessionHandle, NvDRSProfileHandle, c_uint32]
        )

        status = delete_setting(self._session, profile_handle, setting_id)

        if status == NvAPIStatus.SETTING_NOT_FOUND:
            return  # Already not set
        elif status != NvAPIStatus.OK:
            raise NVAPIError(f"Failed to delete setting 0x{setting_id:08X}", status)

        logger.debug(f"Deleted setting 0x{setting_id:08X}")

    def unload(self) -> None:
        """Unload NVAPI and clean up all resources."""
        if self._session:
            self.destroy_session()

        if self._initialized and self._nvapi:
            # NvAPI_Unload - interface ID 0xD22BDD7E
            try:
                unload = self._get_function(
                    "NvAPI_Unload",
                    0xD22BDD7E,
                    c_int,
                    []
                )
                unload()
            except Exception as e:
                logger.debug(f"NVAPI unload error (non-critical): {e}")

        self._initialized = False
        self._nvapi = None
        self._interface_table.clear()
        logger.debug("NVAPI unloaded")

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        self.create_session()
        self.load_settings()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is None:
            # No exception - save settings
            try:
                self.save_settings()
            except Exception as e:
                logger.error(f"Failed to save settings: {e}")
        self.destroy_session()
        return False


# =============================================================================
# High-Level DRS Manager
# =============================================================================

class DRSProfileManager:
    """High-level interface for managing NVIDIA driver profiles.

    This class provides a simple API for common operations like
    setting G-Sync, Low Latency Mode, V-Sync, etc. for specific games.
    """

    # Setting IDs - verified against NVIDIA nvapi/NvApiDriverSettings.h
    # https://github.com/NVIDIA/nvapi
    SETTING_IDS = {
        # V-Sync and frame control
        "vsync_mode": 0x00A879CF,           # VSYNCMODE_ID
        "vsync_tear_control": 0x005A375C,   # VSYNCTEARCONTROL_ID
        "frame_rate_limiter": 0x10835002,   # FRL_FPS_ID (v1 and v3 use same ID)
        "frame_rate_limiter_v3": 0x10835002, # FRL_FPS_ID

        # Low Latency Mode / Pre-rendered frames (same underlying setting)
        "low_latency_mode": 0x007BA09E,     # PRERENDERLIMIT_ID
        "prerendered_frames": 0x007BA09E,   # PRERENDERLIMIT_ID (alias)

        # G-Sync / VRR
        "vrr_app_override": 0x10A879CF,     # VRR_APP_OVERRIDE_ID
        "vrr_app_override_request_state": 0x10A879AC,  # VRR_APP_OVERRIDE_REQUEST_STATE_ID
        "vrr_mode": 0x1194F158,             # VRR_MODE_ID (Enable G-SYNC globally)
        "vrr_request_state": 0x1094F1F7,    # VRRREQUESTSTATE_ID
        "vrr_requested_state": 0x1094F1F7,  # VRRREQUESTSTATE_ID (backwards-compat alias)
        "vsync_vrr_control": 0x10A879CE,    # VSYNCVRRCONTROL_ID

        # Power management
        "power_management": 0x1057EB71,     # PREFERRED_PSTATE_ID
        "preferred_pstate": 0x1057EB71,     # PREFERRED_PSTATE_ID (alias)

        # Threading
        "threaded_optimization": 0x20C1221E, # OGL_THREAD_CONTROL_ID

        # Shader cache
        "shader_cache": 0x00198FFF,         # PS_SHADERDISKCACHE_ID

        # Triple buffering
        "triple_buffering": 0x20FDD1F9,     # OGL_TRIPLE_BUFFER_ID
    }

    # Setting value mappings
    VSYNC_VALUES = {
        # NvApiDriverSettings.h: EValues_VSYNCMODE
        "off": 0x08416747,           # VSYNCMODE_FORCEOFF
        "on": 0x47814940,            # VSYNCMODE_FORCEON
        "use_3d_app": 0x60925292,    # VSYNCMODE_PASSIVE
        "passive": 0x60925292,       # VSYNCMODE_PASSIVE
        "adaptive": 0x18888888,      # VSYNCMODE_VIRTUAL
        "adaptive_half": 0x32610244, # VSYNCMODE_FLIPINTERVAL2
        # Fast Sync is represented by VSYNCTEARCONTROL_ENABLE.
        # Keep this alias for compatibility; callers should also set
        # vsync_tear_control=enable for deterministic behavior.
        "fast": 0x47814940,          # VSYNCMODE_FORCEON
    }

    LOW_LATENCY_VALUES = {
        "off": 0x00000000,
        "on": 0x00000001,
        "ultra": 0x00000002,
    }

    VRR_OVERRIDE_VALUES = {
        "allow": 0x00000000,       # Enable G-Sync
        "force_off": 0x00000001,   # Force G-Sync OFF
        "disallow": 0x00000002,    # Disallow VRR
        "ulmb": 0x00000003,        # Use ULMB instead
        "fixed_refresh": 0x00000004,  # Fixed refresh
    }

    VRR_MODE_VALUES = {
        "off": 0x00000000,                       # VRR_MODE_DISABLED
        "disabled": 0x00000000,                  # VRR_MODE_DISABLED
        "on": 0x00000001,                        # VRR_MODE_FULLSCREEN_ONLY
        "enabled": 0x00000001,                   # VRR_MODE_FULLSCREEN_ONLY
        "fullscreen": 0x00000001,                # VRR_MODE_FULLSCREEN_ONLY
        "fullscreen_only": 0x00000001,           # VRR_MODE_FULLSCREEN_ONLY
        "fullscreen_and_windowed": 0x00000002,   # VRR_MODE_FULLSCREEN_AND_WINDOWED
        "windowed": 0x00000002,                  # VRR_MODE_FULLSCREEN_AND_WINDOWED
    }

    POWER_MGMT_VALUES = {
        "adaptive": 0x00000000,
        "prefer_max_performance": 0x00000001,
        "driver_controlled": 0x00000002,
    }

    THREADED_OPT_VALUES = {
        "auto": 0x00000000,
        "on": 0x00000001,
        "off": 0x00000002,
    }

    SHADER_CACHE_VALUES = {
        "off": 0x00000000,
        "on": 0x00000001,
        "unlimited": 0x00000002,
    }

    TRIPLE_BUFFER_VALUES = {
        "off": 0x00000000,
        "on": 0x00000001,
    }

    VSYNC_TEAR_CONTROL_VALUES = {
        # NvApiDriverSettings.h: EValues_VSYNCTEARCONTROL
        "disable": 0x96861077,  # VSYNCTEARCONTROL_DISABLE
        "off": 0x96861077,      # VSYNCTEARCONTROL_DISABLE
        "enable": 0x99941284,   # VSYNCTEARCONTROL_ENABLE
        "on": 0x99941284,       # VSYNCTEARCONTROL_ENABLE
    }

    def __init__(self):
        """Initialize the profile manager."""
        self._drs = NVAPIDRS()

    @staticmethod
    def _get_profile_num_apps(drs: NVAPIDRS, profile_name: str) -> int | None:
        """Get application count for a profile by name."""
        try:
            for info in drs.enumerate_profiles():
                if info.get("name") == profile_name:
                    return int(info.get("num_apps", 0))
        except Exception:
            return None
        return None

    def apply_settings_to_app(
        self,
        app_executable: str,
        settings: dict[str, Any],
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        """Apply NVIDIA settings to a specific application.

        Args:
            app_executable: The executable name (e.g., "game.exe").
            settings: Dictionary of setting names to values.
            profile_name: Optional custom profile name. If None, uses
                         "ABSO - {app_name}" format.

        Returns:
            Dictionary with results of each setting change.

        Example:
            manager.apply_settings_to_app(
                "Rivals2.exe",
                {
                    "vsync": "on",
                    "low_latency_mode": "on",
                    "vrr_app_override": "allow",
                    "power_management": "prefer_max_performance",
                }
            )
        """
        profile_name_was_explicit = profile_name is not None
        if profile_name is None:
            app_base = app_executable.rsplit(".", 1)[0]
            profile_name = f"ABSO - {app_base}"

        results = {
            "profile_name": profile_name,
            "app_executable": app_executable,
            "settings_applied": {},
            "errors": [],
        }

        try:
            with self._drs as drs:
                # Find or create the profile
                profile = drs.find_profile_by_name(profile_name)
                if not profile:
                    profile = drs.create_profile(profile_name)
                    results["profile_created"] = True
                else:
                    results["profile_created"] = False

                existing_profile_num_apps = 0
                if not results["profile_created"]:
                    existing_profile_num_apps = self._get_profile_num_apps(drs, profile_name) or 0

                # Add the application to the profile (may fail on newer drivers)
                drs._app_binding_failures = []  # Reset tracking
                drs.add_application_to_profile(profile, app_executable)

                # Detect silent binding failure cases (e.g., executable already owned by
                # a different profile). These can leave a profile with zero bound apps.
                profile_num_apps = self._get_profile_num_apps(drs, profile_name)
                if profile_num_apps == 0 and app_executable not in drs._app_binding_failures:
                    drs._app_binding_failures.append(app_executable)

                # Check if app binding succeeded
                if drs._app_binding_failures:
                    if (
                        profile_name_was_explicit
                        and existing_profile_num_apps > 0
                        and (profile_num_apps or 0) > 0
                    ):
                        # Existing predefined profile likely already has executable binding.
                        # Driver may reject CreateApplication updates with struct-version errors.
                        results["app_bound"] = True
                        results["app_binding_note"] = (
                            f"Using existing executable binding for profile '{profile_name}'. "
                            "Skipped CreateApplication update."
                        )
                        drs._app_binding_failures = []
                    else:
                        results["app_bound"] = False

                        # NPI GUI launch disabled — popping up a window during
                        # headless profile apply is confusing.  Provide manual
                        # instructions instead.
                        results["app_binding_note"] = (
                            f"Profile '{profile_name}' created with all settings configured. "
                            f"Automatic app binding unavailable on this driver version. "
                            f"To activate: NVCP > Manage 3D Settings > Program Settings > "
                            f"Add '{app_executable}' > Select '{profile_name}'"
                        )
                        results["manual_instructions"] = self.get_manual_binding_instructions(
                            profile_name, app_executable
                        )
                else:
                    results["app_bound"] = True

                # Apply each setting
                for setting_name, value in settings.items():
                    try:
                        self._apply_single_setting(drs, profile, setting_name, value)
                        results["settings_applied"][setting_name] = value
                    except Exception as e:
                        results["errors"].append({
                            "setting": setting_name,
                            "error": str(e),
                        })
                        logger.error(f"Failed to apply {setting_name}: {e}")

        except Exception as e:
            results["fatal_error"] = str(e)
            logger.error(f"Failed to apply settings: {e}")
            raise

        return results

    def apply_settings_to_profile(
        self,
        app_executables: list[str],
        settings: dict[str, Any],
        profile_name: str,
    ) -> dict[str, Any]:
        """Apply NVIDIA settings to a profile and bind multiple executables.

        This creates (or reuses) a single profile, applies settings once,
        and binds all provided executables to that profile.

        Args:
            app_executables: List of executable names.
            settings: Dictionary of setting names to values.
            profile_name: Profile name to create/use.

        Returns:
            Dictionary with results of each setting change and binding status.
        """
        results = {
            "profile_name": profile_name,
            "executables": app_executables,
            "settings_applied": {},
            "errors": [],
        }

        if not app_executables:
            results["errors"].append({"setting": "executables", "error": "No executables provided"})
            return results

        try:
            with self._drs as drs:
                # Find or create the profile
                profile = drs.find_profile_by_name(profile_name)
                if not profile:
                    profile = drs.create_profile(profile_name)
                    results["profile_created"] = True
                else:
                    results["profile_created"] = False

                existing_profile_num_apps = 0
                if not results["profile_created"]:
                    existing_profile_num_apps = self._get_profile_num_apps(drs, profile_name) or 0

                # Bind all applications to the profile
                drs._app_binding_failures = []
                for exe in app_executables:
                    drs.add_application_to_profile(profile, exe)

                # Detect silent binding failure where profile still has no executables.
                profile_num_apps = self._get_profile_num_apps(drs, profile_name)
                if profile_num_apps == 0 and not drs._app_binding_failures:
                    drs._app_binding_failures.extend(app_executables)

                if drs._app_binding_failures:
                    if existing_profile_num_apps > 0 and (profile_num_apps or 0) > 0:
                        results["app_bound"] = True
                        results["app_binding_note"] = (
                            f"Using existing executable binding for profile '{profile_name}'. "
                            "Skipped CreateApplication updates."
                        )
                        drs._app_binding_failures = []
                    else:
                        results["app_bound"] = False
                        results["app_binding_failures"] = list(drs._app_binding_failures)

                        first_failed = drs._app_binding_failures[0]
                        results["app_binding_note"] = (
                            f"Profile '{profile_name}' created with all settings configured. "
                            f"Automatic app binding unavailable on this driver version. "
                            f"To activate: NVCP > Manage 3D Settings > Program Settings > "
                            f"Add executables to '{profile_name}'."
                        )
                        results["manual_instructions"] = self.get_manual_binding_instructions(
                            profile_name, first_failed
                        )
                else:
                    results["app_bound"] = True

                # Apply each setting once
                for setting_name, value in settings.items():
                    try:
                        self._apply_single_setting(drs, profile, setting_name, value)
                        results["settings_applied"][setting_name] = value
                    except Exception as e:
                        results["errors"].append({
                            "setting": setting_name,
                            "error": str(e),
                        })
                        logger.error(f"Failed to apply {setting_name}: {e}")

        except Exception as e:
            results["fatal_error"] = str(e)
            logger.error(f"Failed to apply settings: {e}")
            raise

        return results

    def apply_settings_to_global(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply NVIDIA settings to the global/base profile.

        Args:
            settings: Dictionary of setting names to values.

        Returns:
            Dictionary with settings_applied and errors.
        """
        results = {
            "profile_name": NVDRS_GLOBAL_PROFILE_NAME,
            "settings_applied": {},
            "errors": [],
        }

        if not settings:
            return results

        try:
            with self._drs as drs:
                global_profile = drs.get_base_profile()

                for setting_name, value in settings.items():
                    try:
                        self._apply_single_setting(drs, global_profile, setting_name, value)
                        results["settings_applied"][setting_name] = value
                    except Exception as e:
                        results["errors"].append({
                            "setting": setting_name,
                            "error": str(e),
                        })
                        logger.error(f"Failed to apply global setting {setting_name}: {e}")

        except Exception as e:
            results["fatal_error"] = str(e)
            logger.error(f"Failed to apply global settings: {e}")
            raise

        return results

    def _apply_single_setting(
        self,
        drs: NVAPIDRS,
        profile: NvDRSProfileHandle,
        setting_name: str,
        value: Any
    ) -> None:
        """Apply a single setting to a profile."""
        # Map setting name to ID and value
        setting_id, numeric_value = self._resolve_setting(setting_name, value)

        if numeric_value is None:
            # Delete the setting (revert to default)
            drs.delete_setting(profile, setting_id)
        else:
            drs.set_setting(profile, setting_id, numeric_value)

    def _resolve_setting(self, setting_name: str, value: Any) -> tuple[int, int | None]:
        """Resolve a setting name and value to ID and numeric value.

        Args:
            setting_name: The setting name (e.g., "vsync", "low_latency_mode").
            value: The value (can be string like "on" or numeric).

        Returns:
            Tuple of (setting_id, numeric_value). numeric_value is None if
            the setting should be deleted.
        """
        # Normalize setting name
        name_lower = setting_name.lower().replace("-", "_").replace(" ", "_")

        # Handle special cases and aliases
        setting_map = {
            "vsync": ("vsync_mode", self.VSYNC_VALUES),
            "v_sync": ("vsync_mode", self.VSYNC_VALUES),
            "vsync_mode": ("vsync_mode", self.VSYNC_VALUES),
            "low_latency_mode": ("low_latency_mode", self.LOW_LATENCY_VALUES),
            "llm": ("low_latency_mode", self.LOW_LATENCY_VALUES),
            "nvidia_reflex": ("low_latency_mode", self.LOW_LATENCY_VALUES),
            "vrr_app_override": ("vrr_app_override", self.VRR_OVERRIDE_VALUES),
            "vrr_app_override_request_state": ("vrr_app_override_request_state", self.VRR_OVERRIDE_VALUES),
            "gsync": ("vrr_app_override", self.VRR_OVERRIDE_VALUES),
            "g_sync": ("vrr_app_override", self.VRR_OVERRIDE_VALUES),
            "vrr_mode": ("vrr_mode", self.VRR_MODE_VALUES),
            "global_vrr_mode": ("vrr_mode", self.VRR_MODE_VALUES),
            "global_gsync_mode": ("vrr_mode", self.VRR_MODE_VALUES),
            "global_gsync": ("vrr_mode", self.VRR_MODE_VALUES),
            "vrr_request_state": ("vrr_request_state", self.VRR_MODE_VALUES),
            "vrr_requested_state": ("vrr_request_state", self.VRR_MODE_VALUES),
            "power_management": ("power_management", self.POWER_MGMT_VALUES),
            "power_management_mode": ("power_management", self.POWER_MGMT_VALUES),
            "threaded_optimization": ("threaded_optimization", self.THREADED_OPT_VALUES),
            "shader_cache": ("shader_cache", self.SHADER_CACHE_VALUES),
            "triple_buffering": ("triple_buffering", self.TRIPLE_BUFFER_VALUES),
            # Frame rate limiter - accepts FPS value or "off"
            "max_frame_rate": ("frame_rate_limiter_v3", {"off": 0, "disabled": 0}),
            "frame_rate_limit": ("frame_rate_limiter_v3", {"off": 0, "disabled": 0}),
            "fps_cap": ("frame_rate_limiter_v3", {"off": 0, "disabled": 0}),
            "vsync_tear_control": ("vsync_tear_control", self.VSYNC_TEAR_CONTROL_VALUES),
            "vsync_vrr_control": ("vsync_vrr_control", {"disable": 0, "off": 0, "enable": 1, "on": 1}),
        }

        if name_lower in setting_map:
            canonical_name, value_map = setting_map[name_lower]
        else:
            # Try direct lookup
            canonical_name = name_lower
            value_map = None

        # Get setting ID
        if canonical_name not in self.SETTING_IDS:
            raise ValueError(f"Unknown setting: {setting_name}")
        setting_id = self.SETTING_IDS[canonical_name]

        # Handle "default" or None value
        if value is None or (isinstance(value, str) and value.lower() == "default"):
            return setting_id, None

        # Convert value to numeric
        if isinstance(value, int):
            numeric_value = value
        elif isinstance(value, str):
            value_lower = value.lower()
            if value_map and value_lower in value_map:
                numeric_value = value_map[value_lower]
            else:
                # Try parsing as hex or int
                try:
                    if value_lower.startswith("0x"):
                        numeric_value = int(value_lower, 16)
                    else:
                        numeric_value = int(value_lower)
                except ValueError:
                    raise ValueError(f"Invalid value '{value}' for setting '{setting_name}'")
        else:
            raise ValueError(f"Unsupported value type for setting '{setting_name}': {type(value)}")

        return setting_id, numeric_value

    def get_app_settings(
        self,
        app_executable: str | None = None,
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        """Get current NVIDIA settings for an application/profile.

        Args:
            app_executable: The executable name.
            profile_name: Optional explicit profile name. When provided, this
                profile is read directly.

        Returns:
            Dictionary of current settings.
        """
        results = {}

        try:
            with self._drs as drs:
                profile = None
                selected_profile_name = None

                if profile_name:
                    profile = drs.find_profile_by_name(profile_name)
                    selected_profile_name = profile_name

                # Look for profile containing this app
                # For now, try ABSO profile first when no explicit profile was requested.
                if not profile and app_executable:
                    app_base = app_executable.rsplit(".", 1)[0]
                    selected_profile_name = f"ABSO - {app_base}"
                    profile = drs.find_profile_by_name(selected_profile_name)

                if not profile:
                    # Check global profile
                    profile = drs.get_base_profile()
                    results["_profile"] = "Base Profile"
                else:
                    results["_profile"] = selected_profile_name

                # Read key settings
                for name, setting_id in self.SETTING_IDS.items():
                    try:
                        value = drs.get_setting(profile, setting_id)
                        if value is not None:
                            results[name] = value
                    except Exception:
                        pass  # Setting not available

        except Exception as e:
            results["_error"] = str(e)

        return results

    def set_gsync_for_app(self, app_executable: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable G-Sync for a specific application.

        Args:
            app_executable: The executable name.
            enabled: True to enable G-Sync, False to disable.

        Returns:
            Results dictionary.
        """
        return self.apply_settings_to_app(
            app_executable,
            {"vrr_app_override": "allow" if enabled else "force_off"}
        )

    def set_low_latency_for_app(
        self,
        app_executable: str,
        mode: str = "on"
    ) -> dict[str, Any]:
        """Set Low Latency Mode for a specific application.

        Args:
            app_executable: The executable name.
            mode: "off", "on", or "ultra".

        Returns:
            Results dictionary.
        """
        return self.apply_settings_to_app(
            app_executable,
            {"low_latency_mode": mode}
        )

    def list_profiles(
        self,
        include_predefined: bool = False,
        include_empty: bool = True,
    ) -> list[dict[str, Any]]:
        """List all NVIDIA profiles.

        Args:
            include_predefined: Include NVIDIA's predefined system profiles.
            include_empty: Include profiles with no applications assigned.

        Returns:
            List of profile info dicts.
        """
        with self._drs as drs:
            all_profiles = drs.enumerate_profiles()

        # Filter
        result = []
        for p in all_profiles:
            if not include_predefined and p.get("is_predefined"):
                continue
            if not include_empty and p.get("num_apps", 0) == 0:
                continue
            result.append(p)

        return result

    def delete_profiles_by_name(
        self,
        names: list[str],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Delete profiles by name.

        Args:
            names: List of profile names to delete.
            dry_run: If True, don't actually delete, just report what would be deleted.

        Returns:
            Dict with 'deleted', 'skipped', 'errors' lists.
        """
        result = {
            "deleted": [],
            "skipped": [],
            "errors": [],
            "dry_run": dry_run,
        }

        # Protected profiles that should never be deleted
        protected_prefixes = [
            "Base Profile",
            "NVIDIA",
            "_GLOBAL_DRIVER_PROFILE",
        ]

        with self._drs as drs:
            for name in names:
                # Check if protected
                is_protected = any(name.startswith(p) for p in protected_prefixes)
                if is_protected:
                    result["skipped"].append({"name": name, "reason": "protected system profile"})
                    continue

                # Find the profile
                try:
                    profile = drs.find_profile_by_name(name)
                    if not profile:
                        result["errors"].append({"name": name, "error": "not found"})
                        continue

                    if dry_run:
                        result["deleted"].append(name)
                    else:
                        if drs.delete_profile(profile):
                            result["deleted"].append(name)
                            logger.info(f"Deleted profile: {name}")
                        else:
                            result["errors"].append({"name": name, "error": "delete failed"})

                except Exception as e:
                    result["errors"].append({"name": name, "error": str(e)})

            # Save if we actually deleted anything
            if not dry_run and result["deleted"]:
                drs.save_settings()

        return result

    def cleanup_unused_profiles(
        self,
        keep_patterns: list[str] | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Clean up unused/unknown game profiles.

        Removes profiles for games that aren't in our known list, keeping
        only ABSO profiles and user-specified patterns.

        Args:
            keep_patterns: List of name patterns to keep (case-insensitive substring match).
            dry_run: If True, just report what would be deleted without deleting.

        Returns:
            Dict with cleanup results.
        """
        keep_patterns = keep_patterns or []

        # Always keep these
        always_keep = [
            "Base Profile",
            "NVIDIA",
            "_GLOBAL",
            "ABSO",
            # Games the user might care about
            "Rivals",
            "Slippi",
            "Dolphin",
            "Melee",
            "Diablo",
            "Ryujinx",
        ]
        keep_patterns.extend(always_keep)

        with self._drs as drs:
            all_profiles = drs.enumerate_profiles()

        to_delete = []
        to_keep = []

        for p in all_profiles:
            name = p.get("name", "")

            # Skip predefined NVIDIA profiles
            if p.get("is_predefined"):
                to_keep.append({"name": name, "reason": "predefined"})
                continue

            # Check if matches any keep pattern
            should_keep = False
            for pattern in keep_patterns:
                if pattern.lower() in name.lower():
                    should_keep = True
                    to_keep.append({"name": name, "reason": f"matches '{pattern}'"})
                    break

            if not should_keep:
                to_delete.append(name)

        result = {
            "total_profiles": len(all_profiles),
            "to_delete": len(to_delete),
            "to_keep": len(to_keep),
            "dry_run": dry_run,
            "delete_list": to_delete[:50],  # First 50 for preview
            "delete_list_truncated": len(to_delete) > 50,
        }

        if not dry_run and to_delete:
            delete_result = self.delete_profiles_by_name(to_delete, dry_run=False)
            result["deleted"] = delete_result["deleted"]
            result["errors"] = delete_result["errors"]

        return result

    def _try_npi_for_app_binding(self, profile_name: str, app_executable: str) -> bool:
        """Try to launch NPI for easy app binding.

        When NVAPI app binding fails, this launches NPI so the user can
        easily add the application to the profile manually.

        Args:
            profile_name: The profile to bind to.
            app_executable: The executable to add.

        Returns:
            True if NPI was launched successfully.
        """
        try:
            from abso.settings.nvidia.npi import NPIManager

            npi = NPIManager()
            if npi.is_available():
                logger.info(f"Launching NPI for app binding: {app_executable} -> {profile_name}")
                return npi.launch_for_app_binding(profile_name, app_executable)
            else:
                logger.debug("NPI not available for app binding fallback")
                return False
        except Exception as e:
            logger.warning(f"Failed to launch NPI for app binding: {e}")
            return False

    @staticmethod
    def open_nvidia_control_panel() -> bool:
        """Open NVIDIA Control Panel to the 3D settings page.

        Returns:
            True if NVCP was launched, False if not available.
        """
        import subprocess
        import os

        # Try different methods to open NVCP
        nvcp_commands = [
            # Modern Windows - ms-settings URI (opens to NVCP if installed)
            ["cmd", "/c", "start", "ms-settings:display-advancedgraphics"],
            # Direct NVCP launch via control panel
            ["control", "desk.cpl,,3"],
            # Try nvcplui.exe directly
            [os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"),
                          "NVIDIA Corporation", "Control Panel Client", "nvcplui.exe")],
        ]

        for cmd in nvcp_commands:
            try:
                subprocess.Popen(cmd, shell=False)
                logger.info(f"Launched NVIDIA Control Panel via: {cmd[0]}")
                return True
            except (FileNotFoundError, OSError):
                continue

        logger.warning("Could not find NVIDIA Control Panel")
        return False

    @staticmethod
    def get_manual_binding_instructions(profile_name: str, app_executable: str) -> str:
        """Get instructions for manually binding an app to an NVIDIA profile.

        Args:
            profile_name: The name of the ABSO profile.
            app_executable: The executable to bind.

        Returns:
            Formatted instructions string.
        """
        return f"""
NVIDIA Profile Manual Binding Instructions
==========================================

Your NVIDIA profile '{profile_name}' has been created with all settings configured.
However, automatic application binding failed due to driver compatibility.

To complete the setup, please add '{app_executable}' to the profile manually:

Option 1: NVIDIA Control Panel
------------------------------
1. Right-click desktop > NVIDIA Control Panel
2. Go to: Manage 3D Settings > Program Settings
3. Click "Add" and browse to select '{app_executable}'
4. Under "Use the settings for this program:", select '{profile_name}'
5. Click "Apply"

Option 2: NVIDIA Profile Inspector (Recommended)
------------------------------------------------
1. Download NPI from: https://github.com/Orbmu2k/nvidiaProfileInspector
2. Launch nvidiaProfileInspector.exe
3. Find '{profile_name}' in the profile dropdown
4. In the "Application name" section, click the green + button
5. Enter: {app_executable}
6. Click "Apply changes"

The profile settings are already configured - you just need to link the executable.
"""


# =============================================================================
# Module-level convenience functions
# =============================================================================

_manager: DRSProfileManager | None = None


def get_manager() -> DRSProfileManager:
    """Get the global DRS profile manager instance."""
    global _manager
    if _manager is None:
        _manager = DRSProfileManager()
    return _manager


def apply_nvidia_settings(
    app_executable: str,
    settings: dict[str, Any],
    profile_name: str | None = None,
) -> dict[str, Any]:
    """Apply NVIDIA settings to an application.

    Convenience function that uses the global manager.

    Args:
        app_executable: The executable name (e.g., "game.exe").
        settings: Dictionary of settings to apply.
        profile_name: Optional custom profile name.

    Returns:
        Results dictionary.
    """
    return get_manager().apply_settings_to_app(app_executable, settings, profile_name)


def set_gsync(app_executable: str, enabled: bool) -> dict[str, Any]:
    """Enable or disable G-Sync for an application.

    Args:
        app_executable: The executable name.
        enabled: True to enable, False to disable.

    Returns:
        Results dictionary.
    """
    return get_manager().set_gsync_for_app(app_executable, enabled)


def set_low_latency(app_executable: str, mode: str = "on") -> dict[str, Any]:
    """Set Low Latency Mode for an application.

    Args:
        app_executable: The executable name.
        mode: "off", "on", or "ultra".

    Returns:
        Results dictionary.
    """
    return get_manager().set_low_latency_for_app(app_executable, mode)
