"""Post-apply reconciliation of borderless/windowed VRR enablers.

Borderless (windowed-fullscreen) G-SYNC requires THREE enablers, each owned by a
different handler, that the display/HDR re-enumeration triggered by *other*
handlers during the same profile apply can silently reset back to default:

  * NVIDIA global ``vrr_mode`` = ``fullscreen_and_windowed`` (driver DRS)
  * Windows ``SwapEffectUpgradeEnable``  (``windowed_optimizations``)
  * Windows ``VRROptimizeEnable``        (``vrr_optimize``)

Each enabler is written correctly by its handler earlier in the apply, but a
later handler that toggles HDR / MPO re-enumerates the display and the driver/OS
drop the global VRR mode (and the windowed-VRR flags) back to fullscreen-only /
off. The user-visible symptom is severe: borderless G-SYNC never engages, the
forced-VSync backstop kicks in, and the game locks to *half* the refresh rate
(e.g. 150 fps on a 300 Hz panel).

The drop is stable once the display has settled, so the robust, mechanism-proof
fix is to re-assert and *verify* the three enablers AFTER every handler has run.
This module is the single source of truth for that reconciliation. It is fully
dependency-injected so it can be unit-tested without a live GPU or registry.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Local mirror of DRSProfileManager.VRR_MODE_VALUES so this module imports
# without pulling in the ctypes/NVAPI stack (keeps hermetic tests clean).
_VRR_MODE_NUMERIC: dict[str, int] = {
    "off": 0,
    "disabled": 0,
    "on": 1,
    "enabled": 1,
    "fullscreen": 1,
    "fullscreen_only": 1,
    "fullscreen_and_windowed": 2,
    "windowed": 2,
}

# Only these global VRR-mode targets use the borderless/windowed path. A
# fullscreen-only or off profile must NOT be touched by this reconciliation.
_WINDOWED_VRR_MODES = {"fullscreen_and_windowed", "windowed"}


@dataclass
class VrrEnablers:
    """The borderless-VRR enablers a profile declares, normalized."""

    global_vrr_mode: str | None = None  # canonical, e.g. "fullscreen_and_windowed"
    windowed_optimizations: bool | None = None
    vrr_optimize: bool | None = None

    @property
    def wants_windowed_vrr(self) -> bool:
        """Whether this profile uses the borderless/windowed G-SYNC path."""
        return (
            (self.global_vrr_mode in _WINDOWED_VRR_MODES)
            or bool(self.windowed_optimizations)
            or bool(self.vrr_optimize)
        )


def _normalize_vrr_mode(value: Any) -> str | None:
    """Normalize a profile's VRR-mode value to a canonical lowercase token."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "fullscreen_only" if value else "off"
    token = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return token or None


def extract_vrr_enablers(settings_map: dict[str, dict[str, Any]]) -> VrrEnablers:
    """Pull the declared borderless-VRR enablers out of a finalized settings map.

    Mirrors the key handling in
    :meth:`NvidiaSettingsHandler._extract_requested_settings` so the
    reconciliation targets exactly what the apply intended to write.
    """
    nvidia = settings_map.get("NvidiaSettingsHandler") or {}
    windows = settings_map.get("WindowsSettingsHandler") or {}

    vrr_mode: str | None = None
    for key in ("global_vrr_mode", "global_gsync_mode", "vrr_mode"):
        if nvidia.get(key) is not None:
            vrr_mode = _normalize_vrr_mode(nvidia[key])
            break
    if vrr_mode is None and nvidia.get("global_gsync") is not None:
        vrr_mode = _normalize_vrr_mode(nvidia["global_gsync"])

    wo = windows.get("windowed_optimizations")
    vo = windows.get("vrr_optimize")
    return VrrEnablers(
        global_vrr_mode=vrr_mode,
        windowed_optimizations=bool(wo) if wo is not None else None,
        vrr_optimize=bool(vo) if vo is not None else None,
    )


def _default_drs_manager() -> Any:
    from abso.settings.nvidia.nvapi_drs import DRSProfileManager

    return DRSProfileManager()


def _default_windows_handler() -> Any:
    from abso.settings.windows import WindowsSettingsHandler

    return WindowsSettingsHandler()


