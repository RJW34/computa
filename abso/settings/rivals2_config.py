"""Rivals of Aether 2 game config handler.

Manages Rivals 2-specific game configuration files to enforce ABSO profile targets
like exclusive fullscreen mode and raw input.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from abso.core.config_safety import (
    apply_ini_key_patch,
    parse_ini_assignments,
    validate_allowed_keys,
)
from abso.core.models import Issue
from abso.settings.base import SettingsHandler
from abso.settings.value_parsing import parse_bool_like

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
    - Exclusive fullscreen mode for strict profiles
    - VSync off (handled by NVCP instead)
    - Raw input for best input latency
    """

    is_critical_verify = True

    TARGET_SECTION_NAME = "/Script/Engine.GameUserSettings"

    MUTABLE_SETTINGS_TO_INI: dict[str, str] = {
        "fullscreen_mode": "FullscreenMode",
        "vsync": "bUseVSync",
        "raw_input": "bUseRawInput",
        "frame_rate_limit": "FrameRateLimit",
        "hdr_output": "bUseHDRDisplayOutput",
        "hdr_nits": "HDRDisplayOutputNits",
    }

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
            content = ini_path.read_text(encoding="utf-8", errors="replace")
            assignments = parse_ini_assignments(
                content.splitlines(),
                section_name=self.TARGET_SECTION_NAME,
            )

            if "FullscreenMode" in assignments:
                result["fullscreen_mode"] = int(float(assignments["FullscreenMode"]))
            if "bUseVSync" in assignments:
                result["vsync"] = parse_bool_like(assignments["bUseVSync"])
            if "bUseRawInput" in assignments:
                result["raw_input"] = parse_bool_like(assignments["bUseRawInput"])
            if "FrameRateLimit" in assignments:
                try:
                    result["frame_rate_limit"] = int(float(assignments["FrameRateLimit"]))
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
        """Audit Rivals 2 game config."""
        issues: list[Issue] = []
        current = self.detect()

        if not current.get("config_found"):
            return issues  # Game not installed, nothing to audit

        if current.get("fullscreen_mode") is not None and current["fullscreen_mode"] != 0:
            mode_names = {0: "Exclusive", 1: "Borderless", 2: "Windowed"}
            issues.append(Issue(
                title="Rivals 2 not in exclusive fullscreen",
                severity="warning",
                current_value=mode_names.get(current["fullscreen_mode"], f"Unknown ({current['fullscreen_mode']})"),
                optimal_value="Exclusive Fullscreen (0)",
                explanation=(
                    "This strict Rivals 2 profile expects exclusive fullscreen. "
                    "Use a capture/borderless profile if you want the windowed path."
                ),
                category="game_config",
            ))

        if current.get("vsync") is True:
            issues.append(Issue(
                title="Rivals 2 VSync enabled in game",
                severity="warning",
                current_value="Enabled",
                optimal_value="Disabled (use NVCP instead)",
                explanation="In-game VSync should be off; sync is managed by NVIDIA Control Panel.",
                category="game_config",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply Rivals 2 game config settings."""
        settings = dict(settings)

        if settings.pop("auto_vrr_fps_cap", False):
            try:
                from abso.core.vrr import get_vrr_fps_cap
                from abso.settings.nvidia import NvidiaSettingsHandler

                refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
                if refresh_hz and refresh_hz > 0:
                    settings["frame_rate_limit"] = get_vrr_fps_cap(refresh_hz)
                    logger.info(
                        "Rivals 2 auto VRR FPS cap: %d (from %d Hz)",
                        settings["frame_rate_limit"],
                        refresh_hz,
                    )
            except Exception as e:
                logger.warning("Rivals 2 auto VRR FPS cap detection failed: %s", e)

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
                "success": True,
                "error": None,
                "requires_reboot": False,
                "skipped": "Rivals 2 GameUserSettings.ini not found",
            }

        try:
            content = ini_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
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
                ini_path.write_text("\n".join(patch_result.lines) + "\n", encoding="utf-8")
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
        settings = dict(settings)
        if settings.pop("auto_vrr_fps_cap", False):
            try:
                from abso.core.vrr import get_vrr_fps_cap
                from abso.settings.nvidia import NvidiaSettingsHandler

                refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
                if refresh_hz and refresh_hz > 0:
                    settings["frame_rate_limit"] = get_vrr_fps_cap(refresh_hz)
            except Exception as e:
                logger.warning("Rivals 2 auto VRR FPS cap verification failed: %s", e)

        current = self.detect()
        results: dict[str, Any] = {"all_active": True, "settings": {}}

        if not current.get("config_found"):
            return results

        for key in self.MUTABLE_SETTINGS_TO_INI:
            if key not in settings:
                continue

            target = settings[key]
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
        """Back up the full Rivals 2 config file for lossless restore."""
        ini_path = self._get_config_path()
        if not ini_path:
            return {"config_found": False}

        try:
            return {
                "config_found": True,
                "config_path": str(ini_path),
                "file_content": ini_path.read_text(encoding="utf-8", errors="replace"),
            }
        except Exception as e:
            logger.error("Failed to back up Rivals 2 config %s: %s", ini_path, e)
            return {"config_found": False}

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Rivals 2 config from a backup payload.

        New backups store the full INI under ``file_content``. Older backups
        (taken before the full-file format) only persisted detected values,
        so we fall back to re-applying those detected fields rather than
        failing the baseline restore.
        """
        if not data.get("config_found"):
            return True  # Nothing to restore

        file_content = data.get("file_content")
        if file_content is None:
            return self._restore_from_legacy_payload(data)

        config_path = data.get("config_path")
        if not config_path:
            return False

        try:
            ini_path = Path(config_path)
            ini_path.parent.mkdir(parents=True, exist_ok=True)
            ini_path.write_text(file_content, encoding="utf-8")
            return True
        except OSError as e:
            logger.error("Failed to restore Rivals 2 config %s: %s", config_path, e)
            return False

    def _restore_from_legacy_payload(self, data: dict[str, Any]) -> bool:
        """Re-apply detected fields from a pre-full-file backup payload."""
        legacy_keys = (
            "fullscreen_mode",
            "vsync",
            "raw_input",
            "frame_rate_limit",
            "hdr_output",
            "hdr_nits",
        )
        settings = {key: data[key] for key in legacy_keys if key in data}
        if not settings:
            return True

        if self._get_config_path() is None:
            return True

        result = self.apply(settings)
        return bool(result.get("success", False))

    def _build_replacements(self, settings: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
        """Build INI replacements and collect conversion errors."""
        replacements: dict[str, str] = {}
        errors: list[str] = []

        if "fullscreen_mode" in settings:
            try:
                fullscreen_mode = str(int(settings["fullscreen_mode"]))
                replacements["FullscreenMode"] = fullscreen_mode
                replacements["LastConfirmedFullscreenMode"] = fullscreen_mode
            except (TypeError, ValueError):
                errors.append("fullscreen_mode must be an integer")

        if "vsync" in settings:
            parsed = parse_bool_like(settings["vsync"])
            if parsed is None:
                errors.append("vsync must be a boolean")
            else:
                replacements["bUseVSync"] = "True" if parsed else "False"

        if "raw_input" in settings:
            parsed = parse_bool_like(settings["raw_input"])
            if parsed is None:
                errors.append("raw_input must be a boolean")
            else:
                replacements["bUseRawInput"] = "True" if parsed else "False"

        if "frame_rate_limit" in settings:
            try:
                frame_cap = int(float(settings["frame_rate_limit"]))
                if frame_cap < 0:
                    raise ValueError
                replacements["FrameRateLimit"] = str(frame_cap)
            except (TypeError, ValueError):
                errors.append("frame_rate_limit must be a non-negative number")

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
            except (TypeError, ValueError):
                errors.append("hdr_nits must be a positive number")

        return replacements, errors
