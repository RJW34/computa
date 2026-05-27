# A.B.S.O.

**Adaptive Battle Station Optimizer**

A.B.S.O. is a CLI-first Windows 11 gaming tuning tool that automatically detects your hardware, audits your system configuration, and applies game-specific profiles for competitive gaming.

> **A.B.S.O.** stands for **A**daptive **B**attle **S**tation **O**ptimizer - an evidence-aware Windows gaming profile tool.

## Features

- **Hardware Detection** - Auto-detects GPU, CPU, RAM, and monitors (including G-Sync/VRR support)
- **Configuration Audit** - Scans 15+ system areas for optimization opportunities
- **Game Profiles** - Pre-configured optimization profiles for specific games
- **Safe by Default** - Automatic backups before any changes
- **Easy Restore** - One-click rollback to previous settings
- **Live State Verification** - `state --json --verify`, `health --json`, and
  targeted `apply-pending` checks for tray/GUI-safe remediation, including
  tray runtime staleness detection after LocalAppData deploys and read-only
  display-event evidence with optional channel-error reporting
- **Passive Display Stability Diagnostics** - `display-diagnostics --json` and
  `health --json` report active monitor topology, mixed-refresh/VRR risk
  factors, active-profile reboot context, and whether clean event logs point
  away from a physical disconnect
- **Tray-Safe Reapply Flow** - selecting the already-active tray profile is
  verify-gated to avoid redundant display/color writes
- **Narrow Apply Preflight** - Windows settings probe only the requested
  setting groups before apply, avoiding unrelated HDR/WCG/SDR-white/refresh
  detection for registry-only toggles
- **Narrow Profile Verification** - current-profile status verifies known
  Game Mode, Game Bar/DVR, windowed VRR, and refresh-rate targets without
  invoking unrelated Windows probes
- **Grouped DirectX Readback** - Auto HDR, windowed optimizations, and VRR
  optimize are parsed exactly from one registry read in hot detect/apply/verify
  paths
- **Deterministic DirectX Writes** - DirectX global settings preserve unknown
  tokens while normalizing ABSO-owned Auto HDR/windowed/VRR flags to one clean
  canonical set, not duplicate or conflicting pairs
- **Backend No-Op Apply/Reapply Guard** - `apply <current-profile>` and
  `reapply` verify first, skip the transaction when nothing is pending, or
  route supported pending settings through targeted `apply-pending`
- **No-Apply Launch Guard** - `launch <current-profile>` skips redundant apply
  transactions when live verification is already clean
- **Reboot-Gated Safety** - pending reboot-only verifier states are treated as
  no-apply states instead of rerunning display-sensitive handlers
- **Mixed-Monitor HDR Safety** - HDR profile writes skip known SDR-only active
  targets instead of sending unnecessary display-config calls to every monitor

## Quality Bar

A.B.S.O. is being hardened against a stricter product standard than a typical tweak tool. The current quality rubric, agent protocol, and remediation roadmap live here:

