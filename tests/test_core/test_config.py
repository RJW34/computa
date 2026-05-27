"""Tests for configuration management module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from abso.core.config import (
    DEFAULT_CONFIG_NAME,
    PROFILE_OVERRIDE_HANDLER_ATTRS,
    ABSOConfig,
    ConfigManager,
    ProfileOverrides,
    get_config,
    get_handler_profile_overrides,
    load_config,
    merge_profile_override_settings,
    resolve_default_config_path,
)
from abso.core.exceptions import (
    ConfigLoadError,
    ConfigValidationError,
)


class TestABSOConfig:
    """Tests for ABSOConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ABSOConfig()

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
        config = ABSOConfig(
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
        config = ABSOConfig(
            profile_overrides={
                "slippi-melee": {
                    "nvidia": {"preset": "minimum_latency"},
                    "registry": {"game_priority": {"priority": 6}},
                    "timer": {"resolution_ms": 0.5},
                }
            }
        )

        assert "slippi-melee" in config.profile_overrides
        override = config.profile_overrides["slippi-melee"]
        assert isinstance(override, ProfileOverrides)
        assert override.nvidia == {"preset": "minimum_latency"}
        assert override.registry == {"game_priority": {"priority": 6}}
        assert override.timer == {"resolution_ms": 0.5}
        assert override.graphics == {}


class TestProfileOverrides:
    """Tests for ProfileOverrides dataclass."""

    def test_default_values(self):
        """Test default empty dictionaries."""
        overrides = ProfileOverrides()

        assert overrides.nvidia == {}
        assert overrides.windows == {}
        assert overrides.registry == {}
        assert overrides.graphics == {}
        assert overrides.network == {}
        assert overrides.power == {}
        assert overrides.timer == {}
        assert overrides.mouse == {}

    def test_custom_values(self):
        """Test with custom override values."""
        overrides = ProfileOverrides(
            nvidia={"preset": "low_latency"},
            registry={"system_responsiveness": 10},
            graphics={"disable_mpo": True},
            timer={"resolution_ms": 1.0},
        )

        assert overrides.nvidia["preset"] == "low_latency"
        assert overrides.registry["system_responsiveness"] == 10
        assert overrides.graphics["disable_mpo"] is True
        assert overrides.timer["resolution_ms"] == 1.0

    def test_handler_routing_targets_declared_override_fields(self):
        """Handler routing should not drift from the ProfileOverrides schema."""
        declared_fields = set(ProfileOverrides.__dataclass_fields__)

        assert set(PROFILE_OVERRIDE_HANDLER_ATTRS.values()) == declared_fields
        assert PROFILE_OVERRIDE_HANDLER_ATTRS["RegistrySettingsHandler"] == "registry"

    def test_get_handler_profile_overrides_routes_known_handlers(self):
        overrides = ProfileOverrides(
            registry={"game_priority": {"priority": 6}},
        )

        routed = get_handler_profile_overrides(overrides, "RegistrySettingsHandler")

        assert routed == {"game_priority": {"priority": 6}}
        assert get_handler_profile_overrides(overrides, "UnknownHandler") == {}

    def test_merge_profile_override_settings_deep_merges_without_shared_state(self):
        settings = {
            "game_priority": {
                "gpu_priority": 8,
                "priority": 2,
                "scheduling_category": "Medium",
            },
            "system_responsiveness": 20,
        }
        overrides = ProfileOverrides(
            registry={
                "game_priority": {
                    "priority": 6,
                },
            }
        )

        merged = merge_profile_override_settings(
            settings,
            "RegistrySettingsHandler",
            overrides,
        )
        merged["game_priority"]["gpu_priority"] = 1

        assert merged["game_priority"]["priority"] == 6
        assert merged["game_priority"]["scheduling_category"] == "Medium"
        assert settings["game_priority"]["gpu_priority"] == 8


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

        config = ABSOConfig(backup_dir="saved_backups")
        manager.save(config)

        assert config_path.exists()
        content = config_path.read_text()
        assert "saved_backups" in content

    def test_save_preserves_values(self, tmp_path):
        """Test saved values can be loaded back."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path)

        original = ABSOConfig(
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
        assert "# A.B.S.O. Configuration" in content

    def test_validate_valid_config(self, tmp_path):
        """Test validation of valid configuration."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = ABSOConfig()

        warnings = manager.validate(config)

        assert warnings == []

    def test_validate_invalid_log_level(self, tmp_path):
        """Test validation rejects invalid log level."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = ABSOConfig(log_level="INVALID")

        with pytest.raises(ConfigValidationError) as exc_info:
            manager.validate(config)

        assert "log_level" in str(exc_info.value)

    def test_validate_unknown_handler_warning(self, tmp_path):
        """Test validation warns about unknown handlers."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = ABSOConfig(disabled_handlers=["UnknownHandler"])

        warnings = manager.validate(config)

        assert len(warnings) == 1
        assert "UnknownHandler" in warnings[0]

    def test_validate_unknown_profile_warning(self, tmp_path):
        """Test validation warns about unknown default profile."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = ABSOConfig(default_profile="unknown-game")

        warnings = manager.validate(config)

        assert any("unknown-game" in w for w in warnings)

    def test_validate_default_profile_accepts_known_alias(self, tmp_path):
        """Default profile validation should accept aliases that resolve."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = ABSOConfig(default_profile="rivals2")

        warnings = manager.validate(config)

        assert not any("default_profile" in warning for warning in warnings)

    def test_validate_profile_override_accepts_known_alias(self, tmp_path):
        """Profile override validation should accept retired aliases that resolve."""
        manager = ConfigManager(tmp_path / "config.yaml")
        config = ABSOConfig(
            profile_overrides={
                "rivals2": {
                    "nvidia": {
                        "preset": "minimum_latency",
                    },
                },
            }
        )

        warnings = manager.validate(config)

        assert not any("rivals2" in warning for warning in warnings)

    def test_get_profile_overrides(self, tmp_path):
        """Test getting profile overrides."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
profile_overrides:
  slippi-melee:
    nvidia:
      preset: minimum_latency
    registry:
      game_priority:
        priority: 6
""")

        manager = ConfigManager(config_path)
        manager.load()

        overrides = manager.get_profile_overrides("slippi-melee")

        assert overrides is not None
        assert overrides.nvidia["preset"] == "minimum_latency"
        assert overrides.registry["game_priority"]["priority"] == 6

    def test_get_profile_overrides_resolves_alias_to_canonical_profile(self, tmp_path):
        """Alias lookups should find overrides stored under the canonical profile id."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
profile_overrides:
  rivals2-offline:
    nvidia:
      preset: minimum_latency
""")

        manager = ConfigManager(config_path)
        manager.load()

        overrides = manager.get_profile_overrides("rivals2")

        assert overrides is not None
        assert overrides.nvidia["preset"] == "minimum_latency"

    def test_get_profile_overrides_resolves_canonical_to_alias_profile(self, tmp_path):
        """Canonical lookups should find overrides stored under a known alias."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
profile_overrides:
  rivals2:
    nvidia:
      preset: minimum_latency
""")

        manager = ConfigManager(config_path)
        manager.load()

        overrides = manager.get_profile_overrides("rivals2-offline")

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

    def test_default_path_prefers_cwd_config(self, tmp_path, monkeypatch):
        """Source checkouts should continue using the working tree config."""
        local_root = tmp_path / "local"
        cwd = tmp_path / "repo"
        cwd.mkdir()
        cwd_config = cwd / DEFAULT_CONFIG_NAME
        cwd_config.write_text("backup_dir: repo_backups", encoding="utf-8")
        installed_config = local_root / "AdaptiveBattleStationOptimizer" / DEFAULT_CONFIG_NAME
        installed_config.parent.mkdir(parents=True)
        installed_config.write_text("backup_dir: installed_backups", encoding="utf-8")

        monkeypatch.chdir(cwd)
        with patch.dict("os.environ", {"LOCALAPPDATA": str(local_root)}, clear=False):
            manager = ConfigManager()

        assert manager.config_path == cwd_config

    def test_default_path_falls_back_to_installed_config(self, tmp_path, monkeypatch):
        """Installed tray/GUI runs from LocalAppData must still see machine overrides."""
        local_root = tmp_path / "local"
        work_dir = tmp_path / "installed_workdir"
        work_dir.mkdir()
        installed_config = local_root / "AdaptiveBattleStationOptimizer" / DEFAULT_CONFIG_NAME
        installed_config.parent.mkdir(parents=True)
        installed_config.write_text(
            """
profile_overrides:
  overwatch2-gsync-hdr-capture:
    graphics:
      disable_mpo: true
""",
            encoding="utf-8",
        )

        monkeypatch.chdir(work_dir)
        with patch.dict("os.environ", {"LOCALAPPDATA": str(local_root)}, clear=False):
            manager = ConfigManager()
            config = manager.load()

        assert manager.config_path == installed_config
        assert (
            config.profile_overrides[
                "overwatch2-gsync-hdr-capture"
            ].graphics["disable_mpo"]
            is True
        )

    def test_default_path_honors_env_override(self, tmp_path, monkeypatch):
        """ABSO_CONFIG should pin config discovery for support/debug sessions."""
        env_config = tmp_path / "pinned.yaml"
        env_config.write_text("backup_dir: pinned", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with patch.dict("os.environ", {"ABSO_CONFIG": str(env_config)}, clear=False):
            assert resolve_default_config_path() == env_config
            assert ConfigManager().config_path == env_config


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
    registry:
      game_priority:
        priority: 6
    graphics:
      disable_mpo: true
      disable_auto_color_management: true
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
        assert overrides.registry["game_priority"]["priority"] == 6
        assert overrides.graphics["disable_mpo"] is True
        assert overrides.graphics["disable_auto_color_management"] is True
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

    def test_invalid_profile_overrides_type(self, tmp_path):
        """Profile overrides must be keyed by profile id."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
profile_overrides:
  - slippi-melee
""")

        manager = ConfigManager(config_path)

        with pytest.raises(ConfigValidationError) as exc_info:
            manager.load()

        assert "profile_overrides" in str(exc_info.value)

    def test_invalid_profile_override_section_name(self, tmp_path):
        """Unknown override sections should fail before dataclass parsing."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
profile_overrides:
  slippi-melee:
    RegistrySettingsHandler:
      game_priority:
        priority: 6
""")

        manager = ConfigManager(config_path)

        with pytest.raises(ConfigValidationError) as exc_info:
            manager.load()

        assert "Unknown profile override section" in str(exc_info.value)
        assert "RegistrySettingsHandler" in str(exc_info.value)
        assert "registry" in exc_info.value.details

    def test_invalid_profile_override_section_type(self, tmp_path):
        """Each override section must be a setting map."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
profile_overrides:
  slippi-melee:
    graphics: true
""")

        manager = ConfigManager(config_path)

        with pytest.raises(ConfigValidationError) as exc_info:
            manager.load()

        assert "profile_overrides.slippi-melee.graphics" in str(exc_info.value)
