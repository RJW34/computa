# A.B.S.O.

**Adaptive Battle Station Optimizer**

A.B.S.O. is a CLI-first Windows 11 gaming optimization tool that automatically detects your hardware, audits your system configuration, and applies game-specific optimization profiles for competitive gaming.

> **A.B.S.O.** stands for **A**daptive **B**attle **S**tation **O**ptimizer - your intelligent companion for achieving peak gaming performance on Windows.

## Features

- **Hardware Detection** - Auto-detects GPU, CPU, RAM, and monitors (including G-Sync/VRR support)
- **Configuration Audit** - Scans 15+ system areas for optimization opportunities
- **Game Profiles** - Pre-configured optimization profiles for specific games
- **Safe by Default** - Automatic backups before any changes
- **Easy Restore** - One-click rollback to previous settings

## Quality Bar

A.B.S.O. is being hardened against a stricter product standard than a typical tweak tool. The current quality rubric, agent protocol, and remediation roadmap live here:

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

# Restore from backup
python -m abso restore latest
python -m abso restore 20240115_143022  # Specific backup
```

## Available Game Profiles

| Profile | Game | Focus |
|---------|------|-------|
| `slippi-melee` / `slippi-melee-hdr` | Super Smash Bros. Melee (Slippi) | Ultra-low latency (SDR / HDR) |
| `slippi-melee-console-parity` / `slippi-melee-console-parity-hdr` | Super Smash Bros. Melee (Slippi) | Console-like pacing/feel (SDR / HDR) |
| `slippi-melee-universal` / `slippi-melee-universal-hdr` | Super Smash Bros. Melee (Slippi) | Lowest latency with fixed HAGS (no reboot) (SDR / HDR) |
| `rivals2-offline` | Rivals of Aether 2 | Offline no-sync latency |
| `rivals2-online` | Rivals of Aether 2 | Rollback-safe online play |
| `rivals2-gsync` | Rivals of Aether 2 | Low-latency VRR offline |
| `rivals2-online-gsync` | Rivals of Aether 2 | Rollback-safe VRR online |
| `fortnite` / `fortnite-hdr` | Fortnite | Reflex no-sync latency (SDR / HDR) |
| `marvel-rivals-sdr` / `marvel-rivals-hdr` | Marvel Rivals | Reflex VRR (SDR / HDR) |
| `overwatch2` / `overwatch2-hdr` | Overwatch 2 (No Sync) | Minimum latency no-sync (SDR / HDR) |
| `overwatch2-gsync` / `overwatch2-gsync-hdr` | Overwatch 2 (G-SYNC) | Tear-free low latency VRR (SDR / HDR) |
| `overwatch2-gsync-capture` / `overwatch2-gsync-hdr-capture` | Overwatch 2 (G-SYNC) | Borderless VRR path for capture/overlay workflows |
| `diablo4` / `diablo4-sdr` | Diablo 4 | Balanced performance (HDR / SDR) |
| `ryujinx-ssbu` | Ryujinx (SSBU) | Low-latency emulator system path |

## What Gets Optimized

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
- Processor performance maximized

### Graphics Settings
- Per-executable Fullscreen Optimizations (FSO) forced on or off to match each profile's presentation path (exclusive fullscreen vs composited borderless)
- Multi-Plane Overlay (MPO) is **not** disabled by default. ABSO only touches MPO in profiles where MPO compositor behavior was specifically measured to interfere; most profiles leave MPO enabled because it is required for G-SYNC/VRR on Windows 11 24H2+

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
- `SystemResponsiveness = 0` is only applied under the opt-in legacy-tweaks flag

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

A.B.S.O. will notify you if a reboot may be required, but if you've previously applied the same profile and rebooted, you can skip the reboot.

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
│   ├── handler_registry.py # Central registry (one HandlerEntry per handler)
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

For agents picking up this project, the canonical entry point is
[`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md).

## License

This project is provided as-is for personal use. Use at your own risk.

## Disclaimer

This tool modifies Windows system settings. While it includes backup and restore functionality, always ensure you have system restore points or full backups before making system changes. The authors are not responsible for any issues that may arise from using this tool.
