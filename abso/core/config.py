"""Configuration file management.

This module handles loading, saving, and validating YAML configuration files
for computa user preferences and custom settings.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from abso.core.app_paths import app_data_dir
from abso.core.exceptions import (
    ConfigLoadError,
    ConfigSaveError,
    ConfigValidationError,
)

logger = logging.getLogger(__name__)

# Default configuration file name
DEFAULT_CONFIG_NAME = "abso.yaml"
CONFIG_ENV_VAR = "ABSO_CONFIG"


def resolve_default_config_path(cwd: Path | None = None) -> Path:
    """Return the default config path for source and installed runtimes."""
    configured = os.environ.get(CONFIG_ENV_VAR)
    if configured:
        return Path(configured).expanduser()

    current_dir = cwd or Path.cwd()
    cwd_config = current_dir / DEFAULT_CONFIG_NAME
    if cwd_config.exists():
        return cwd_config

    installed_config = app_data_dir() / DEFAULT_CONFIG_NAME
    if installed_config.exists():
        return installed_config

    return cwd_config


@dataclass
class StandbyListConfig:
    """Standby list clearing configuration (ISLC equivalent)."""

    enabled: bool = False
    threshold_mb: int = 1024  # Purge when standby >= this
    free_threshold_mb: int = 1024  # AND free RAM < this
    poll_interval_ms: int = 1000


@dataclass
class CpuBalancerConfig:
    """ProBalance-style CPU priority intervention configuration."""

    enabled: bool = False
    # Defaults tuned for a high-core-count desktop (24C/32T): the system metric
    # aggregates across all logical processors, so a capped game keeps it low
    # and only a genuine background spike crosses 55%. The per-process metric is
    # normalized to total capacity (~3% per saturated core on a 32-thread box),
    # so 8% catches multi-core offenders without demoting light background apps.
    # Tune against live measurement. Keep in sync with
    # abso.core.cpu_balancer.CpuBalancerConfig.
    system_cpu_threshold: int = 55
    process_cpu_threshold: int = 8
    trigger_delay_ms: int = 2800
    restraint_duration_ms: int = 6000
    poll_interval_ms: int = 1000
    excluded_processes: list[str] = field(
        default_factory=lambda: [
            "csrss.exe",
            "dwm.exe",
            "audiodg.exe",
            "System",
            "svchost.exe",
            "wininit.exe",
            "services.exe",
            "smss.exe",
            "lsass.exe",
            "winlogon.exe",
        ]
    )


@dataclass
class EfficiencyModeConfig:
    """EcoQoS background-herding configuration (Tier B scaffold, default OFF).

    When ``enabled`` the tray may, during a game session, throttle the
    ``background_images`` onto E-cores via EcoQoS and reset them on game exit.
    The herder never throttles the game, anti-cheat, capture tools, or Discord.
    """

    enabled: bool = False
    background_images: list[str] = field(default_factory=list)


@dataclass
class CpuSetsConfig:
    """CPU Sets core-partition steering configuration.

    Soft ``SetProcessDefaultCpuSets`` biasing only -- hard affinity is never
    touched (threads still spill under load), which is anti-cheat-safe and
    hybrid-correct, unlike hard affinity. Activation is normally
    profile-driven (``BaseProfile.cpu_partition_policy``); ``enabled`` forces
    the game-side steering on for every profile, and the remaining knobs tune
    or veto the background half of the partition.
    """

    enabled: bool = False
    """Force game->fast-core steering on regardless of the profile policy."""

    background_steer: bool = True
    """Allow background apps to be steered to the background side when the
    active profile's policy is ``full``. Placement only (full clock speed),
    never EcoQoS throttling."""

    background_images: list[str] = field(default_factory=list)
    """Extra image names to steer to the background side, unioned with the
    profile's own list (e.g. OBS on capture lanes, browsers on gaming lanes)."""

    auto_steer: bool = True
    """Auto-detect heavy background processes (sustained CPU while the game
    runs) and steer them to the background side. Anti-cheat, protected images,
    the game subtree, and the foreground app are never auto-steered."""

    auto_steer_process_threshold: int = 4
    """Per-process CPU % (normalized to total capacity) that qualifies a
    background process for auto-steer. ~1.3 saturated cores on 32 threads."""

    auto_steer_sustain_ms: int = 5000
    """How long the process must stay above the threshold before steering."""

    smt_avoid: bool = False
    """Restrict the game side to one thread per physical core (experimental;
    charlie754-style 'no SMT' mask). Off by default."""

    x3d_partition: bool = True
    """Permit the AMD X3D cache-CCD split (larger-L3 CCD = game side). When
    False, dual-CCD X3D parts classify as symmetric and steering no-ops.
    Note: Windows Game Mode's own CCD parking can conflict with manual
    steering on Ryzen X3D parts."""


