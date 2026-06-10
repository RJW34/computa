"""EcoQoS / Efficiency-Mode per-process power throttling (Tier B scaffold).

Default OFF. Provides the "throttle instead of kill" middle tier that the
launch janitor lacks: keep a busy background app alive but herd it onto the
E-cores via the Windows ``ProcessPowerThrottling`` (EcoQoS) API, freeing
P-cores for the game's sim / netcode thread. State is ephemeral (per process
instance, vanishes on exit) so there is no backup/restore — the herder simply
resets every process it touched on game exit, and a tray restart can re-sweep.

Mechanism: ``SetProcessInformation(hProcess, ProcessPowerThrottling, &state)``.

ONLINE SAFETY: this only ever throttles *background* images. It never opens or
throttles the game, anti-cheat, capture/encode tools, Discord (voice), or the
foreground process. Forcing EcoQoS *off* on the game (the other half PL offers)
is deliberately NOT implemented — Windows does not auto-eco a focused
fullscreen game, and poking a protected game/anti-cheat process is exactly the
anti-cheat-suspicion class ABSO avoids.

Nothing here runs until the tray wires it on a game-launch edge AND
``cpu``-side config opts in; see ``EfficiencyModeConfig.enabled``.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
from collections.abc import Callable, Iterable

from abso.core.process_janitor import CAPTURE_ALLOWED_IMAGES, NEVER_KILL_IMAGES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------
# PROCESS_INFORMATION_CLASS::ProcessPowerThrottling
PROCESS_POWER_THROTTLING = 4
PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1

PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

TH32CS_SNAPPROCESS = 0x00000002

# Images that must never be eco-throttled: everything we would never kill
# (game launchers, anti-cheat, audio, editors, Discord voice) plus the
# capture/encode tools that must keep P-core time to avoid dropped frames.
NEVER_ECO_IMAGES: frozenset[str] = NEVER_KILL_IMAGES | CAPTURE_ALLOWED_IMAGES

# Valid modes for :func:`set_process_eco_qos`.
_MODE_MASKS: dict[str, tuple[int, int]] = {
    # (ControlMask, StateMask)
    "eco": (PROCESS_POWER_THROTTLING_EXECUTION_SPEED, PROCESS_POWER_THROTTLING_EXECUTION_SPEED),
    "high": (PROCESS_POWER_THROTTLING_EXECUTION_SPEED, 0),
    "reset": (0, 0),
}


# ---------------------------------------------------------------------------
# Win32 structures
# ---------------------------------------------------------------------------
class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    """Win32 PROCESS_POWER_THROTTLING_STATE."""

    _fields_ = [
        ("Version", wintypes.ULONG),
        ("ControlMask", wintypes.ULONG),
        ("StateMask", wintypes.ULONG),
    ]


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


# ---------------------------------------------------------------------------
# Low-level helpers (Win32; not exercised by the hermetic tests, which inject)
# ---------------------------------------------------------------------------
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_KERNEL32: ctypes.WinDLL | None = None
_USER32: ctypes.WinDLL | None = None


def _kernel32() -> ctypes.WinDLL:
    """Cached kernel32 with explicit prototypes (avoids Win64 HANDLE truncation)."""
    global _KERNEL32
    if _KERNEL32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.CloseHandle.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.SetProcessInformation.restype = wintypes.BOOL
        k.SetProcessInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k.Process32FirstW.restype = wintypes.BOOL
        k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        k.Process32NextW.restype = wintypes.BOOL
        k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        _KERNEL32 = k
    return _KERNEL32


def _user32() -> ctypes.WinDLL:
    """Cached user32 with explicit prototypes."""
    global _USER32
    if _USER32 is None:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetForegroundWindow.argtypes = []
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        _USER32 = u
    return _USER32


def _build_throttling_state(mode: str) -> PROCESS_POWER_THROTTLING_STATE:
    """Build the power-throttling struct for a mode (pure; unit-testable)."""
    control_mask, state_mask = _MODE_MASKS[mode]
    state = PROCESS_POWER_THROTTLING_STATE()
    state.Version = PROCESS_POWER_THROTTLING_CURRENT_VERSION
    state.ControlMask = control_mask
    state.StateMask = state_mask
    return state


def set_process_eco_qos(pid: int, mode: str, *, kernel32: ctypes.WinDLL | None = None) -> bool:
    """Set the EcoQoS power-throttling state for a single process.

    Args:
        pid: Target process id.
        mode: ``"eco"`` (throttle onto E-cores), ``"high"`` (force high QoS,
            never throttled), or ``"reset"`` (return to system management).
        kernel32: Injectable handle for testing; defaults to the live DLL.

    Returns:
        ``True`` on success, ``False`` if the process could not be opened or
        the call failed (e.g. it already exited).

    Raises:
        ValueError: If ``mode`` is not one of the supported modes.
    """
    if mode not in _MODE_MASKS:
        raise ValueError(f"invalid eco-qos mode: {mode!r} (expected one of {sorted(_MODE_MASKS)})")

    k = kernel32 or _kernel32()

    handle = k.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        state = _build_throttling_state(mode)
        ok = k.SetProcessInformation(
            handle,
            PROCESS_POWER_THROTTLING,
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
        return bool(ok)
    finally:
        k.CloseHandle(handle)


def _enumerate_processes(kernel32: ctypes.WinDLL | None = None) -> list[tuple[int, str]]:
    """List ``(pid, image_name)`` for every running process via toolhelp."""
    k = kernel32 or _kernel32()
    snapshot = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
        return []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        processes: list[tuple[int, str]] = []
        if k.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                processes.append((entry.th32ProcessID, entry.szExeFile))
                if not k.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        return processes
    finally:
        k.CloseHandle(snapshot)


def _get_foreground_pid(user32: ctypes.WinDLL | None = None) -> int | None:
    """Return the PID owning the foreground window, or ``None``."""
    u = user32 or _user32()
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


# ---------------------------------------------------------------------------
# Herder
# ---------------------------------------------------------------------------
class EcoQosHerder:
    """Throttle busy background images to E-cores for a game session.

    The herder is intentionally *additive* over the launch janitor: the janitor
    kills the heavy offenders it is confident about; the herder demotes a
    curated set of keep-alive-but-busy background images (the
    ``background_images`` list) to EcoQoS while a game runs, then resets them on
    exit. It never touches the game, the foreground process, or anything in
    :data:`NEVER_ECO_IMAGES`.

    Dependencies are injected so the decision logic is fully unit-testable
    without touching real processes.
    """

    def __init__(
        self,
        game_pid: int,
        background_images: Iterable[str],
        *,
        never_eco: Iterable[str] | None = None,
        lister: Callable[[], list[tuple[int, str]]] | None = None,
        setter: Callable[[int, str], bool] | None = None,
        foreground_pid_getter: Callable[[], int | None] | None = None,
    ) -> None:
        self._game_pid = game_pid
        self._background = {name.lower() for name in background_images}
        never = NEVER_ECO_IMAGES if never_eco is None else {n.lower() for n in never_eco}
        self._never_eco = frozenset(never)
        self._lister = lister or _enumerate_processes
        self._setter = setter or set_process_eco_qos
        self._fg = foreground_pid_getter or _get_foreground_pid
        self._throttled: set[int] = set()

    def _should_throttle(self, pid: int, name: str, foreground_pid: int | None) -> bool:
        if pid == self._game_pid or pid == foreground_pid or pid <= 4:
            return False
        name_lower = name.lower()
        if name_lower in self._never_eco:
            return False
        return name_lower in self._background

    def herd(self) -> int:
        """Throttle every eligible background image. Returns count newly throttled."""
        if not self._background:
            return 0
        foreground_pid = self._fg()
        newly = 0
        for pid, name in self._lister():
            if pid in self._throttled:
                continue
            if self._should_throttle(pid, name, foreground_pid) and self._setter(pid, "eco"):
                self._throttled.add(pid)
                newly += 1
        return newly

    def release_all(self) -> None:
        """Reset EcoQoS on every process this herder throttled."""
        for pid in list(self._throttled):
            self._setter(pid, "reset")
        self._throttled.clear()

    @property
    def throttled_pids(self) -> frozenset[int]:
        return frozenset(self._throttled)


def efficiency_mode_enabled() -> bool:
    """Return ``True`` if EcoQoS herding is opted in via ``abso.yaml``."""
    try:
        from abso.core.config import get_config

        return bool(get_config().efficiency_mode.enabled)
    except Exception as exc:
        logger.debug("efficiency_mode config unavailable: %s", exc)
        return False
