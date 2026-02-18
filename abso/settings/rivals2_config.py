"""Rivals of Aether 2 game config handler.

Manages Rivals 2-specific game configuration files to enforce optimal settings
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
    """Enforces Rivals 2 game config settings for optimal performance.

    Manages the game's GameUserSettings.ini to enforce:
    - Exclusive fullscreen mode (lowest latency)
    - VSync off (handled by NVCP instead)
    - Raw input for best input latency
    """

    MUTABLE_SETTINGS_TO_INI: dict[str, str] = {
        "fullscreen_mode": "FullscreenMode",
        "vsync": "bUseVSync",
        "raw_input": "bUseRawInput",
        "frame_rate_limit": "FrameRateLimit",
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

    def detect(self) -> dict[str, Any]:
        """Detect current Rivals 2 game config settings."""
        config_dir = _get_rivals2_config_dir()
        if not config_dir:
            return {"config_found": False}

        ini_path = config_dir / "GameUserSettings.ini"
        if not ini_path.is_file():
            return {"config_found": False}

        result: dict[str, Any] = {"config_found": True, "config_path": str(ini_path)}

        try:
            content = ini_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("FullscreenMode="):
                    result["fullscreen_mode"] = int(stripped.split("=", 1)[1])
                elif stripped.startswith("bUseVSync="):
                    result["vsync"] = stripped.split("=", 1)[1].lower() == "true"
                elif stripped.startswith("bUseRawInput="):
                    result["raw_input"] = stripped.split("=", 1)[1].lower() == "true"
                elif stripped.startswith("FrameRateLimit="):
                    try:
                        result["frame_rate_limit"] = int(float(stripped.split("=", 1)[1]))
                    except ValueError:
                        logger.debug("Rivals 2 frame rate limit value was non-numeric")
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
                    "Exclusive fullscreen provides the lowest input latency. "
                    "Borderless windowed adds ~1 frame of latency through DWM composition."
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

        config_dir = _get_rivals2_config_dir()
        if not config_dir:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "skipped": "Rivals 2 config directory not found (game may not be installed)",
            }

        ini_path = config_dir / "GameUserSettings.ini"
        if not ini_path.is_file():
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "skipped": "GameUserSettings.ini not found",
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

            original_assignments = parse_ini_assignments(lines)
            patch_result = apply_ini_key_patch(
                lines=lines,
                replacements=replacements,
                append_missing=True,
            )
            new_assignments = parse_ini_assignments(patch_result.lines)

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
        """Backup current Rivals 2 config."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Rivals 2 config from backup."""
        if not data.get("config_found"):
            return True  # Nothing to restore

        settings = {}
        if "fullscreen_mode" in data:
            settings["fullscreen_mode"] = data["fullscreen_mode"]
        if "vsync" in data:
            settings["vsync"] = data["vsync"]
        if "raw_input" in data:
            settings["raw_input"] = data["raw_input"]
        if "frame_rate_limit" in data:
            settings["frame_rate_limit"] = data["frame_rate_limit"]

        if settings:
            result = self.apply(settings)
            return result.get("success", False)
        return True

    def _build_replacements(self, settings: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
        """Build INI replacements and collect conversion errors."""
        replacements: dict[str, str] = {}
        errors: list[str] = []

        if "fullscreen_mode" in settings:
            try:
                replacements["FullscreenMode"] = str(int(settings["fullscreen_mode"]))
            except (TypeError, ValueError):
                errors.append("fullscreen_mode must be an integer")

        if "vsync" in settings:
            parsed = self._parse_bool(settings["vsync"])
            if parsed is None:
                errors.append("vsync must be a boolean")
            else:
                replacements["bUseVSync"] = "True" if parsed else "False"

        if "raw_input" in settings:
            parsed = self._parse_bool(settings["raw_input"])
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

        return replacements, errors

    def _parse_bool(self, value: Any) -> bool | None:
        """Convert bool-like values into a bool or None when unsupported."""
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
