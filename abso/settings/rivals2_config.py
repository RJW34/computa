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
    read_config_text,
    restore_managed_key_lines,
    validate_allowed_keys,
    write_config_text,
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

    # The game's own settings UI writes ``FrameRateLimit=999`` for its
    # uncapped option; Unreal also treats ``0`` as no cap. Both mean the
    # same effective state, so verification must not report drift when the
    # game rewrites one sentinel over the other.
    UNCAPPED_FRAME_RATE_SENTINEL = 999

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

        vrr_cap_policy = settings.pop("vrr_cap_policy", None)
        if settings.pop("auto_vrr_fps_cap", False):
            try:
                from abso.core.vrr import get_vrr_fps_cap_for_policy
                from abso.settings.nvidia import NvidiaSettingsHandler

                refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
                if refresh_hz and refresh_hz > 0:
                    settings["frame_rate_limit"] = get_vrr_fps_cap_for_policy(
                        refresh_hz, vrr_cap_policy
                    )
                    logger.info(
                        "Rivals 2 auto VRR FPS cap: %d (from %d Hz%s)",
                        settings["frame_rate_limit"],
                        refresh_hz,
                        f", {vrr_cap_policy}" if vrr_cap_policy else "",
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

    @classmethod
    def _is_uncapped_frame_rate(cls, value: Any) -> bool:
        """True when a FrameRateLimit value means "no cap" (0 or >= 999)."""
        return isinstance(value, int | float) and not isinstance(value, bool) and (
            value == 0 or value >= cls.UNCAPPED_FRAME_RATE_SENTINEL
        )

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify requested Rivals 2 config values are active."""
        settings = dict(settings)
        vrr_cap_policy = settings.pop("vrr_cap_policy", None)
        if settings.pop("auto_vrr_fps_cap", False):
            try:
                from abso.core.vrr import get_vrr_fps_cap_for_policy
                from abso.settings.nvidia import NvidiaSettingsHandler

                refresh_hz = NvidiaSettingsHandler()._detect_primary_refresh_rate()
                if refresh_hz and refresh_hz > 0:
                    settings["frame_rate_limit"] = get_vrr_fps_cap_for_policy(
                        refresh_hz, vrr_cap_policy
                    )
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
            if (
                not is_active
                and key == "frame_rate_limit"
                and self._is_uncapped_frame_rate(target)
                and self._is_uncapped_frame_rate(current_value)
            ):
                # 0 and 999 are both "uncapped"; a game-side rewrite between
                # the two sentinels is not real drift.
                is_active = True
            results["settings"][key] = {
                "target": target,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        return results

    def backup(self) -> dict[str, Any]:
        """Capture full Rivals 2 config context for selective managed-key restore."""
        ini_path = self._get_config_path()
        if not ini_path:
            return {"config_found": False}

        try:
            return {
                "config_found": True,
                "config_path": str(ini_path),
                "file_content": read_config_text(ini_path),
            }
        except Exception as e:
            logger.error("Failed to back up Rivals 2 config %s: %s", ini_path, e)
            return {"config_found": False}

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore ABSO-owned Rivals 2 keys from a backup payload.

        New backups store the full INI under ``file_content``. Older backups
        (taken before the full-file format) only persisted detected values,
        so they are converted to the same selective-merge operation.
        """
        if not data.get("config_found"):
            return True  # Nothing to restore

        file_content = data.get("file_content")
        if file_content is None:
            return self._restore_from_legacy_payload(data)

        # Do not recreate a config that is no longer present at its live path.
        ini_path = self._get_config_path()
        if ini_path is None:
            return True

        try:
            self._restore_managed_content(ini_path, file_content)
            return True
        except OSError as e:
            logger.error("Failed to restore Rivals 2 config %s: %s", ini_path, e)
            return False

    def _restore_from_legacy_payload(self, data: dict[str, Any]) -> bool:
        """Selectively restore detected fields from a legacy backup payload."""
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
