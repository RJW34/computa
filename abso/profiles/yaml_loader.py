"""YAML-to-BaseProfile factory for user-defined game profiles.

Loads YAML profile definitions from ~/.abso/profiles/ and creates dynamic
BaseProfile subclasses, returning ProfileCatalogEntry objects for integration
with the profile catalog.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from abso.profiles.base import (
    VALID_CPU_AFFINITY_STRATEGIES,
    VALID_GRAPHICS_APIS,
    VALID_NETWORK_SCOPES,
    BaseProfile,
)
from abso.profiles.catalog import (
    ProfileCatalogEntry,
    SyncMode,
    is_valid_profile_id,
    is_valid_sync_mode,
    is_valid_tray_category,
    normalize_tray_category,
    sync_mode_choices,
    tray_category_choices,
)
from abso.profiles.profile_bases import (
    EmulatorLatencyBaseProfile,
    ReflexShooterBaseProfile,
    Rivals2BaseProfile,
    WebGLBaseProfile,
    add_legacy_system_tweaks,
    build_standard_handlers,
    merged_handler_settings,
)
from abso.settings.registry import WIN32_PRIORITY_GAMING_ONLINE

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = frozenset({
    "profile_id",
    "display_name",
    "description",
    "optimization_target",
    "executable_hints",
})
_OPTIONAL_FIELDS = frozenset({
    "base",
    "settings",
    "metadata",
    "in_game_settings",
    "tray_category",
    "tray_subtitle",
    "tray_description",
    "sync_mode",
    "tray_group",
    "tray_group_name",
    "tray_variant",
    "tray_rank",
    "tray_visible",
})
_ALLOWED_FIELDS = _REQUIRED_FIELDS | _OPTIONAL_FIELDS

# YAML profile loading uses yaml.safe_load (no arbitrary code execution), but
# the metadata fields below feed online-safety checks (e.g. is_online_profile
# gates RollbackGuard). Treat YAML profile files as TRUSTED CONFIGURATION —
# they should never be loaded from unverified sources.
_METADATA_PROPERTIES: set[str] = {
    "is_online_profile",
    "is_emulator_profile",
    "requires_reflex",
    "is_sdr_only",
    "network_scope",
    "graphics_api",
    "allows_aggressive_settings",
    "include_legacy_tweaks",
    "cpu_affinity_strategy",
}
_BOOLEAN_METADATA_PROPERTIES: set[str] = {
    "is_online_profile",
    "is_emulator_profile",
    "requires_reflex",
    "is_sdr_only",
    "allows_aggressive_settings",
    "include_legacy_tweaks",
}


def _field_type_error(path: Path, field: str, expected: str) -> ValueError:
    return ValueError(f"Expected '{field}' to be {expected} in {path}")


def _one_of(values: tuple[str, ...]) -> str:
    return "one of " + ", ".join(values)


def _guidance_scalar_to_string(value: Any) -> str:
    if isinstance(value, bool):
        return "On" if value else "Off"
    return str(value)


def _normalize_in_game_settings(
    settings: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            key: _guidance_scalar_to_string(value)
            for key, value in item.items()
        }
        for item in settings
    ]


def _normalize_sync_mode(value: Any, path: Path) -> SyncMode:
    if value is None:
        return "agnostic"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, str):
        sync_mode = value.strip().lower()
        if is_valid_sync_mode(sync_mode):
            return sync_mode
        raise _field_type_error(path, "sync_mode", _one_of(sync_mode_choices()))
    raise _field_type_error(path, "sync_mode", "a string or boolean")


def _normalize_literal_metadata(
    path: Path,
    metadata: dict[str, Any],
    key: str,
    allowed_values: frozenset[str],
    *,
    allow_none: bool = False,
) -> None:
    if key not in metadata:
        return
    value = metadata[key]
    if value is None and allow_none:
        return
    if not isinstance(value, str):
        expected = "one of " + ", ".join(sorted(allowed_values))
        if allow_none:
            expected += ", or null"
        raise _field_type_error(path, f"metadata.{key}", expected)
    normalized = value.strip().lower()
    if normalized not in allowed_values:
        expected = "one of " + ", ".join(sorted(allowed_values))
        if allow_none:
            expected += ", or null"
        raise _field_type_error(path, f"metadata.{key}", expected)
    metadata[key] = normalized


class BalancedBaseProfile(BaseProfile):
    """Sensible-defaults base for profiles that don't need a specialized base.

    Provides standard gaming handlers with moderate settings: Game Mode on,
    Ultimate Performance power plan, and conservative OS-default network tuning.
    """

    def get_handlers(self) -> list[SettingsHandler]:
        return build_standard_handlers(
            self,
            include_mouse=True,
            include_cpu_affinity=False,
        )

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        settings: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "processor_max_performance": True,
            },
            "RegistrySettingsHandler": {
                "win32_priority_separation": WIN32_PRIORITY_GAMING_ONLINE,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    # sfio_priority omitted — has no effect per Microsoft docs
                },
            },
            "NetworkSettingsHandler": {
                "disable_nagle": False,
                "preset": "default",
            },
            "MouseSettingsHandler": {
                "disable_acceleration": True,
                "set_linear_curve": True,
                "mouse_sensitivity": 10,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": True,
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 2,
                "io_priority": 2,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "balanced",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        if self.include_legacy_tweaks:
            add_legacy_system_tweaks(settings)

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        return merged_handler_settings(self, handler_name)

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return []


class YAMLProfileLoader:
    """Loads user-defined YAML profiles as dynamic BaseProfile subclasses."""

    BASE_TEMPLATES: dict[str, type[BaseProfile]] = {
        "competitive_fps": Rivals2BaseProfile,
        "reflex_shooter": ReflexShooterBaseProfile,
        "emulator": EmulatorLatencyBaseProfile,
        "browser": WebGLBaseProfile,
        "balanced": BalancedBaseProfile,
    }

    USER_PROFILES_DIR: Path = Path.home() / ".abso" / "profiles"

    def load_directory(
        self, directory: Path | None = None
    ) -> dict[str, ProfileCatalogEntry]:
        """Load all .yaml/.yml files from a directory.

        Args:
            directory: Path to scan. Defaults to ``~/.abso/profiles/``.

        Returns:
            Mapping of profile_id to ProfileCatalogEntry for every file that
            loaded successfully. Files that fail validation are logged and
            skipped.
        """
        target_dir = directory or self.USER_PROFILES_DIR
        entries: dict[str, ProfileCatalogEntry] = {}

        if not target_dir.is_dir():
            logger.debug("YAML profiles directory does not exist: %s", target_dir)
            return entries

        yaml_files = sorted(
            p for p in target_dir.iterdir()
            if p.suffix in {".yaml", ".yml"} and p.is_file()
        )

        if not yaml_files:
            logger.debug("No YAML profile files found in %s", target_dir)
            return entries

        for path in yaml_files:
            try:
                profile_id, entry = self.load_file(path)
                if profile_id in entries:
                    logger.warning(
                        "Duplicate profile_id '%s' in %s — skipping "
                        "(already loaded from another file)",
                        profile_id,
                        path,
                    )
                    continue
                entries[profile_id] = entry
                logger.info("Loaded YAML profile '%s' from %s", profile_id, path)
            except Exception:
                logger.warning("Failed to load YAML profile %s", path, exc_info=True)

        return entries

    def load_file(self, path: Path) -> tuple[str, ProfileCatalogEntry]:
        """Load a single YAML profile file.

        Args:
            path: Path to the ``.yaml`` / ``.yml`` file.

        Returns:
            Tuple of (profile_id, ProfileCatalogEntry).

        Raises:
            ValueError: If the file is missing required fields or references
                an unknown base template.
            yaml.YAMLError: If the file contains invalid YAML.
            OSError: If the file cannot be read.
        """
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict):
            raise ValueError(f"Expected a YAML mapping at top level in {path}")

        self._validate(data, path)

        profile_class = self._create_profile_class(data)

        tray_category = normalize_tray_category(data.get("tray_category", "Other"))

        sync_mode = _normalize_sync_mode(data.get("sync_mode"), path)

        entry = ProfileCatalogEntry(
            profile_class=profile_class,
            tray_category=tray_category,
            tray_subtitle=data.get("tray_subtitle", data["display_name"]),
            tray_description=data.get("tray_description"),
            sync_mode=sync_mode,
            tray_group=data.get("tray_group"),
            tray_group_name=data.get("tray_group_name"),
            tray_variant=data.get("tray_variant"),
            tray_rank=int(data.get("tray_rank", 100)),
            tray_visible=bool(data.get("tray_visible", True)),
        )

        return data["profile_id"], entry

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate(self, data: dict[str, Any], path: Path) -> None:
        """Validate that all required fields are present.

        Raises:
            ValueError: On missing required fields or unknown base template.
        """
        missing = _REQUIRED_FIELDS - data.keys()
        if missing:
            raise ValueError(
                f"Missing required fields {sorted(missing)} in {path}"
            )
        unknown_fields = sorted(set(data) - _ALLOWED_FIELDS)
        if unknown_fields:
            field = unknown_fields[0]
            raise _field_type_error(
                path,
                field,
                _one_of(tuple(sorted(_ALLOWED_FIELDS))),
            )

        for field in (
            "profile_id",
            "display_name",
            "description",
            "optimization_target",
        ):
            if not isinstance(data[field], str) or not data[field].strip():
                raise _field_type_error(path, field, "a non-empty string")
        if not is_valid_profile_id(data["profile_id"]):
            raise _field_type_error(
                path,
                "profile_id",
                "a lowercase slug using letters, numbers, and single hyphens",
            )

        executable_hints = data["executable_hints"]
        if (
            not isinstance(executable_hints, list)
            or not executable_hints
            or not all(isinstance(item, str) and item.strip() for item in executable_hints)
        ):
            raise _field_type_error(
                path,
                "executable_hints",
                "a non-empty list of non-empty strings",
            )

        base_name = data.get("base", "balanced")
        if not isinstance(base_name, str):
            raise _field_type_error(path, "base", "a string")
        if base_name not in self.BASE_TEMPLATES:
            raise ValueError(
                f"Unknown base template '{base_name}' in {path}. "
                f"Valid options: {sorted(self.BASE_TEMPLATES)}"
            )

        for field in ("settings", "metadata"):
            value = data.get(field, {})
            if not isinstance(value, dict):
                raise _field_type_error(path, field, "a mapping")

        settings = data.get("settings", {})
        for handler_name, handler_settings in settings.items():
            if not isinstance(handler_name, str) or not handler_name.strip():
                raise _field_type_error(
                    path,
                    "settings",
                    "a mapping of non-empty handler names to settings mappings",
                )
            if not isinstance(handler_settings, dict):
                raise _field_type_error(
                    path,
                    f"settings.{handler_name}",
                    "a mapping",
                )

        metadata = data.get("metadata", {})
        if not all(isinstance(key, str) and key.strip() for key in metadata):
            raise _field_type_error(
                path,
                "metadata",
                "a mapping with non-empty string keys",
            )
        unknown_metadata = sorted(set(metadata) - _METADATA_PROPERTIES)
        if unknown_metadata:
            key = unknown_metadata[0]
            raise _field_type_error(
                path,
                f"metadata.{key}",
                _one_of(tuple(sorted(_METADATA_PROPERTIES))),
            )
        for key in _BOOLEAN_METADATA_PROPERTIES:
            if key not in metadata:
                continue
            value = metadata[key]
            if not isinstance(value, bool):
                raise _field_type_error(path, f"metadata.{key}", "a boolean")
        _normalize_literal_metadata(
            path,
            metadata,
            "network_scope",
            VALID_NETWORK_SCOPES,
        )
        _normalize_literal_metadata(
            path,
            metadata,
            "graphics_api",
            VALID_GRAPHICS_APIS,
        )
        _normalize_literal_metadata(
            path,
            metadata,
            "cpu_affinity_strategy",
            VALID_CPU_AFFINITY_STRATEGIES,
            allow_none=True,
        )

        in_game_settings = data.get("in_game_settings", [])
        if not isinstance(in_game_settings, list):
            raise _field_type_error(path, "in_game_settings", "a list")
        if not all(isinstance(item, dict) for item in in_game_settings):
            raise _field_type_error(path, "in_game_settings", "a list of mappings")
        for item in in_game_settings:
            if not all(isinstance(key, str) for key in item):
                raise _field_type_error(
                    path,
                    "in_game_settings",
                    "a list of string-keyed mappings",
                )
            if any(isinstance(value, dict | list) or value is None for value in item.values()):
                raise _field_type_error(
                    path,
                    "in_game_settings",
                    "a list of mappings with scalar values",
                )

        for field in (
            "tray_category",
            "tray_subtitle",
            "tray_description",
            "tray_group",
            "tray_group_name",
            "tray_variant",
        ):
            value = data.get(field)
            if value is not None and not isinstance(value, str):
                raise _field_type_error(path, field, "a string")

        tray_category = data.get("tray_category")
        if tray_category is not None and not is_valid_tray_category(tray_category):
            raise _field_type_error(
                path,
                "tray_category",
                _one_of(tray_category_choices()),
            )

        sync_mode = data.get("sync_mode")
        if sync_mode is not None and not isinstance(sync_mode, str | bool):
            raise _field_type_error(path, "sync_mode", "a string or boolean")
        if isinstance(sync_mode, str) and not is_valid_sync_mode(
            sync_mode.strip().lower()
        ):
            raise _field_type_error(path, "sync_mode", _one_of(sync_mode_choices()))

        if "tray_visible" in data and not isinstance(data["tray_visible"], bool):
            raise _field_type_error(path, "tray_visible", "a boolean")

        if "tray_rank" in data:
            try:
                int(data["tray_rank"])
            except (TypeError, ValueError) as exc:
                raise _field_type_error(path, "tray_rank", "an integer") from exc

    def _create_profile_class(self, data: dict[str, Any]) -> type[BaseProfile]:
        """Create a dynamic BaseProfile subclass from parsed YAML data.

        Uses ``type()`` to build a new class inheriting from the selected
        base template, with abstract properties satisfied by the YAML values
        and ``_settings_overrides`` returning the user-defined settings.
        """
        base_name: str = data.get("base", "balanced")
        base_class = self.BASE_TEMPLATES[base_name]

        yaml_settings: dict[str, dict[str, Any]] = data.get("settings", {})
        yaml_metadata: dict[str, Any] = data.get("metadata", {})
        yaml_in_game: list[dict[str, Any]] = data.get("in_game_settings", [])
        yaml_executables: list[str] = data["executable_hints"]

        # --- Build the class namespace ---
        namespace: dict[str, Any] = {}

        # Required abstract properties
        pid = data["profile_id"]
        namespace["profile_id"] = property(lambda self, _v=pid: _v)

        dname = data["display_name"]
        namespace["display_name"] = property(lambda self, _v=dname: _v)

        desc = data["description"]
        namespace["description"] = property(lambda self, _v=desc: _v)

        opt = data["optimization_target"]
        namespace["optimization_target"] = property(lambda self, _v=opt: _v)

        exes = list(yaml_executables)
        namespace["executable_hints"] = property(lambda self, _v=exes: list(_v))

        # Settings overrides — feeds into the base class merge pipeline
        frozen_settings = deepcopy(yaml_settings)
        namespace["_settings_overrides"] = lambda self, _v=frozen_settings: deepcopy(_v)

        # In-game settings
        frozen_in_game = _normalize_in_game_settings(yaml_in_game)
        namespace["get_in_game_settings"] = lambda self, _v=frozen_in_game: deepcopy(_v)

        # Optional metadata property overrides
        for key, value in yaml_metadata.items():
            namespace[key] = property(lambda self, v=value: deepcopy(v))

        # Derive a valid Python class name from the profile ID
        class_name = "YAMLProfile_" + data["profile_id"].replace("-", "_")

        return type(class_name, (base_class,), namespace)
