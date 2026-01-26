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
        # Log a warning but don't fail - the profile still works, just needs manual app binding
        logger.warning(
            f"Could not automatically bind application '{app_name}' to profile "
            f"(driver struct version mismatch). The profile settings are saved. "
            f"Please add the application to the profile manually using NVIDIA Control Panel "
            f"or NVIDIA Profile Inspector."
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

    # Setting IDs (from NVIDIA's documentation and NPI)
    SETTING_IDS = {
        # V-Sync and frame control
        "vsync_mode": 0x00A879CF,  # VSync Mode
        "vsync_behavior": 0x00A879AC,  # VSync Behavior Flags
        "vsync_smooth_afi": 0x00A879AB,  # Smooth AFR
        "frame_rate_limiter": 0x00A879C4,  # Frame Rate Limiter (v1)
        "frame_rate_limiter_v3": 0x00A879C9,  # Frame Rate Limiter (v3)
        "frame_rate_limiter_gps": 0x00A879C8,  # FRL GPS Control

        # Low Latency Mode
        "low_latency_mode": 0x00A879CE,  # Low Latency Mode (Reflex/LLM)
        "prerendered_frames": 0x00A879CF,  # Maximum Pre-Rendered Frames

        # G-Sync / VRR
        "vrr_app_override": 0x10A879CF,  # Per-app G-Sync control
        "vrr_requested_state": 0x10A879AC,  # VRR requested state
        "gsync_app_mode": 0x10A879CF,  # G-Sync application mode

        # Power management
        "power_management": 0x00A879CF,  # Power management mode
        "preferred_pstate": 0x00A879E1,  # Preferred P-State

        # Threading
        "threaded_optimization": 0x00A879E2,  # Threaded Optimization

        # Shader cache
        "shader_cache": 0x00A879A6,  # Shader Cache

        # Triple buffering
        "triple_buffering": 0x00A879A7,  # Triple Buffering

        # Anisotropic filtering
        "aniso_filter": 0x00A879A0,  # Anisotropic Filtering
        "aniso_filter_sample": 0x00A879A1,  # AF Sample Optimization

        # Antialiasing
        "aa_mode": 0x00A879B3,  # AA Mode
        "aa_mode_method": 0x00A879B4,  # AA Method

        # Texture filtering
        "texture_filter_quality": 0x00A879B1,  # Texture Filter Quality
        "texture_filter_neg_lod": 0x00A879B2,  # Negative LOD Bias
    }

    # Setting value mappings
    VSYNC_VALUES = {
        "off": 0x00000000,
        "on": 0x00000001,
        "fast": 0x00000002,
        "adaptive": 0x00000003,
        "adaptive_half": 0x00000004,
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

    def __init__(self):
        """Initialize the profile manager."""
        self._drs = NVAPIDRS()

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

                # Add the application to the profile (may fail on newer drivers)
                drs._app_binding_failures = []  # Reset tracking
                drs.add_application_to_profile(profile, app_executable)

                # Check if app binding succeeded
                if drs._app_binding_failures:
                    results["app_bound"] = False
                    results["app_binding_note"] = (
                        f"Profile '{profile_name}' created with settings, but automatic "
                        f"application binding failed. Please add '{app_executable}' to this "
                        f"profile manually in NVIDIA Control Panel (Manage 3D Settings > "
                        f"Program Settings) or NVIDIA Profile Inspector."
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
            "gsync": ("vrr_app_override", self.VRR_OVERRIDE_VALUES),
            "g_sync": ("vrr_app_override", self.VRR_OVERRIDE_VALUES),
            "power_management": ("power_management", self.POWER_MGMT_VALUES),
            "power_management_mode": ("power_management", self.POWER_MGMT_VALUES),
            "threaded_optimization": ("threaded_optimization", self.THREADED_OPT_VALUES),
            "shader_cache": ("shader_cache", self.SHADER_CACHE_VALUES),
            "triple_buffering": ("triple_buffering", self.TRIPLE_BUFFER_VALUES),
            # Frame rate limiter - accepts FPS value or "off"
            "max_frame_rate": ("frame_rate_limiter_v3", {"off": 0, "disabled": 0}),
            "frame_rate_limit": ("frame_rate_limiter_v3", {"off": 0, "disabled": 0}),
            "fps_cap": ("frame_rate_limiter_v3", {"off": 0, "disabled": 0}),
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

    def get_app_settings(self, app_executable: str) -> dict[str, Any]:
        """Get current NVIDIA settings for an application.

        Args:
            app_executable: The executable name.

        Returns:
            Dictionary of current settings.
        """
        results = {}

        try:
            with self._drs as drs:
                # Look for profile containing this app
                # For now, try ABSO profile first
                app_base = app_executable.rsplit(".", 1)[0]
                profile_name = f"ABSO - {app_base}"

                profile = drs.find_profile_by_name(profile_name)
                if not profile:
                    # Check global profile
                    profile = drs.get_base_profile()
                    results["_profile"] = "Base Profile"
                else:
                    results["_profile"] = profile_name

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
