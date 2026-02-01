"""Rivals of Aether 2 game config handler.

Manages Rivals 2-specific game configuration files to enforce optimal settings
like exclusive fullscreen mode and raw input.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

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
            modified = False

            setting_map = {}
            if "fullscreen_mode" in settings:
                setting_map["FullscreenMode"] = str(settings["fullscreen_mode"])
            if "vsync" in settings:
                setting_map["bUseVSync"] = "True" if settings["vsync"] else "False"
            if "raw_input" in settings:
                setting_map["bUseRawInput"] = "True" if settings["raw_input"] else "False"

            new_lines = []
            for line in lines:
                stripped = line.strip()
                replaced = False
                for key, value in setting_map.items():
                    if stripped.startswith(f"{key}="):
                        old_value = stripped.split("=", 1)[1]
                        if old_value != value:
                            new_lines.append(f"{key}={value}")
                            modified = True
                            replaced = True
                        break
                if not replaced:
                    new_lines.append(line)

            if modified:
                ini_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                logger.info(f"Updated Rivals 2 config: {ini_path}")

            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "requires_reboot": False,
            }

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

        if settings:
            result = self.apply(settings)
            return result.get("success", False)
        return True
