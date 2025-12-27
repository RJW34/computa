"""Configuration file management.

This module handles loading, saving, and validating YAML configuration files
for A.B.S.O. (Adaptive Battle Station Optimizer) user preferences and custom settings.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from abso.core.exceptions import (
    ConfigLoadError,
    ConfigSaveError,
    ConfigValidationError,
)

logger = logging.getLogger(__name__)

# Default configuration file name
DEFAULT_CONFIG_NAME = "abso.yaml"


@dataclass
class ProfileOverrides:
    """Custom overrides for a game profile."""

    nvidia: dict[str, Any] = field(default_factory=dict)
    windows: dict[str, Any] = field(default_factory=dict)
    network: dict[str, Any] = field(default_factory=dict)
    power: dict[str, Any] = field(default_factory=dict)
    timer: dict[str, Any] = field(default_factory=dict)
    mouse: dict[str, Any] = field(default_factory=dict)


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
    log_level: str = "INFO"
    default_profile: str | None = None
    profile_overrides: dict[str, ProfileOverrides] = field(default_factory=dict)
    custom_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    disabled_handlers: list[str] = field(default_factory=list)
    confirm_destructive: bool = True

    def __post_init__(self) -> None:
        """Convert nested dicts to ProfileOverrides objects."""
        if self.profile_overrides:
            converted = {}
            for profile_id, overrides in self.profile_overrides.items():
                if isinstance(overrides, dict):
                    converted[profile_id] = ProfileOverrides(**overrides)
                else:
                    converted[profile_id] = overrides
            self.profile_overrides = converted


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
    }

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize configuration manager.

        Args:
            config_path: Path to configuration file. If None, uses default location.
        """
        if config_path is None:
            config_path = Path.cwd() / DEFAULT_CONFIG_NAME
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
                    "Invalid configuration format",
                    details="Configuration must be a YAML mapping"
                )

            # Validate before creating config
            self._validate_config_data(data)

            # Filter out unknown keys before creating config
            known_keys = {
                "backup_dir",
                "auto_backup",
                "log_level",
                "default_profile",
                "profile_overrides",
                "custom_profiles",
                "disabled_handlers",
                "confirm_destructive",
            }
            filtered_data = {k: v for k, v in data.items() if k in known_keys}

            return ABSOConfig(**filtered_data)

        except yaml.YAMLError as e:
            raise ConfigLoadError(
                "Failed to parse configuration file",
                details=str(e)
            )
        except TypeError as e:
            raise ConfigValidationError(
                "Invalid configuration structure",
                details=str(e)
            )
        except OSError as e:
            raise ConfigLoadError(
                "Failed to read configuration file",
                details=str(e)
            )

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
                "# A.B.S.O. Configuration\n"
                "# Adaptive Battle Station Optimizer\n"
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
            raise ConfigSaveError(
                "Failed to write configuration file",
                details=str(e)
            )

    def create_default(self) -> None:
        """Create a default configuration file with comments."""
        default_yaml = """# A.B.S.O. Configuration
# Adaptive Battle Station Optimizer
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
#     timer:
#       resolution_ms: 0.5

# Custom profiles (advanced)
# custom_profiles:
#   my-game:
#     display_name: "My Custom Game"
#     description: "Custom profile for my game"
#     optimization_target: "Ultra-low latency"
#     handlers:
#       WindowsSettingsHandler:
#         game_mode: true
#         game_bar: false
#       NvidiaSettingsHandler:
#         preset: minimum_latency
"""
        try:
            self.config_path.write_text(default_yaml, encoding="utf-8")
            logger.info(f"Created default configuration at {self.config_path}")
        except OSError as e:
            raise ConfigSaveError(
                "Failed to create default configuration",
                details=str(e)
            )

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
                details=f"Must be one of: {', '.join(self.VALID_LOG_LEVELS)}"
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
            if config.default_profile not in ProfileApplier.PROFILES:
                warnings.append(f"Unknown default_profile: {config.default_profile}")

        # Validate profile overrides reference existing profiles
        if config.profile_overrides:
            from abso.core.applier import ProfileApplier
            for profile_id in config.profile_overrides:
                if profile_id not in ProfileApplier.PROFILES:
                    warnings.append(f"Profile override for unknown profile: {profile_id}")

        return warnings

    def get_profile_overrides(self, profile_id: str) -> ProfileOverrides | None:
        """Get custom overrides for a profile.

        Args:
            profile_id: Profile identifier.

        Returns:
            ProfileOverrides if configured, None otherwise.
        """
        return self.config.profile_overrides.get(profile_id)

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
        # Check for unknown keys
        known_keys = {
            "backup_dir",
            "auto_backup",
            "log_level",
            "default_profile",
            "profile_overrides",
            "custom_profiles",
            "disabled_handlers",
            "confirm_destructive",
        }

        unknown_keys = set(data.keys()) - known_keys
        if unknown_keys:
            logger.warning(f"Unknown configuration keys: {unknown_keys}")

        # Validate types
        if "auto_backup" in data and not isinstance(data["auto_backup"], bool):
            raise ConfigValidationError(
                "Invalid type for auto_backup",
                details="Must be a boolean (true/false)"
            )

        if "disabled_handlers" in data and not isinstance(data["disabled_handlers"], list):
            raise ConfigValidationError(
                "Invalid type for disabled_handlers",
                details="Must be a list of handler names"
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
