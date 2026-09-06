"""Shared handler for UE-style GameUserSettings.ini files."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from abso.core.config_safety import (
    INI_ASSIGNMENT_RE,
    INI_SECTION_RE,
    apply_ini_key_patch,
    find_ini_section_bounds,
    parse_ini_assignments,
    validate_allowed_keys,
)
from abso.core.models import Issue
from abso.settings.base import SettingsHandler
from abso.settings.value_parsing import parse_bool_like
from abso.utils.atomic_io import atomic_write_text

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
        """Compare presentation settings with the active profile's contract.

        Borderless and in-game VSync are intentional in some capture lanes;
        neither is a universal latency defect when no profile is selected.
        """
        issues: list[Issue] = []
        current = self.detect()

        if not current.get("config_found"):
            return issues

        targets = self._get_audit_targets()
        for key, label in (("fullscreen_mode", "Display mode"), ("vsync", "In-game VSync")):
            if key not in targets or current.get(key) == targets[key]:
                continue
            issues.append(Issue(
                title=f"{self.__class__.__name__}: {label} differs from active profile",
                severity="warning",
                current_value=str(current.get(key, "Unreadable")),
                optimal_value=str(targets[key]),
                explanation=(
                    "Use the active profile's presentation and synchronization settings. "
                    "Streaming profiles can intentionally require borderless mode and in-game VSync."
                ),
                category="game_config",
            ))

        return issues

    def _get_audit_targets(self) -> dict[str, Any]:
        """Read profile intent without applying settings or changing state."""
        from abso.core.app_paths import app_state_file
        from abso.core.config import ConfigManager, merge_profile_override_settings
        from abso.core.state_reconcile import state_file_write_targets
        from abso.core.state_store import read_state_snapshot
        from abso.profiles.catalog import get_profile_instances

        # Match source/installed CLI state reconciliation, including a newer
        # source state whose LocalAppData mirror could not be written.
        package_root = Path(__file__).resolve().parents[2]
        primary = app_state_file() if getattr(sys, "frozen", False) else package_root / ".abso_state.json"
        targets = state_file_write_targets(primary, package_root=package_root)
        profile_id = read_state_snapshot(targets).get("current_profile")
        if not profile_id:
            return {}
        profile = get_profile_instances().get(profile_id)
        handler_name = self.__class__.__name__
        config = ConfigManager()
        if not profile or config.is_handler_disabled(handler_name):
            return {}
        settings = profile.get_settings(handler_name)
        overrides = config.get_profile_overrides(profile_id)
        return merge_profile_override_settings(settings, handler_name, overrides) if overrides else settings

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
                atomic_write_text(ini_path, "\n".join(patch_result.lines) + "\n")
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

        applied_settings = dict(settings)
        if applied_settings.pop(self.AUTO_VRR_CAP_KEY, False):
            notice = self._apply_auto_vrr_cap(applied_settings)
            if notice:
                # An unresolved target cannot be silently omitted: even a
                # matching explicit fallback does not prove the auto-cap policy.
                results["all_active"] = False
                results["error"] = notice
                results["settings"][self.AUTO_VRR_CAP_KEY] = {
                    "target": True,
                    "current": None,
                    "active": False,
                    "status": "unverifiable",
                    "note": (
                        "Primary display refresh could not be detected; "
                        "the requested automatic FPS cap cannot be verified."
                    ),
                }

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
            is_active = bool(current.get("config_found")) and key in current and current_value == target
            results["settings"][key] = {
                "target": target,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False
                if not current.get("config_found") or key not in current:
                    results["settings"][key].update({
                        "status": "unverifiable",
                        "note": (
                            f"{self.CONFIG_FILENAME} not found; launch the game to create its settings."
                            if not current.get("config_found")
                            else "The requested setting could not be read from the game config."
                        ),
                    })

        return results

    def backup(self) -> dict[str, Any]:
        """Capture the full file for managed-key rollback and missing-file recovery."""
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
        """Restore owned settings while retaining subsequent in-game edits.

        Backups retain the full file for recovery, but an existing file may
        contain newer graphics, controls, or renderer choices. Only mapped
        keys and their fullscreen mirrors belong to this handler's rollback.
        """
        if not data.get("config_found"):
            return True

        file_content = data.get("file_content")
        config_path = data.get("config_path")
        if not isinstance(file_content, str) or not config_path:
            return False

        try:
            ini_path = Path(config_path)
            if not ini_path.exists():
                # No current file exists whose newer values could be lost.
                atomic_write_text(ini_path, file_content)
                return True

            current = ini_path.read_text(encoding="utf-8")
            original_lines = file_content.splitlines(keepends=True)
            current_lines = current.splitlines(keepends=True)
            owned = (
                set(self.MUTABLE_SETTINGS_TO_INI.values())
                | set(self.MIRROR_FULLSCREEN_MODE_KEYS)
            ) - self.PROTECTED_INI_KEYS

            def bounds(lines: list[str]) -> tuple[int, int] | None:
                # The generic patch helper falls back to the entire file when
                # a section is absent. Rollback must never use that fallback
                # on a sectioned file: identical keys elsewhere are unowned.
                normalized = [line.lstrip("\ufeff") for line in lines]
                found = find_ini_section_bounds(normalized, self.TARGET_SECTION_NAME)
                if found is not None:
                    return found
                if self.TARGET_SECTION_NAME and any(INI_SECTION_RE.match(line) for line in normalized):
                    return None
                return 0, len(lines)

            def owned_key(line: str) -> str | None:
                match = INI_ASSIGNMENT_RE.match(line.lstrip("\ufeff"))
                return match.group(1) if match and match.group(1) in owned else None

            def without_owned(lines: list[str], scope: tuple[int, int] | None) -> list[str]:
                start, end = scope if scope is not None else (0, 0)
                return [
                    line for index, line in enumerate(lines)
                    if not (start <= index < end and owned_key(line))
                ]

            original_scope = bounds(original_lines)
            current_scope = bounds(current_lines)
            if without_owned(original_lines, original_scope) == without_owned(current_lines, current_scope):
                # No unowned text changed, so preserve the exact backup layout
                # as well as its values (including keys absent at backup).
                restored_content = file_content
            else:
                start, end = original_scope if original_scope is not None else (0, 0)
                saved = [
                    (owned_key(line), line) for line in original_lines[start:end]
                    if owned_key(line)
                ]
                if current_scope is None:
                    if not saved:
                        return True
                    # Recreate only the managed section/keys, never its stale
                    # unowned graphics or controls from the backup.
                    prefix = current if not current or current.endswith("\n") else current + "\n"
                    restored_content = prefix + f"[{self.TARGET_SECTION_NAME}]\n"
                    restored_content += "".join(line.rstrip("\r\n") + "\n" for _, line in saved)
                else:
                    start, end = current_scope
                    body: list[str] = []
                    remaining = list(saved)
                    for line in current_lines[start:end]:
                        key = owned_key(line)
                        if key is None:
                            body.append(line)
                            continue
                        match_index = next(
                            (index for index, (saved_key, _) in enumerate(remaining) if saved_key == key),
                            None,
                        )
                        if match_index is not None:
                            body.append(remaining.pop(match_index)[1].rstrip("\r\n") + "\n")
                        # Keys introduced after backup are removed; duplicates
                        # are restored only as many times as the backup had.
                    if remaining and body and not body[-1].endswith("\n"):
                        body[-1] += "\n"
                    body.extend(line.rstrip("\r\n") + "\n" for _, line in remaining)
                    prefix_lines = current_lines[:start]
                    if body and prefix_lines and not prefix_lines[-1].endswith("\n"):
                        prefix_lines[-1] += "\n"
                    restored_content = "".join(prefix_lines + body + current_lines[end:])

            if restored_content != current:
                atomic_write_text(ini_path, restored_content)
            return True
        except (OSError, UnicodeError) as e:
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
