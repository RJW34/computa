"""NVAPI Display Color Control bindings.

Covers the "Output Dynamic Range" (NVCP → Change Resolution → full vs limited
RGB) and companion color fields via NvAPI_Disp_ColorControl. Extends the DRS
binding pattern from ``nvapi_drs.py`` with display-level APIs.

Scope:
- Enumerate NVIDIA physical GPUs and their connected display IDs.
- GET current dynamic range / colorFormat / colorimetry / bpc per display.
- SET dynamic range (full/limited/auto) per display with policy=USER so the
  choice persists across reboots and driver updates.

Graceful degradation: missing nvapi64.dll, non-NVIDIA displays, and
INCOMPATIBLE_STRUCT_VERSION all result in empty/skipped results — never
raised back to the caller's apply path.
"""

from __future__ import annotations

import concurrent.futures
import ctypes
import logging
import os
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_int,
    c_uint8,
    c_uint16,
    c_uint32,
    c_void_p,
)
from enum import IntEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Constants (matching nvapi.h)
# =============================================================================

NVAPI_MAX_PHYSICAL_GPUS = 64
NVAPI_MAX_DISPLAY_HEADS = 16


class NvAPIStatus(IntEnum):
    """Subset of NVAPI status codes relevant to display color control."""
    OK = 0
    ERROR = -1
    LIBRARY_NOT_FOUND = -2
    API_NOT_INITIALIZED = -4
    INVALID_ARGUMENT = -5
    NVIDIA_DEVICE_NOT_FOUND = -6
    INCOMPATIBLE_STRUCT_VERSION = -9
    NOT_SUPPORTED = -104
    INSUFFICIENT_BUFFER = -174
    FUNCTION_NOT_FOUND = -136
    INVALID_DISPLAY_ID = -187


class NvColorCmd(IntEnum):
    """NV_COLOR_CMD values for NvAPI_Disp_ColorControl."""
    GET = 1
    SET = 2
    IS_SUPPORTED_COLOR = 3
    GET_DEFAULT = 4
    RESET = 5


class NvDynamicRange(IntEnum):
    """NV_DYNAMIC_RANGE values.

    VESA = "Full" PC range (0-255). This is the right choice for any PC
    monitor in Desktop/Game mode, including OLEDs and Mini-LEDs used as
    monitors. CEA = "Limited" TV range (16-235) — used by actual-TV outputs
    or when the EDID reports the display as a TV. Driver installs often
    reset PC displays back to CEA, which looks like everything is washed
    out / gray-black.
    """
    VESA = 0       # Full range
    CEA = 1        # Limited range
    AUTO = 0xFF    # Driver picks from EDID


class NvColorSelectionPolicy(IntEnum):
    """NV_COLOR_SELECTION_POLICY values.

    USER = explicit user choice, persists across driver restarts.
    BEST_QUALITY = driver auto-picks (the one that flaps after updates).
    """
    USER = 0
    BEST_QUALITY = 1
    DEFAULT = 2


# =============================================================================
# Structures
# =============================================================================


def _make_version(struct_cls: type, version: int) -> int:
    """NVAPI MAKE_NVAPI_VERSION macro."""
    return ctypes.sizeof(struct_cls) | (version << 16)


NvPhysicalGpuHandle = c_void_p
NvDisplayHandle = c_void_p


class NV_GPU_DISPLAYIDS_V3(Structure):
    """Per-display identity returned by NvAPI_GPU_GetConnectedDisplayIds.

    The bitfield is packed into one uint32 flags word — we don't need to
    decode every bit; the isConnected/isActive bits (bits 2 and 6) are the
    only ones we care about.
    """
    _fields_ = [
        ("version", c_uint32),
        ("connectorType", c_uint32),
        ("displayId", c_uint32),
        ("flags", c_uint32),
    ]


NV_GPU_DISPLAYIDS_V3_VER = _make_version(NV_GPU_DISPLAYIDS_V3, 3)

# Bit positions inside the flags field (matches NVAPI bitfield ordering).
_FLAG_IS_DYNAMIC = 1 << 0
_FLAG_IS_MULTISTREAM_ROOT = 1 << 1
_FLAG_IS_ACTIVE = 1 << 2
_FLAG_IS_CLUSTER = 1 << 3
_FLAG_IS_OS_VISIBLE = 1 << 4
_FLAG_IS_WFD = 1 << 5
_FLAG_IS_CONNECTED = 1 << 6


class NV_COLOR_DATA_V5_DATA(Structure):
    """Inner data struct for NV_COLOR_DATA_V5.

    Per public nvapi.h: all color-category fields are NvU8 (one byte each)
    after the u32 bIsSelectable field. NOT int-sized enums.
    """
    _fields_ = [
        ("bIsSelectable", c_uint32),
        ("colorFormat", c_uint8),
        ("colorimetry", c_uint8),
        ("dynamicRange", c_uint8),
        ("bpc", c_uint8),
        ("colorSelectionPolicy", c_uint8),
        ("depth", c_uint8),
    ]


