# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**A.B.S.O.** (**A**daptive **B**attle **S**tation **O**ptimizer) is a CLI-first Windows 11 gaming optimization tool that:
- Auto-detects gaming hardware (GPU, CPU, monitor, etc.)
- Audits system configuration for gaming optimization issues
- Applies game-specific optimization profiles
- Manages backups and rollbacks of all changes
- Includes a system tray app for easy profile switching

**Target:** Single enthusiast gamer. Aggressive latency optimization with comprehensive backup/rollback for safety.

## Available Profiles

- **slippi-melee** / **slippi-melee-console-parity** / **slippi-melee-universal** — Slippi Dolphin (SSBM) variants
- **rivals2-offline** / **rivals2-online** — Rivals 2 no-sync offline vs rollback-safe online
- **rivals2-gsync** / **rivals2-online-gsync** — Rivals 2 VRR lanes (offline vs online)
- **fortnite** / **fortnite-hdr** — Fortnite Reflex path
- **marvel-rivals-sdr** / **marvel-rivals-hdr** — Marvel Rivals Reflex path
- **overwatch2** / **overwatch2-hdr** — OW2 no-sync lanes (SDR / HDR) for absolute minimum latency
- **overwatch2-gsync** / **overwatch2-gsync-hdr** — Strict fullscreen G-SYNC lanes (SDR / HDR)
- **overwatch2-gsync-capture** / **overwatch2-gsync-hdr-capture** — Borderless OW2 G-SYNC for capture/overlay workflows
- **diablo4** / **diablo4-sdr** — Diablo 4 (balanced ARPG)
- **pokemon-auto-chess** — Browser game optimization
- **pacdeluxe** — Tauri client optimization
- **productivity** — Non-gaming desktop work
- **ryujinx-ssbu** — Switch emulation (SSBU)

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
python -m abso apply <profile> --no-backup  # Skip backup (not recommended)
python -m abso restore latest      # Restore last backup
python -m abso profiles            # List available profiles

# Run tests
pytest tests/
pytest tests/test_detector.py -v      # Single test file

# Tray app (PowerShell, requires admin)
powershell -File abso\tray\ABSO-Tray.ps1
```

## Architecture

```
abso/
├── main.py              # CLI entry (Click-based)
├── core/
│   ├── detector.py      # Hardware detection (WMI, nvidia-smi, pynvml)
│   ├── auditor.py       # Scans settings, compares to optimal
│   ├── applier.py       # Applies profile settings with validation pipeline
│   ├── backup.py        # Timestamped backup/restore system
│   ├── linter.py        # ProfileLinter - static validation
│   ├── rollback_guard.py # RollbackGuard - online netcode protection
│   ├── stability_gate.py # StabilityGate - gated aggressive settings
│   └── ...              # Other validation subsystems
├── profiles/
│   ├── base.py          # Base profile class with validation metadata
│   └── <game>.py        # Game-specific profiles (data + logic)
├── settings/            # One module per settings domain (15 handlers)
│   ├── nvidia.py        # Nvidia Profile Inspector integration
│   ├── windows.py       # Game Mode, HAGS, VBS
│   ├── registry.py      # Registry read/write with validation
│   ├── power.py         # Power plan management (powercfg)
│   ├── network.py       # Nagle, TCP optimizations
│   ├── services.py      # Windows services control
│   ├── mouse.py         # Mouse acceleration settings
│   └── ...              # 8 more handlers
├── tray/
│   ├── ABSO-Tray.ps1    # System tray app (PowerShell)
│   └── ABSO-Watcher.ps1 # Game process monitor
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
    def apply(settings) -> dict # Apply settings, returns result
    def backup() -> dict        # Export current state
    def restore(data) -> bool   # Restore from backup
```

**Profiles** — Contain both target settings (data) and game-specific logic. Include validation metadata:
- `is_online_profile` — Whether profile is safe for online play
- `is_emulator_profile` — Whether this is for an emulator
- `optimization_target` — What the profile optimizes for

**Backup System** — Creates timestamped folders in `/backups/` with manifest.json tracking all components. Every state-mutating settings handler is backed up; the canonical list is `_get_backup_handlers()` in `abso/core/backup.py`.

**Validation Pipeline** — Profile application runs through:
1. ProfileLinter (static validation)
2. MultiMonitorDetector (environment checks)
3. RollbackGuard (online netcode protection)
4. StabilityGate (gate aggressive settings)
5. NetworkScopeManager (per-game network tuning)

## Critical Constraints

1. **Always backup before apply** — Never modify system state without creating a restore point first (use `--no-backup` flag only if you understand the risks)
2. **Require admin elevation** — Check at startup, re-launch elevated if needed
3. **Fail gracefully** — Registry/WMI errors must not crash the tool; log and continue
4. **Idempotent operations** — Applying the same profile twice must be safe
5. **Online safety** — Profiles with `is_online_profile=True` have stricter validation

## Technical Notes

### Nvidia Settings
- Use Nvidia Profile Inspector (`nvidiaProfileInspector.exe`) for profile management
- Some settings require driver restart or reboot to take effect
- G-Sync detection requires NVAPI or EDID parsing
- LLM Ultra can cause rollback contention in online games

### Windows Settings
- HAGS (`HwSchMode` registry key): Game-dependent, make per-profile
- VBS/Memory Integrity: Requires reboot after change
- Fullscreen optimizations: Disable per-executable via AppCompatFlags

### Registry Paths
- Game priority: `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games`
- Network: `HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{GUID}`
- Scheduler: `HKLM\SYSTEM\CurrentControlSet\Control\PriorityControl\Win32PrioritySeparation`

### Tray App
- Requires admin elevation (auto-elevates via UAC; uses `-ExecutionPolicy Bypass` to re-launch under a single-user trust model)
- Single instance enforced via named mutex (`Global\ABSO_Tray_SingleInstance_v2`)
- Game watcher monitors for game start/exit and adapts process priorities (no fixed wall-clock timeout — runs until tray exits)

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
