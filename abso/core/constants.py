"""Constants for computa.

This module centralizes registry paths, Windows API constants, and other
magic values used throughout the codebase.
"""

from __future__ import annotations

# =============================================================================
# Registry Root Constants
# =============================================================================

# Base paths for common Windows registry locations
class RegistryPaths:
    """Windows registry path constants.

    These are the subkey paths (without the hive prefix).
    Use with winreg.HKEY_LOCAL_MACHINE or winreg.HKEY_CURRENT_USER.
    """

    # Multimedia and Audio
    MULTIMEDIA_SYSTEM_PROFILE = (
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
    )
    MULTIMEDIA_TASKS = (
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks"
    )
    MULTIMEDIA_GAMES_TASK = (
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
    )
    MULTIMEDIA_AUDIO_TASK = (
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Audio"
    )

    # Graphics and Gaming
    GAME_BAR = r"Software\Microsoft\GameBar"
    GAME_DVR = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
    GAME_CONFIG_STORE = r"System\GameConfigStore"
    GRAPHICS_DRIVERS = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
    DWM = r"SOFTWARE\Microsoft\Windows\Dwm"
    DWM_USER = r"Software\Microsoft\Windows\DWM"

    # Security
    VBS = r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity"

    # Process and Priority
    IFEO = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
    PRIORITY_CONTROL = r"SYSTEM\CurrentControlSet\Control\PriorityControl"
    APPCOMPAT_LAYERS = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"

    # Network
    TCPIP_PARAMETERS = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
    TCPIP_INTERFACES = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"

    # Memory
    MEMORY_MANAGEMENT = r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"

    # Visual Effects
    VISUAL_EFFECTS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
    EXPLORER_ADVANCED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    DESKTOP = r"Control Panel\Desktop"
    WINDOW_METRICS = r"Control Panel\Desktop\WindowMetrics"
    PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

    # Input
    MOUSE = r"Control Panel\Mouse"

    # Audio
    AUDIO = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Audio"
    MMDEVICES_RENDER = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"

    # Windows Update
    DELIVERY_OPTIMIZATION = r"SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config"
    WINDOWS_UPDATE_UX = r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
    WINDOWS_UPDATE_AU = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"


# =============================================================================
# Registry Value Names
# =============================================================================

class RegistryValues:
    """Common registry value names."""

    # Game Mode
    GAME_MODE_ENABLED = "AutoGameModeEnabled"
    GAME_BAR_ENABLED = "AppCaptureEnabled"
    GAME_DVR_ENABLED = "GameDVR_Enabled"

    # HAGS (Hardware Accelerated GPU Scheduling)
    HAGS_ENABLED = "HwSchMode"

    # VBS
    VBS_ENABLED = "Enabled"

    # Memory
    LARGE_SYSTEM_CACHE = "LargeSystemCache"
    DISABLE_PAGING_EXECUTIVE = "DisablePagingExecutive"

    # Multimedia
    SYSTEM_RESPONSIVENESS = "SystemResponsiveness"
    NETWORK_THROTTLING_INDEX = "NetworkThrottlingIndex"

    # Games Task
    GPU_PRIORITY = "GPU Priority"
    PRIORITY = "Priority"
    SCHEDULING_CATEGORY = "Scheduling Category"
    SFIO_PRIORITY = "SFIO Priority"

    # Network
    TCP_ACK_FREQUENCY = "TcpAckFrequency"
    TCP_NO_DELAY = "TcpNoDelay"
    NAGLING_DISABLED = "TcpDelAckTicks"

    # Mouse
    MOUSE_SPEED = "MouseSpeed"
    MOUSE_THRESHOLD1 = "MouseThreshold1"
    MOUSE_THRESHOLD2 = "MouseThreshold2"


# =============================================================================
# Default Values
# =============================================================================

class Defaults:
    """Legacy default/target values for settings."""

    # System Responsiveness (ABSO legacy target = 10, Windows desktop default often = 20)
    SYSTEM_RESPONSIVENESS_GAMING = 10
    SYSTEM_RESPONSIVENESS_DEFAULT = 20

    # Network Throttling (-1 = disabled, 10 = default in Mbps)
    NETWORK_THROTTLING_DISABLED = 0xFFFFFFFF  # -1 as unsigned
    NETWORK_THROTTLING_DEFAULT = 10

    # GPU Priority (8 = high, 1 = normal)
    GPU_PRIORITY_HIGH = 8
    GPU_PRIORITY_NORMAL = 1

    # Scheduling Categories
    SCHEDULING_HIGH = "High"
    SCHEDULING_MEDIUM = "Medium"
    SCHEDULING_LOW = "Low"

    # Mouse (for raw input)
    MOUSE_SPEED_RAW = "0"
    MOUSE_THRESHOLD_DISABLED = "0"


# =============================================================================
# AppCompat Flags
# =============================================================================

class AppCompatFlags:
    """Application compatibility flags for registry."""

    # Fullscreen optimizations
    DISABLE_FULLSCREEN_OPT = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"
    HIGH_DPI_AWARE = "~ HIGHDPIAWARE"

    # Combined flags for gaming
    GAMING_FLAGS = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE HIGHDPIAWARE"


# =============================================================================
# Error Messages
# =============================================================================

class ErrorMessages:
    """Common error message templates.

    Use .format() or f-strings to fill in placeholders.
    """

    # Permission errors
    PERMISSION_DENIED = "Permission denied: {error}"
    PERMISSION_DENIED_ADMIN = "Permission denied. Run as administrator. ({error})"
    ADMIN_REQUIRED = "This operation requires administrator privileges"
    SOME_FEATURES_REQUIRE_ADMIN = "Some features require admin privileges to work correctly."
    ELEVATED_PRIVILEGES_REQUIRED = "Some optimizations require elevated privileges."

    # Registry errors
    REGISTRY_KEY_NOT_FOUND = "Registry key not found: {key_path}"
    REGISTRY_VALUE_NOT_FOUND = "Registry value not found: {key_path}\\{value_name}"
    REGISTRY_READ_FAILED = "Failed to read registry: {key_path}\\{value_name}"
    REGISTRY_WRITE_FAILED = "Failed to write registry: {key_path}\\{value_name}"

    # Detection errors
    DETECTION_FAILED = "Failed to detect {component}: {error}"
    WMI_QUERY_FAILED = "WMI query failed: {error}"

    # Apply errors
    APPLY_FAILED = "Failed to apply {setting}: {error}"
    BACKUP_REQUIRED = "Backup required before applying changes"

    # Restore errors
    RESTORE_FAILED = "Failed to restore {component}: {error}"
    BACKUP_NOT_FOUND = "Backup not found: {backup_id}"
    BACKUP_CORRUPTED = "Backup is corrupted: {backup_id}"

    # General
    OPERATION_FAILED = "Operation failed: {error}"
    REBOOT_REQUIRED = "A system reboot is required for changes to take effect"
