# Product Requirements Document: Windows Gaming Optimization Tool

## Project Name: **A.B.S.O.** (Adaptive Battle Station Optimizer)

---

## 1. Overview

A.B.S.O. is a Windows 11 diagnostic and optimization tool designed to cut through the fragmented chaos of gaming configuration across multiple system layers. It consolidates settings from Windows, Nvidia Control Panel, registry, and more into a single intelligent interface that applies game-specific optimization profiles.

---

## 2. Problem Statement

Windows 11 gaming configuration is scattered across:
- Windows Settings (Display, Graphics, Game Mode)
- Nvidia Control Panel (3D Settings, G-Sync, display configuration)
- Registry edits (timer resolution, fullscreen optimizations, etc.)
- Power plans
- Background services and processes
- Per-game in-game settings

There is no unified way to:
1. Audit current configuration for issues or conflicts
2. Understand which settings override others
3. Apply known-optimal settings for specific games
4. Safely experiment with aggressive optimizations
5. Roll back changes when something breaks

---

## 3. Target Users

**Primary (v1.0):** The developer (single-user tool for personal use)

**Future:** Enthusiast PC gamers who want granular control without manually navigating multiple interfaces.

---

## 4. Design Principles

1. **Aggressive by default** — Optimize for competitive performance (latency) unless otherwise specified
2. **Safety through rollback** — Always backup before changes; one-click restore
3. **Transparency** — Explain *why* each setting matters, not just *what* to change
4. **Auto-detect everything possible** — Only prompt user when detection fails
5. **Game-aware** — Different games have different optimal configurations

---

## 5. Core Features

### 5.1 Hardware Detection Module

Automatically detect and report:

| Component | Detection Method | Fallback |
|-----------|------------------|----------|
| GPU | Nvidia API / WMI / `nvidia-smi` | Prompt user |
| CPU | WMI `Win32_Processor` | Prompt user |
| RAM | WMI `Win32_PhysicalMemory` | Prompt user |
| Monitor(s) | Windows Display API / EDID | Prompt for make/model, refresh rate, G-Sync capability, HDR |
| Storage (game install location) | Query game install path, determine drive type via WMI | Prompt user |
| Windows version/build | Registry / `winver` | N/A |
| Nvidia driver version | Nvidia API / registry | Prompt user |

**Output:** Hardware profile summary (JSON + human-readable markdown)

---

### 5.2 Current Configuration Audit

Scan and report current state of all settings in scope (see Section 6). For each setting:
- Current value
- Optimal value for competitive gaming
- Risk level of changing
- Explanation of what it does

**Output modes:**
- **Terse:** Checklist of issues/recommendations
- **Verbose:** Full explanations for each item

---

### 5.3 Game Profile System

#### Profile Structure

Each game profile contains:
```
{
  "game_id": "slippi-melee",
  "display_name": "Super Smash Bros. Melee (Slippi)",
  "executable_hint": ["Slippi Dolphin.exe", "Dolphin.exe"],
  "optimization_target": "minimum_latency",
  "settings": {
    "nvidia_3d": { ... },
    "windows": { ... },
    "registry": { ... },
    "power": { ... }
  },
  "in_game_recommendations": [
    { "setting": "VSync", "value": "Off", "reason": "..." },
    ...
  ]
}
```

#### Profile Activation

- **Manual selection** from CLI or UI
- User selects profile → tool applies all system-level settings
- Tool generates markdown file with in-game settings the user must configure manually

#### Initial Game Profiles

| Game | Launcher/Runtime | Optimization Focus |
|------|------------------|-------------------|
| Super Smash Bros. Melee | Slippi Launcher / Slippi Dolphin | Ultra-low latency (competitive) |
| Call of Duty: Black Ops 7 | Battle.net / Steam | Low latency, stable high FPS |
| Diablo 4 | Battle.net | Balanced (stable FPS, visual quality) |

#### Future: "Sweetspot" Mode

A planned feature to find optimal balance between:
- Target FPS (user-specified)
- Visual quality
- Latency

This would involve benchmarking and iterative adjustment.

---

### 5.4 Backup & Rollback System

Before applying any changes:
1. Export current Nvidia profile settings
2. Export relevant registry keys
3. Record current Windows settings
4. Save power plan configuration
5. Store all in timestamped backup folder

**Rollback command:** Restore all settings from a specific backup.

**Backup format:**
```
/backups/
  /2024-01-15_143022/
    nvidia_profile.nip
    registry_export.reg
    windows_settings.json
    power_plan.pow
    manifest.json
```

---

### 5.5 Output & Reporting

| Output Type | Format | Purpose |
|-------------|--------|---------|
| Hardware profile | JSON + Markdown | Record system specs |
| Configuration audit | Markdown | Diagnose current state |
| Applied changes log | Markdown | Document what was changed |
| In-game recommendations | Markdown | Settings user must change manually |
| Backup manifest | JSON | Track restore points |

---

## 6. Settings Scope

### 6.1 Windows Display Settings
- Resolution and refresh rate per monitor
- Multiple display arrangement
- HDR toggle and calibration
- Scaling (DPI)
- Variable Refresh Rate (OS-level)

### 6.2 Nvidia Control Panel — 3D Settings