- [`docs/CURRENT_AGENT_BRIEFING.md`](docs/CURRENT_AGENT_BRIEFING.md) — current machine state, verified local build/deploy status, and monitor-flicker precautions for zero-context agents
- [`AGENTS.md`](AGENTS.md) — root-level zero-context entrypoint for Codex-style agents
- [`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md) — forward-looking start-here for any agent
- [`docs/INDEX.md`](docs/INDEX.md)
- [`docs/QUALITY_RUBRIC.md`](docs/QUALITY_RUBRIC.md)
- [`docs/REMEDIATION_ROADMAP.md`](docs/REMEDIATION_ROADMAP.md)

These documents define:

- the fastest reading order for new agents
- machine-role policy for implementation vs validation
- what the project is allowed to claim
- how profile quality is graded
- what must be true before calling a profile "optimal"
- the execution plan to raise the project to `A` grades across the board

## Requirements

- Windows 10/11 (64-bit)
- Python 3.11 or later
- Administrator privileges (required for system changes)
- NVIDIA GPU (optional, for GPU-specific optimizations)

### Optional: NVIDIA Profile Inspector

For full NVIDIA GPU optimization (Low Latency Mode, Power Management, etc.), install NVIDIA Profile Inspector:

1. Download the latest release from [GitHub](https://github.com/Orbmu2k/nvidiaProfileInspector/releases)
2. Extract to one of these locations (auto-detected):
   - `tools/npi/nvidiaProfileInspector.exe` (project directory)
   - `%USERPROFILE%\nvidiaProfileInspector\nvidiaProfileInspector.exe`
   - Any location in your PATH

A.B.S.O. will automatically detect NPI and use it for advanced NVIDIA settings. Without NPI, basic NVIDIA optimizations via the driver will still work.

## Installation

1. Clone or download this repository
2. Open a terminal in the project directory
3. Create a virtual environment and install dependencies:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Quick Start

### Interactive Mode (Recommended)

Simply run A.B.S.O. without arguments to launch the interactive menu:

```powershell
python -m abso
```

You'll see a menu with options to:
1. Run a system audit
2. Apply a game profile
3. Detect hardware
4. Restore from backup
5. View available profiles

### Command Line Mode

For scripting or advanced users:

```powershell
# Detect hardware
python -m abso detect

# Audit system configuration
python -m abso audit
python -m abso audit --verbose  # With detailed explanations

# List available profiles
python -m abso profiles

# Apply a game profile
python -m abso apply slippi-melee
python -m abso apply rivals2-online
python -m abso apply fortnite
python -m abso apply diablo4

# Check active profile health without changing display state
python -m abso state --json --verify
python -m abso health --json
python -m abso health --json --full-verify  # Include full per-handler details
python -m abso health --json --full-backups # Include recent backup rows

# Sample only display flicker evidence without profile verification or writes
python -m abso display-diagnostics --json
python -m abso display-diagnostics --samples 6 --interval 10 --json
python -m abso display-diagnostics --samples 6 --interval 10 --jsonl

# Apply only supported missing pending settings, not a full profile
python -m abso apply-pending overwatch2-gsync-hdr-capture --json

# Restore from backup
python -m abso restore latest
python -m abso restore 20240115_143022  # Specific backup
```

## Available Game Profiles

The tray lists each game once, then shows the available variants inside that game's flyout.

| Game / target | Variants | Profile IDs |
|---------------|----------|-------------|
| Desktop / Productivity | SDR, HDR | `productivity`, `productivity-hdr` |
| Rivals 2 | Online No Sync, Online G-SYNC, Offline No Sync, Offline G-SYNC; each in SDR and Windows HDR composition | `rivals2-online`, `rivals2-online-hdr`, `rivals2-online-gsync`, `rivals2-online-gsync-hdr`, `rivals2-offline`, `rivals2-offline-hdr`, `rivals2-gsync`, `rivals2-gsync-hdr` |
| Super Smash Bros. Melee (Slippi) | Competitive No Sync, Console-Parity 60 Hz, Universal No Sync; each in SDR and Windows HDR composition | `slippi-melee`, `slippi-melee-hdr`, `slippi-melee-console-parity`, `slippi-melee-console-parity-hdr`, `slippi-melee-universal`, `slippi-melee-universal-hdr` |
| SSBU / HewDraw Remix (Ryujinx) | Low-latency emulator | `ryujinx-ssbu` |
| Deadlock | No Sync and G-SYNC; each in SDR and Windows HDR composition | `deadlock`, `deadlock-hdr`, `deadlock-gsync`, `deadlock-gsync-hdr` |
| Fortnite | No Sync in SDR or HDR | `fortnite`, `fortnite-hdr` |
| Marvel Rivals | G-SYNC in SDR or HDR | `marvel-rivals-sdr`, `marvel-rivals-hdr` |
| Overwatch 2 | No Sync, strict G-SYNC, and capture-safe G-SYNC; each in SDR or HDR | `overwatch2`, `overwatch2-hdr`, `overwatch2-gsync`, `overwatch2-gsync-hdr`, `overwatch2-gsync-capture`, `overwatch2-gsync-hdr-capture` |
| Diablo 4 | HDR or SDR | `diablo4`, `diablo4-sdr` |
| Pokemon Auto Chess | Browser WebGL or native PACDeluxe client | `pokemon-auto-chess`, `pacdeluxe` |

## What Profiles Change

A.B.S.O. applies optimizations across multiple system areas. Exact settings vary by profile; the list below describes what built-in profiles actually touch today.

### Windows Settings
- Game Mode enabled
- Game Bar / Game DVR disabled (per-user registry toggles; background capture policy is not globally enforced)
- Hardware-Accelerated GPU Scheduling (HAGS) enabled on most gaming profiles (hardware/driver dependent; requires reboot on first change)
- Windowed-game optimizations (FSO per-executable) tuned per profile

### Power Settings
- Ultimate Performance power plan
- USB selective suspend disabled
- PCIe link-state power saving disabled
- Processor maximum state set to 100%; selected offline profiles may also raise minimum processor state

### Graphics Settings
- Per-executable Fullscreen Optimizations (FSO) forced on or off to match each profile's presentation path (exclusive fullscreen vs composited borderless)
- Multi-Plane Overlay (MPO) is **not** disabled by default. Most profiles leave MPO enabled because disabling it can alter or break the Windows 11 VRR/compositor path on some systems
- A local profile override may disable MPO for a specific capture-safe mixed-refresh setup. When that happens, `apply-pending` writes only the supported missing graphics target and marks the profile reboot-pending instead of re-running a full profile apply

### Input Settings
- Mouse acceleration disabled
- Linear mouse curves applied
- Enhanced pointer precision disabled

### Network Settings
- Built-in profiles use the `default` network preset and do **not** disable Nagle, TCP auto-tuning, or ECN. Microsoft documents TCP receive-window autotuning default `normal` as a TCP throughput win, and most competitive gameplay traffic is UDP so Nagle/TCP tweaks don't meaningfully affect gameplay latency
- TCP tuning (Nagle / autotuning / ECN / timestamps) is available as an opt-in preset but is not part of any built-in profile
- Network throttling index changes (`NetworkThrottlingIndex = 0xFFFFFFFF`) are only applied under the opt-in legacy-tweaks flag

### System Scheduler
- Process priority boosted for the game's executable(s) via IFEO (risk-managed: can conflict with anti-cheat, audio, OBS, and launchers)
- `Win32PrioritySeparation = 0x2A` is applied in most gaming base profiles; this is an old global tweak whose measured effect varies and should be considered experimental
- `SystemResponsiveness = 10` is only applied under the opt-in legacy-tweaks flag

### Background Services
- ABSO does **not** disable telemetry, search indexer, or Xbox background services by default. Broad service disabling is out of scope because it causes brittle systems and has no reliable gaming win on modern Windows 11

### Memory Management
- `LargeSystemCache` and `DisablePagingExecutive` are only applied under the opt-in legacy-tweaks flag. They are not default for any built-in gaming profile

### NVIDIA / VRR
- Per-application NVIDIA driver profile (via NPI / NVAPI DRS) with Low Latency Mode, VSync, Power Management, Max Frame Rate, and VRR App Override tuned per profile
- Native Reflex is preferred over driver Low Latency Mode whenever the game supports Reflex (CoD, Apex, Valorant, Fortnite, Overwatch 2, Diablo 4, Marvel Rivals). ABSO keeps driver LLM off for those games; the Reflex toggle itself must still be enabled in-game

### VBS / HVCI / Virtualization-Based Security
- ABSO does **not** silently disable Memory Integrity (HVCI), Virtual Machine Platform, or hypervisor launch state. Disabling VBS is a security tradeoff and is only available through an explicit opt-in flow with warnings and a restore path

## Safety Features

### Automatic Backups

Before applying any profile, A.B.S.O. automatically creates a backup of all settings that will be changed. Backups are stored in the `backups/` folder with timestamps.

### Easy Restore

If something doesn't work as expected, restore your previous settings:

```powershell
python -m abso restore latest
```

Or list and restore a specific backup:

```powershell
# Backups are named by timestamp: YYYY-MM-DD_HHMMSS
python -m abso restore 2026-05-13_181906
```

### Skip Backup (Not Recommended)

If you really need to skip the backup:

```powershell
python -m abso apply slippi-melee --no-backup
```

## In-Game Settings

After applying a profile, A.B.S.O. generates a report with recommended in-game settings. These are saved to the `reports/` folder.

For example, after applying the Rivals 2 profile, check:
```
reports/rivals2_settings.md
```

This includes game-specific recommendations for:
- Display mode
- VSync settings
- Frame rate limits
- NVIDIA Reflex
- Graphics quality
- Audio latency

## Troubleshooting

### "Admin privileges required"

A.B.S.O. needs administrator access to modify system settings. Right-click your terminal and select "Run as administrator", or launch the interactive mode which will prompt for elevation.

### Changes not taking effect

Some optimizations require a system reboot **the first time they're applied**:
- HAGS changes
- VBS / Memory Integrity (HVCI) state changes (opt-in only)
- Memory management settings (`DisablePagingExecutive`, opt-in legacy tweaks)
- MPO (Multi-Plane Overlay) changes, when a profile opts into toggling MPO

**Important:** Once you've applied a profile and rebooted, switching between profiles typically does NOT require another reboot. The kernel-level settings persist in the registry, so subsequent profile switches are instant.

A.B.S.O. will notify you if a reboot may be required. Use `state --json --verify` or `health --json` to distinguish a missing pending apply from a reboot-gated setting whose registry target is already written.

### Restoring doesn't work

If automatic restore fails:
1. Check the `backups/` folder for your backup
2. The `manifest.json` file lists all changed settings
3. Each component has its own backup file that can be manually inspected

### NVIDIA settings not applied

- Ensure you have an NVIDIA GPU
- NVIDIA Profile Inspector may be required for some settings
- Driver restart or reboot may be needed

## Project Structure

```
abso/
├── main.py                 # CLI entry point
├── interactive.py          # Interactive menu system
├── core/
│   ├── detector.py         # Hardware detection
│   ├── auditor.py          # Configuration auditing
│   ├── applier.py          # Profile application
│   ├── backup.py           # Backup/restore system
│   ├── app_paths.py        # Installed LocalAppData paths
│   ├── handler_registry.py # Central registry (one HandlerEntry per handler)
│   ├── pending_apply.py    # Narrow targeted remediation path
│   ├── profile_status.py   # Shared verification/status summaries
│   ├── state_reconcile.py  # Reboot-pending reconciliation
│   ├── state_store.py      # Active-profile state read/write helpers
│   ├── compliance.py       # Post-apply compliance / severity escalation
│   ├── kb_checker.py       # Known-bad Windows updates + supersession
│   ├── bios_detector.py    # BIOS/firmware + Secure Boot cert state
│   └── ...
├── data/
│   ├── hardware_db.py      # OEM / chassis / G-Sync model tables
│   ├── monitor_osd.py      # Per-monitor OSD recommendations
│   └── debloat_tweaks.yaml
├── profiles/
│   ├── base.py             # Base profile class
│   ├── profile_bases.py    # Reflex / Emulator / Rivals2 family bases
│   └── <game>.py           # Game-specific profiles
├── settings/               # Settings handlers (~25)
│   ├── base.py             # SettingsHandler interface
│   ├── windows.py          # Windows settings
│   ├── power.py            # Power plan settings
│   ├── nvidia/             # NVIDIA package (NPI + NVAPI DRS)
│   ├── registry.py         # Registry tweaks
│   ├── xbox_mode.py        # 25H2 Xbox Mode rollout (detect-only)
│   ├── ai_agents.py        # 25H2 AI taskbar agents (detect-only)
│   └── ...
├── tray/                   # PowerShell tray app
└── utils/
    ├── admin.py            # Admin elevation
    ├── os_release.py       # OsRelease single source of truth
    ├── registry.py         # Safe registry helpers
    └── atomic_io.py        # Atomic JSON I/O
```

For agents picking up this project on a **freshly cloned / new PC**, read
[`docs/NEW_MACHINE_SETUP.md`](docs/NEW_MACHINE_SETUP.md) first. On an
already-configured machine, read
[`docs/CURRENT_AGENT_BRIEFING.md`](docs/CURRENT_AGENT_BRIEFING.md) first for
the current live-PC state (machine-specific — re-verify on a fresh clone), then
[`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md) for durable workflow and
architecture rules.

## License

This project is provided as-is for personal use. Use at your own risk.

## Disclaimer

This tool modifies Windows system settings. While it includes backup and restore functionality, always ensure you have system restore points or full backups before making system changes. The authors are not responsible for any issues that may arise from using this tool.
