"""Dolphin emulator configuration handler for Slippi.

Manages latency-critical Dolphin settings including:
- Immediately Present XFB (ImmediateXFBEnable) - skips frame buffer queue
- Rush Frame Presentation (RushPresentation) - experimental 8-14ms reduction
- Smooth Frame Presentation (SmoothPresentation) - for VRR displays
- Backend Multithreading (BackendMultithreading) - driver threading overhead
- GPU Sync (SyncGPU) - adds latency when enabled

Sources:
- Dolphin Progress Report December 2025 (Rush Frame Presentation)
- Dolphin Performance Guide
- melee.tv competitive optimization
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DolphinConfigHandler:
    """Handler for Dolphin/Slippi configuration files.

    Slippi Launcher tends to overwrite certain Dolphin settings on launch.
    This handler ensures optimal latency settings are applied to the config
    files before the game is launched.
    """

    def __init__(self) -> None:
        self.slippi_base = Path(os.environ["APPDATA"]) / "Slippi Launcher" / "netplay"
        self.config_dir = self.slippi_base / "User" / "Config"
        self.gfx_ini = self.config_dir / "GFX.ini"
        self.dolphin_ini = self.config_dir / "Dolphin.ini"

    GFX_KEY_MAP: dict[str, tuple[str, str]] = {
        "efb_scale": ("EFBScale", "Settings"),
        "texture_scaling_factor": ("TextureScalingFactor", "Enhancements"),
        "use_scaling_filter": ("UseScalingFilter", "Enhancements"),
        "use_deposterize": ("UseDePosterize", "Enhancements"),
        "backend_multithreading": ("BackendMultithreading", "Settings"),
        "vsync": ("VSync", "Hardware"),
    }

    DOLPHIN_KEY_MAP: dict[str, tuple[str, str]] = {
        "reduce_timing_dispersion": ("ReduceTimingDispersion", "Core"),
        "immediate_xfb_enable": ("ImmediateXFBEnable", "Core"),
        "rush_presentation": ("RushPresentation", "Core"),
        "smooth_presentation": ("SmoothPresentation", "Core"),
        "sync_gpu": ("SyncGPU", "Core"),
        "timing_variance": ("TimingVariance", "Core"),
    }

    def detect(self) -> dict[str, Any]:
        """Detect current Dolphin configuration state."""
        result = {
            "slippi_installed": self.slippi_base.exists(),
            "gfx_ini_exists": self.gfx_ini.exists(),
            "dolphin_ini_exists": self.dolphin_ini.exists(),
            "current_settings": {},
        }

        if self.gfx_ini.exists():
            content = self.gfx_ini.read_text(encoding="utf-8")
            result["current_settings"]["EFBScale"] = self._extract_value(content, "EFBScale")
            result["current_settings"]["TextureScalingFactor"] = self._extract_value(
                content, "TextureScalingFactor"
            )
            result["current_settings"]["UseScalingFilter"] = self._extract_value(
                content, "UseScalingFilter"
            )
            result["current_settings"]["UseDePosterize"] = self._extract_value(
                content, "UseDePosterize"
            )
            result["current_settings"]["BackendMultithreading"] = self._extract_value(
                content, "BackendMultithreading"
            )
            result["current_settings"]["VSync"] = self._extract_value(content, "VSync")

        if self.dolphin_ini.exists():
            content = self.dolphin_ini.read_text(encoding="utf-8")
            result["current_settings"]["ReduceTimingDispersion"] = self._extract_value(
                content, "ReduceTimingDispersion"
            )
            result["current_settings"]["ImmediateXFBEnable"] = self._extract_value(
                content, "ImmediateXFBEnable"
            )
            result["current_settings"]["RushPresentation"] = self._extract_value(
                content, "RushPresentation"
            )
            result["current_settings"]["SmoothPresentation"] = self._extract_value(
                content, "SmoothPresentation"
            )
            result["current_settings"]["SyncGPU"] = self._extract_value(
                content, "SyncGPU"
            )
            result["current_settings"]["TimingVariance"] = self._extract_value(
                content, "TimingVariance"
            )

        return result

    def _extract_value(self, content: str, key: str) -> str | None:
        """Extract a value from INI content."""
        match = re.search(rf"^{key}\s*=\s*(.+)$", content, re.MULTILINE)
        return match.group(1).strip() if match else None

    def _replace_value(self, content: str, key: str, old_value: str, new_value: str) -> str:
        """Replace a value in INI content."""
        pattern = rf"^({key}\s*=\s*){re.escape(old_value)}$"
        return re.sub(pattern, rf"\g<1>{new_value}", content, flags=re.MULTILINE)

    def _upsert_value(self, content: str, section: str, key: str, value: str) -> tuple[str, str | None, bool]:
        """Update key value if present, otherwise insert it into section."""
        current = self._extract_value(content, key)
        if current is not None:
            if current == value:
                return content, current, False
            updated = self._replace_value(content, key, current, value)
            return updated, current, True

        section_pattern = rf"(?ms)^(\[{re.escape(section)}\]\s*\n)(.*?)(?=^\[|\Z)"
        section_match = re.search(section_pattern, content)
        if section_match:
            body = section_match.group(2)
            if body and not body.endswith("\n"):
                body += "\n"
            body += f"{key} = {value}\n"
            updated = content[:section_match.start(2)] + body + content[section_match.end(2):]
            return updated, None, True

        suffix = "" if content.endswith("\n") else "\n"
        updated = f"{content}{suffix}\n[{section}]\n{key} = {value}\n"
        return updated, None, True

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply optimal Dolphin configuration settings.

        Args:
            settings: Dict with target values for each setting.

        Returns:
            Result dict with success status.
        """
        if not self.slippi_base.exists():
            return {
                "success": False,
                "error": "Slippi Launcher not found",
            }

        changes_made = []
        errors = []

        # Apply only keys explicitly provided by the profile.
        gfx_settings: list[tuple[str, str, str]] = []
        for input_key, (ini_key, section) in self.GFX_KEY_MAP.items():
            if input_key in settings and settings[input_key] is not None:
                gfx_settings.append((section, ini_key, str(settings[input_key])))

        if self.gfx_ini.exists():
            try:
                content = self.gfx_ini.read_text(encoding="utf-8")
                modified = False

                for section, key, target_value in gfx_settings:
                    content, previous, changed = self._upsert_value(content, section, key, target_value)
                    if changed:
                        prior = previous if previous is not None else "<missing>"
                        changes_made.append(f"GFX.ini: {key} {prior} -> {target_value}")
                        modified = True

                if modified:
                    self.gfx_ini.write_text(content, encoding="utf-8")

            except OSError as e:
                errors.append(f"GFX.ini: {e}")

        dolphin_settings: list[tuple[str, str, str]] = []
        for input_key, (ini_key, section) in self.DOLPHIN_KEY_MAP.items():
            if input_key in settings and settings[input_key] is not None:
                dolphin_settings.append((section, ini_key, str(settings[input_key])))

        if self.dolphin_ini.exists():
            try:
                content = self.dolphin_ini.read_text(encoding="utf-8")
                modified = False

                for section, key, target_value in dolphin_settings:
                    content, previous, changed = self._upsert_value(content, section, key, target_value)
                    if changed:
                        prior = previous if previous is not None else "<missing>"
                        changes_made.append(f"Dolphin.ini: {key} {prior} -> {target_value}")
                        modified = True

                if modified:
                    self.dolphin_ini.write_text(content, encoding="utf-8")

            except OSError as e:
                errors.append(f"Dolphin.ini: {e}")

        if errors:
            return {
                "success": False,
                "error": "; ".join(errors),
                "changes": changes_made,
            }

        if changes_made:
            logger.info(f"Dolphin config fixes applied: {changes_made}")
        else:
            logger.info("Dolphin configs already optimal")

        return {
            "success": True,
            "changes": changes_made,
        }

    def audit(self) -> list[dict[str, Any]]:
        """Audit Dolphin config for latency issues."""
        issues = []
        detection = self.detect()

        if not detection["slippi_installed"]:
            return issues  # No Slippi, no issues to report

        current = detection.get("current_settings", {})

        # Check EFBScale
        if current.get("EFBScale") not in (None, "1"):
            issues.append({
                "severity": "medium",
                "setting": "EFBScale",
                "current": current.get("EFBScale"),
                "recommended": "1",
                "reason": "Higher internal resolution adds render latency",
            })

        # Check TextureScalingFactor
        if current.get("TextureScalingFactor") not in (None, "1"):
            issues.append({
                "severity": "low",
                "setting": "TextureScalingFactor",
                "current": current.get("TextureScalingFactor"),
                "recommended": "1",
                "reason": "Texture upscaling adds GPU overhead",
            })

        # Check ReduceTimingDispersion
        if current.get("ReduceTimingDispersion") == "False":
            issues.append({
                "severity": "medium",
                "setting": "ReduceTimingDispersion",
                "current": "False",
                "recommended": "True",
                "reason": "Ishiiruka-specific setting for tighter frame timing",
            })

        # Check BackendMultithreading
        if current.get("BackendMultithreading") == "True":
            issues.append({
                "severity": "low",
                "setting": "BackendMultithreading",
                "current": "True",
                "recommended": "False",
                "reason": "Backend multithreading adds driver overhead",
            })

        # Check SyncGPU
        if current.get("SyncGPU") == "True":
            issues.append({
                "severity": "medium",
                "setting": "SyncGPU",
                "current": "True",
                "recommended": "False",
                "reason": "GPU sync adds latency - disable for competitive play",
            })

        # Check ImmediateXFBEnable (should be True for Melee)
        if current.get("ImmediateXFBEnable") == "False":
            issues.append({
                "severity": "medium",
                "setting": "ImmediateXFBEnable",
                "current": "False",
                "recommended": "True",
                "reason": "Immediately Present XFB skips frame buffer queue for lower latency",
            })

        return issues