@dataclass
class CpuLimiterConfig:
    """Reversible CPU limiter (affinity-shrink throttle) — Tier B scaffold, OFF.

    When ``enabled`` the governor may shrink a runaway background process's HARD
    affinity to ``keep_cores`` cores while it exceeds threshold, restoring the
    original mask on release/exit. MUST stay disabled for online profiles:
    mid-match affinity mutation injects the timing nondeterminism RollbackGuard
    exists to prevent.
    """

    enabled: bool = False
    keep_cores: int = 4


@dataclass
class WatchdogRule:
    """One declarative, reversible process-watchdog rule.

    ``action`` is restricted to reversible verbs; terminate is intentionally not
    expressible here (it would route through ProcessJanitor's NEVER_KILL net,
    never as a free-form rule).
    """

    match: str
    metric: str = "cpu"  # cpu | ram | priority
    threshold: float = 90.0
    sustain_s: float = 5.0
    action: str = "demote"  # demote | throttle | trim


@dataclass
class WatchdogConfig:
    """Declarative watchdog rule list (Tier B scaffold, default: no rules)."""

    enabled: bool = False
    rules: list[WatchdogRule] = field(default_factory=list)

    def __post_init__(self) -> None:
        coerced: list[WatchdogRule] = []
        for rule in self.rules:
            if isinstance(rule, WatchdogRule):
                coerced.append(rule)
            elif isinstance(rule, dict):
                coerced.append(WatchdogRule(**rule))
        self.rules = coerced


@dataclass
class DDCIConfig:
    """DDC/CI monitor control configuration.

    DDC/CI Adaptive Sync toggling is OFF by default because VCP codes
    are manufacturer-specific. Sending wrong codes to an unsupported
    monitor can cause display glitches or hangs.

    Enable only if you know your monitor's controller is supported.
    """

    enabled: bool = False
    controller_override: str | None = None  # e.g., "CVTE" to force a VCP profile


@dataclass
class ColorConfig:
    """User color preferences that override profile defaults.

    Digital vibrance and ICC profiles are personal preferences, not
    performance optimizations. These overrides let users keep their
    preferred color settings regardless of which game profile is active.
    """

    digital_vibrance: int | None = None  # None = use profile default, 0-100 = override
    icc_profile: str | None = None  # None = use profile default, "srgb"/"native"/filename
    manage_vibrance: bool = True  # False = never touch vibrance
    manage_icc: bool = True  # False = never touch ICC profiles


@dataclass
class ProfileOverrides:
    """Custom overrides for a game profile.

    Each field maps to one settings handler. The override dict is shallow-
    merged into the profile's declared settings for that handler at apply /
    verify time (see ``merge_profile_override_settings``). Adding a new
    handler-specific override surface requires (1) a new field here,
    (2) a row in ``PROFILE_OVERRIDE_HANDLER_ATTRS``, and (3) the handler
    has to be on the ``_coerce_profile_overrides`` allowlist via being a
    field of this dataclass — that is automatic.
    """

    nvidia: dict[str, Any] = field(default_factory=dict)
    windows: dict[str, Any] = field(default_factory=dict)
    registry: dict[str, Any] = field(default_factory=dict)
    graphics: dict[str, Any] = field(default_factory=dict)
    network: dict[str, Any] = field(default_factory=dict)
    power: dict[str, Any] = field(default_factory=dict)
    timer: dict[str, Any] = field(default_factory=dict)
    mouse: dict[str, Any] = field(default_factory=dict)
    cpu_affinity: dict[str, Any] = field(default_factory=dict)
    color: dict[str, Any] = field(default_factory=dict)
    display_color_range: dict[str, Any] = field(default_factory=dict)
    # Per-game config-file handlers — exposed individually so users can
    # disable a profile's auto_vrr_fps_cap, pin a specific frame_rate_cap,
    # or otherwise tune the in-game settings file without modifying source.
    ow2_config: dict[str, Any] = field(default_factory=dict)
    diablo4_config: dict[str, Any] = field(default_factory=dict)
    rivals2_config: dict[str, Any] = field(default_factory=dict)
    marvel_rivals_config: dict[str, Any] = field(default_factory=dict)
    fortnite_config: dict[str, Any] = field(default_factory=dict)


