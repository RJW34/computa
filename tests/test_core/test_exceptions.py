"""Tests for custom exceptions module."""

from __future__ import annotations

import pytest

from gametune.core.exceptions import (
    GameTuneError,
    DetectionError,
    GPUDetectionError,
    CPUDetectionError,
    MonitorDetectionError,
    WMIError,
    RegistryError,
    RegistryReadError,
    RegistryWriteError,
    RegistryKeyNotFoundError,
    SettingsError,
    SettingsApplyError,
    SettingsDetectError,
    SettingsAuditError,
    ProfileError,
    ProfileNotFoundError,
    ProfileApplyError,
    BackupError,
    BackupCreateError,
    BackupRestoreError,
    BackupNotFoundError,
    BackupCorruptedError,
    ElevationRequiredError,
    AdminRequiredError,
    ExternalToolError,
    NvidiaSmiError,
    NvidiaProfileInspectorError,
    PowerCfgError,
    NetshError,
    ConfigurationError,
    ConfigLoadError,
    ConfigSaveError,
    ConfigValidationError,
    OperationTimeoutError,
    CommandTimeoutError,
)


class TestGameTuneError:
    """Tests for base GameTuneError."""

    def test_basic_message(self):
        """Test error with basic message."""
        error = GameTuneError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.details is None

    def test_message_with_details(self):
        """Test error with message and details."""
        error = GameTuneError("Something went wrong", details="More info here")

        assert str(error) == "Something went wrong: More info here"
        assert error.message == "Something went wrong"
        assert error.details == "More info here"

    def test_inheritance(self):
        """Test GameTuneError inherits from Exception."""
        error = GameTuneError("test")

        assert isinstance(error, Exception)

    def test_raise_and_catch(self):
        """Test error can be raised and caught."""
        with pytest.raises(GameTuneError) as exc_info:
            raise GameTuneError("Test error")

        assert "Test error" in str(exc_info.value)


class TestExceptionHierarchy:
    """Tests for exception inheritance hierarchy."""

    def test_detection_errors(self):
        """Test detection error hierarchy."""
        assert issubclass(DetectionError, GameTuneError)
        assert issubclass(GPUDetectionError, DetectionError)
        assert issubclass(CPUDetectionError, DetectionError)
        assert issubclass(MonitorDetectionError, DetectionError)
        assert issubclass(WMIError, DetectionError)

    def test_registry_errors(self):
        """Test registry error hierarchy."""
        assert issubclass(RegistryError, GameTuneError)
        assert issubclass(RegistryReadError, RegistryError)
        assert issubclass(RegistryWriteError, RegistryError)
        assert issubclass(RegistryKeyNotFoundError, RegistryError)

    def test_settings_errors(self):
        """Test settings error hierarchy."""
        assert issubclass(SettingsError, GameTuneError)
        assert issubclass(SettingsApplyError, SettingsError)
        assert issubclass(SettingsDetectError, SettingsError)
        assert issubclass(SettingsAuditError, SettingsError)

    def test_profile_errors(self):
        """Test profile error hierarchy."""
        assert issubclass(ProfileError, GameTuneError)
        assert issubclass(ProfileNotFoundError, ProfileError)
        assert issubclass(ProfileApplyError, ProfileError)

    def test_backup_errors(self):
        """Test backup error hierarchy."""
        assert issubclass(BackupError, GameTuneError)
        assert issubclass(BackupCreateError, BackupError)
        assert issubclass(BackupRestoreError, BackupError)
        assert issubclass(BackupNotFoundError, BackupError)
        assert issubclass(BackupCorruptedError, BackupError)

    def test_permission_errors(self):
        """Test permission error hierarchy."""
        assert issubclass(ElevationRequiredError, GameTuneError)
        assert issubclass(AdminRequiredError, ElevationRequiredError)

    def test_external_tool_errors(self):
        """Test external tool error hierarchy."""
        assert issubclass(ExternalToolError, GameTuneError)
        assert issubclass(NvidiaSmiError, ExternalToolError)
        assert issubclass(NvidiaProfileInspectorError, ExternalToolError)
        assert issubclass(PowerCfgError, ExternalToolError)
        assert issubclass(NetshError, ExternalToolError)

    def test_configuration_errors(self):
        """Test configuration error hierarchy."""
        assert issubclass(ConfigurationError, GameTuneError)
        assert issubclass(ConfigLoadError, ConfigurationError)
        assert issubclass(ConfigSaveError, ConfigurationError)
        assert issubclass(ConfigValidationError, ConfigurationError)

    def test_timeout_errors(self):
        """Test timeout error hierarchy."""
        assert issubclass(OperationTimeoutError, GameTuneError)
        assert issubclass(CommandTimeoutError, OperationTimeoutError)


class TestSpecificExceptions:
    """Tests for specific exception behaviors."""

    def test_profile_not_found_error(self):
        """Test ProfileNotFoundError with details."""
        error = ProfileNotFoundError(
            "Profile 'unknown' not found",
            details="Available: slippi-melee, cod-bo7"
        )

        assert "unknown" in str(error)
        assert "slippi-melee" in error.details

    def test_backup_corrupted_error(self):
        """Test BackupCorruptedError."""
        error = BackupCorruptedError(
            "Manifest is corrupted",
            details="JSON parse error at line 5"
        )

        assert "corrupted" in str(error).lower()
        assert "JSON" in error.details

    def test_admin_required_error(self):
        """Test AdminRequiredError."""
        error = AdminRequiredError(
            "This operation requires administrator privileges",
            details="Run as administrator"
        )

        assert "administrator" in str(error).lower()

    def test_netsh_error(self):
        """Test NetshError."""
        error = NetshError(
            "Failed to set TCP parameter",
            details="netsh returned error code 1"
        )

        assert "TCP" in str(error)

    def test_config_validation_error(self):
        """Test ConfigValidationError."""
        error = ConfigValidationError(
            "Invalid configuration",
            details="'preset' must be one of: gaming, balanced, default"
        )

        assert "Invalid" in str(error)
        assert "preset" in error.details


class TestCatchingParentExceptions:
    """Tests for catching exceptions by parent type."""

    def test_catch_detection_errors(self):
        """Test catching specific detection errors as DetectionError."""
        errors = [
            GPUDetectionError("GPU not found"),
            CPUDetectionError("CPU not found"),
            WMIError("WMI failed"),
        ]

        for error in errors:
            with pytest.raises(DetectionError):
                raise error

    def test_catch_gametune_errors(self):
        """Test catching all custom errors as GameTuneError."""
        errors = [
            ProfileNotFoundError("test"),
            BackupCorruptedError("test"),
            SettingsApplyError("test"),
            NetshError("test"),
        ]

        for error in errors:
            with pytest.raises(GameTuneError):
                raise error

    def test_catch_backup_errors(self):
        """Test catching backup errors by parent type."""
        with pytest.raises(BackupError):
            raise BackupNotFoundError("test")

        with pytest.raises(BackupError):
            raise BackupCorruptedError("test")

        with pytest.raises(BackupError):
            raise BackupCreateError("test")
