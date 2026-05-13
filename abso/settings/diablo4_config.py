"""Diablo IV LocalPrefs.txt handler."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


def _get_diablo4_local_prefs_path() -> Path | None:
    """Return the Diablo IV LocalPrefs.txt path when available."""
    import os

    userprofile = os.environ.get("USERPROFILE")
    if not userprofile:
        return None

    prefs_path = Path(userprofile) / "Documents" / "Diablo IV" / "LocalPrefs.txt"
    if prefs_path.is_file():
        return prefs_path
    return None


class Diablo4ConfigHandler(SettingsHandler):
    """Enforce Diablo IV's native LocalPrefs.txt settings."""

    is_critical_verify = True

    _KV_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\s+"([^"]*)"\s*$')

    MUTABLE_SETTINGS_TO_PREFS: dict[str, str] = {
        "window_mode": "DisplayModeWindowMode",
        "refresh_rate": "DisplayModeRefreshRate",
        "hdr_output": "DisplayModeColorSpace",
        "hdr_black_point": "HDRBlackPoint",
        "hdr_white_point": "HDRWhitePoint",
        "hdr_brightness": "HDRBrightness",
        "vsync": "Vsync",
        "reflex": "Reflex",
        "limit_foreground_fps": "LimitForegroundFPS",
        "foreground_fps_limit": "MaxForegroundFPS",
        "limit_background_fps": "LimitBackgroundFPS",
        "background_fps_limit": "MaxBackgroundFPS",
    }

    BOOL_SETTINGS: frozenset[str] = frozenset({
        "hdr_output",
        "vsync",
        "reflex",
        "limit_foreground_fps",
        "limit_background_fps",
    })
    FLOAT_SETTINGS: frozenset[str] = frozenset({
        "hdr_black_point",
        "hdr_white_point",
        "hdr_brightness",
    })

    AUTO_REFRESH_RATE_KEY = "auto_refresh_rate"
    AUTO_VRR_FPS_CAP_KEY = "auto_vrr_fps_cap"

    def detect(self) -> dict[str, Any]:
        """Detect current Diablo IV LocalPrefs.txt values."""
        prefs_path = _get_diablo4_local_prefs_path()
        if not prefs_path:
            return {"config_found": False}

        result: dict[str, Any] = {"config_found": True, "config_path": str(prefs_path)}

        try:
            content = prefs_path.read_text(encoding="utf-8", errors="replace")
            values = self._parse_pref_lines(content.splitlines())
            prefs_to_settings = {v: k for k, v in self.MUTABLE_SETTINGS_TO_PREFS.items()}
            for pref_key, raw_value in values.items():
                profile_key = prefs_to_settings.get(pref_key)
                if profile_key is None:
                    continue
                result[profile_key] = self._coerce_detected(profile_key, raw_value)
        except Exception as e:
            logger.error("Failed to read Diablo IV LocalPrefs.txt: %s", e)

        return result

    def audit(self) -> list[Issue]:
        """Audit Diablo IV's native config for the low-latency HDR/SDR lanes."""
        issues: list[Issue] = []
        current = self.detect()

        if not current.get("config_found"):
            return issues

        if current.get("window_mode") not in {1, None}:
            issues.append(Issue(
                title="Diablo IV is not using the intended fullscreen path",
                severity="warning",
                current_value=str(current.get("window_mode")),
                optimal_value="1 (Fullscreen)",
                explanation="ABSO expects Diablo IV to stay on the native fullscreen presentation path.",
                category="game_config",
            ))

        if current.get("vsync") is True:
            issues.append(Issue(
                title="Diablo IV VSync enabled in-game",
                severity="warning",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation="Keep in-game VSync off so the chosen VRR/driver sync path stays authoritative.",
                category="game_config",
            ))

        if current.get("reflex") is not True:
            issues.append(Issue(
                title="Diablo IV Reflex not enabled",
                severity="info",
                current_value=str(current.get("reflex")),
                optimal_value="Enabled",
                explanation="Diablo IV exposes native Reflex in LocalPrefs.txt, so ABSO expects it to stay on.",
                category="game_config",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply native Diablo IV LocalPrefs.txt values."""
        requested = dict(settings)
        notices: list[str] = []

        auto_refresh = requested.pop(self.AUTO_REFRESH_RATE_KEY, False)
        auto_vrr_cap = requested.pop(self.AUTO_VRR_FPS_CAP_KEY, False)

        refresh_hz: float | None = None
        if auto_refresh or auto_vrr_cap:
            try:
                from abso.settings.nvidia import NvidiaSettingsHandler

                refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
            except Exception as e:
                logger.warning("Diablo IV auto-detect refresh rate failed: %s", e)

        if auto_refresh and refresh_hz and refresh_hz > 0:
            requested["refresh_rate"] = int(round(refresh_hz))
            logger.info(
                "Diablo IV auto refresh rate: %d Hz",
                requested["refresh_rate"],
            )

        if auto_vrr_cap:
            # Prefer in-game limiter per Blur Busters G-SYNC 101: in-game caps have
            # lower latency than driver/NVCP caps. If we can't compute refresh - 3,
            # surface a notice so the caller can fall back to the NVIDIA driver cap.
            if refresh_hz and refresh_hz > 0:
                from abso.core.vrr import get_vrr_fps_cap

                cap = get_vrr_fps_cap(refresh_hz)
                requested["limit_foreground_fps"] = True
                requested["foreground_fps_limit"] = cap
                logger.info(
                    "Diablo IV auto VRR FPS cap: %d (from %.2f Hz)", cap, refresh_hz,
                )
            else:
                notices.append(
                    "Diablo IV auto_vrr_fps_cap skipped: refresh rate detection "
                    "failed. In-game foreground cap was NOT set; fall back to the "
                    "NVIDIA driver cap (NvidiaSettingsHandler.auto_vrr_fps_cap) "
                    "or set refresh_rate + foreground_fps_limit manually."
                )

        invalid_keys = sorted(set(requested.keys()) - set(self.MUTABLE_SETTINGS_TO_PREFS))
        if invalid_keys:
            return {
                "success": False,
                "error": "Unsupported Diablo IV config keys requested: " + ", ".join(invalid_keys),
                "requires_reboot": False,
            }

        prefs_path = _get_diablo4_local_prefs_path()
        if not prefs_path:
            result: dict[str, Any] = {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "skipped": "Diablo IV LocalPrefs.txt not found",
            }
            if auto_vrr_cap:
                notices.append(
                    "Diablo IV LocalPrefs.txt not found; auto_vrr_fps_cap could "
                    "not be enforced in-game. The NVIDIA driver cap (if enabled) "
                    "will remain the limiter."
                )
            if notices:
                result["notices"] = notices
            return result

        try:
            content = prefs_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            replacements, conversion_errors = self._build_replacements(requested)
            if conversion_errors:
                return {
                    "success": False,
                    "error": "; ".join(conversion_errors),
                    "requires_reboot": False,
                }

            if not replacements:
                result = {
                    "success": True,
                    "error": None,
                    "requires_reboot": False,
                    "applied": [],
                }
                if notices:
                    result["notices"] = notices
                return result

            patched_lines, changed_keys, appended_keys = self._apply_replacements(lines, replacements)

            if changed_keys or appended_keys:
                prefs_path.write_text("\n".join(patched_lines) + "\n", encoding="utf-8")
                logger.info(
                    "Updated Diablo IV LocalPrefs.txt: %s (%d changed, %d appended)",
                    prefs_path,
                    len(changed_keys),
                    len(appended_keys),
                )

            result = {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "applied": sorted(changed_keys | appended_keys),
            }
            if notices:
                result["notices"] = notices
            return result
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "requires_reboot": False,
            }

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify Diablo IV LocalPrefs.txt values are active."""
        current = self.detect()
        results: dict[str, Any] = {"all_active": True, "settings": {}}

        if not current.get("config_found"):
            return results

        requested = dict(settings)
        auto_refresh = requested.pop(self.AUTO_REFRESH_RATE_KEY, False)
        auto_vrr_cap = requested.pop(self.AUTO_VRR_FPS_CAP_KEY, False)

        refresh_hz: float | None = None
        if auto_refresh or auto_vrr_cap:
            try:
                from abso.settings.nvidia import NvidiaSettingsHandler

                refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
            except Exception:
                pass

        if auto_refresh and refresh_hz and refresh_hz > 0:
            requested["refresh_rate"] = int(round(refresh_hz))

        if auto_vrr_cap and refresh_hz and refresh_hz > 0:
            from abso.core.vrr import get_vrr_fps_cap

            requested["limit_foreground_fps"] = True
            requested["foreground_fps_limit"] = get_vrr_fps_cap(refresh_hz)

        for key, target in requested.items():
            current_value = current.get(key)
            is_active = current_value == target
            results["settings"][key] = {
                "target": target,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        return results

    def backup(self) -> dict[str, Any]:
        """Back up the full LocalPrefs.txt contents for lossless restore."""
        prefs_path = _get_diablo4_local_prefs_path()
        if not prefs_path:
            return {"config_found": False}

        try:
            return {
                "config_found": True,
                "config_path": str(prefs_path),
                "file_content": prefs_path.read_text(encoding="utf-8", errors="replace"),
            }
        except Exception as e:
            logger.error("Failed to back up Diablo IV LocalPrefs.txt: %s", e)
            return {"config_found": False}

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Diablo IV LocalPrefs.txt from backup."""
        if not data.get("config_found"):
            return True

        file_content = data.get("file_content")
        config_path = data.get("config_path")
        if file_content is None or not config_path:
            return False

        try:
            prefs_path = Path(config_path)
            prefs_path.parent.mkdir(parents=True, exist_ok=True)
            prefs_path.write_text(file_content, encoding="utf-8")
            return True
        except OSError as e:
            logger.error("Failed to restore Diablo IV LocalPrefs.txt: %s", e)
            return False

    def _parse_pref_lines(self, lines: list[str]) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in lines:
            match = self._KV_RE.match(line)
            if not match:
                continue
            values[match.group(1)] = match.group(2)
        return values

    def _apply_replacements(
        self,
        lines: list[str],
        replacements: dict[str, str],
    ) -> tuple[list[str], set[str], set[str]]:
        changed: set[str] = set()
        appended: set[str] = set()
        updated = list(lines)

        for pref_key, value in replacements.items():
            line_value = f'{pref_key} "{value}"'
            for index, line in enumerate(updated):
                match = self._KV_RE.match(line)
                if not match or match.group(1) != pref_key:
                    continue
                if match.group(2) == value:
                    break
                updated[index] = line_value
                changed.add(pref_key)
                break
            else:
                updated.append(line_value)
                appended.add(pref_key)

        return updated, changed, appended

    def _build_replacements(self, settings: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
        replacements: dict[str, str] = {}
        errors: list[str] = []

        for profile_key, value in settings.items():
            pref_key = self.MUTABLE_SETTINGS_TO_PREFS.get(profile_key)
            if pref_key is None:
                continue

            converted = self._convert_value(profile_key, value)
            if converted is None:
                errors.append(f"{profile_key} has an invalid value")
                continue

            replacements[pref_key] = converted

        return replacements, errors

    def _convert_value(self, profile_key: str, value: Any) -> str | None:
        if profile_key in self.BOOL_SETTINGS:
            parsed = self._parse_bool(value)
            return None if parsed is None else ("1" if parsed else "0")

        if profile_key in self.FLOAT_SETTINGS:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None
            if numeric < 0:
                return None
            return f"{numeric:.6f}"

        try:
            numeric = int(float(value))
        except (TypeError, ValueError):
            return None

        if profile_key in {"refresh_rate", "foreground_fps_limit", "background_fps_limit"} and numeric < 0:
            return None
        return str(numeric)

    def _coerce_detected(self, profile_key: str, raw_value: str) -> Any:
        if profile_key in self.BOOL_SETTINGS:
            parsed = self._parse_bool(raw_value)
            return bool(parsed) if parsed is not None else raw_value

        if profile_key in self.FLOAT_SETTINGS:
            try:
                return float(raw_value)
            except (TypeError, ValueError):
                return raw_value

        try:
            return int(float(raw_value))
        except (TypeError, ValueError):
            return raw_value

    @staticmethod
    def _parse_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return None
