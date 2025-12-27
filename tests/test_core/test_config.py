"""Tests for configuration management module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from gametune.core.config import (
    GameTuneConfig,
    ProfileOverrides,
    ConfigManager,
    get_config,
    load_config,
    DEFAULT_CONFIG_NAME,
)
from gametune.core.exceptions import (
    ConfigLoadError,
    ConfigSaveError,
    ConfigValidationError,
)


class TestGameTuneConfig:
    """Tests for GameTuneConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = GameTuneConfig()

        assert config.backup_dir == "backups"
        assert config.auto_backup is True
        assert config.log_level == "INFO"
        assert config.default_profile is None
        assert config.profile_overrides == {}
        assert config.custom_profiles == {}
        assert config.disabled_handlers == []
        assert config.confirm_destructive is True

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = GameTuneConfig(
            backup_dir="my_backups",
            auto_backup=False,
            log_level="DEBUG",
            default_profile="slippi-melee",
            disabled_handlers=["ServicesSettingsHandler"],
        )

        assert config.backup_dir == "my_backups"
        assert config.auto_backup is False
        assert config.log_level == "DEBUG"
        assert config.default_profile == "slippi-melee"
        assert "ServicesSettingsHandler" in config.disabled_handlers

    def test_profile_overrides_conversion(self):
        """Test that dict profile_overrides are converted to ProfileOverrides."""
        config = GameTuneConfig(
            profile_overrides={
                "slippi-melee": {
                    "nvidia": {"preset": "minimum_latency"},
                    "timer": {"resolution_ms": 0.5},
                }
            }
        )

        assert "slippi-melee" in config.profile_overrides
        override = config.profile_overrides["slippi-melee"]
        assert isinstance(override, ProfileOverrides)
        assert override.nvidia == {"preset": "minimum_latency"}
        assert override.timer == {"resolution_ms": 0.5}


class TestProfileOverrides:
    """Tests for ProfileOverrides dataclass."""

    def test_default_values(self):
        """Test default empty dictionaries."""
        overrides = ProfileOverrides()

        assert overrides.nvidia == {}
        assert overrides.windows == {}
        assert overrides.network == {}
        assert overrides.power == {}
        assert overrides.timer == {}
        assert overrides.mouse == {}

    def test_custom_values(self):
        """Test with custom override values."""
        overrides = ProfileOverrides(
            nvidia={"preset": "low_latency"},
            timer={"resolution_ms": 1.0},
        )

        assert overrides.nvidia["preset"] == "low_latency"
        assert overrides.timer["resolution_ms"] == 1.0


class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_init_default_path(self):
        """Test manager uses default path if none specified."""
        manager = ConfigManager()

        assert manager.config_path.name == DEFAULT_CONFIG_NAME

    def test_init_custom_path(self, tmp_path):
        """Test manager uses custom path."""
        custom_path = tmp_path / "custom.yaml"
        manager = ConfigManager(custom_path)

        assert manager.config_path == custom_path

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading returns defaults when file doesn't exist."""
        manager = ConfigManager(tmp_path / "nonexistent.yaml")
        config = manager.load()

        assert config.backup_dir == "backups"
        assert config.auto_backup is True

    def test_load_empty_file(self, tmp_path):
        """Test loading empty file returns defaults."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("")

        manager = ConfigManager(config_path)
        config = manager.load()

        assert config.backup_dir == "backups"

    def test_load_valid_yaml(self, tmp_path):
        """Test loading valid YAML configuration."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
backup_dir: custom_backups
auto_backup: false
log_level: DEBUG
disabled_handlers:
  - ServicesSettingsHandler
