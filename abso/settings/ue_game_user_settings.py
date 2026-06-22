"""Shared handler for UE-style GameUserSettings.ini files."""

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


class UEGameUserSettingsHandler(SettingsHandler):
    """Generic handler for Unreal Engine GameUserSettings.ini mutation."""

    CONFIG_FILENAME = "GameUserSettings.ini"
    TARGET_SECTION_NAME: str | None = None
    MUTABLE_SETTINGS_TO_INI: dict[str, str] = {}
    PROTECTED_INI_KEYS: set[str] = set()
    BOOL_SETTINGS: frozenset[str] = frozenset({
        "vsync",
        "hdr_output",
    })
    MIRROR_FULLSCREEN_MODE_KEYS: tuple[str, ...] = ()
    AUTO_VRR_CAP_KEY = "auto_vrr_fps_cap"

    def _get_config_dir(self) -> Path | None:
        raise NotImplementedError

    def _get_config_path(self) -> Path | None:
        config_dir = self._get_config_dir()
        if not config_dir:
            return None
        ini_path = config_dir / self.CONFIG_FILENAME
        if not ini_path.is_file():
            return None
        return ini_path

    def detect(self) -> dict[str, Any]:
        """Detect current config values from GameUserSettings.ini."""
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

            for profile_key, ini_key in self.MUTABLE_SETTINGS_TO_INI.items():
                raw_value = assignments.get(ini_key)
                if raw_value is None:
                    continue
                result[profile_key] = self._coerce_detected(profile_key, raw_value)
        except Exception as e:
            logger.error("Failed to read UE config %s: %s", ini_path, e)

        return result

    def audit(self) -> list[Issue]:
        """Audit common latency-sensitive UE settings."""
        issues: list[Issue] = []
        current = self.detect()

        if not current.get("config_found"):
            return issues

        if current.get("fullscreen_mode") is not None and current["fullscreen_mode"] != 0:
            mode_names = {0: "Exclusive", 1: "Borderless", 2: "Windowed"}
            issues.append(Issue(
                title="Game not in exclusive fullscreen",
                severity="warning",
                current_value=mode_names.get(current["fullscreen_mode"], f"Unknown ({current['fullscreen_mode']})"),
                optimal_value="Exclusive Fullscreen (0)",
                explanation=(
                    "Exclusive fullscreen is the lowest-latency presentation path for the strict ABSO profiles."
                ),
                category="game_config",
            ))

        if current.get("vsync") is True:
            issues.append(Issue(
                title="In-game VSync enabled",
                severity="warning",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation="Keep in-game VSync off so the chosen NVIDIA/Windows sync path stays authoritative.",
                category="game_config",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply validated config settings to GameUserSettings.ini."""
        settings = dict(settings)
        notices: list[str] = []

        if settings.pop(self.AUTO_VRR_CAP_KEY, False):
            notice = self._apply_auto_vrr_cap(settings)
            if notice:
                notices.append(notice)

        invalid_requested_keys = validate_allowed_keys(
            set(settings.keys()),
            set(self.MUTABLE_SETTINGS_TO_INI.keys()),
        )
        if invalid_requested_keys:
            return {
                "success": False,
                "error": (
                    f"Unsupported {self.__class__.__name__} keys requested: "
                    + ", ".join(invalid_requested_keys)
                ),
                "requires_reboot": False,
            }

        ini_path = self._get_config_path()
        if not ini_path:
            result_skipped: dict[str, Any] = {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "skipped": f"{self.CONFIG_FILENAME} not found",
            }
            if notices:
                result_skipped["notices"] = notices
            return result_skipped

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
                result_noop: dict[str, Any] = {
                    "success": True,
                    "error": None,
                    "requires_reboot": False,
                    "applied": [],
                }
                if notices:
                    result_noop["notices"] = notices
                return result_noop

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
                        f"Protected {self.__class__.__name__} keys were modified: "
                        + ", ".join(sorted(protected_mutations))
                    ),
                    "requires_reboot": False,
                }

            if patch_result.changed:
                ini_path.write_text("\n".join(patch_result.lines) + "\n", encoding="utf-8")
                logger.info(
                    "Updated %s: %s (%s changed, %s appended)",
                    self.CONFIG_FILENAME,
                    ini_path,
                    len(patch_result.changed_keys),
                    len(patch_result.appended_keys),
                )

            result_applied: dict[str, Any] = {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "applied": sorted(patch_result.changed_keys | patch_result.appended_keys),
            }
            if notices:
                result_applied["notices"] = notices
            return result_applied
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "requires_reboot": False,
            }

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify requested config values are active."""
        current = self.detect()
        results: dict[str, Any] = {"all_active": True, "settings": {}}

        if not current.get("config_found"):
            return results

        applied_settings = dict(settings)
        if applied_settings.pop(self.AUTO_VRR_CAP_KEY, False):
            self._apply_auto_vrr_cap(applied_settings)

        for key, target in applied_settings.items():
            # Skip framework-injected synthetic keys. The applier threads a
            # "_reboot_pending" flag into every handler's verify settings for
            # reboot-gated handlers (e.g. GraphicsSettingsHandler/MPO). It is
            # not a GameUserSettings.ini key, so verifying it against the INI
            # would always mismatch — and on a handler with
            # is_critical_verify=True that turns into a false critical rollback.
            if key.startswith("_"):
                continue
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
        """Back up the full config file for lossless restore."""
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
            logger.error("Failed to back up %s: %s", ini_path, e)
            return {"config_found": False}

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore the original config file contents."""
        if not data.get("config_found"):
            return True

        file_content = data.get("file_content")
        config_path = data.get("config_path")
        if file_content is None or not config_path:
            return False

        try:
            ini_path = Path(config_path)
            ini_path.parent.mkdir(parents=True, exist_ok=True)
            ini_path.write_text(file_content, encoding="utf-8")
            return True
        except OSError as e:
            logger.error("Failed to restore UE config %s: %s", config_path, e)
            return False

    def _apply_auto_vrr_cap(self, settings: dict[str, Any]) -> str | None:
        """Resolve the in-game VRR FPS cap from the primary refresh rate.

        Returns a notice string when refresh detection fails and the in-game
        ``frame_rate_limit`` was therefore NOT set, so the caller can surface it
        (mirrors :class:`Diablo4ConfigHandler`). Returns ``None`` on success.
        """
        try:
            from abso.core.vrr import get_vrr_fps_cap
            from abso.settings.nvidia import NvidiaSettingsHandler

            refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
            if refresh_hz and refresh_hz > 0:
                settings["frame_rate_limit"] = get_vrr_fps_cap(refresh_hz)
                logger.info(
                    "%s auto VRR FPS cap: %d (from %d Hz)",
                    self.__class__.__name__,
                    settings["frame_rate_limit"],
                    refresh_hz,
                )
                return None
            return (
                f"{self.__class__.__name__} auto_vrr_fps_cap skipped: refresh rate "
                "detection failed. The in-game FrameRateLimit was NOT set. To "
                "recover, enable nvidia.auto_vrr_fps_cap so the driver imposes the "
                "cap, or set frame_rate_limit explicitly in your profile overrides."
            )
        except Exception as e:
            logger.warning("%s auto VRR FPS cap detection failed: %s", self.__class__.__name__, e)
            return (
                f"{self.__class__.__name__} auto_vrr_fps_cap failed: {e}. The in-game "
                "FrameRateLimit was NOT set; verify your NVIDIA driver cap or set "
                "frame_rate_limit explicitly in your profile overrides."
            )

    def _build_replacements(self, settings: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
        replacements: dict[str, str] = {}
        errors: list[str] = []

        for profile_key, value in settings.items():
            ini_key = self.MUTABLE_SETTINGS_TO_INI.get(profile_key)
            if ini_key is None:
                continue

            converted = self._convert_value(profile_key, value)
            if converted is None:
                errors.append(f"{profile_key} has an invalid value")
                continue

            replacements[ini_key] = converted
            if profile_key == "fullscreen_mode":
                for mirror_key in self.MIRROR_FULLSCREEN_MODE_KEYS:
                    replacements[mirror_key] = converted

        return replacements, errors

    def _convert_value(self, profile_key: str, value: Any) -> str | None:
        if profile_key in self.BOOL_SETTINGS:
            parsed = parse_bool_like(value)
            return None if parsed is None else ("True" if parsed else "False")

        try:
            numeric = int(float(value))
        except (TypeError, ValueError):
            return None

        if profile_key == "hdr_nits" and numeric <= 0:
            return None
        if profile_key == "frame_rate_limit" and numeric < 0:
            return None

        return str(numeric)

    def _coerce_detected(self, profile_key: str, raw_value: str) -> Any:
        if profile_key in self.BOOL_SETTINGS:
            parsed = parse_bool_like(raw_value)
            return bool(parsed) if parsed is not None else raw_value

        try:
            return int(float(raw_value))
        except (TypeError, ValueError):
            return raw_value