def _reconcile_nvidia_vrr_mode(
    target_mode: str,
    drs_factory: Callable[[], Any],
    result: dict[str, Any],
) -> None:
    """Re-assert + verify the NVIDIA global ``vrr_mode``.

    Read-first: only writes when the live value differs from the target, so a
    correctly-committed apply is a no-op. A write that does not read back as the
    target is surfaced as a verification failure (never silently swallowed).
    """
    expected = _VRR_MODE_NUMERIC.get(target_mode)
    if expected is None:
        return
    try:
        manager = drs_factory()
        current = manager.get_app_settings().get("vrr_mode")
    except Exception as exc:  # noqa: BLE001 - non-NVIDIA / no driver: silent skip
        logger.debug("VRR reconcile: NVIDIA read skipped (%s)", exc)
        return

    if current == expected:
        return

    try:
        manager.apply_settings_to_global({"vrr_mode": target_mode})
        after = manager.get_app_settings().get("vrr_mode")
    except Exception as exc:  # noqa: BLE001
        logger.debug("VRR reconcile: NVIDIA re-assert skipped (%s)", exc)
        return

    if after == expected:
        line = f"NVIDIA global vrr_mode -> {target_mode}"
        result["reasserted"].append(line)
        logger.info("VRR reconcile: re-asserted NVIDIA vrr_mode=%s (was %s)", target_mode, current)
    else:
        result["verified"] = False
        result["warnings"].append(
            f"NVIDIA global vrr_mode did not persist (have {after}, want {expected})"
        )


def _reconcile_windows_flags(
    targets: dict[str, bool],
    windows_factory: Callable[[], Any],
    result: dict[str, Any],
) -> None:
    """Re-assert + verify the Windows windowed-VRR DirectX flags."""
    try:
        handler = windows_factory()
        current = handler.get_windowed_vrr_flags()
    except Exception as exc:  # noqa: BLE001 - non-Windows / no key: silent skip
        logger.debug("VRR reconcile: Windows read skipped (%s)", exc)
        return

    needed = {k: v for k, v in targets.items() if current.get(k) != v}
    if not needed:
        return

    try:
        handler.apply(needed)
        after = handler.get_windowed_vrr_flags()
    except Exception as exc:  # noqa: BLE001
        logger.debug("VRR reconcile: Windows re-assert skipped (%s)", exc)
        return

    for key, want in needed.items():
        if after.get(key) == want:
            result["reasserted"].append(f"Windows {key} -> {want}")
            logger.info("VRR reconcile: re-asserted Windows %s=%s", key, want)
        else:
            result["verified"] = False
            result["warnings"].append(
                f"Windows {key} did not persist (have {after.get(key)}, want {want})"
            )


def reconcile_vrr_enablers(
    settings_map: dict[str, dict[str, Any]],
    *,
    drs_factory: Callable[[], Any] | None = None,
    windows_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Re-assert + verify borderless-VRR enablers after a profile apply.

    Returns a result dict::

        {"ran": bool, "reasserted": list[str], "warnings": list[str], "verified": bool}

    ``ran`` is False for profiles that don't use the borderless/windowed VRR
    path (no work done). ``warnings`` holds only genuine persistence-verification
    failures; unavailable subsystems (non-NVIDIA host, missing registry key) are
    logged at debug level and never pollute the apply result.
    """
    result: dict[str, Any] = {"ran": False, "reasserted": [], "warnings": [], "verified": True}

    enablers = extract_vrr_enablers(settings_map)
    if not enablers.wants_windowed_vrr:
        return result
    result["ran"] = True

    if enablers.global_vrr_mode is not None:
        _reconcile_nvidia_vrr_mode(
            enablers.global_vrr_mode, drs_factory or _default_drs_manager, result
        )

    win_targets: dict[str, bool] = {}
    if enablers.windowed_optimizations is not None:
        win_targets["windowed_optimizations"] = enablers.windowed_optimizations
    if enablers.vrr_optimize is not None:
        win_targets["vrr_optimize"] = enablers.vrr_optimize
    if win_targets:
        _reconcile_windows_flags(win_targets, windows_factory or _default_windows_handler, result)

    return result