_PROFILE_OVERRIDE_SECTION_NAMES: frozenset[str] = frozenset(
    f.name for f in dataclasses.fields(ProfileOverrides)
)


PROFILE_OVERRIDE_HANDLER_ATTRS: dict[str, str] = {
    "NvidiaSettingsHandler": "nvidia",
    "WindowsSettingsHandler": "windows",
    "RegistrySettingsHandler": "registry",
    "GraphicsSettingsHandler": "graphics",
    "NetworkSettingsHandler": "network",
    "PowerSettingsHandler": "power",
    "TimerSettingsHandler": "timer",
    "MouseSettingsHandler": "mouse",
    "CpuAffinityHandler": "cpu_affinity",
    "ColorProfileSettingsHandler": "color",
    "DisplayColorRangeHandler": "display_color_range",
    "OW2ConfigHandler": "ow2_config",
    "Diablo4ConfigHandler": "diablo4_config",
    "Rivals2ConfigHandler": "rivals2_config",
    "MarvelRivalsConfigHandler": "marvel_rivals_config",
    "FortniteConfigHandler": "fortnite_config",
}


def _format_known_profile_override_sections() -> str:
    return ", ".join(sorted(_PROFILE_OVERRIDE_SECTION_NAMES))


def _coerce_profile_overrides(
    profile_overrides: Mapping[str, Any] | dict[str, ProfileOverrides],
) -> dict[str, ProfileOverrides]:
    """Validate and convert raw profile override config."""
    if not profile_overrides:
        return {}

    if not isinstance(profile_overrides, Mapping):
        raise ConfigValidationError(
            "Invalid type for profile_overrides",
            details="Must be a mapping of profile IDs to override sections",
        )

    converted: dict[str, ProfileOverrides] = {}
    for profile_id, overrides in profile_overrides.items():
        if not isinstance(profile_id, str):
            raise ConfigValidationError(
                "Invalid profile_overrides key",
                details=f"Profile override keys must be strings, got {profile_id!r}",
            )

        if isinstance(overrides, ProfileOverrides):
            converted[profile_id] = overrides
            continue

        if not isinstance(overrides, Mapping):
            raise ConfigValidationError(
                f"Invalid profile_overrides.{profile_id}",
                details="Must be a mapping of override sections",
            )

        unknown_sections = set(overrides) - _PROFILE_OVERRIDE_SECTION_NAMES
        if unknown_sections:
            unknown = ", ".join(str(section) for section in sorted(unknown_sections, key=str))
            raise ConfigValidationError(
                f"Unknown profile override section for {profile_id}: {unknown}",
                details=f"Known sections: {_format_known_profile_override_sections()}",
            )

        for section, values in overrides.items():
            if not isinstance(values, Mapping):
                raise ConfigValidationError(
                    f"Invalid profile_overrides.{profile_id}.{section}",
                    details="Must be a mapping of setting names to values",
                )

        converted[profile_id] = ProfileOverrides(**dict(overrides))

    return converted


def get_handler_profile_overrides(
    overrides: ProfileOverrides,
    handler_name: str,
) -> Mapping[str, Any]:
    """Return the override map that targets a handler."""
    attr_name = PROFILE_OVERRIDE_HANDLER_ATTRS.get(handler_name)
    if not attr_name:
        return {}
    handler_overrides = getattr(overrides, attr_name, {})
    if not isinstance(handler_overrides, Mapping):
        return {}
    return handler_overrides


