# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Freshly cloned onto a new PC? Read
> [`docs/NEW_MACHINE_SETUP.md`](docs/NEW_MACHINE_SETUP.md) first** — it explains
> what ABSO is, how to set up the dev environment, how to establish this
> machine's real state, and why the live-state docs may describe a different box.
>
> **On an already-configured machine, read
> [`docs/CURRENT_AGENT_BRIEFING.md`](docs/CURRENT_AGENT_BRIEFING.md) first, then
> [`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md).** The briefing is the
> live-machine truth for the active profile, installed build, monitor-flicker
> status, LocalAppData deployment state, and reboot-gated work — but it is
> **machine-local and gitignored** (see
> [`docs/LOCAL_ONLY_FILES.md`](docs/LOCAL_ONLY_FILES.md)); on a fresh clone it
> does not exist and its role is served by `NEW_MACHINE_SETUP.md` until this
> machine writes its own. The protocol is the durable workflow and
> architecture guide. Everything below is a short-form orientation, not the
> authoritative source.

## Project Overview

**A.B.S.O.** (**A**daptive **B**attle **S**tation **O**ptimizer) is a CLI-first Windows 11 gaming optimization tool that:
- Auto-detects gaming hardware (GPU, CPU, monitor, etc.)
- Audits system configuration for gaming optimization issues
- Applies game-specific optimization profiles
- Manages backups and rollbacks of all changes
- Includes a system tray app for easy profile switching

**Target:** Single enthusiast gamer. Aggressive latency optimization with comprehensive backup/rollback for safety.

## Available Profiles

Do not keep a hand-written profile list in sync here. Use:

```bash
python -m abso profiles
```

The current catalog includes Desktop/Productivity, Rivals 2, Slippi Melee,
Ryujinx SSBU, Deadlock, Fortnite, Marvel Rivals, Overwatch 2, Diablo 4,
Pokemon Auto Chess, and PACDeluxe families, with SDR/HDR, no-sync, G-SYNC, and
capture-safe variants where supported.

## Build & Run Commands

```bash
# Environment setup (use the .venv name — build/deploy commands assume it)
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt   # runtime deps + pytest/pyinstaller/ruff

# CLI commands (requires admin elevation)
python -m abso detect              # Hardware detection
python -m abso audit               # Configuration audit
python -m abso audit --verbose     # Detailed audit
python -m abso apply <profile>     # Apply game profile
python -m abso apply <profile> --no-backup  # Skip backup (not recommended)
python -m abso state --json --verify
python -m abso health --json
python -m abso health --json --full-verify
python -m abso health --json --full-backups
python -m abso apply-pending <profile> --json
python -m abso restore latest      # Restore last backup
python -m abso profiles            # List available profiles

# Local installed runtime deploy
.\.venv\Scripts\python.exe build.py deploy             # Build CLI, then deploy to LocalAppData
.\.venv\Scripts\python.exe build.py deploy-existing    # Deploy current dist\abso.exe

# Run tests
pytest tests/
pytest tests/test_detector.py -v      # Single test file
ruff check .

# Tray app (PowerShell, requires admin)
powershell -File abso\tray\ABSO-Tray.ps1
```

## Architecture

```
abso/
├── main.py                 # CLI entry (Click-based)
├── core/
│   ├── detector.py         # Hardware detection (WMI, nvidia-smi, pynvml)
│   ├── auditor.py          # Scans settings, compares to optimal
│   ├── applier.py          # Applies profile settings with validation pipeline
│   ├── app_paths.py        # Installed LocalAppData path helpers
│   ├── backup.py           # Timestamped backup/restore system
│   ├── backup_actions.py   # Shared backup command actions
│   ├── compliance.py       # Post-apply compliance / severity escalation
│   ├── capabilities.py     # Profile preflight: VRR / HDR / OS-build / monitor checks
│   ├── handler_registry.py # Central HandlerEntry registry (audit + backup tags)
│   ├── pending_apply.py    # Narrow targeted remediation path
│   ├── profile_status.py   # Shared state/verify summaries
│   ├── state_reconcile.py  # Reboot-pending reconciliation
│   ├── state_store.py      # Active-profile state read/write helpers
│   ├── kb_checker.py       # Known-bad Windows updates + supersession tracking
│   ├── bios_detector.py    # BIOS/firmware + Secure Boot cert state
│   ├── linter.py           # ProfileLinter - static validation
│   ├── rollback_guard.py   # RollbackGuard - online netcode protection
│   ├── stability_gate.py   # StabilityGate - gated aggressive settings
│   └── ...                 # Other validation subsystems
├── data/
│   ├── hardware_db.py      # OEM / chassis / G-Sync model lookup tables
│   ├── monitor_osd.py      # Per-monitor OSD recommendations
│   └── debloat_tweaks.yaml # Opt-in debloat preset definitions
├── profiles/
│   ├── base.py             # BaseProfile (+ xbox_mode / ai_agents / min_os_build fields)
│   ├── profile_bases.py    # ReflexShooter / EmulatorLatency / Rivals2 base classes
│   └── <game>.py           # Game-specific profiles (data + logic)
├── settings/               # One module per settings domain
│   ├── base.py             # SettingsHandler interface (+ is_critical_verify)
│   ├── nvidia/             # Nvidia Profile Inspector + NVAPI DRS package
│   ├── windows.py          # Game Mode, HAGS, VBS, HDR, FSO
│   ├── registry.py         # Registry read/write (+ WIN32_PRIORITY_* constants)
│   ├── power.py            # Power plan management (powercfg)
│   ├── network.py          # Nagle, TCP optimizations
│   ├── services.py         # Windows services control
│   ├── mouse.py            # Mouse acceleration settings
│   ├── xbox_mode.py        # 25H2 Xbox Mode rollout (detect-only)
│   ├── ai_agents.py        # 25H2 AI taskbar agents rollout (detect-only)
│   └── ...                 # ~25 handlers total
├── tray/
│   ├── ABSO-Tray.ps1       # System tray app (PowerShell)
│   └── ABSO-Watcher.ps1    # Game process monitor
└── utils/
    ├── admin.py            # UAC elevation handling
    ├── os_release.py       # OsRelease.at_least(build, ubr) — single source of truth
    ├── registry.py         # Safe registry read/write helpers
    ├── validation.py       # Input validation helpers
    ├── atomic_io.py        # Atomic JSON write helpers
    └── verify.py           # Post-apply verification helpers
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

**Backup System** — Creates timestamped folders in `/backups/` (format
`YYYY-MM-DD_HHMMSS`) with `manifest.json` tracking all components.
Every state-mutating settings handler is backed up; the canonical list
is the `audit + backup` set in `abso/core/handler_registry.py`. Adding
a handler is one `HandlerEntry` row there — both auditor and backup
pipelines pick it up automatically.

**Validation Pipeline** — Profile application runs through:
1. ProfileLinter (static validation)
2. MultiMonitorDetector (environment checks)
3. RollbackGuard (online netcode protection)
4. StabilityGate (gate aggressive settings)
5. NetworkScopeManager (per-game network tuning)

**Targeted Pending Apply** — `apply-pending` is the safe repair path when
`state --json --verify` reports supported missing settings. It must stay
narrow: no full backup/baseline/display reset path, and no repeated full apply
when the active profile is already verified.

## Critical Constraints

1. **Always backup before apply** — Never modify system state without creating a restore point first (use `--no-backup` flag only if you understand the risks)
2. **Require admin elevation** — Check at startup, re-launch elevated if needed
3. **Fail gracefully** — Registry/WMI errors must not crash the tool; log and continue
4. **Idempotent operations** — Applying the same profile twice must be safe
5. **Online safety** — Profiles with `is_online_profile=True` have stricter validation
6. **Live monitor-flicker safety** — On this PC, do not run full profile apply,
   live display reset, HDR cycling, DWM restart, or driver reset just because
   the secondary monitor flickers. Read the current briefing first.
7. **Local deploy discipline** — Use `.\.venv\Scripts\python.exe build.py
   deploy` or `.\.venv\Scripts\python.exe build.py deploy-existing` so the
   backend, installed GUI executable, GUI sidecars, tray assets, config, and
   backup mirror stay aligned in LocalAppData. After tray script changes,
   `health --json` may warn `tray_runtime_marker` until the live tray restarts
   and writes its installed-script hash marker.
8. **Hermetic mutation tests** — Tests that invoke restore/apply/launch paths
   must redirect `STATE_FILE`, `_state_file_targets`, or `LOCALAPPDATA` to
   `tmp_path`; never let tests mutate this PC's real LocalAppData state.

## Technical Notes

### Nvidia Settings
- Use Nvidia Profile Inspector (`nvidiaProfileInspector.exe`) for profile management
- Some settings require driver restart or reboot to take effect
- G-Sync detection requires NVAPI or EDID parsing
- LLM Ultra can cause rollback contention in online games

### Windows Settings
- HAGS (`HwSchMode` registry key): Game-dependent, make per-profile
- VBS/Memory Integrity: Requires reboot after change
- Fullscreen optimizations: Tune per-executable via AppCompatFlags
- MPO changes are registry-target writes that only become live after reboot;
  verification can prove the target is written, not that DWM has committed the
  compositor path before reboot.

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
