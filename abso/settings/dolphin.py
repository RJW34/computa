"""Dolphin emulator configuration handler for Slippi.

Manages latency-critical Dolphin settings including:
- Immediately Present XFB (ImmediateXFBEnable) - skips frame buffer queue
- Rush Frame Presentation (RushPresentation) - mainline-only, see BUILD LINEAGE
- Smooth Frame Presentation (SmoothPresentation) - VRR pacing aid, costs latency
- Backend Multithreading (BackendMultithreading) - driver threading overhead
- GPU Sync (SyncGPU) - adds latency when enabled

BUILD LINEAGE
-------------
Slippi Launcher's ``netplay`` Dolphin is historically **Ishiiruka**-based, while
Rush Frame Presentation shipped in **mainline** Dolphin 2512 (December 2025).
An Ishiiruka build silently ignores ``RushPresentation``; ``_upsert_value`` will
still write the key, so its presence in Dolphin.ini proves nothing about whether
the running build honours it. ``detect()`` reports a best-effort lineage guess
from Ishiiruka-exclusive GFX.ini keys so callers can gate guidance instead of
assuming the mainline feature set.

Sources:
- Dolphin Progress Report December 2025 (Rush/Smooth Frame Presentation)
- Dolphin Performance Guide
- melee.tv competitive optimization
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Literal, NamedTuple

from abso.core.config_safety import (
    read_config_text,
    restore_managed_key_lines,
    write_config_text,
)
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# GFX.ini keys that only ever exist in Ishiiruka-derived builds. Mainline
# Dolphin has none of them, so any hit is a reliable lineage signal.
ISHIIRUKA_GFX_MARKERS: tuple[str, ...] = (
    "SimBumpEnabled",
    "ForcePhongShading",
    "PredictiveFifo",
    "TextureScalingType",
    "EnableOpenCL",
    "TessellationEarlyCulling",
)


class AuditRule(NamedTuple):
    """Expected value for a managed Dolphin key, plus why it matters."""

    expected: str
    severity: str
    reason: str


class DolphinConfigHandler(SettingsHandler):
    """Handler for Dolphin/Slippi configuration files.

    Slippi Launcher tends to overwrite certain Dolphin settings on launch.
    This handler applies ABSO profile targets to the config
    files before the game is launched.
    """

    def __init__(self) -> None:
        self.slippi_base = Path(os.environ["APPDATA"]) / "Slippi Launcher" / "netplay"
        self.config_dir = self.slippi_base / "User" / "Config"
        self.gfx_ini = self.config_dir / "GFX.ini"
        self.dolphin_ini = self.config_dir / "Dolphin.ini"

    GFX_KEY_MAP: dict[str, tuple[str, str]] = {
        "efb_scale": ("EFBScale", "Settings"),
        "texture_scaling_type": ("TextureScalingType", "Enhancements"),
        "texture_scaling_factor": ("TextureScalingFactor", "Enhancements"),
        "use_scaling_filter": ("UseScalingFilter", "Enhancements"),
        "use_deposterize": ("UseDePosterize", "Enhancements"),
        "backend_multithreading": ("BackendMultithreading", "Settings"),
        "vsync": ("VSync", "Hardware"),
        "efb_access_enable": ("EFBAccessEnable", "Hacks"),
        "enable_gpu_texture_decoding": ("EnableGPUTextureDecoding", "Hacks"),
        "borderless_fullscreen": ("BorderlessFullscreen", "Settings"),
    }

    DOLPHIN_KEY_MAP: dict[str, tuple[str, str]] = {
        "reduce_timing_dispersion": ("ReduceTimingDispersion", "Core"),
        "immediate_xfb_enable": ("ImmediateXFBEnable", "Core"),
        "rush_presentation": ("RushPresentation", "Core"),
        "smooth_presentation": ("SmoothPresentation", "Core"),
        "sync_gpu": ("SyncGPU", "Core"),
        "timing_variance": ("TimingVariance", "Core"),
        "time_stretching": ("TimeStretching", "Core"),
    }

    # Expected values for keys whose correct setting is identical across every
    # Slippi profile in the catalog. Keys that legitimately differ per profile
    # must be declared in UNAUDITED_KEYS instead - never left out silently.
    AUDIT_RULES: dict[str, AuditRule] = {
        "efb_scale": AuditRule(
            "1", "medium", "Higher internal resolution adds render latency"
        ),
        "texture_scaling_type": AuditRule(
            "0",
            "low",
            "TextureScalingType is the switch that actually enables xBRZ-style "
            "texture upscaling; 0 disables it. TextureScalingFactor is inert "
            "while this is 0",
        ),
        "texture_scaling_factor": AuditRule(
            "2",
            "low",
            "Texture upscaling adds GPU overhead. NOTE: Ishiiruka's factor range "
            "is 2-5, so a target of 1 is out of range - Dolphin silently clamps "
            "it back to 2 on every run, which made this audit report a permanent "
            "false mismatch and made the handler look like it was not sticking. "
            "2 is the valid floor; TextureScalingType = 0 does the real work",
        ),
        "use_scaling_filter": AuditRule("False", "low", "Scaling adds GPU overhead"),
        "use_deposterize": AuditRule(
            "False", "low", "Post-processing adds GPU overhead"
        ),
        "backend_multithreading": AuditRule(
            "False", "low", "Backend multithreading adds driver overhead"
        ),
        "efb_access_enable": AuditRule(
            "False", "low", "EFB access is slow and unnecessary for Melee"
        ),
        "enable_gpu_texture_decoding": AuditRule(
            "True", "low", "Offloads texture decoding to the GPU"
        ),
        "borderless_fullscreen": AuditRule(
            "False",
            "medium",
            "Borderless routes Dolphin through the desktop compositor; "
            "exclusive fullscreen is the lower-latency scanout path",
        ),
        "reduce_timing_dispersion": AuditRule(
            "True", "medium", "Ishiiruka-specific setting for tighter frame timing"
        ),
        "immediate_xfb_enable": AuditRule(
            "True",
            "medium",
            "Immediately Present XFB skips the frame buffer queue for lower latency",
        ),
        "smooth_presentation": AuditRule(
            "False",
            "medium",
            "Smooth Frame Presentation deliberately delays presentation ~1-2ms to "
            "regularise pacing. It is a VRR range-holding aid, not a latency feature, "
            "and every Slippi profile targets it off",
        ),
        "sync_gpu": AuditRule(
            "False", "medium", "GPU sync adds latency - disable for competitive play"
        ),
        "timing_variance": AuditRule(
            "8", "low", "Ishiiruka-specific frame timing variance target"
        ),
        "time_stretching": AuditRule(
            "False", "low", "Audio time stretching adds processing overhead"
        ),
    }

    # Managed keys deliberately excluded from audit, with the reason. Enforced
    # by tests/test_handlers/test_dolphin.py so a new key map entry cannot be
    # added without an explicit audit decision.
    UNAUDITED_KEYS: dict[str, str] = {
        "vsync": (
            "Profile-dependent: the competitive no-sync lane targets False while "
            "slippi-melee-console-parity targets True."
        ),
        "rush_presentation": (
            "Mainline-only (Dolphin 2512) and an explicit A/B setting. Ishiiruka "
            "netplay builds ignore the key, so a mismatch is not actionable."
        ),
    }

    def detect(self) -> dict[str, Any]:
        """Detect current Dolphin configuration state.

        Every key in ``GFX_KEY_MAP`` / ``DOLPHIN_KEY_MAP`` is read, so adding a
        managed key automatically surfaces it here rather than requiring a
        parallel hand-written list to be kept in sync.
        """
        current: dict[str, str | None] = {}
        result: dict[str, Any] = {
            "slippi_installed": self.slippi_base.exists(),
            "gfx_ini_exists": self.gfx_ini.exists(),
            "dolphin_ini_exists": self.dolphin_ini.exists(),
            "build_lineage": "unknown",
            "current_settings": current,
        }

        gfx_content: str | None = None
        if self.gfx_ini.exists():
            try:
                gfx_content = self.gfx_ini.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning(f"Failed to read GFX.ini: {e}")

        if gfx_content is not None:
            for ini_key, _section in self.GFX_KEY_MAP.values():
                current[ini_key] = self._extract_value(gfx_content, ini_key)
            result["build_lineage"] = self._detect_build_lineage(gfx_content)

        if self.dolphin_ini.exists():
            try:
                dolphin_content = self.dolphin_ini.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning(f"Failed to read Dolphin.ini: {e}")
            else:
                for ini_key, _section in self.DOLPHIN_KEY_MAP.values():
                    current[ini_key] = self._extract_value(dolphin_content, ini_key)

        return result

    def _detect_build_lineage(
        self, gfx_content: str
    ) -> Literal["ishiiruka", "mainline", "unknown"]:
        """Guess whether the netplay build is Ishiiruka- or mainline-derived.

        Ishiiruka-exclusive GFX.ini keys are a positive signal. Their absence is
        weaker evidence, so a config without them reports ``mainline`` only when
        it is otherwise populated; an empty/near-empty file stays ``unknown``.
        """
        if any(
            re.search(rf"^{marker}\s*=", gfx_content, re.MULTILINE)
            for marker in ISHIIRUKA_GFX_MARKERS
        ):
            return "ishiiruka"
        if re.search(r"^EFBScale\s*=", gfx_content, re.MULTILINE):
            return "mainline"
        return "unknown"

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
        """Apply Dolphin configuration targets.

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
            logger.info("Dolphin configs already match ABSO targets")

        return {
            "success": True,
            "changes": changes_made,
        }

    def audit(self) -> list[dict[str, Any]]:
        """Audit Dolphin config for latency issues.

        Driven off ``AUDIT_RULES`` so every managed key is either checked or
        explicitly waived in ``UNAUDITED_KEYS``. The previous hand-written form
        silently skipped SmoothPresentation, letting a Slippi Launcher rewrite
        re-enable a ~1-2ms presentation delay without the audit noticing.
        """
        issues: list[dict[str, Any]] = []
        detection = self.detect()

        if not detection["slippi_installed"]:
            return issues  # No Slippi, no issues to report

        current = detection.get("current_settings", {})
        key_map = {**self.GFX_KEY_MAP, **self.DOLPHIN_KEY_MAP}

        for input_key, rule in self.AUDIT_RULES.items():
            ini_key = key_map[input_key][0]
            value = current.get(ini_key)
            # None means the key is absent: apply() will insert it, and an
            # absent key is not evidence of a wrong setting.
            if value is None or value == rule.expected:
                continue
            issues.append({
                "severity": rule.severity,
                "setting": ini_key,
                "current": value,
                "recommended": rule.expected,
                "reason": rule.reason,
            })

        return issues

    def backup(self) -> dict[str, Any]:
        """Backup current Dolphin configuration files."""
        data: dict[str, Any] = {
            "slippi_installed": self.slippi_base.exists(),
            "gfx_ini": None,
            "dolphin_ini": None,
        }

        try:
            if self.gfx_ini.exists():
                data["gfx_ini"] = read_config_text(self.gfx_ini)
        except OSError as e:
            logger.warning(f"Failed to backup GFX.ini: {e}")

        try:
            if self.dolphin_ini.exists():
                data["dolphin_ini"] = read_config_text(self.dolphin_ini)
        except OSError as e:
            logger.warning(f"Failed to backup Dolphin.ini: {e}")

        return data

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore only the Dolphin keys managed by ABSO.

        Slippi keeps the renderer, ISO paths, controller choices, audio, and
        many other user-owned values in these same files.  Those live values
        must survive baseline restore and unrelated profile switches.
        """
        if not data.get("slippi_installed"):
            return True  # Nothing to restore if Slippi wasn't installed

        try:
            self._restore_managed_file(
                path=self.gfx_ini,
                backup_content=data.get("gfx_ini"),
                key_map=self.GFX_KEY_MAP,
            )
            self._restore_managed_file(
                path=self.dolphin_ini,
                backup_content=data.get("dolphin_ini"),
                key_map=self.DOLPHIN_KEY_MAP,
            )

            return True
        except OSError as e:
            logger.error(f"Failed to restore Dolphin config: {e}")
            return False

    def _restore_managed_file(
        self,
        *,
        path: Path,
        backup_content: str | None,
        key_map: dict[str, tuple[str, str]],
    ) -> None:
        """Merge backed-up managed keys into one existing Dolphin INI."""
        if backup_content is None or not path.is_file():
            return

        current_content = read_config_text(path)
        restored_content = current_content
        keys_by_section: dict[str, set[str]] = {}
        for ini_key, section in key_map.values():
            keys_by_section.setdefault(section, set()).add(ini_key)

        for section, managed_keys in keys_by_section.items():
            restored_content = restore_managed_key_lines(
                current_content=restored_content,
                backup_content=backup_content,
                managed_keys=managed_keys,
                section_name=section,
            )

        if restored_content != current_content:
            write_config_text(path, restored_content)