def _merge_override_values(
    settings: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> dict[str, Any]:
    """Recursively merge profile overrides without sharing nested state."""
    merged: dict[str, Any] = deepcopy(dict(settings))
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_override_values(current, value)
        else:
            merged[key] = deepcopy(value)
    return merged


def merge_profile_override_settings(
    settings: dict[str, Any],
    handler_name: str,
    overrides: ProfileOverrides,
) -> dict[str, Any]:
    """Merge one handler's profile settings with configured overrides."""
    handler_overrides = get_handler_profile_overrides(overrides, handler_name)
    if not handler_overrides:
        return settings
    return _merge_override_values(settings, handler_overrides)


@dataclass
class ProcessOverridesConfig:
    """Per-machine launch-time process sweep overrides.

    ``protect`` augments the built-in :data:`NEVER_KILL_IMAGES` set. Items
    listed here are guaranteed never to be killed by the launch sanitizer,
    even if a profile killset mistakenly includes them. Use this for
    peripheral software your specific hardware actually needs (e.g.
    ``["lghub.exe"]`` if your mouse loses functionality without G HUB).

    ``kill`` appends to every gaming profile's always-safe killset. Use
    this for personal background apps that should always die at game time
    (e.g. ``["MyNotesApp.exe", "BackgroundSyncTool.exe"]``).

    Both lists are case-insensitive on the protect side and case-preserving
    on the kill side (taskkill /IM is case-insensitive on Windows).
    """

    protect: list[str] = field(default_factory=list)
    kill: list[str] = field(default_factory=list)


@dataclass
class ABSOConfig:
    """ABSO configuration settings.

    Attributes:
        backup_dir: Directory for storing backups
        auto_backup: Whether to automatically create backups before applying
        log_level: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
        default_profile: Default profile to apply if none specified
        profile_overrides: Custom settings overrides per profile
        custom_profiles: User-defined custom profiles
        disabled_handlers: List of handler names to skip during apply
        confirm_destructive: Whether to prompt before destructive operations
    """

    backup_dir: str = "backups"
    auto_backup: bool = True
    max_backups: int = 20
    log_level: str = "INFO"
    default_profile: str | None = None
    profile_overrides: dict[str, ProfileOverrides] = field(default_factory=dict)
    custom_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    disabled_handlers: list[str] = field(default_factory=list)
    confirm_destructive: bool = True
    ddci: DDCIConfig = field(default_factory=DDCIConfig)
    color: ColorConfig = field(default_factory=ColorConfig)
    standby_list: StandbyListConfig = field(default_factory=StandbyListConfig)
    cpu_balancer: CpuBalancerConfig = field(default_factory=CpuBalancerConfig)
    efficiency_mode: EfficiencyModeConfig = field(default_factory=EfficiencyModeConfig)
    cpu_sets: CpuSetsConfig = field(default_factory=CpuSetsConfig)
    cpu_limiter: CpuLimiterConfig = field(default_factory=CpuLimiterConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    process_overrides: ProcessOverridesConfig = field(default_factory=ProcessOverridesConfig)

    def __post_init__(self) -> None:
        """Convert nested dicts to typed config objects."""
        self.profile_overrides = _coerce_profile_overrides(self.profile_overrides)
        if isinstance(self.ddci, dict):
            self.ddci = DDCIConfig(**self.ddci)
        if isinstance(self.color, dict):
            self.color = ColorConfig(**self.color)
        if isinstance(self.standby_list, dict):
            self.standby_list = StandbyListConfig(**self.standby_list)
        if isinstance(self.cpu_balancer, dict):
            self.cpu_balancer = CpuBalancerConfig(**self.cpu_balancer)
        if isinstance(self.efficiency_mode, dict):
            self.efficiency_mode = EfficiencyModeConfig(**self.efficiency_mode)
        if isinstance(self.cpu_sets, dict):
            self.cpu_sets = CpuSetsConfig(**self.cpu_sets)
        if isinstance(self.cpu_limiter, dict):
            self.cpu_limiter = CpuLimiterConfig(**self.cpu_limiter)
        if isinstance(self.watchdog, dict):
            self.watchdog = WatchdogConfig(**self.watchdog)
        if isinstance(self.process_overrides, dict):
            self.process_overrides = ProcessOverridesConfig(**self.process_overrides)


# Derived from ABSOConfig dataclass fields — never manually maintained.
# Adding a new field to ABSOConfig automatically makes it a known config key.
_ABSO_CONFIG_KNOWN_KEYS: frozenset[str] = frozenset(f.name for f in dataclasses.fields(ABSOConfig))


class ConfigManager:
    """Manages ABSO configuration files."""

    # Valid log levels
    VALID_LOG_LEVELS: set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    # Known handler names
    KNOWN_HANDLERS: set[str] = {
        "WindowsSettingsHandler",
        "PowerSettingsHandler",
        "RegistrySettingsHandler",
        "NvidiaSettingsHandler",
        "TimerSettingsHandler",
        "MouseSettingsHandler",
        "GraphicsSettingsHandler",
        "ServicesSettingsHandler",
        "TasksSettingsHandler",
        "MemorySettingsHandler",
        "NetworkSettingsHandler",
        "VisualSettingsHandler",
        "StorageSettingsHandler",
        "AudioSettingsHandler",
        "UpdatesSettingsHandler",
        # Profile-specific handlers
        "Diablo4ConfigHandler",
        "DolphinConfigHandler",
        "FortniteConfigHandler",
        "MarvelRivalsConfigHandler",
        "OW2ConfigHandler",
        "Rivals2ConfigHandler",
        "NvidiaNotificationHandler",
        "OBSSettingsHandler",
        "ProcessPriorityHandler",
        "CNMSettingsHandler",
        "ColorProfileSettingsHandler",
        "DisplayColorRangeHandler",
        "CpuAffinityHandler",
        "StandbyListHandler",
        "DebloatHandler",
    }

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize configuration manager.

        Args:
            config_path: Path to configuration file. If None, uses default location.
        """
        if config_path is None:
            config_path = resolve_default_config_path()
        self.config_path = config_path
        self._config: ABSOConfig | None = None

    @property
    def config(self) -> ABSOConfig:
        """Get current configuration, loading from file if needed."""
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self) -> ABSOConfig:
        """Load configuration from file.

        Returns:
            Loaded configuration, or default configuration if file doesn't exist.

        Raises:
            ConfigLoadError: If file exists but cannot be read or parsed.
        """
        if not self.config_path.exists():
            logger.debug(f"Config file not found at {self.config_path}, using defaults")
            return ABSOConfig()

        try:
            content = self.config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if data is None:
                return ABSOConfig()

            if not isinstance(data, dict):
                raise ConfigValidationError(
                    "Invalid configuration format", details="Configuration must be a YAML mapping"
                )

            # Validate before creating config
            self._validate_config_data(data)

            # Filter out unknown keys before creating config
            known_keys = _ABSO_CONFIG_KNOWN_KEYS
            filtered_data = {k: v for k, v in data.items() if k in known_keys}

            return ABSOConfig(**filtered_data)

        except yaml.YAMLError as e:
            raise ConfigLoadError("Failed to parse configuration file", details=str(e)) from e
        except TypeError as e:
            raise ConfigValidationError("Invalid configuration structure", details=str(e)) from e
        except OSError as e:
            raise ConfigLoadError("Failed to read configuration file", details=str(e)) from e

    def save(self, config: ABSOConfig | None = None) -> None:
        """Save configuration to file.

        Args:
            config: Configuration to save. If None, saves current config.

        Raises:
            ConfigSaveError: If file cannot be written.
        """
        if config is None:
            config = self.config

        try:
            # Convert to dict for YAML serialization
            data = self._config_to_dict(config)

            # Add header comment
            yaml_content = (
                "# computa Configuration\n"
                "# Per-game Windows optimization\n"
                "# See docs/API.md for configuration options\n\n"
            )
            yaml_content += yaml.dump(
                data,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

            self.config_path.write_text(yaml_content, encoding="utf-8")
            logger.info(f"Configuration saved to {self.config_path}")

            # Update cached config
            self._config = config

        except OSError as e:
            raise ConfigSaveError("Failed to write configuration file", details=str(e)) from e

    def create_default(self) -> None:
        """Create a default configuration file with comments."""
        default_yaml = """# computa Configuration
# Per-game Windows optimization
# See docs/API.md for configuration options

# Directory for storing backups (relative to working directory)
backup_dir: backups

# Automatically create backup before applying profiles
auto_backup: true

# Logging verbosity: DEBUG, INFO, WARNING, ERROR, CRITICAL
log_level: INFO

# Default profile to use if none specified (optional)
# default_profile: slippi-melee

# Prompt before destructive operations
confirm_destructive: true

# Handlers to disable (skip during apply)
# disabled_handlers:
#   - ServicesSettingsHandler
#   - UpdatesSettingsHandler

# Custom overrides for existing profiles
# profile_overrides:
#   slippi-melee:
#     nvidia:
#       preset: minimum_latency
#     registry:
#       game_priority:
#         priority: 6
#     graphics:
#       disable_mpo: true
#     timer:
#       resolution_ms: 0.5

# Custom profiles (advanced) — see also ~/.abso/profiles/ for YAML profiles
# custom_profiles:
#   my-game:
#     display_name: "My Custom Game"
#     description: "Custom profile for my game"
#     optimization_target: "latency-focused no-sync"
#     handlers:
#       WindowsSettingsHandler:
#         game_mode: true
#         game_bar: false
#       NvidiaSettingsHandler:
#         preset: minimum_latency

# DDC/CI monitor Adaptive Sync control (OFF by default)
# Only enable if your monitor's controller board is supported.
# Sending wrong VCP codes can cause display glitches.
# ddci:
#   enabled: true
#   controller_override: CVTE   # Force a specific VCP profile

# Color preferences (override all profiles)
# Set to prevent ABSO from changing your display colors.
# color:
#   digital_vibrance: 50        # 0-100, overrides all profiles
#   icc_profile: srgb           # srgb, native, or ICC filename
#   manage_vibrance: true       # false = never touch vibrance
#   manage_icc: true            # false = never touch ICC profiles

# Per-machine launch-time process sweep overrides.
#   protect: process image names that must NEVER be killed by the launch
#            sanitizer, even if a profile killset includes them. Use this
#            for peripheral SW your hardware actually requires (e.g. add
#            lghub.exe if your mouse loses functionality without G HUB).
#   kill:    process image names to ALWAYS kill at game time, on top of
#            ABSO's built-in always-safe list. Use this for personal apps
#            you never want running during gameplay.
# process_overrides:
#   protect:
#     - lghub.exe       # only if your specific Logi peripheral needs it
#     - iCUE.exe        # only if your Corsair RGB profile requires it
#   kill:
#     - SomePersonalApp.exe
"""
        try:
            self.config_path.write_text(default_yaml, encoding="utf-8")
            logger.info(f"Created default configuration at {self.config_path}")
        except OSError as e:
            raise ConfigSaveError("Failed to create default configuration", details=str(e)) from e

    def validate(self, config: ABSOConfig | None = None) -> list[str]:
        """Validate configuration and return list of warnings.

        Args:
            config: Configuration to validate. If None, validates current config.

        Returns:
            List of validation warning messages.

        Raises:
            ConfigValidationError: If configuration has critical errors.
        """
        if config is None:
            config = self.config

        warnings: list[str] = []

        # Validate log level
        if config.log_level.upper() not in self.VALID_LOG_LEVELS:
            raise ConfigValidationError(
                f"Invalid log_level: {config.log_level}",
                details=f"Must be one of: {', '.join(self.VALID_LOG_LEVELS)}",
            )

        # Validate backup directory
        backup_path = Path(config.backup_dir)
        if backup_path.exists() and not backup_path.is_dir():
            raise ConfigValidationError(
                f"backup_dir exists but is not a directory: {config.backup_dir}"
            )

        # Validate disabled handlers
        for handler in config.disabled_handlers:
            if handler not in self.KNOWN_HANDLERS:
                warnings.append(f"Unknown handler in disabled_handlers: {handler}")

        # Validate default profile
        if config.default_profile:
            from abso.core.applier import ProfileApplier
            from abso.profiles.catalog import resolve_profile_id

            canonical_default_profile = resolve_profile_id(config.default_profile)
            if canonical_default_profile not in ProfileApplier.PROFILES:
                warnings.append(f"Unknown default_profile: {config.default_profile}")

        # Validate profile overrides reference existing profiles
        if config.profile_overrides:
            from abso.core.applier import ProfileApplier
            from abso.profiles.catalog import resolve_profile_id

            for profile_id in config.profile_overrides:
                canonical_profile_id = resolve_profile_id(profile_id) or profile_id
                if canonical_profile_id not in ProfileApplier.PROFILES:
                    warnings.append(f"Profile override for unknown profile: {profile_id}")

        return warnings

    def get_profile_overrides(self, profile_id: str) -> ProfileOverrides | None:
        """Get custom overrides for a profile.

        Args:
            profile_id: Profile identifier.

        Returns:
            ProfileOverrides if configured, None otherwise.
        """
        exact = self.config.profile_overrides.get(profile_id)
        if exact is not None:
            return exact

        from abso.profiles.catalog import resolve_profile_id

        canonical_profile_id = resolve_profile_id(profile_id)
        if not canonical_profile_id:
            return None

        canonical_match = self.config.profile_overrides.get(canonical_profile_id)
        if canonical_match is not None:
            return canonical_match

        for configured_profile_id, overrides in self.config.profile_overrides.items():
            if resolve_profile_id(configured_profile_id) == canonical_profile_id:
                return overrides
        return None

    def is_handler_disabled(self, handler_name: str) -> bool:
        """Check if a handler is disabled in configuration.

        Args:
            handler_name: Name of the handler class.

        Returns:
            True if handler should be skipped.
        """
        return handler_name in self.config.disabled_handlers

    def _validate_config_data(self, data: dict[str, Any]) -> None:
        """Validate raw configuration data before parsing.

        Args:
            data: Raw configuration dictionary.

        Raises:
            ConfigValidationError: If data is invalid.
        """
        # Check for unknown keys. The known-key set is derived from ABSOConfig
        # fields so config validation cannot drift when new top-level options
        # are added.
        unknown_keys = set(data.keys()) - _ABSO_CONFIG_KNOWN_KEYS
        if unknown_keys:
            logger.warning(f"Unknown configuration keys: {unknown_keys}")

        # Validate types
        if "auto_backup" in data and not isinstance(data["auto_backup"], bool):
            raise ConfigValidationError(
                "Invalid type for auto_backup", details="Must be a boolean (true/false)"
            )

        if "disabled_handlers" in data and not isinstance(data["disabled_handlers"], list):
            raise ConfigValidationError(
                "Invalid type for disabled_handlers", details="Must be a list of handler names"
            )

    def _config_to_dict(self, config: ABSOConfig) -> dict[str, Any]:
        """Convert configuration to dictionary for serialization.

        Args:
            config: Configuration object.

        Returns:
            Dictionary representation.
        """
        data = asdict(config)

        # Convert ProfileOverrides to dicts
        if data["profile_overrides"]:
            data["profile_overrides"] = {
                k: asdict(v) if hasattr(v, "__dataclass_fields__") else v
                for k, v in data["profile_overrides"].items()
            }

        # Remove None values for cleaner YAML
        return {k: v for k, v in data.items() if v is not None}


def get_config() -> ABSOConfig:
    """Get the global configuration instance.

    Returns:
        Current configuration.
    """
    return ConfigManager().config


def load_config(path: Path | None = None) -> ABSOConfig:
    """Load configuration from a file.

    Args:
        path: Path to configuration file.

    Returns:
        Loaded configuration.
    """
    return ConfigManager(path).load()
