"""Custom exceptions for A.B.S.O. (Adaptive Battle Station Optimizer).

This module defines a hierarchy of exceptions for specific error conditions,
enabling more precise error handling and better error messages.
"""

from __future__ import annotations


class ABSOError(Exception):
    """Base exception for all ABSO errors."""

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


# Detection Errors
class DetectionError(ABSOError):
    """Base error for hardware/software detection failures."""
    pass


class GPUDetectionError(DetectionError):
    """Failed to detect GPU information."""
    pass


class CPUDetectionError(DetectionError):
    """Failed to detect CPU information."""
    pass


class MonitorDetectionError(DetectionError):
    """Failed to detect monitor information."""
    pass


class WMIError(DetectionError):
    """WMI query failed or WMI is unavailable."""
    pass


# Registry Errors
class RegistryError(ABSOError):
    """Base error for Windows registry operations."""
    pass


class RegistryReadError(RegistryError):
    """Failed to read from Windows registry."""
    pass


class RegistryWriteError(RegistryError):
    """Failed to write to Windows registry."""
    pass


class RegistryKeyNotFoundError(RegistryError):
    """Registry key does not exist."""
    pass


# Settings Errors
class SettingsError(ABSOError):
    """Base error for settings operations."""
    pass


class SettingsApplyError(SettingsError):
    """Failed to apply settings."""
    pass


class SettingsDetectError(SettingsError):
    """Failed to detect current settings."""
    pass


class SettingsAuditError(SettingsError):
    """Failed to audit settings."""
    pass


# Profile Errors
class ProfileError(ABSOError):
    """Base error for profile operations."""
    pass


class ProfileNotFoundError(ProfileError):
    """Requested profile does not exist."""
    pass


class ProfileApplyError(ProfileError):
    """Failed to apply profile."""
    pass


# Backup Errors
class BackupError(ABSOError):
    """Base error for backup/restore operations."""
    pass


class BackupCreateError(BackupError):
    """Failed to create backup."""
    pass


class BackupRestoreError(BackupError):
    """Failed to restore from backup."""
    pass


class BackupNotFoundError(BackupError):
    """Requested backup does not exist."""
    pass


class BackupCorruptedError(BackupError):
    """Backup data is corrupted or invalid."""
    pass


# Permission Errors
class ElevationRequiredError(ABSOError):
    """Operation requires elevated privileges."""
    pass


class AdminRequiredError(ElevationRequiredError):
    """Operation requires administrator privileges."""
    pass


# External Tool Errors
class ExternalToolError(ABSOError):
    """Base error for external tool operations."""
    pass


class NvidiaSmiError(ExternalToolError):
    """nvidia-smi command failed or is unavailable."""
    pass


class NvidiaProfileInspectorError(ExternalToolError):
    """Nvidia Profile Inspector operation failed."""
    pass


class PowerCfgError(ExternalToolError):
    """powercfg command failed."""
    pass


class NetshError(ExternalToolError):
    """netsh command failed."""
    pass


# Configuration Errors
class ConfigurationError(ABSOError):
    """Base error for configuration operations."""
    pass


class ConfigLoadError(ConfigurationError):
    """Failed to load configuration file."""
    pass


class ConfigSaveError(ConfigurationError):
    """Failed to save configuration file."""
    pass


class ConfigValidationError(ConfigurationError):
    """Configuration file is invalid."""
    pass


# Timeout Errors
class OperationTimeoutError(ABSOError):
    """Operation timed out."""
    pass


class CommandTimeoutError(OperationTimeoutError):
    """External command timed out."""
    pass
