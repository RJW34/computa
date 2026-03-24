"""YAML-to-BaseProfile factory for user-defined game profiles.

Loads YAML profile definitions from ~/.abso/profiles/ and creates dynamic
BaseProfile subclasses, returning ProfileCatalogEntry objects for integration
with the profile catalog.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from abso.profiles.base import BaseProfile
from abso.profiles.catalog import ProfileCatalogEntry, SyncMode, TrayCategory
from abso.profiles.profile_bases import (
    EmulatorLatencyBaseProfile,
    ReflexShooterBaseProfile,
    Rivals2BaseProfile,
    WebGLBaseProfile,
    merge_settings_map,
)

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

_VALID_TRAY_CATEGORIES: set[TrayCategory] = {
    "Productivity",
    "Fighting",
    "ARPG",
    "Shooter",
    "Streaming",
    "Other",
}

_VALID_SYNC_MODES: set[SyncMode] = {"on", "off", "agnostic"}

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


class BalancedBaseProfile(BaseProfile):
    """Sensible-defaults base for profiles that don't need a specialized base.

    Provides standard gaming handlers with moderate settings: Game Mode on,
    Ultimate Performance power plan, and standard service/network tuning.
    """

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.cnm import CNMSettingsHandler
        from abso.settings.color import ColorProfileSettingsHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.mouse import MouseSettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.services import ServicesSettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        handlers: list[SettingsHandler] = [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            NetworkSettingsHandler(),
            MouseSettingsHandler(),
            GraphicsSettingsHandler(),
            ServicesSettingsHandler(),
        ]

        if self.include_legacy_tweaks:
            handlers.append(MemorySettingsHandler())

        handlers += [
            ProcessPriorityHandler(self.executable_hints),
            CNMSettingsHandler(),
            ColorProfileSettingsHandler(),
        ]
        return handlers

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
                "win32_priority_separation": 0x26,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    "sfio_priority": "High",
                },
            },
            "NetworkSettingsHandler": {
                "disable_nagle": False,
                "preset": "gaming",
            },
            "MouseSettingsHandler": {
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": True,
            },
            "ServicesSettingsHandler": {
                "preset": "gaming",
            },
            "ProcessPriorityHandler": {
                "gpu_priority": 8,
                "cpu_priority": 2,
                "io_priority": 2,
            },
            "CNMSettingsHandler": {
                "action": "stop",
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "balanced",
            },
        }

        if self.include_legacy_tweaks:
            settings["RegistrySettingsHandler"]["system_responsiveness"] = 10
            settings["RegistrySettingsHandler"]["network_throttling"] = 0xFFFFFFFF
            settings["MemorySettingsHandler"] = {
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            }

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = merge_settings_map(
            self._base_settings(), self._settings_overrides()
        )
        return settings_map.get(handler_name, {})

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
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict):
            raise ValueError(f"Expected a YAML mapping at top level in {path}")

        self._validate(data, path)

        profile_class = self._create_profile_class(data)

        tray_category: TrayCategory = data.get("tray_category", "Other")
        if tray_category not in _VALID_TRAY_CATEGORIES:
            logger.warning(
                "Unknown tray_category '%s' in %s — defaulting to 'Other'",
                tray_category,
                path,
            )
            tray_category = "Other"

        sync_mode: SyncMode = data.get("sync_mode", "agnostic")
        if sync_mode not in _VALID_SYNC_MODES:
            logger.warning(
                "Unknown sync_mode '%s' in %s — defaulting to 'agnostic'",
                sync_mode,
                path,
            )
            sync_mode = "agnostic"

        entry = ProfileCatalogEntry(
            profile_class=profile_class,
            tray_category=tray_category,
            tray_subtitle=data.get("tray_subtitle", data["display_name"]),
            tray_description=data.get("tray_description"),
            sync_mode=sync_mode,
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

        base_name = data.get("base", "balanced")
        if base_name not in self.BASE_TEMPLATES:
            raise ValueError(
                f"Unknown base template '{base_name}' in {path}. "
                f"Valid options: {sorted(self.BASE_TEMPLATES)}"
            )

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
        yaml_in_game: list[dict[str, str]] = data.get("in_game_settings", [])
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
        frozen_settings = dict(yaml_settings)
        namespace["_settings_overrides"] = lambda self, _v=frozen_settings: _v

        # In-game settings
        frozen_in_game = list(yaml_in_game)
        namespace["get_in_game_settings"] = lambda self, _v=frozen_in_game: list(_v)

        # Optional metadata property overrides
        for key, value in yaml_metadata.items():
            if key not in _METADATA_PROPERTIES:
                logger.warning(
                    "Ignoring unknown metadata key '%s' in profile '%s'",
                    key,
                    data["profile_id"],
                )
                continue
            namespace[key] = property(lambda self, v=value: v)

        # Derive a valid Python class name from the profile ID
        class_name = "YAMLProfile_" + data["profile_id"].replace("-", "_")

        return type(class_name, (base_class,), namespace)
