"""Rivals of Aether 2 game config handler.

Manages Rivals 2-specific game configuration files to enforce ABSO profile targets
such as display mode, VSync, and the native frame-rate limit.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from abso.core.config_safety import (
    INI_SECTION_RE,
    apply_ini_key_patch,
    find_ini_section_bounds,
    parse_ini_assignments,
    read_config_text,
    restore_managed_key_lines,
    validate_allowed_keys,
    write_config_text,
)
from abso.core.models import Issue
from abso.settings.base import SettingsHandler
from abso.settings.ue_game_user_settings import UEGameUserSettingsHandler
from abso.settings.value_parsing import parse_bool_like
from abso.utils.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)


def _get_rivals2_config_dir() -> Path | None:
    """Find the Rivals 2 config directory."""
    import os

    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None

    # UE5 games store configs in LocalAppData/<ProjectName>/Saved/Config/Windows
    candidates = [
        Path(local_appdata) / "Rivals2" / "Saved" / "Config" / "Windows",
        Path(local_appdata) / "RivalsofAether2" / "Saved" / "Config" / "Windows",
    ]

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    return None


class Rivals2ConfigHandler(SettingsHandler):
    """Enforces Rivals 2 game config settings for ABSO profiles.

    Manages the game's GameUserSettings.ini to enforce:
    - Profile-selected fullscreen or borderless mode
    - Profile-selected VSync and native FPS cap
    - Native HDR output intent (saved-file readback, not runtime proof)
    """

    is_critical_verify = True

    TARGET_SECTION_NAME = "/Script/Engine.GameUserSettings"

    MUTABLE_SETTINGS_TO_INI: dict[str, str] = {
        "fullscreen_mode": "FullscreenMode",
        "vsync": "bUseVSync",
        "frame_rate_limit": "FrameRateLimit",
        "hdr_output": "bUseHDRDisplayOutput",
        "hdr_nits": "HDRDisplayOutputNits",
    }

    # bUseRawInput is not documented by UGameUserSettings. Do not write it,
    # even for legacy overrides; leave existing input configuration user-owned.

    # These keys should never be mutated by profile automation.
    PROTECTED_INI_KEYS: set[str] = {
        "PlayerTag",
        "PlayerName",
        "DefaultControlScheme",
        "CurrentControlScheme",
        "ControllerProfile",
        "InputProfile",
        "OnlineProfileName",
        "LastUsedProfile",
        "ProfileName",
    }

    def _get_config_path(self) -> Path | None:
        config_dir = _get_rivals2_config_dir()
        if not config_dir:
            return None

        ini_path = config_dir / "GameUserSettings.ini"
        if not ini_path.is_file():
            return None
        return ini_path

    def detect(self) -> dict[str, Any]:
        """Detect current Rivals 2 game config settings."""
        ini_path = self._get_config_path()
        if not ini_path:
            return {"config_found": False}

        result: dict[str, Any] = {"config_found": True, "config_path": str(ini_path)}

        try:
            content = ini_path.read_text(encoding="utf-8-sig")
            if not self._section_available(content.splitlines()):
                result["config_section_found"] = False
                return result
            assignments = parse_ini_assignments(
                content.splitlines(),
                section_name=self.TARGET_SECTION_NAME,
            )

            if "FullscreenMode" in assignments:
                mode = float(assignments["FullscreenMode"])
                if mode in (0, 1, 2):
                    result["fullscreen_mode"] = int(mode)
            if "bUseVSync" in assignments:
                result["vsync"] = parse_bool_like(assignments["bUseVSync"])
            if "bUseRawInput" in assignments:
                result["raw_input"] = parse_bool_like(assignments["bUseRawInput"])
            if "FrameRateLimit" in assignments:
                try:
                    cap = float(assignments["FrameRateLimit"])
                    if math.isfinite(cap) and cap >= 0:
                        result["frame_rate_limit"] = int(cap) if cap.is_integer() else cap
                except ValueError:
                    logger.debug("Rivals 2 frame rate limit value was non-numeric")
            if "bUseHDRDisplayOutput" in assignments:
                result["hdr_output"] = parse_bool_like(assignments["bUseHDRDisplayOutput"])
            if "HDRDisplayOutputNits" in assignments:
                try:
                    result["hdr_nits"] = int(float(assignments["HDRDisplayOutputNits"]))
                except ValueError:
                    logger.debug("Rivals 2 HDR nits value was non-numeric")
        except Exception as e:
            logger.error(f"Failed to read Rivals 2 config: {e}")

        return result

    def audit(self) -> list[Issue]:
        """verify_active owns lane-specific presentation/sync comparisons.

        Borderless and native VSync are intentional in the capture lanes.
        Neither is a universal defect when the selected target is unknown.
        """
        return []

    @classmethod
    def _section_available(cls, lines: list[str]) -> bool:
        if find_ini_section_bounds(lines, cls.TARGET_SECTION_NAME) is not None:
            return True
        # Support historical sectionless files, but never edit another section
        # through the generic INI helper's whole-file fallback.
        return not any(INI_SECTION_RE.match(line) for line in lines)

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply Rivals 2 game config settings."""
        settings = {key: value for key, value in settings.items() if not key.startswith("_")}

        vrr_cap_policy = settings.pop("vrr_cap_policy", None)
        if settings.pop("auto_vrr_fps_cap", False):
            cap_resolved = False
            try:
                from abso.core.vrr import get_vrr_fps_cap_for_policy
                from abso.settings.nvidia import NvidiaSettingsHandler

                refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
                if refresh_hz and refresh_hz > 0:
                    settings["frame_rate_limit"] = get_vrr_fps_cap_for_policy(
                        refresh_hz, vrr_cap_policy
                    )
                    cap_resolved = True
                    logger.info(
                        "Rivals 2 auto VRR FPS cap: %d (from %d Hz%s)",
                        settings["frame_rate_limit"],
                        refresh_hz,
                        f", {vrr_cap_policy}" if vrr_cap_policy else "",
                    )
            except Exception as e:
                logger.warning("Rivals 2 auto VRR FPS cap detection failed: %s", e)
            if not cap_resolved:
                return {
                    "success": False,
                    "error": (
                        "Rivals 2 automatic FPS cap could not be resolved; no settings were written. "
                        "Check display refresh and cap policy, or request an explicit frame_rate_limit."
                    ),
                    "requires_reboot": False,
                }

        invalid_requested_keys = validate_allowed_keys(
            set(settings.keys()),
            set(self.MUTABLE_SETTINGS_TO_INI.keys()),
        )
        if invalid_requested_keys:
            return {
                "success": False,
                "error": (
                    "Unsupported Rivals 2 config keys requested: "
                    + ", ".join(invalid_requested_keys)
                ),
                "requires_reboot": False,
            }

        ini_path = self._get_config_path()
        if not ini_path:
            return {
                "success": not bool(settings),
                "error": "Rivals 2 GameUserSettings.ini not found; launch the game once to create it." if settings else None,
                "requires_reboot": False,
                "applied": [],
            }

        try:
            content = ini_path.read_text(encoding="utf-8-sig")
            lines = content.splitlines()
            if not self._section_available(lines):
                return {
                    "success": False,
                    "error": "Rivals 2 Engine.GameUserSettings section not found; no settings were written.",
                    "requires_reboot": False,
                }
            replacements, conversion_errors = self._build_replacements(settings)
            if conversion_errors:
                return {
                    "success": False,
                    "error": "; ".join(conversion_errors),
                    "requires_reboot": False,
                }

            if not replacements:
                return {
                    "success": True,
                    "error": None,
                    "requires_reboot": False,
                    "applied": [],
                }

            original_assignments = parse_ini_assignments(
                lines,
                section_name=self.TARGET_SECTION_NAME,
            )
            patch_result = apply_ini_key_patch(
                lines=lines,
                replacements=replacements,
                append_missing=True,
                section_name=self.TARGET_SECTION_NAME,
            )
            new_assignments = parse_ini_assignments(
                patch_result.lines,
                section_name=self.TARGET_SECTION_NAME,
            )

            protected_mutations = []
            for key in self.PROTECTED_INI_KEYS:
                if key not in original_assignments:
                    continue
                if new_assignments.get(key) != original_assignments.get(key):
                    protected_mutations.append(key)

            if protected_mutations:
                return {
                    "success": False,
                    "error": (
                        "Protected Rivals 2 profile/control keys were modified: "
                        + ", ".join(sorted(protected_mutations))
                    ),
                    "requires_reboot": False,
                }

            if patch_result.changed:
                atomic_write_text(ini_path, "\n".join(patch_result.lines) + "\n")
                logger.info(
                    "Updated Rivals 2 config: %s (%s changed, %s appended)",
                    ini_path,
                    len(patch_result.changed_keys),
                    len(patch_result.appended_keys),
                )

            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "applied": sorted(patch_result.changed_keys | patch_result.appended_keys),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "requires_reboot": False,
            }

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify requested Rivals 2 config values are active."""
        settings = {key: value for key, value in settings.items() if not key.startswith("_")}
        results: dict[str, Any] = {"all_active": True, "settings": {}}
        vrr_cap_policy = settings.pop("vrr_cap_policy", None)
        invalid_requested_keys = validate_allowed_keys(
            set(settings) - {"auto_vrr_fps_cap"}, set(self.MUTABLE_SETTINGS_TO_INI)
        )
        for key in invalid_requested_keys:
            results["all_active"] = False
            results["settings"][key] = {
                "target": settings[key], "current": None, "active": False,
                "status": "unsupported",
                "note": "This setting is not managed by the Rivals 2 config handler.",
            }
        if settings.pop("auto_vrr_fps_cap", False):
            cap_resolved = False
            try:
                from abso.core.vrr import get_vrr_fps_cap_for_policy
                from abso.settings.nvidia import NvidiaSettingsHandler

                refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
                if refresh_hz and refresh_hz > 0:
                    settings["frame_rate_limit"] = get_vrr_fps_cap_for_policy(
                        refresh_hz, vrr_cap_policy
                    )
                    cap_resolved = True
            except Exception as e:
                logger.warning("Rivals 2 auto VRR FPS cap verification failed: %s", e)
            if not cap_resolved:
                results["all_active"] = False
                results["settings"]["auto_vrr_fps_cap"] = {
                    "target": True,
                    "current": None,
                    "active": False,
                    "status": "unverifiable",
                    "note": (
                        "The requested automatic FPS cap could not be resolved "
                        "from the primary display refresh and cap policy."
                    ),
                }

        current = self.detect()

        for key in self.MUTABLE_SETTINGS_TO_INI:
            if key not in settings:
                continue

            target = settings[key]
            current_value = current.get(key)
            _, conversion_errors = self._build_replacements({key: target})
            readable = bool(current.get("config_found")) and key in current
            is_active = not conversion_errors and readable and current_value == target
            results["settings"][key] = {
                "target": target,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False
                if conversion_errors:
                    results["settings"][key].update({
                        "status": "invalid", "note": "; ".join(conversion_errors),
                    })
                elif not readable:
                    results["settings"][key].update({
                        "status": "unverifiable",
                        "note": (
                            "GameUserSettings.ini not found; launch Rivals 2 to create its settings."
                            if not current.get("config_found")
                            else "The requested setting could not be read from the game config."
                        ),
                    })

        return results

    def backup(self) -> dict[str, Any]:
        """Retain the full file for recovery; normal restore patches owned keys."""
        ini_path = self._get_config_path()
        if not ini_path:
            return {"config_found": False}

        try:
            return {
                "config_found": True,
                "config_path": str(ini_path),
                "file_content": ini_path.read_text(encoding="utf-8"),
            }
        except Exception as e:
            logger.error("Failed to back up Rivals 2 config %s: %s", ini_path, e)
            return {"config_found": False}

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore managed keys while preserving newer controls and graphics.

        Reuse the UE handler's section-aware restore and missing-file recovery.
        Undocumented raw input remains user-owned during baseline restoration.
        """
        if not data.get("config_found"):
            return True
        if data.get("file_content") is None:
            return self._restore_from_legacy_payload(data)
        restorer = UEGameUserSettingsHandler()
        restorer.TARGET_SECTION_NAME = self.TARGET_SECTION_NAME
        restorer.MUTABLE_SETTINGS_TO_INI = dict(self.MUTABLE_SETTINGS_TO_INI)
        restorer.MIRROR_FULLSCREEN_MODE_KEYS = ("LastConfirmedFullscreenMode",)
        restorer.PROTECTED_INI_KEYS = self.PROTECTED_INI_KEYS
        return restorer.restore(data)

    def _restore_from_legacy_payload(self, data: dict[str, Any]) -> bool:
        """Selectively restore detected fields from a legacy backup payload."""
        legacy_keys = (
            "fullscreen_mode",
            "vsync",
            "frame_rate_limit",
            "hdr_output",
            "hdr_nits",
        )
        settings = {key: data[key] for key in legacy_keys if key in data}
        if not settings:
            return True

        ini_path = self._get_config_path()
        if ini_path is None:
            return True

        replacements, errors = self._build_replacements(settings)
        if errors:
            logger.error(
                "Failed to restore legacy Rivals 2 config payload: %s",
                "; ".join(errors),
            )
            return False

        # Legacy payloads contain detected values instead of file text.  An
        # unsectioned synthetic backup is accepted as the target section while
        # the merge remains strict against the sectioned live file.
        backup_content = "\n".join(
            f"{key}={value}" for key, value in replacements.items()
        )
        try:
            self._restore_managed_content(
                ini_path,
                backup_content,
                managed_keys=set(replacements),
            )
            return True
        except OSError as e:
            logger.error("Failed to restore legacy Rivals 2 config %s: %s", ini_path, e)
            return False

    def _restore_managed_content(
        self,
        ini_path: Path,
        backup_content: str,
        *,
        managed_keys: set[str] | None = None,
    ) -> None:
        """Merge a backed-up Rivals settings section into the current file."""
        current_content = read_config_text(ini_path)
        if managed_keys is None:
            managed_keys = set(self.MUTABLE_SETTINGS_TO_INI.values()) | {
                "LastConfirmedFullscreenMode"
            }
        restored_content = restore_managed_key_lines(
            current_content=current_content,
            backup_content=backup_content,
            managed_keys=managed_keys,
            section_name=self.TARGET_SECTION_NAME,
        )
        if restored_content != current_content:
            write_config_text(ini_path, restored_content)

    def _build_replacements(self, settings: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
        """Build INI replacements and collect conversion errors."""
        replacements: dict[str, str] = {}
        errors: list[str] = []

        if "fullscreen_mode" in settings:
            try:
                mode = float(settings["fullscreen_mode"])
                if isinstance(settings["fullscreen_mode"], bool) or mode not in (0, 1, 2):
                    raise ValueError
                fullscreen_mode = str(int(mode))
                replacements["FullscreenMode"] = fullscreen_mode
                replacements["LastConfirmedFullscreenMode"] = fullscreen_mode
            except (TypeError, ValueError):
                errors.append("fullscreen_mode must be 0 (fullscreen), 1 (borderless), or 2 (windowed)")

        if "vsync" in settings:
            parsed = parse_bool_like(settings["vsync"])
            if parsed is None:
                errors.append("vsync must be a boolean")
            else:
                replacements["bUseVSync"] = "True" if parsed else "False"

        if "frame_rate_limit" in settings:
            try:
                frame_cap = float(settings["frame_rate_limit"])
                if (isinstance(settings["frame_rate_limit"], bool) or not math.isfinite(frame_cap)
                        or frame_cap < 0 or not frame_cap.is_integer()):
                    raise ValueError
                replacements["FrameRateLimit"] = str(int(frame_cap))
            except (TypeError, ValueError):
                errors.append("frame_rate_limit must be a finite non-negative integer")

        if "hdr_output" in settings:
            parsed = parse_bool_like(settings["hdr_output"])
            if parsed is None:
                errors.append("hdr_output must be a boolean")
            else:
                replacements["bUseHDRDisplayOutput"] = "True" if parsed else "False"

        if "hdr_nits" in settings:
            try:
                hdr_nits = int(float(settings["hdr_nits"]))
                if hdr_nits <= 0:
                    raise ValueError
                replacements["HDRDisplayOutputNits"] = str(hdr_nits)
            except (TypeError, ValueError, OverflowError):
                errors.append("hdr_nits must be a positive number")

        return replacements, errors
