"""NVIDIA Output Dynamic Range (Full / Limited RGB) settings handler.

Wraps ``abso.settings.nvidia.nvapi_display`` with the standard detect /
audit / apply / backup / restore contract so ABSO profiles can assert
"Full" RGB on every apply. This closes the loop where an NVIDIA driver
install silently resets a PC monitor's output pixel format to Limited
(CEA/TV range) — the classic "everything looks washed out after a driver
update" symptom.

The handler is a no-op on systems without NVAPI (non-NVIDIA GPUs, DLL
missing, driver broken) and logs skipped reasons instead of failing.
"""

from __future__ import annotations

import logging
from typing import Any

from abso.core.models import EvidenceTier, Issue
from abso.settings.base import SettingsHandler
from abso.settings.nvidia.nvapi_display import (
    NVAPIDisplay,
    NvColorSelectionPolicy,
    NvDynamicRange,
    parse_dynamic_range,
)

logger = logging.getLogger(__name__)


# Labels accepted from profiles / user config.
DYNAMIC_RANGE_CHOICES = ("full", "limited", "auto")


class DisplayColorRangeHandler(SettingsHandler):
    """Manage per-display NVIDIA Output Dynamic Range via NvAPI_Disp_ColorControl.

    Settings shape accepted by ``apply``:
        {"dynamic_range": "full" | "limited" | "auto"}

    Empty or missing settings → no-op.
    """

    def __init__(self) -> None:
        self._nvdisp: NVAPIDisplay | None = None

    # ---------------------------------------------------------------------
    # Interface
    # ---------------------------------------------------------------------

    def detect(self) -> dict[str, Any]:
        """Report per-display current range and policy (empty list if no NVAPI)."""
        displays = self._collect_display_state()
        any_limited = any(d.get("dynamic_range_label") == "limited" for d in displays)
        any_non_user_policy = any(
            d.get("color_selection_policy") != int(NvColorSelectionPolicy.USER) for d in displays
        )
        return {
            "displays": displays,
            "display_count": len(displays),
            "any_limited": any_limited,
            "any_non_user_policy": any_non_user_policy,
            "nvapi_available": self._nvdisp is not None and self._nvdisp._initialized,
        }

    def audit(self) -> list[Issue]:
        """Surface displays that are currently on Limited range or a non-user policy."""
        issues: list[Issue] = []
        state = self.detect()
        if not state["displays"]:
            return issues

        limited = [d for d in state["displays"] if d.get("dynamic_range_label") == "limited"]
        if limited:
            ids = ", ".join(str(d["display_id"]) for d in limited)
            issues.append(
                Issue(
                    title="NVIDIA Output Dynamic Range set to Limited (TV range)",
                    severity="warning",
                    current_value=f"Limited on {len(limited)} display(s) [IDs: {ids}]",
                    optimal_value="Full (VESA / PC range)",
                    explanation=(
                        "PC monitors should output Full RGB (0-255) for correct black "
                        "level and contrast. Limited range (16-235) is for TVs and will "
                        "make the desktop look washed out with elevated blacks. NVIDIA "
                        "driver installs commonly reset this back to Limited when the "
                        "display's EDID advertises TV-style signalling."
                    ),
                    category="color",
                    evidence_tier=EvidenceTier.VERIFIED,
                )
            )

        auto_policy = [
            d
            for d in state["displays"]
            if d.get("color_selection_policy") != int(NvColorSelectionPolicy.USER)
        ]
        if auto_policy and not limited:
            # Only surface this if we didn't already flag a harder problem.
            ids = ", ".join(str(d["display_id"]) for d in auto_policy)
            issues.append(
                Issue(
                    title="NVIDIA color selection policy is non-USER",
                    severity="info",
                    current_value=f"Driver-managed on {len(auto_policy)} display(s) [IDs: {ids}]",
                    optimal_value="User (explicit) so the choice survives driver restarts",
                    explanation=(
                        "Driver-managed color policy lets NVIDIA reselect format and "
                        "range on each display attach, which is why these settings "
                        "flap across driver updates. A USER policy persists."
                    ),
                    category="color",
                    evidence_tier=EvidenceTier.EMPIRICAL,
                )
            )

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Assert ``dynamic_range`` on every active NVIDIA-driven display."""
        if not settings or "dynamic_range" not in settings:
            return {"success": True, "error": None, "requires_reboot": False}

        requested = settings["dynamic_range"]
        target = parse_dynamic_range(requested)

        nvdisp = self._ensure_nvapi()
        if nvdisp is None:
            logger.info(
                "DisplayColorRangeHandler: NVAPI unavailable, skipping dynamic_range=%r",
                requested,
            )
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "applied": [],
                "skipped": ["NVAPI not available (non-NVIDIA system or driver missing)"],
            }

        display_ids = nvdisp.enumerate_display_ids(require_active=True)
        if not display_ids:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "applied": [],
                "skipped": ["No active NVIDIA-driven displays enumerated"],
            }

        applied: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        changed = False

        for display_id in display_ids:
            try:
                outcome = nvdisp.set_dynamic_range(display_id, target)
            except Exception as exc:
                logger.info(
                    "DisplayColorRangeHandler: NVAPI raised for display %s: %s",
                    display_id,
                    exc,
                )
                skipped.append(f"Display {display_id}: NVAPI raised ({exc})")
                continue

            if not outcome["success"]:
                errors.append(f"Display {display_id}: {outcome.get('error') or 'unknown error'}")
                continue

            label = _range_value_label(target)
            if outcome["changed"]:
                changed = True
                applied.append(f"Display {display_id}: Output Dynamic Range → {label}")
            else:
                applied.append(f"Display {display_id}: already {label} (no change)")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
            "applied": applied,
            "skipped": skipped,
            "changed": changed,
            "changed_keys": ["dynamic_range"] if changed else [],
        }

    def backup(self) -> dict[str, Any]:
        """Snapshot current per-display dynamic_range + color policy."""
        return {"displays": self._collect_display_state()}

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore dynamic_range per displayId from a prior backup payload.

        Graceful: unknown display IDs, NVAPI-unavailable, and unexpected
        schemas all return True without raising (matches how ColorProfile
        handler treats these). Only real SET failures against an
        enumerated display flip the return value to False.
        """
        displays = data.get("displays") or []
        if not displays:
            return True

        nvdisp = self._ensure_nvapi()
        if nvdisp is None:
            logger.info("DisplayColorRangeHandler: NVAPI unavailable, skipping restore")
            return True

        active_ids = set(nvdisp.enumerate_display_ids(require_active=True))
        any_failure = False

        for entry in displays:
            display_id = entry.get("display_id")
            range_value = entry.get("dynamic_range")
            if display_id is None or range_value is None:
                continue
            if display_id not in active_ids:
                # Monitor was disconnected since backup — skip.
                logger.info(
                    "DisplayColorRangeHandler.restore: display %s not currently active",
                    display_id,
                )
                continue
            try:
                target = (
                    NvDynamicRange(range_value)
                    if range_value
                    in (
                        NvDynamicRange.VESA,
                        NvDynamicRange.CEA,
                        NvDynamicRange.AUTO,
                    )
                    else NvDynamicRange.AUTO
                )
                outcome = nvdisp.set_dynamic_range(display_id, target)
                if not outcome["success"]:
                    any_failure = True
                    logger.error(
                        "DisplayColorRangeHandler.restore failed for display %s: %s",
                        display_id,
                        outcome.get("error"),
                    )
            except Exception as exc:
                any_failure = True
                logger.error(
                    "DisplayColorRangeHandler.restore raised for display %s: %s",
                    display_id,
                    exc,
                )

        return not any_failure

    @property
    def restore_guarantee(self) -> str:
        # NVAPI faithfully round-trips the integer values we captured, but a
        # monitor can be unplugged/replaced between backup and restore — mark
        # as partial so the user isn't surprised when an offline monitor is
        # skipped.
        return "partial"

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    def _ensure_nvapi(self) -> NVAPIDisplay | None:
        if self._nvdisp is not None and self._nvdisp._initialized:
            return self._nvdisp
        nvdisp = NVAPIDisplay()
        if nvdisp.initialize():
            self._nvdisp = nvdisp
            return nvdisp
        self._nvdisp = None
        return None

    def _collect_display_state(self) -> list[dict[str, Any]]:
        nvdisp = self._ensure_nvapi()
        if nvdisp is None:
            return []
        out: list[dict[str, Any]] = []
        for did in nvdisp.enumerate_display_ids(require_active=True):
            info = nvdisp.get_color(did)
            if info is not None:
                out.append(info)
        return out


def _range_value_label(target: NvDynamicRange) -> str:
    if target == NvDynamicRange.VESA:
        return "Full (VESA/PC)"
    if target == NvDynamicRange.CEA:
        return "Limited (CEA/TV)"
    return "Auto"