""")

        manager = ConfigManager(config_path)
        config = manager.load()

        assert config.backup_dir == "custom_backups"
        assert config.auto_backup is False
        assert config.log_level == "DEBUG"
        assert "ServicesSettingsHandler" in config.disabled_handlers

    def test_load_invalid_yaml(self, tmp_path):
        """Test loading invalid YAML raises error."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("invalid: yaml: syntax: {{{}}")

        manager = ConfigManager(config_path)

        with pytest.raises(ConfigLoadError):
            manager.load()

    def test_load_invalid_structure(self, tmp_path):
        """Test loading non-dict YAML raises error."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("- this\n- is\n- a list")

        manager = ConfigManager(config_path)

        with pytest.raises(ConfigValidationError):
            manager.load()

    def test_save_creates_file(self, tmp_path):
        """Test save creates configuration file."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path)

        config = GameTuneConfig(backup_dir="saved_backups")
        manager.save(config)

        assert config_path.exists()
        content = config_path.read_text()
        assert "saved_backups" in content

    def test_save_preserves_values(self, tmp_path):
        """Test saved values can be loaded back."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path)

        original = GameTuneConfig(
            backup_dir="my_backups",
            auto_backup=False,
            log_level="WARNING",
            disabled_handlers=["Handler1", "Handler2"],
        )
        manager.save(original)

        loaded = manager.load()

        assert loaded.backup_dir == "my_backups"
        assert loaded.auto_backup is False
        assert loaded.log_level == "WARNING"
        assert loaded.disabled_handlers == ["Handler1", "Handler2"]

    def test_create_default(self, tmp_path):
        """Test creating default configuration file."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path)

        manager.create_default()

        assert config_path.exists()
        content = config_path.read_text()
        assert "backup_dir: backups" in content
        assert "auto_backup: true" in content
        assert "# GameTune Configuration" in content

    def test_validate_valid_config(self, tmp_path):
        """Test validation of valid configuration."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = GameTuneConfig()

        warnings = manager.validate(config)

        assert warnings == []

    def test_validate_invalid_log_level(self, tmp_path):
        """Test validation rejects invalid log level."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = GameTuneConfig(log_level="INVALID")

        with pytest.raises(ConfigValidationError) as exc_info:
            manager.validate(config)

        assert "log_level" in str(exc_info.value)

    def test_validate_unknown_handler_warning(self, tmp_path):
        """Test validation warns about unknown handlers."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = GameTuneConfig(disabled_handlers=["UnknownHandler"])

        warnings = manager.validate(config)

        assert len(warnings) == 1
        assert "UnknownHandler" in warnings[0]

    def test_validate_unknown_profile_warning(self, tmp_path):
        """Test validation warns about unknown default profile."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = GameTuneConfig(default_profile="unknown-game")

        warnings = manager.validate(config)

        assert any("unknown-game" in w for w in warnings)

    def test_get_profile_overrides(self, tmp_path):
        """Test getting profile overrides."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
profile_overrides:
  slippi-melee:
    nvidia:
      preset: minimum_latency
""")

        manager = ConfigManager(config_path)
        manager.load()

        overrides = manager.get_profile_overrides("slippi-melee")

        assert overrides is not None
        assert overrides.nvidia["preset"] == "minimum_latency"

    def test_get_profile_overrides_nonexistent(self, tmp_path):
        """Test getting overrides for profile without overrides."""
        manager = ConfigManager(tmp_path / "config.yaml")

        overrides = manager.get_profile_overrides("unknown-profile")

        assert overrides is None

    def test_is_handler_disabled(self, tmp_path):
        """Test checking if handler is disabled."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
disabled_handlers:
  - ServicesSettingsHandler
  - UpdatesSettingsHandler
""")

        manager = ConfigManager(config_path)
        manager.load()

        assert manager.is_handler_disabled("ServicesSettingsHandler") is True
        assert manager.is_handler_disabled("UpdatesSettingsHandler") is True
        assert manager.is_handler_disabled("NetworkSettingsHandler") is False

    def test_config_property_caches(self, tmp_path):
        """Test config property caches loaded config."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("backup_dir: test")

        manager = ConfigManager(config_path)

        config1 = manager.config
        config2 = manager.config

        assert config1 is config2


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_config_returns_default(self):
        """Test get_config returns default config when no file."""
        with patch.object(Path, "exists", return_value=False):
            config = get_config()

        assert config.backup_dir == "backups"

    def test_load_config_with_path(self, tmp_path):
        """Test load_config with explicit path."""
        config_path = tmp_path / "custom.yaml"
        config_path.write_text("backup_dir: custom")

        config = load_config(config_path)

        assert config.backup_dir == "custom"


class TestConfigWithProfileOverrides:
    """Tests for configuration with profile overrides."""

    def test_full_profile_override(self, tmp_path):
        """Test loading configuration with full profile overrides."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
profile_overrides:
  slippi-melee:
    nvidia:
      preset: minimum_latency
      low_latency_mode: 3
    windows:
      game_mode: true
    network:
      disable_nagle: true
    power:
      plan: ultimate_performance
    timer:
      resolution_ms: 0.5
    mouse:
      enhance_pointer_precision: false
""")

        manager = ConfigManager(config_path)
        config = manager.load()

        overrides = config.profile_overrides["slippi-melee"]
        assert overrides.nvidia["preset"] == "minimum_latency"
        assert overrides.nvidia["low_latency_mode"] == 3
        assert overrides.windows["game_mode"] is True
        assert overrides.network["disable_nagle"] is True
        assert overrides.power["plan"] == "ultimate_performance"
        assert overrides.timer["resolution_ms"] == 0.5
        assert overrides.mouse["enhance_pointer_precision"] is False


class TestConfigEdgeCases:
    """Tests for edge cases in configuration handling."""

    def test_load_with_extra_keys(self, tmp_path):
        """Test loading config with unknown keys logs warning."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
backup_dir: test
unknown_key: value
another_unknown: 123
""")

        manager = ConfigManager(config_path)
        # Should load without error, just log warning
        config = manager.load()

        assert config.backup_dir == "test"

    def test_backup_dir_is_file(self, tmp_path):
        """Test validation fails if backup_dir is a file."""
        # Create a file where backup_dir should be
        (tmp_path / "backups").write_text("not a directory")

        config_path = tmp_path / "config.yaml"
        config_path.write_text(f"backup_dir: {tmp_path / 'backups'}")

        manager = ConfigManager(config_path)
        config = manager.load()

        with pytest.raises(ConfigValidationError):
            manager.validate(config)

    def test_invalid_auto_backup_type(self, tmp_path):
        """Test validation fails for non-boolean auto_backup."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text('auto_backup: "yes"')  # String, not boolean

        manager = ConfigManager(config_path)

        with pytest.raises(ConfigValidationError) as exc_info:
            manager.load()

        assert "auto_backup" in str(exc_info.value)

    def test_invalid_disabled_handlers_type(self, tmp_path):
        """Test validation fails for non-list disabled_handlers."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("disabled_handlers: not_a_list")

        manager = ConfigManager(config_path)

        with pytest.raises(ConfigValidationError) as exc_info:
            manager.load()

        assert "disabled_handlers" in str(exc_info.value)
