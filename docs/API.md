# A.B.S.O. API Documentation

**Adaptive Battle Station Optimizer**

This document provides detailed API documentation for A.B.S.O.'s core modules and interfaces.

## Table of Contents

- [Core Modules](#core-modules)
  - [HardwareDetector](#hardwaredetector)
  - [ConfigurationAuditor](#configurationauditor)
  - [ProfileApplier](#profileapplier)
  - [BackupManager](#backupmanager)
- [Settings Handlers](#settings-handlers)
  - [SettingsHandler Interface](#settingshandler-interface)
  - [Available Handlers](#available-handlers)
- [Profiles](#profiles)
  - [BaseProfile](#baseprofile)
  - [Available Profiles](#available-profiles)
- [Exceptions](#exceptions)
- [Data Models](#data-models)

---

## Core Modules

### HardwareDetector

**Module:** `abso.core.detector`

Detects gaming hardware components including GPU, CPU, RAM, monitors, and Windows version.

#### Class: `HardwareDetector`

```python
from abso.core.detector import HardwareDetector

detector = HardwareDetector()
```

#### Methods

##### `detect_all() -> dict[str, Any]`

Detects all hardware components.

**Returns:** Dictionary containing:
- `gpu`: GPU information or `None`
- `cpu`: CPU information or `None`
- `ram`: RAM information or `None`
- `monitors`: List of monitor information
- `windows_version`: Windows version info or `None`

**Example:**
```python
hardware = detector.detect_all()
print(f"GPU: {hardware['gpu']['name']}")
print(f"CPU: {hardware['cpu']['name']}")
```

##### `detect_gpu() -> dict[str, Any] | None`

Detects GPU information. Tries nvidia-smi first, falls back to WMI.

**Returns:** Dictionary containing:
- `name`: GPU model name
- `driver_version`: Driver version string
- `vram_mb`: VRAM in megabytes

##### `detect_cpu() -> dict[str, Any] | None`

Detects CPU information using WMI.

**Returns:** Dictionary containing:
- `name`: CPU model name
- `cores`: Physical core count
- `threads`: Logical processor count
- `max_clock_mhz`: Maximum clock speed

##### `detect_ram() -> dict[str, Any] | None`

Detects total system RAM.

**Returns:** Dictionary containing:
- `total_gb`: Total RAM in gigabytes

##### `detect_monitors() -> list[dict[str, Any]]`

Detects connected monitors with VRR/G-Sync capability.

**Returns:** List of dictionaries containing:
- `name`: Monitor name
- `adapter`: Graphics adapter name
- `resolution`: Resolution string (e.g., "2560x1440")
- `refresh_rate`: Current refresh rate in Hz
- `is_primary`: Whether this is the primary display
- `vrr_supported`: VRR support status
- `vrr_type`: Type of VRR (e.g., "freesync", "gsync")
- `vrr_range`: VRR frequency range

##### `detect_windows_version() -> dict[str, Any] | None`

Detects Windows version information.

**Returns:** Dictionary containing:
- `display_version`: Display version (e.g., "23H2")
- `build`: Build number

---

### ConfigurationAuditor

**Module:** `abso.core.auditor`

Audits system configuration for gaming optimization issues.

#### Class: `ConfigurationAuditor`

```python
from abso.core.auditor import ConfigurationAuditor

auditor = ConfigurationAuditor()
```

#### Methods

##### `audit_all() -> list[Issue]`

Runs all configuration audits across all settings handlers.

**Returns:** List of `Issue` objects sorted by severity (critical first).

**Example:**
```python
issues = auditor.audit_all()
for issue in issues:
    print(f"[{issue.severity}] {issue.title}")
    print(f"  Current: {issue.current_value}")
    print(f"  Optimal: {issue.optimal_value}")
```

##### `audit_category(category: str) -> list[Issue]`

Runs audit for a specific category.

**Parameters:**
- `category`: One of: `windows`, `power`, `registry`, `nvidia`, `timer`, `mouse`, `graphics`, `services`, `tasks`, `memory`, `network`, `visual`, `storage`, `audio`, `updates`

**Returns:** List of `Issue` objects for that category.

**Raises:** `ValueError` if category is unknown.

---

### ProfileApplier

**Module:** `abso.core.applier`

Applies game optimization profiles to the system.

#### Class: `ProfileApplier`

```python
from abso.core.applier import ProfileApplier

applier = ProfileApplier()
```

#### Class Attributes

- `PROFILES`: Dictionary mapping profile names to profile classes

#### Methods

##### `apply_profile(profile_name: str) -> ApplyResult`

Applies a game optimization profile.

**Parameters:**
- `profile_name`: Name of the profile (e.g., "slippi-melee", "cod-bo7")

**Returns:** `ApplyResult` dataclass containing:
- `success`: Boolean indicating overall success
- `error`: Error message if failed
- `requires_reboot`: Whether a reboot is required
- `in_game_settings`: Whether profile has in-game recommendations
- `applied_settings`: List of successfully applied handlers
- `failed_settings`: List of failed handlers with errors

**Example:**
```python
result = applier.apply_profile("slippi-melee")
if result.success:
    print("Profile applied successfully!")
    if result.requires_reboot:
        print("Please reboot for changes to take effect.")
else:
    print(f"Failed: {result.error}")
```

##### `generate_report(profile_name: str, output_dir: Path) -> Path`

Generates an in-game settings report for a profile.

**Parameters:**
- `profile_name`: Name of the profile
- `output_dir`: Directory to save the report

**Returns:** Path to the generated markdown report.

##### `list_profiles() -> list[dict[str, Any]]`

Lists all available profiles.

**Returns:** List of dictionaries containing:
- `id`: Profile identifier
- `display_name`: Human-readable name
- `description`: Profile description
- `optimization_target`: What the profile optimizes for

---

### BackupManager

**Module:** `abso.core.backup`

Manages backup and restore of system settings.

#### Class: `BackupManager`

```python
from abso.core.backup import BackupManager
from pathlib import Path

manager = BackupManager(Path("./backups"))
```

#### Methods

##### `create_backup() -> str`

Creates a new backup of current settings.

**Returns:** Backup ID (timestamp string, e.g., "2024-01-15_143052").

**Example:**
```python
backup_id = manager.create_backup()
print(f"Backup created: {backup_id}")
```

##### `restore_backup(backup_id: str) -> None`

Restores settings from a backup.

**Parameters:**
- `backup_id`: Backup ID or "latest" for most recent backup

**Raises:**
- `BackupNotFoundError`: If backup doesn't exist
- `BackupCorruptedError`: If backup is corrupted

##### `list_backups() -> list[dict[str, Any]]`

Lists all available backups.

**Returns:** List of dictionaries (newest first) containing:
- `id`: Backup ID
- `created_at`: ISO timestamp
- `components`: List of backed up handler names

##### `delete_backup(backup_id: str) -> None`

Deletes a backup.

**Parameters:**
- `backup_id`: Backup ID to delete

**Raises:** `BackupNotFoundError` if backup doesn't exist.

---

## Settings Handlers

### SettingsHandler Interface

**Module:** `abso.settings.base`

Abstract base class that all settings handlers must implement.

```python
from abc import ABC, abstractmethod
from abso.settings.base import SettingsHandler

class CustomHandler(SettingsHandler):
    def detect(self) -> dict[str, Any]:
        """Detect current state of settings."""
        pass

    def audit(self) -> list[Issue]:
        """Audit settings for optimization issues."""
        pass

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply settings from a profile."""
        pass

    def backup(self) -> dict[str, Any]:
        """Export current settings for backup."""
        pass

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore settings from backup data."""
        pass
```

### Available Handlers

| Handler | Module | Description |
|---------|--------|-------------|
| `WindowsSettingsHandler` | `abso.settings.windows` | Game Mode, Game Bar, HAGS, VBS |
| `PowerSettingsHandler` | `abso.settings.power` | Power plan management |
| `RegistrySettingsHandler` | `abso.settings.registry` | Game priority, scheduling |
| `NvidiaSettingsHandler` | `abso.settings.nvidia` | Nvidia Profile Inspector |
| `TimerSettingsHandler` | `abso.settings.timer` | Windows timer resolution |
| `MouseSettingsHandler` | `abso.settings.mouse` | Mouse acceleration, raw input |
| `GraphicsSettingsHandler` | `abso.settings.graphics` | Fullscreen optimizations |
| `ServicesSettingsHandler` | `abso.settings.services` | Background services |
| `TasksSettingsHandler` | `abso.settings.tasks` | Scheduled tasks |
| `MemorySettingsHandler` | `abso.settings.memory` | Virtual memory, paging |
| `NetworkSettingsHandler` | `abso.settings.network` | Nagle, TCP settings |
| `VisualSettingsHandler` | `abso.settings.visual` | Visual effects |
| `StorageSettingsHandler` | `abso.settings.storage` | Disk optimization |
| `AudioSettingsHandler` | `abso.settings.audio` | Audio latency |
| `UpdatesSettingsHandler` | `abso.settings.updates` | Windows Update |

---

## Profiles

### BaseProfile

**Module:** `abso.profiles.base`

Abstract base class for game profiles.

#### Methods

##### `get_handlers() -> list[SettingsHandler]`

Returns list of settings handlers for this profile.

##### `get_settings(handler_name: str) -> dict[str, Any]`

Gets settings for a specific handler.

##### `get_in_game_settings() -> list[dict[str, Any]]`

Gets in-game settings recommendations.

##### `has_in_game_settings() -> bool`

Returns whether profile has in-game recommendations.

##### `generate_in_game_report() -> str`

Generates markdown report of in-game settings.

### Available Profiles

| Profile ID | Class | Game |
|------------|-------|------|
| `slippi-melee` | `SlippiMeleeProfile` | Super Smash Bros. Melee (Slippi) |
| `cod-bo7` | `CodBo7Profile` | Call of Duty: Black Ops 7 |
| `diablo4` | `Diablo4Profile` | Diablo 4 |
| `rivals2` | `Rivals2Profile` | Rivals of Aether 2 |

---

## Exceptions

**Module:** `abso.core.exceptions`

### Exception Hierarchy

```
ABSOError (base)
├── DetectionError
│   ├── GPUDetectionError
│   ├── CPUDetectionError
│   ├── MonitorDetectionError
│   └── WMIError
├── RegistryError
│   ├── RegistryReadError
│   ├── RegistryWriteError
│   └── RegistryKeyNotFoundError
├── SettingsError
│   ├── SettingsApplyError
│   ├── SettingsDetectError
│   └── SettingsAuditError
├── ProfileError
│   ├── ProfileNotFoundError
│   └── ProfileApplyError
├── BackupError
│   ├── BackupCreateError
│   ├── BackupRestoreError
│   ├── BackupNotFoundError
│   └── BackupCorruptedError
├── PermissionError
│   └── AdminRequiredError
├── ExternalToolError
│   ├── NvidiaSmiError
│   ├── NvidiaProfileInspectorError
│   ├── PowerCfgError
│   └── NetshError
├── ConfigurationError
│   ├── ConfigLoadError
│   ├── ConfigSaveError
│   └── ConfigValidationError
└── TimeoutError
    └── CommandTimeoutError
```

### Usage Example

```python
from abso.core.exceptions import ProfileNotFoundError, BackupError

try:
    applier.apply_profile("unknown-game")
except ProfileNotFoundError as e:
    print(f"Profile not found: {e.message}")
    print(f"Available: {e.details}")
except BackupError as e:
    print(f"Backup operation failed: {e}")
```

---

## Data Models

### Issue

**Module:** `abso.core.models`

Represents a configuration issue found during audit.

```python
@dataclass
class Issue:
    title: str
    severity: Literal["critical", "warning", "info"]
    current_value: str
    optimal_value: str
    explanation: str | None = None
    category: str = "general"
```

### ApplyResult

**Module:** `abso.core.applier`

Result of applying a profile.

```python
@dataclass
class ApplyResult:
    success: bool
    error: str | None = None
    requires_reboot: bool = False
    in_game_settings: bool = False
    applied_settings: list[str] = field(default_factory=list)
    failed_settings: list[str] = field(default_factory=list)
```

---

## CLI Commands

ABSO provides a command-line interface:

```bash
# Hardware detection
python -m abso detect

# Configuration audit
python -m abso audit
python -m abso audit --verbose

# List profiles
python -m abso profiles

# Apply a profile
python -m abso apply slippi-melee
python -m abso apply cod-bo7 --no-backup

# Restore from backup
python -m abso restore latest
python -m abso restore 2024-01-15_143052

# Generate in-game settings report
python -m abso report slippi-melee

# Interactive mode
python -m abso
```
