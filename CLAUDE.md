# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**A.B.S.O.** (**A**daptive **B**attle **S**tation **O**ptimizer) is a CLI-first Windows 11 gaming optimization tool that:
- Auto-detects gaming hardware (GPU, CPU, monitor, etc.)
- Audits system configuration for gaming optimization issues
- Applies game-specific optimization profiles (Slippi Melee, CoD BO7, Diablo 4)
- Manages backups and rollbacks of all changes

**Target:** Single enthusiast gamer. Aggressive latency optimization with comprehensive backup/rollback for safety.

## Build & Run Commands

```bash
# Environment setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# CLI commands (requires admin elevation)
python -m abso detect              # Hardware detection
python -m abso audit               # Configuration audit
python -m abso audit --verbose     # Detailed audit
python -m abso apply <profile>     # Apply game profile
python -m abso restore latest      # Restore last backup

# Run tests
pytest tests/
pytest tests/test_detector.py -v      # Single test file
```

## Architecture

```
abso/
├── main.py              # CLI entry (Click-based)
├── core/
│   ├── detector.py      # Hardware detection (WMI, nvidia-smi, pynvml)
│   ├── auditor.py       # Scans settings, compares to optimal
│   ├── applier.py       # Applies profile settings
│   └── backup.py        # Timestamped backup/restore system
├── profiles/
│   ├── base.py          # Base profile class
│   └── <game>.py        # Game-specific profiles (data + logic)
├── settings/            # One module per settings domain
│   ├── nvidia.py        # Nvidia Profile Inspector integration
│   ├── windows.py       # Game Mode, HAGS, VBS
│   ├── registry.py      # Registry read/write
│   ├── power.py         # Power plan management (powercfg)
│   └── network.py       # Nagle, TCP optimizations
└── utils/
    ├── admin.py         # UAC elevation handling
    └── wmi_helper.py    # WMI query utilities
```

### Key Design Patterns

**Settings Handler Interface** — Each settings module implements:
```python
class SettingsHandler:
    def detect() -> dict        # Current state
    def audit() -> list[Issue]  # Problems found
    def apply(profile) -> bool  # Apply settings
    def backup() -> BackupData  # Export current
    def restore(data) -> bool   # Restore from backup
```

**Profiles** — Contain both target settings (data) and game-specific logic.

**Backup System** — Creates timestamped folders in `/backups/` with manifest.json tracking all components.

## Critical Constraints

1. **Always backup before apply** — Never modify system state without creating a restore point first
2. **Require admin elevation** — Check at startup, re-launch elevated if needed
3. **Fail gracefully** — Registry/WMI errors must not crash the tool; log and continue
4. **Idempotent operations** — Applying the same profile twice must be safe

## Technical Notes

### Nvidia Settings
- Use Nvidia Profile Inspector (`nvidiaProfileInspector.exe`) for profile management
- Some settings require driver restart or reboot to take effect
- G-Sync detection requires NVAPI or EDID parsing

### Windows Settings
- HAGS (`HwSchMode` registry key): Game-dependent, make per-profile
- VBS/Memory Integrity: Requires reboot after change
- Fullscreen optimizations: Disable per-executable via AppCompatFlags

### Registry Paths
- Game priority: `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games`
- Network: `HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{GUID}`

## Code Style

- Python 3.11+ with type hints everywhere
- Google-style docstrings for public functions
- Use `Path` objects, no hardcoded paths
- Use `logging` module with configurable verbosity

## Dependencies

- `wmi`, `pywin32` — Windows system access
- `pynvml` — Nvidia GPU queries
- `click` — CLI framework
- `rich` — Pretty terminal output
- `pyyaml` — Configuration files
