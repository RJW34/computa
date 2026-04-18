"""Overwatch 2 game config handler.

Manages OW2's Settings_v0.ini to pre-configure latency-critical render
settings before launch.  OW2 uses a quoted INI format inside versioned
``[Render.X]`` sections::

    [Render.13]
    WindowMode = "1"
    LimitToRefresh = "0"

This handler uses custom extract/upsert helpers (following the Dolphin
handler pattern) instead of ``config_safety.apply_ini_key_patch`` because
the latter does not preserve OW2's quoted-value format.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from abso.core.config_safety import validate_allowed_keys
from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def _get_ow2_settings_path() -> Path | None:
    """Return the path to OW2's Settings_v0.ini, or *None* if not found."""
    import os

    userprofile = os.environ.get("USERPROFILE")
    if not userprofile:
        return None

    ini_path = Path(userprofile) / "Documents" / "Overwatch" / "Settings" / "Settings_v0.ini"
    if ini_path.is_file():
        return ini_path

    return None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class OW2ConfigHandler(SettingsHandler):
    """Enforces OW2 render settings for optimal latency.

    Patches values inside the ``[Render.X]`` section of
    ``%USERPROFILE%\\Documents\\Overwatch\\Settings\\Settings_v0.ini``.
    """

    # Matches versioned render section headers like [Render.13]
    RENDER_SECTION_RE = re.compile(r"^\[Render\.\d+\]$")

    # Matches any Key = "value" pair inside a section
    _KV_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\s*=\s*"([^"]*)"\s*$')

    # Profile snake_case key -> INI key inside [Render.X]
    MUTABLE_SETTINGS: dict[str, str] = {
        "window_mode": "WindowMode",
        "vsync": "LimitToRefresh",
        "reduce_buffering": "CpuForceSyncEnabled",
        "dynamic_render_scale": "UseGPUScale",
        "dynamic_render_scale_v2": "DynamicRenderScale",
        "frame_rate_cap": "FrameRateCap",
        "use_custom_frame_rates": "UseCustomFrameRates",
        "render_scale": "RenderScale",
        "gfx_preset": "GFXPresetLevel",
        "effects_quality": "EffectsQuality",
        "texture_detail": "TextureDetail",
        "model_quality": "ModelQuality",
        "aa_detail": "AADetail",
        "upscaling": "HighQualityUpsample",
        "triple_buffering": "TripleBufferingEnabled",
        "show_fps": "ShowFPSCounter",
        "show_latency": "ShowIND",
        "hdr": "HDR",
    }

    # Settings that accept bool-like input and are stored as "0"/"1" in the INI.
    # Kept as a class constant so new boolean keys only need one addition.
    BOOL_SETTINGS: frozenset[str] = frozenset({
        "vsync", "reduce_buffering", "dynamic_render_scale", "dynamic_render_scale_v2",
        "use_custom_frame_rates",
        "upscaling", "triple_buffering", "show_fps", "show_latency",
        "hdr",
    })

    # Keys that must never be mutated by automation.
    PROTECTED_INI_KEYS: set[str] = {
        "MouseSensitivity",
        "MouseSensitivityY",
        "MouseSensitivityHero",
        "KeyBinds",
        "KeyBindsV2",
        "CrosshairSettings",
        "CrosshairSettingsV2",
    }

    # ------------------------------------------------------------------
    # SettingsHandler interface
    # ------------------------------------------------------------------

    def detect(self) -> dict[str, Any]:
        """Detect current OW2 render settings."""
        ini_path = _get_ow2_settings_path()
        if not ini_path:
            return {"config_found": False}

        result: dict[str, Any] = {"config_found": True, "config_path": str(ini_path)}

        try:
            content = ini_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            render_values = self._parse_render_section(lines)

            # Map INI keys back to snake_case profile keys
            ini_to_profile = {v: k for k, v in self.MUTABLE_SETTINGS.items()}
            for ini_key, raw_value in render_values.items():
                profile_key = ini_to_profile.get(ini_key)
                if profile_key is not None:
                    result[profile_key] = self._coerce_detected(raw_value)
        except Exception as e:
            logger.error("Failed to read OW2 config: %s", e)

        return result

    def audit(self) -> list[Issue]:
        """Check for sub-optimal latency settings in OW2 config."""
        issues: list[Issue] = []
        current = self.detect()

        if not current.get("config_found"):
            return issues

        if current.get("vsync") == 1:
            issues.append(Issue(
                title="OW2 VSync enabled in-game",
                severity="warning",
                current_value="On",
                optimal_value="Off (use NVCP instead)",
                explanation="In-game VSync adds input latency; sync should be managed by the driver.",
                category="game_config",
            ))

        if current.get("reduce_buffering") == 0:
            issues.append(Issue(
                title="OW2 Reduce Buffering disabled",
                severity="warning",
                current_value="Off",
                optimal_value="On",
                explanation="Reduce Buffering lowers the render queue depth for lower latency.",
                category="game_config",
            ))

        if current.get("triple_buffering") == 1:
            issues.append(Issue(
                title="OW2 Triple Buffering enabled",
                severity="warning",
                current_value="On",
                optimal_value="Off",
                explanation="Triple buffering adds a frame of latency.",
                category="game_config",
            ))

        if current.get("dynamic_render_scale") == 1:
            issues.append(Issue(
                title="OW2 Dynamic Render Scale enabled",
                severity="info",
                current_value="On",
                optimal_value="Off",
                explanation="Dynamic scaling causes frametime variance.",
                category="game_config",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply OW2 render settings to Settings_v0.ini."""
        settings = dict(settings)  # Don't mutate caller's dict

        # Auto VRR FPS cap: detect refresh rate and set in-game cap to refresh - 3
        if settings.pop("auto_vrr_fps_cap", False):
            try:
                from abso.core.vrr import get_vrr_fps_cap
                from abso.settings.nvidia import NvidiaSettingsHandler

                refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
                if refresh_hz and refresh_hz > 0:
                    settings["frame_rate_cap"] = get_vrr_fps_cap(refresh_hz)
                    logger.info(
                        "OW2 auto VRR FPS cap: %d (from %d Hz)",
                        settings["frame_rate_cap"], refresh_hz,
                    )
            except Exception as e:
                logger.warning("OW2 auto VRR FPS cap detection failed: %s", e)

        # OW2 ignores FrameRateCap unless UseCustomFrameRates is "1".
        # Automatically enable it whenever we set a custom cap.
        if "frame_rate_cap" in settings and "use_custom_frame_rates" not in settings:
            settings["use_custom_frame_rates"] = True

        invalid = validate_allowed_keys(
            set(settings.keys()),
            set(self.MUTABLE_SETTINGS.keys()),
        )
        if invalid:
            return {
                "success": False,
                "error": (
                    "Unsupported OW2 config keys requested: "
                    + ", ".join(invalid)
                ),
                "requires_reboot": False,
            }

        ini_path = _get_ow2_settings_path()
        if not ini_path:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "skipped": "OW2 settings file not found (game may not be installed)",
            }

        try:
            content = ini_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            # Snapshot protected keys before mutation
            original_protected = self._snapshot_protected(lines)

            replacements = self._build_replacements(settings)
            lines, changed_keys, appended_keys = self._apply_to_render_section(
                lines, replacements,
            )

            # Verify protected keys are untouched
            new_protected = self._snapshot_protected(lines)
            mutations = [
                k for k in self.PROTECTED_INI_KEYS
                if original_protected.get(k) != new_protected.get(k)
            ]
            if mutations:
                return {
                    "success": False,
                    "error": (
                        "Protected OW2 keys were modified: "
                        + ", ".join(sorted(mutations))
                    ),
                    "requires_reboot": False,
                }

            if changed_keys or appended_keys:
                ini_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                logger.info(
                    "Updated OW2 config: %s (%d changed, %d appended)",
                    ini_path,
                    len(changed_keys),
                    len(appended_keys),
                )

            notices: list[str] = []
            drift = self._detect_post_apply_drift(ini_path, replacements)
            if drift:
                notices.extend(drift)
                logger.warning("OW2 config drift after write: %s", "; ".join(drift))

            result: dict[str, Any] = {
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
        """Verify requested OW2 config values are active."""
        current = self.detect()
        results: dict[str, Any] = {"all_active": True, "settings": {}}

        if not current.get("config_found"):
            return results

        replacements = self._build_replacements(settings)
        ini_to_profile = {v: k for k, v in self.MUTABLE_SETTINGS.items()}

        for ini_key, target_str in replacements.items():
            profile_key = ini_to_profile.get(ini_key)
            if profile_key is None:
                continue

            current_value = current.get(profile_key)
            target_value = self._coerce_detected(target_str)
            is_active = current_value == target_value
            results["settings"][profile_key] = {
                "target": target_value,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        return results

    def backup(self) -> dict[str, Any]:
        """Backup the entire Settings_v0.ini for lossless restore."""
        ini_path = _get_ow2_settings_path()
        if not ini_path:
            return {"config_found": False}

        try:
            content = ini_path.read_text(encoding="utf-8", errors="replace")
            return {
                "config_found": True,
                "config_path": str(ini_path),
                "file_content": content,
            }
        except Exception as e:
            logger.error("Failed to backup OW2 config: %s", e)
            return {"config_found": False}

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Settings_v0.ini from backup."""
        if not data.get("config_found"):
            return True  # Nothing to restore

        file_content = data.get("file_content")
        if file_content is None:
            return True

        ini_path = _get_ow2_settings_path()
        if not ini_path:
            # Try to use the original path from backup
            config_path = data.get("config_path")
            if config_path:
                ini_path = Path(config_path)
            else:
                logger.warning("Cannot restore OW2 config: no path available")
                return False

        try:
            ini_path.parent.mkdir(parents=True, exist_ok=True)
            ini_path.write_text(file_content, encoding="utf-8")
            return True
        except OSError as e:
            logger.error("Failed to restore OW2 config: %s", e)
            return False

    # ------------------------------------------------------------------
    # INI parsing helpers (OW2 quoted format)
    # ------------------------------------------------------------------

    def _extract_value(self, line: str, key: str) -> str | None:
        """Extract the unquoted value for *key* from a single INI line.

        Handles OW2's ``Key = "value"`` format.
        """
        match = re.match(
            rf"^\s*{re.escape(key)}\s*=\s*\"([^\"]*)\"\s*$", line,
        )
        return match.group(1) if match else None

    def _upsert_value(
        self,
        lines: list[str],
        render_start: int,
        render_end: int,
        key: str,
        value: str,
    ) -> tuple[list[str], bool, bool]:
        """Replace *key* in place or append it at section end.

        Returns ``(lines, was_changed, was_appended)``.
        """
        for i in range(render_start + 1, render_end):
            existing = self._extract_value(lines[i], key)
            if existing is not None:
                if existing == value:
                    return lines, False, False
                lines[i] = f'{key} = "{value}"'
                return lines, True, False

        # Key not found — append before section end
        lines.insert(render_end, f'{key} = "{value}"')
        return lines, False, True

    def _find_render_section(self, lines: list[str]) -> tuple[int, int] | None:
        """Return (start, end) line indices for the first ``[Render.X]`` section."""
        start: int | None = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if self.RENDER_SECTION_RE.match(stripped):
                start = i
            elif start is not None and stripped.startswith("["):
                return start, i
        if start is not None:
            return start, len(lines)
        return None

    def _parse_render_section(self, lines: list[str]) -> dict[str, str]:
        """Parse all ``Key = "value"`` pairs from the ``[Render.X]`` section."""
        bounds = self._find_render_section(lines)
        if not bounds:
            return {}

        start, end = bounds
        result: dict[str, str] = {}
        for i in range(start + 1, end):
            m = self._KV_RE.match(lines[i])
            if m:
                result[m.group(1)] = m.group(2)
        return result

    def _apply_to_render_section(
        self,
        lines: list[str],
        replacements: dict[str, str],
    ) -> tuple[list[str], set[str], set[str]]:
        """Apply all *replacements* to the ``[Render.X]`` section.

        Returns ``(lines, changed_keys, appended_keys)``.
        """
        bounds = self._find_render_section(lines)
        if not bounds:
            return lines, set(), set()

        changed: set[str] = set()
        appended: set[str] = set()

        for ini_key, value in replacements.items():
            # Re-find bounds each iteration since appends shift indices
            bounds = self._find_render_section(lines)
            if not bounds:
                break
            start, end = bounds
            lines, was_changed, was_appended = self._upsert_value(
                lines, start, end, ini_key, value,
            )
            if was_changed:
                changed.add(ini_key)
            if was_appended:
                appended.add(ini_key)

        return lines, changed, appended

    def _detect_post_apply_drift(
        self,
        ini_path: Path,
        replacements: dict[str, str],
    ) -> list[str]:
        """Re-read the INI and list any keys that didn't land as requested.

        OW2 can overwrite Settings_v0.ini on exit (and on some multi-monitor
        configurations it reverts ``WindowMode`` back to borderless on launch).
        Surface a clear notice so the caller can tell the user instead of
        silently accepting drift the next time they wonder why their cap is
        cap-bound but they're still GPU-bound.
        """
        try:
            content = ini_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        actual = self._parse_render_section(content.splitlines())
        if not actual:
            return []

        ini_to_profile = {v: k for k, v in self.MUTABLE_SETTINGS.items()}
        drift: list[str] = []
        for ini_key, target_value in replacements.items():
            current_value = actual.get(ini_key)
            if current_value is None or current_value == target_value:
                continue
            profile_key = ini_to_profile.get(ini_key, ini_key)
            drift.append(
                f"OW2 {profile_key} drifted to {current_value!r} "
                f"(expected {target_value!r}) - close OW2 and re-apply, "
                f"or verify in-game Display Mode matches this profile."
            )
        return drift

    def _snapshot_protected(self, lines: list[str]) -> dict[str, str | None]:
        """Capture current values of protected keys across all sections."""
        snapshot: dict[str, str | None] = {}
        for key in self.PROTECTED_INI_KEYS:
            for line in lines:
                val = self._extract_value(line, key)
                if val is not None:
                    snapshot[key] = val
                    break
            else:
                snapshot[key] = None
        return snapshot

    def _build_replacements(self, settings: dict[str, Any]) -> dict[str, str]:
        """Convert profile settings dict to ``{INI_key: quoted_value_str}``."""
        replacements: dict[str, str] = {}

        for profile_key, value in settings.items():
            ini_key = self.MUTABLE_SETTINGS.get(profile_key)
            if ini_key is None:
                continue
            replacements[ini_key] = self._to_ini_value(profile_key, value)

        return replacements

    def _to_ini_value(self, profile_key: str, value: Any) -> str:
        """Convert a single profile value to its INI string representation."""
        if profile_key in self.BOOL_SETTINGS:
            if isinstance(value, bool):
                return "1" if value else "0"
            return str(int(bool(value)))

        # Everything else (window_mode, frame_rate_cap, gfx_preset, etc.)
        return str(int(value))

    @staticmethod
    def _coerce_detected(raw: str) -> int | str:
        """Coerce a raw INI string to int if possible, else return as-is."""
        try:
            return int(raw)
        except (ValueError, TypeError):
            return raw
