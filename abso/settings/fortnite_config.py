"""Fortnite GameUserSettings.ini handler."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

from abso.core.config_safety import INI_SECTION_RE, find_ini_section_bounds, parse_ini_assignments
from abso.settings.ue_game_user_settings import UEGameUserSettingsHandler


class FortniteConfigHandler(UEGameUserSettingsHandler):
    """Enforce Fortnite display settings from GameUserSettings.ini."""

    is_critical_verify = True

    TARGET_SECTION_NAME = "/Script/FortniteGame.FortGameUserSettings"
    # Fortnite uses the stock Unreal EWindowMode enum for its fullscreen mode:
    #   0 = Fullscreen, 1 = Windowed Fullscreen (borderless), 2 = Windowed.
    # Locally observed keys are PreferredFullscreenMode and its last-confirmed
    # mirror. Do not append the generic FullscreenMode key. A saved enum does
    # not prove exclusive presentation, VRR engagement, or measured latency.
    MUTABLE_SETTINGS_TO_INI = {
        "fullscreen_mode": "PreferredFullscreenMode",
        "vsync": "bUseVSync",
        "frame_rate_limit": "FrameRateLimit",
    }
    MIRROR_FULLSCREEN_MODE_KEYS = ("LastConfirmedFullscreenMode",)
    PROTECTED_INI_KEYS = {
        "bUseHDRDisplayOutput", "HDRDisplayOutputNits", "bUseHDRDisplayCalibration",
        "LatencyTweak2", "bLatencyTweak1", "bLatencyTweak2",
    }
    REQUIRE_REFLEX_KEY = "require_reflex"
    REFLEX_LABELS = {0: "Off", 1: "On", 2: "On + Boost"}

    def _read_assignments(self) -> dict[str, str] | None:
        """Read this game's section; never borrow a different section's keys."""
        path = self._get_config_path()
        if path is None:
            return None
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        if (find_ini_section_bounds(lines, self.TARGET_SECTION_NAME) is None
                and any(INI_SECTION_RE.match(line) for line in lines)):
            return None
        return parse_ini_assignments(lines, section_name=self.TARGET_SECTION_NAME)

    def detect(self) -> dict[str, Any]:
        current = super().detect()
        try:
            assignments = self._read_assignments()
        except (OSError, UnicodeError):
            assignments = None
        if assignments is None:
            # Do not let the generic headerless-file fallback turn values in an
            # unrelated section into verification evidence for Fortnite.
            return {key: value for key, value in current.items()
                    if key in {"config_found", "config_path"}}
        raw_reflex = assignments.get("LatencyTweak2")
        current["reflex_mode"] = int(raw_reflex) if raw_reflex in {"0", "1", "2"} else None
        # Saved-only observations: these UE keys do not prove active native HDR.
        for profile_key, ini_key in (("hdr_output", "bUseHDRDisplayOutput"),
                                     ("hdr_nits", "HDRDisplayOutputNits")):
            if ini_key in assignments:
                current[profile_key + "_saved"] = self._coerce_detected(profile_key, assignments[ini_key])
        return current

    def _manual_reflex_step(self, current: dict[str, Any]) -> dict[str, Any]:
        mode = current.get("reflex_mode")
        return {
            "key": "reflex_mode",
            "label": "NVIDIA Reflex Low Latency (in-game)",
            "current": mode,
            "current_label": self.REFLEX_LABELS.get(mode, "Unknown / not readable"),
            "expected": 1,
            "accepted": [1, 2],
            "expected_label": "On or On + Boost",
            "satisfied": mode in (1, 2) if mode is not None else None,
            "instruction": (
                "Fortnite Settings > Video > Advanced Graphics > NVIDIA Reflex Low Latency: "
                "choose On or On + Boost and Apply. This check reads the saved choice; "
                "it does not prove runtime Reflex activity. ABSO never changes Reflex."
            ),
        }

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        requested = dict(settings)
        require_reflex = requested.pop(self.REQUIRE_REFLEX_KEY, False)
        try:
            if self._get_config_path() is not None and self._read_assignments() is None:
                return {"success": False, "error": "Fortnite settings section is missing; no values changed.",
                        "requires_reboot": False, "applied": []}
        except (OSError, UnicodeError) as exc:
            return {"success": False, "error": str(exc), "requires_reboot": False, "applied": []}
        # Deprecated hdr_output/hdr_nits and any Reflex-write request fail the
        # superclass allowlist before any file write.
        result = super().apply(requested)
        if require_reflex and result.get("success"):
            result["manual_steps"] = [self._manual_reflex_step(self.detect())]
        return result

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        requested = dict(settings)
        require_reflex = requested.pop(self.REQUIRE_REFLEX_KEY, False)
        result = super().verify_active(requested)
        for key in ("fullscreen_mode", "frame_rate_limit"):
            if key in requested and self._convert_value(key, requested[key]) is None:
                result["all_active"] = False
                result["settings"][key].update({
                    "active": False,
                    "status": "invalid_target",
                    "note": "The requested value is outside the supported numeric setting domain.",
                })
        if require_reflex:
            # An unmet manual choice must not trigger profile reapply/rollback.
            result["manual_steps"] = [self._manual_reflex_step(self.detect())]
        return result

    def _convert_value(self, profile_key: str, value: Any) -> str | None:
        if profile_key == "fullscreen_mode" and (
            isinstance(value, bool) or str(value).strip() not in {"0", "1", "2"}
        ):
            return None
        if profile_key == "frame_rate_limit":
            try:
                cap = float(value)
                if isinstance(value, bool) or not math.isfinite(cap) or cap < 0 or not cap.is_integer():
                    return None
            except (TypeError, ValueError, OverflowError):
                return None
        return super()._convert_value(profile_key, value)

    def _coerce_detected(self, profile_key: str, raw_value: str) -> Any:
        if profile_key in {"fullscreen_mode", "frame_rate_limit"}:
            # Do not truncate a fractional saved limit to zero (Unlimited), or
            # a malformed fullscreen value to an apparently matching enum.
            try:
                numeric = float(raw_value)
            except (TypeError, ValueError, OverflowError):
                return None
            if not math.isfinite(numeric) or numeric < 0:
                return None
            return int(numeric) if numeric.is_integer() else numeric
        return super()._coerce_detected(profile_key, raw_value)

    def _get_config_dir(self) -> Path | None:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None

        candidate = Path(local_appdata) / "FortniteGame" / "Saved" / "Config" / "WindowsClient"
        if candidate.is_dir():
            return candidate
        return None