**Global and per-application profiles:**
- Low Latency Mode (Ultra)
- Power Management Mode (Prefer Maximum Performance)
- Texture Filtering (Quality vs Performance)
- VSync (Off for competitive)
- G-Sync / G-Sync Compatible toggle
- Max Frame Rate
- Threaded Optimization
- Shader Cache Size
- Antialiasing modes
- Anisotropic Filtering
- CUDA - GPUs
- OpenGL rendering GPU
- Preferred refresh rate
- Triple buffering
- Vertical sync

### 6.3 Nvidia Control Panel — Display
- G-Sync enable/disable and mode (fullscreen, windowed, both)
- Refresh rate override
- Color settings (if relevant to HDR)
- Resolution / scaling

### 6.4 Windows Gaming Features
- **Game Mode:** On/Off
- **Game Bar:** Disable for performance
- **Hardware-Accelerated GPU Scheduling (HAGS):** Enable/test
- **Variable Refresh Rate (Windows):** On/Off
- **Captures:** Disable background recording

### 6.5 Virtualization-Based Security (VBS) / Core Isolation
- Memory Integrity (HVCI): Disable for max performance
- VBS status detection

### 6.6 Power Management
- Power plan selection (High Performance / Ultimate Performance)
- Processor power management (min/max state)
- USB selective suspend: Disable
- PCI Express link state power management: Off
- Hard disk turn off: Never

### 6.7 Registry Tweaks

| Key | Purpose |
|-----|---------|
| `HKCU\System\GameConfigStore` | Fullscreen optimizations per-game |
| `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management` | Various memory tweaks |
| `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile` | Multimedia scheduling priority |
| `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games` | Game priority settings |
| Timer resolution (`NtSetTimerResolution`) | Force 0.5ms timer resolution |
| Disable Nagle's algorithm | Network latency reduction |
| `HKCU\Control Panel\Desktop` | Menu show delay, etc. |
| Fullscreen optimizations disable flag | Per-executable |

### 6.8 Background Process Management
- Identify and optionally disable/suspend non-essential processes
- Xbox services
- Windows Search indexing (pause during gaming)
- Telemetry services
- Sysmain (Superfetch)
- Windows Update (pause during gaming)

### 6.9 Network / Latency Tweaks
- Nagle's algorithm (disable for lower latency)
- Network Throttling Index
- TCP auto-tuning level
- DNS optimization
- Adapter-specific settings (interrupt moderation, RSS, etc.)

### 6.10 Emulator-Specific (Slippi Dolphin)
- Dolphin graphics backend (Vulkan vs OpenGL vs D3D)
- Exclusive fullscreen vs borderless
- Audio backend and latency settings
- Adapter polling rate (GameCube controller adapter)
- Slippi-specific rollback and networking settings

---

## 7. User Interface

### 7.1 Phase 1: CLI

```
abso detect              # Run hardware detection
abso audit               # Audit current configuration
abso audit --verbose     # Detailed audit
abso profiles            # List available game profiles
abso apply <profile>     # Apply a game profile
abso backup              # Create manual backup
abso restore <backup_id> # Restore from backup
abso report <profile>    # Generate in-game settings markdown
```

### 7.2 Phase 2 (Future): GUI

- Dashboard showing current system state
- One-click profile switching
- Visual diff of current vs. optimal settings
- Backup manager

---

## 8. Technical Requirements

- **Platform:** Windows 11 (22H2+)
- **Runtime:** Python 3.11+ or compiled executable
- **Privileges:** Administrator (required for registry, power plans, some Nvidia settings)
- **Dependencies:**
  - Nvidia driver with NVAPI access
  - WMI access
  - Registry access
  - PowerShell (for some operations)

---

## 9. Non-Goals (v1.0)

- AMD GPU support
- Intel GPU support
- Linux / SteamOS support
- Automatic game detection and profile switching
- Modifying in-game settings or game files directly
- Overclocking
- BIOS-level optimizations

---

## 10. Success Criteria

1. Tool can detect all hardware components without user input (monitors may require confirmation)
2. Tool can audit current settings and identify suboptimal configurations
3. Applying a profile measurably reduces input latency or improves frame consistency
4. Rollback successfully restores previous state
5. No system instability caused by applied changes

---

## 11. Future Roadmap

| Version | Features |
|---------|----------|
| 1.0 | CLI tool, hardware detection, audit, profiles for 3 games, backup/restore |
| 1.1 | "Sweetspot" mode with target FPS balancing |
| 1.2 | GUI dashboard |
| 1.3 | Community profile sharing |
| 2.0 | AMD GPU support |

---

## 12. Open Questions

1. Should the tool integrate with game launchers (Steam, Battle.net, Slippi Launcher) to detect installed games?
2. Should network optimizations be adapter-specific or global?
3. How should conflicts between Nvidia Control Panel and in-game settings be communicated?
4. Should the tool run as a background service for "gaming mode" detection, or remain on-demand only?

---

## Appendix A: Research Required

- [ ] Slippi community optimal Dolphin settings
- [ ] Call of Duty BO7 competitive settings (input lag analysis)
- [ ] Diablo 4 optimal settings for stable FPS
- [ ] Windows 11 24H2 changes affecting gaming
- [ ] HAGS impact testing (game-dependent)
- [ ] VBS/HVCI performance impact quantification
- [ ] Nvidia Reflex integration points

---

## Appendix B: Reference Resources

- Nvidia Control Panel documentation
- Nvidia Profile Inspector (NPI) documentation
- Battle(non)sense input lag methodology
- Blur Busters forums
- Slippi Discord / documentation
- Windows gaming optimization guides (reputable sources)
