"""Driver application ABI contracts from NVIDIA's nvapi.h.

These fixed sizes and byte offsets are independent of the ctypes declarations:
https://github.com/NVIDIA/nvapi/blob/main/nvapi.h
Incorrect size/version tokens caused real membership reads to exhaust every
fallback and silently return None even for correctly bound games.
"""

from __future__ import annotations

import ctypes
import struct

import pytest

from abso.settings.nvidia.nvapi_drs import (
    NVAPIDRS,
    NVDRS_APPLICATION_V1,
    NVDRS_APPLICATION_V2,
    NVDRS_APPLICATION_V3,
    NVDRS_APPLICATION_V4,
    NVDRS_APPLICATION_VER1,
    NVDRS_APPLICATION_VER2,
    NVDRS_APPLICATION_VER3,
    NVDRS_APPLICATION_VER4,
    NvAPIStatus,
)

# SDK strings are 2048 UTF-16 code units (4096 bytes), flags share one DWORD.
SDK_LAYOUTS = [
    (NVDRS_APPLICATION_V4, NVDRS_APPLICATION_VER4, 20492, 0x0004500C),
    (NVDRS_APPLICATION_V3, NVDRS_APPLICATION_VER3, 16396, 0x0003400C),
    (NVDRS_APPLICATION_V2, NVDRS_APPLICATION_VER2, 16392, 0x00024008),
    (NVDRS_APPLICATION_V1, NVDRS_APPLICATION_VER1, 12296, 0x00013008),
]


@pytest.mark.parametrize("app_type,version,size,sdk_version", SDK_LAYOUTS)
def test_application_layout_matches_sdk(app_type, version, size, sdk_version):
    assert ctypes.sizeof(app_type) == size
    assert version == sdk_version
    assert app_type.appName.offset == 8
    assert app_type.userFriendlyName.offset == 4104
    assert app_type.launcher.offset == 8200
    if app_type is not NVDRS_APPLICATION_V1:
        assert app_type.fileInFolder.offset == 12296
    if app_type is NVDRS_APPLICATION_V4:
        assert app_type.commandLine.offset == 16396


@pytest.mark.parametrize("app_type", [NVDRS_APPLICATION_V3, NVDRS_APPLICATION_V4])
def test_application_flags_share_sdk_dword(app_type):
    app = app_type()
    app.isMetro = 1
    app.isCommandLine = 1
    assert struct.unpack_from("<I", bytes(app), 16392)[0] == 3
    assert app.reserved == 0


@pytest.mark.parametrize("accepted_version", [row[3] for row in SDK_LAYOUTS])
@pytest.mark.parametrize("query", ["owner", "membership"])
def test_binding_readback_with_driver_validated_layout(monkeypatch, accepted_version, query):
    """A fake native endpoint validates SDK tokens and returns raw ABI bytes.

    This exercises the real V4-to-V1 fallback and string decoding without
    loading NVAPI or accessing the machine's driver state.
    """
    drs = NVAPIDRS()
    drs._session = ctypes.c_void_p(0x101)
    seen_versions = []

    def read_application(session, profile_or_name, name_or_owner, app_ptr):
        address = ctypes.cast(app_ptr, ctypes.c_void_p).value
        version = ctypes.c_uint32.from_address(address).value
        seen_versions.append(version)
        if version != accepted_version:
            return NvAPIStatus.INCOMPATIBLE_STRUCT_VERSION

        # Write as the SDK would, without consulting our ctypes field layout.
        for offset, value in [(8, "fortniteclient-win64-shipping.exe"), (4104, "Fortnite")]:
            encoded = (value + "\0").encode("utf-16-le")
            ctypes.memmove(address + offset, encoded, len(encoded))
        if query == "owner":
            ctypes.cast(name_or_owner, ctypes.POINTER(ctypes.c_void_p))[0] = 0x102
        return NvAPIStatus.OK

    def get_function(name, *args):
        expected = "NvAPI_DRS_FindApplicationByName" if query == "owner" else "NvAPI_DRS_GetApplicationInfo"
        assert name == expected
        return read_application

    monkeypatch.setattr(drs, "_get_function", get_function)
    monkeypatch.setattr(drs, "get_profile_name", lambda handle: "Fortnite")

    if query == "owner":
        result = drs.find_application_owner("FortniteClient-Win64-Shipping.exe")
        assert result["profile_name"] == "Fortnite"
        assert result["profile_handle"].value == 0x102
    else:
        result = drs.get_application_info(
            ctypes.c_void_p(0x102), "FortniteClient-Win64-Shipping.exe"
        )
    assert result["app_name"] == "fortniteclient-win64-shipping.exe"
    assert result["user_friendly_name"] == "Fortnite"
    expected_versions = [row[3] for row in SDK_LAYOUTS]
    assert seen_versions == expected_versions[:expected_versions.index(accepted_version) + 1]