class NV_COLOR_DATA_V5(Structure):
    """NvAPI_Disp_ColorControl payload (V5)."""
    _fields_ = [
        ("version", c_uint32),
        ("size", c_uint16),
        ("cmd", c_uint8),
        ("data", NV_COLOR_DATA_V5_DATA),
    ]


NV_COLOR_DATA_V5_VER = _make_version(NV_COLOR_DATA_V5, 5)


class NV_COLOR_DATA_V4_DATA(Structure):
    _fields_ = [
        ("bIsSelectable", c_uint32),
        ("colorFormat", c_uint8),
        ("colorimetry", c_uint8),
        ("dynamicRange", c_uint8),
        ("bpc", c_uint8),
        ("colorSelectionPolicy", c_uint8),
    ]


class NV_COLOR_DATA_V4(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("size", c_uint16),
        ("cmd", c_uint8),
        ("data", NV_COLOR_DATA_V4_DATA),
    ]


NV_COLOR_DATA_V4_VER = _make_version(NV_COLOR_DATA_V4, 4)


class NV_COLOR_DATA_V3_DATA(Structure):
    _fields_ = [
        ("colorFormat", c_uint8),
        ("colorimetry", c_uint8),
        ("dynamicRange", c_uint8),
        ("bpc", c_uint8),
        ("colorSelectionPolicy", c_uint8),
    ]


class NV_COLOR_DATA_V3(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("size", c_uint16),
        ("cmd", c_uint8),
        ("data", NV_COLOR_DATA_V3_DATA),
    ]


NV_COLOR_DATA_V3_VER = _make_version(NV_COLOR_DATA_V3, 3)


# =============================================================================
# Error type
# =============================================================================


class NVAPIDisplayError(Exception):
    """NVAPI display operation error."""

    def __init__(self, message: str, status: int | None = None) -> None:
        self.status = status
        try:
            name = NvAPIStatus(status).name if status is not None else "UNKNOWN"
        except ValueError:
            name = f"UNKNOWN({status})"
        self.status_name = name
        super().__init__(f"{message} (status={name}, code={status})")


# =============================================================================
# Wrapper
# =============================================================================


