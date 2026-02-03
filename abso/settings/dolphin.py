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

        return result

    def _extract_value(self, content: str, key: str) -> str | None:
        """Extract a value from INI content."""
        match = re.search(rf"^{key}\s*=\s*(.+)$", content, re.MULTILINE)
        return match.group(1).strip() if match else None

    def _replace_value(self, content: str, key: str, old_value: str, new_value: str) -> str:
        """Replace a value in INI content."""
        pattern = rf"^({key}\s*=\s*){re.escape(old_value)}$"
        return re.sub(pattern, rf"\g<1>{new_value}", content, flags=re.MULTILINE)

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

        # GFX.ini settings
        gfx_settings = {
            "EFBScale": settings.get("efb_scale", "1"),
            "TextureScalingFactor": settings.get("texture_scaling_factor", "1"),
            "UseScalingFilter": settings.get("use_scaling_filter", "False"),
            "UseDePosterize": settings.get("use_deposterize", "False"),
            "BackendMultithreading": settings.get("backend_multithreading", "False"),
        }

        if self.gfx_ini.exists():
            try:
                content = self.gfx_ini.read_text(encoding="utf-8")
                modified = False

                for key, target_value in gfx_settings.items():
                    current = self._extract_value(content, key)
                    if current is not None and current != target_value:
                        content = self._replace_value(content, key, current, target_value)
                        changes_made.append(f"GFX.ini: {key} {current} -> {target_value}")
                        modified = True

                if modified:
                    self.gfx_ini.write_text(content, encoding="utf-8")

            except OSError as e:
                errors.append(f"GFX.ini: {e}")

        # Dolphin.ini settings
        dolphin_settings = {
            "ReduceTimingDispersion": settings.get("reduce_timing_dispersion", "True"),
            "ImmediateXFBEnable": settings.get("immediate_xfb_enable", "True"),
            "RushPresentation": settings.get("rush_presentation", "False"),
            "SmoothPresentation": settings.get("smooth_presentation", "False"),
            "SyncGPU": settings.get("sync_gpu", "False"),
        }

        if self.dolphin_ini.exists():
            try:
                content = self.dolphin_ini.read_text(encoding="utf-8")
                modified = False

                for key, target_value in dolphin_settings.items():
                    current = self._extract_value(content, key)
                    if current is not None and current != target_value:
                        content = self._replace_value(content, key, current, target_value)
                        changes_made.append(f"Dolphin.ini: {key} {current} -> {target_value}")
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