class NVAPIDisplay:
    """Thin ctypes wrapper around NvAPI display enumeration + color control.

    Usage:
        nvdisp = NVAPIDisplay()
        if nvdisp.initialize():
            displays = nvdisp.enumerate_display_ids()
            for display_id in displays:
                info = nvdisp.get_color(display_id)
                nvdisp.set_dynamic_range(display_id, NvDynamicRange.VESA)
    """

    def __init__(self) -> None:
        self._nvapi: ctypes.WinDLL | None = None
        self._initialized = False
        self._query_interface_func: Any = None
        self._interface_table: dict[str, Any] = {}

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------

    def _find_nvapi_dll(self) -> Path | None:
        """Locate nvapi64.dll in System32 (or the driver store fallback)."""
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        candidate = system32 / "nvapi64.dll"
        if candidate.exists():
            return candidate

        driver_store = system32 / "DriverStore" / "FileRepository"
        if driver_store.exists():
            try:
                for folder in driver_store.iterdir():
                    if folder.is_dir() and folder.name.lower().startswith("nv"):
                        maybe = folder / "nvapi64.dll"
                        if maybe.exists():
                            return maybe
            except OSError:
                return None
        return None

    def _query_interface(self, interface_id: int) -> c_void_p:
        if self._nvapi is None:
            raise NVAPIDisplayError("NVAPI not loaded")

        if self._query_interface_func is None:
            self._query_interface_func = self._nvapi.nvapi_QueryInterface
            self._query_interface_func.restype = c_void_p
            self._query_interface_func.argtypes = [c_uint32]

        ptr = self._query_interface_func(interface_id)
        if not ptr:
            raise NVAPIDisplayError(
                f"Interface 0x{interface_id:08X} not found",
                NvAPIStatus.FUNCTION_NOT_FOUND,
            )
        return ptr

    def _get_function(self, name: str, interface_id: int, restype: Any, argtypes: list) -> Any:
        if name in self._interface_table:
            return self._interface_table[name]

        ptr = self._query_interface(interface_id)
        func_type = ctypes.CFUNCTYPE(restype, *argtypes)
        func = func_type(ptr)
        self._interface_table[name] = func
        return func

    def initialize(self) -> bool:
        """Load nvapi64.dll and call NvAPI_Initialize.

        Returns True on success, False when NVAPI is unavailable (no NVIDIA
        driver, DLL missing, etc.). Never raises to the caller — this is the
        "graceful skip" boundary.
        """
        if self._initialized:
            return True

        nvapi_path = self._find_nvapi_dll()
        if not nvapi_path:
            logger.debug("nvapi64.dll not found — skipping display color control")
            return False

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(ctypes.WinDLL, str(nvapi_path))
            try:
                self._nvapi = future.result(timeout=5)
            except concurrent.futures.TimeoutError:
                logger.warning("nvapi64.dll load timed out — NVIDIA driver may be unhealthy")
                self._initialized = False
                return False
            except OSError as exc:
                logger.debug(f"Failed to load nvapi64.dll: {exc}")
                return False
        finally:
            executor.shutdown(wait=False)

        try:
            init_func = self._get_function(
                "NvAPI_Initialize", 0x0150E828, c_int, []
            )
            status = init_func()
            if status != NvAPIStatus.OK:
                logger.debug(f"NvAPI_Initialize failed: status={status}")
                return False
        except Exception as exc:
            logger.debug(f"NvAPI_Initialize raised: {exc}")
            return False

        self._initialized = True
        return True

    def unload(self) -> None:
        """Call NvAPI_Unload. Safe to call even if init never succeeded."""
        if not self._initialized or self._nvapi is None:
            return
        try:
            unload_func = self._get_function(
                "NvAPI_Unload", 0xD22BDD7E, c_int, []
            )
            unload_func()
        except Exception as exc:
            logger.debug(f"NvAPI_Unload raised: {exc}")
        finally:
            self._initialized = False

    # ---------------------------------------------------------------------
    # Enumeration
    # ---------------------------------------------------------------------

    def _enum_physical_gpus(self) -> list[NvPhysicalGpuHandle]:
        if not self._initialized:
            return []

        enum_gpus = self._get_function(
            "NvAPI_EnumPhysicalGPUs",
            0xE5AC921F,
            c_int,
            [POINTER(NvPhysicalGpuHandle * NVAPI_MAX_PHYSICAL_GPUS), POINTER(c_uint32)],
        )

        handles = (NvPhysicalGpuHandle * NVAPI_MAX_PHYSICAL_GPUS)()
        count = c_uint32(0)
        status = enum_gpus(byref(handles), byref(count))
        if status != NvAPIStatus.OK:
            logger.debug(f"NvAPI_EnumPhysicalGPUs failed: status={status}")
            return []

        return [handles[i] for i in range(count.value) if handles[i]]

    def enumerate_display_ids(self, require_active: bool = True) -> list[int]:
        """Return every NVIDIA-driven displayId, optionally only the active ones."""
        if not self._initialized:
            return []

        gpus = self._enum_physical_gpus()
        if not gpus:
            return []

        get_display_ids = self._get_function(
            "NvAPI_GPU_GetConnectedDisplayIds",
            0x0078DBA2,
            c_int,
            [NvPhysicalGpuHandle, POINTER(NV_GPU_DISPLAYIDS_V3), POINTER(c_uint32), c_uint32],
        )

        display_ids: list[int] = []
        seen: set[int] = set()

        for gpu in gpus:
            # First call with buffer=None to get count
            count = c_uint32(0)
            status = get_display_ids(gpu, None, byref(count), 0)
            if status != NvAPIStatus.OK or count.value == 0:
                logger.debug(
                    f"GetConnectedDisplayIds count probe: status={status} count={count.value}"
                )
                continue

            buf = (NV_GPU_DISPLAYIDS_V3 * count.value)()
            for entry in buf:
                entry.version = NV_GPU_DISPLAYIDS_V3_VER

            status = get_display_ids(gpu, buf, byref(count), 0)
            if status != NvAPIStatus.OK:
                logger.debug(f"GetConnectedDisplayIds fetch failed: status={status}")
                continue

            for idx in range(count.value):
                entry = buf[idx]
                if require_active:
                    flags = entry.flags
                    if not (flags & _FLAG_IS_CONNECTED):
                        continue
                    if not (flags & _FLAG_IS_ACTIVE):
                        continue
                did = int(entry.displayId)
                if did and did not in seen:
                    seen.add(did)
                    display_ids.append(did)

        return display_ids

    # ---------------------------------------------------------------------
    # Color control
    # ---------------------------------------------------------------------

    def _color_control(self, display_id: int, payload: Structure) -> int:
        """Invoke NvAPI_Disp_ColorControl with a prepared payload struct."""
        func = self._get_function(
            "NvAPI_Disp_ColorControl",
            0x92F9D80D,
            c_int,
            [c_uint32, c_void_p],
        )
        return int(func(c_uint32(display_id), ctypes.byref(payload)))

    def _try_get(self, display_id: int) -> tuple[Any, str] | None:
        """Try GET across V5 → V4 → V3 until one succeeds."""
        for struct_cls, version, label in (
            (NV_COLOR_DATA_V5, NV_COLOR_DATA_V5_VER, "v5"),
            (NV_COLOR_DATA_V4, NV_COLOR_DATA_V4_VER, "v4"),
            (NV_COLOR_DATA_V3, NV_COLOR_DATA_V3_VER, "v3"),
        ):
            payload = struct_cls()
            payload.version = version
            payload.size = ctypes.sizeof(struct_cls)
            payload.cmd = NvColorCmd.GET
            status = self._color_control(display_id, payload)
            if status == NvAPIStatus.OK:
                return payload, label
            if status != NvAPIStatus.INCOMPATIBLE_STRUCT_VERSION:
                logger.debug(
                    f"Disp_ColorControl GET ({label}) for display {display_id}: status={status}"
                )
                return None
        return None

    def get_color(self, display_id: int) -> dict[str, Any] | None:
        """Return the current color state for ``display_id``, or None on failure."""
        result = self._try_get(display_id)
        if result is None:
            return None
        payload, version_label = result
        data = payload.data
        info: dict[str, Any] = {
            "display_id": display_id,
            "nv_color_data_version": version_label,
            "color_format": int(data.colorFormat),
            "colorimetry": int(data.colorimetry),
            "dynamic_range": int(data.dynamicRange),
            "bpc": int(data.bpc),
            "color_selection_policy": int(data.colorSelectionPolicy),
        }
        if version_label in ("v4", "v5"):
            info["is_selectable"] = bool(data.bIsSelectable)
        if version_label == "v5":
            info["depth"] = int(data.depth)
        info["dynamic_range_label"] = _dynamic_range_label(data.dynamicRange)
        return info

    def set_dynamic_range(
        self,
        display_id: int,
        target: NvDynamicRange,
    ) -> dict[str, Any]:
        """Set Output Dynamic Range on ``display_id`` to ``target``.

        Reads current state first, mutates only ``dynamicRange`` and
        ``colorSelectionPolicy`` (USER so the driver persists it), then
        writes back with the same struct version the GET succeeded with.

        Returns dict: {"success": bool, "before": int|None, "after": int|None,
                       "changed": bool, "error": str|None}.
        """
        outcome: dict[str, Any] = {
            "display_id": display_id,
            "success": False,
            "before": None,
            "after": None,
            "changed": False,
            "error": None,
        }

        result = self._try_get(display_id)
        if result is None:
            outcome["error"] = "GET failed (no compatible NV_COLOR_DATA version)"
            return outcome

        payload, version_label = result
        before = int(payload.data.dynamicRange)
        outcome["before"] = before

        if before == int(target) and int(payload.data.colorSelectionPolicy) == NvColorSelectionPolicy.USER:
            # Already in the target state with USER policy — idempotent no-op.
            outcome["success"] = True
            outcome["after"] = before
            outcome["changed"] = False
            return outcome

        # Mutate only the fields we own. Keep colorFormat/colorimetry/bpc/depth
        # as they were so we don't force a driver-rejected combination.
        payload.cmd = NvColorCmd.SET
        payload.data.dynamicRange = int(target)
        payload.data.colorSelectionPolicy = int(NvColorSelectionPolicy.USER)

        status = self._color_control(display_id, payload)
        if status != NvAPIStatus.OK:
            outcome["error"] = f"SET failed: NVAPI status {status} (struct {version_label})"
            return outcome

        # Verify by re-reading.
        verify = self._try_get(display_id)
        if verify is not None:
            outcome["after"] = int(verify[0].data.dynamicRange)
        else:
            outcome["after"] = int(target)

        outcome["success"] = True
        outcome["changed"] = before != outcome["after"]
        return outcome


def _dynamic_range_label(value: int) -> str:
    """Map raw NV_DYNAMIC_RANGE byte to a human-readable label."""
    if value == NvDynamicRange.VESA:
        return "full"
    if value == NvDynamicRange.CEA:
        return "limited"
    if value == NvDynamicRange.AUTO:
        return "auto"
    return f"unknown({value})"


def parse_dynamic_range(label: str | int | None) -> NvDynamicRange:
    """Map user-facing string/int to NvDynamicRange. Unknown → AUTO."""
    if label is None:
        return NvDynamicRange.AUTO
    if isinstance(label, NvDynamicRange):
        return label
    if isinstance(label, int):
        if label in (NvDynamicRange.VESA, NvDynamicRange.CEA, NvDynamicRange.AUTO):
            return NvDynamicRange(label)
        return NvDynamicRange.AUTO
    normalized = label.strip().lower()
    if normalized in ("full", "vesa", "pc"):
        return NvDynamicRange.VESA
    if normalized in ("limited", "cea", "tv"):
        return NvDynamicRange.CEA
    if normalized in ("auto", "default"):
        return NvDynamicRange.AUTO
    return NvDynamicRange.AUTO
