# TECHNICAL_REFERENCE.md — GameTune Implementation Guide

This document provides detailed technical reference for implementing the GameTune Windows gaming optimization tool.

---

## Hardware Detection

### GPU Detection
```python
# Primary: nvidia-smi (if available)
import subprocess
result = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader'], capture_output=True)

# Fallback: WMI
import wmi
c = wmi.WMI()
for gpu in c.Win32_VideoController():
    print(gpu.Name, gpu.DriverVersion, gpu.AdapterRAM)

# Advanced: NVAPI (requires pynvml or ctypes bindings)
import pynvml
pynvml.nvmlInit()
handle = pynvml.nvmlDeviceGetHandleByIndex(0)
name = pynvml.nvmlDeviceGetName(handle)
```

### Monitor Detection
```python
# Basic info via Windows API
import ctypes
from ctypes import wintypes

# For detailed EDID parsing (make/model), use:
# - win32api + EnumDisplayDevices
# - WMI WmiMonitorID class
# - Direct EDID parsing from registry

# Refresh rate:
import win32api
device = win32api.EnumDisplayDevices(None, 0)
settings = win32api.EnumDisplaySettings(device.DeviceName, -1)  # ENUM_CURRENT_SETTINGS
print(f"Refresh rate: {settings.DisplayFrequency}Hz")
```

### CPU / RAM
```python
import wmi
c = wmi.WMI()

# CPU
for cpu in c.Win32_Processor():
    print(cpu.Name, cpu.NumberOfCores, cpu.MaxClockSpeed)

# RAM
total_ram = sum(int(mem.Capacity) for mem in c.Win32_PhysicalMemory())
```

---

## Nvidia Control Panel Settings

### Option 1: Nvidia Profile Inspector CLI
The `nvidiaProfileInspector.exe` tool can export/import profiles:
```bash
# Export current profile
nvidiaProfileInspector.exe /export "backup.nip"

# Import profile
nvidiaProfileInspector.exe /import "optimized.nip"
```

### Option 2: Direct Registry Manipulation
Nvidia 3D settings are stored in:
```
HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000\...
```
And in the Nvidia driver's DRS (Driver Recommendation System) database. **Caution:** Direct manipulation is fragile.

### Option 3: NVAPI
Nvidia's NVAPI provides programmatic access but requires C/C++ bindings. Python options:
- `pynvml` for basic queries
- Custom ctypes bindings for full NVAPI (complex)

**Recommendation:** Use Nvidia Profile Inspector for profile management. Parse its XML/NIP format for programmatic control.

### Key Nvidia Settings for Competitive Gaming

| Setting | Competitive Value | Notes |
|---------|-------------------|-------|
| Low Latency Mode | On or Ultra | See notes below |
| Power Management | Prefer Maximum Performance | Prevents downclocking |
| Threaded Optimization | Auto | Off is outdated advice; Auto works well for modern games |
| VSync | Off (with G-Sync) or On (without) | Never both off without VRR - tearing is bad |
| Max Frame Rate | 3 below refresh | With G-Sync; helps avoid VSync activation |
| G-Sync | Enabled (Fullscreen and Windowed) | If monitor supports |
| Texture Filtering Quality | High Performance | Minor visual loss |
| Shader Cache Size | Unlimited | Reduce stutter |
| Triple Buffering | Off | Only for OpenGL VSync |

**Important notes on Low Latency Mode:**
- **Ultra** can cause stuttering/FPS drops in some games - test first
- If game has **Nvidia Reflex**, enable that instead (takes priority over driver setting)
- **On** is safer and still reduces render queue significantly
- Reflex-enabled games: Most modern shooters (CoD, Apex, Valorant, Fortnite, etc.)

---

## Windows Settings

### Game Mode & Game Bar
```python
import winreg

# Game Mode
key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", 0, winreg.KEY_ALL_ACCESS)
winreg.SetValueEx(key, "AllowAutoGameMode", 0, winreg.REG_DWORD, 1)  # 1 = enabled
winreg.SetValueEx(key, "AutoGameModeEnabled", 0, winreg.REG_DWORD, 1)

# Disable Game Bar
key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", 0, winreg.KEY_ALL_ACCESS)
winreg.SetValueEx(key, "AppCaptureEnabled", 0, winreg.REG_DWORD, 0)
```

### Hardware-Accelerated GPU Scheduling (HAGS)
```python
# Check status
key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", 0, winreg.KEY_READ)
hags = winreg.QueryValueEx(key, "HwSchMode")[0]
# 1 = Off, 2 = On
```
**Note:** HAGS impact is game-dependent. Some games benefit, others suffer. Test per-profile.

### VBS / Core Isolation (Memory Integrity)
```python
# Check VBS status
key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity", 0, winreg.KEY_READ)
enabled = winreg.QueryValueEx(key, "Enabled")[0]

# Disable (requires reboot)
winreg.SetValueEx(key, "Enabled", 0, winreg.REG_DWORD, 0)
```
**Warning:** Disabling VBS reduces security. User has accepted this tradeoff.

---

## Registry Tweaks

### Fullscreen Optimizations (Legacy - Test Before Disabling)
```python
# Disable for specific executable
exe_path = r"C:\Path\To\Game.exe"
key_path = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, "~ DISABLEDXMAXIMIZEDWINDOWEDMODE")
```

**Important context:**
- Disabling FSO was common advice for Windows 10, where it caused issues
- **Windows 11 has significantly improved FSO** - latency is now similar to exclusive fullscreen
- Modern games often work better WITH FSO enabled (better alt-tab, overlays, recording)
- **Test per-game** rather than blanket disabling
- If using Nvidia Reflex, FSO impact is negligible

### Multimedia Scheduling (Game Priority)
```
HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile
    - SystemResponsiveness = 0 (give games max CPU)
    - NetworkThrottlingIndex = 0xffffffff (disable throttling)

HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games
    - GPU Priority = 8
    - Priority = 6
    - Scheduling Category = "High"
    - SFIO Priority = "High"
```

**What these actually do:**

- **SystemResponsiveness**: Controls % of CPU reserved for background tasks
  - Default is 20 (20% reserved for background)
  - Setting to 0 gives games maximum scheduling priority
  - Rare side effect: May cause audio buffer underruns - revert if you hear crackling

- **NetworkThrottlingIndex**: Controls multimedia streaming throttling
  - Affects network priority for multimedia applications
  - 0xFFFFFFFF disables all multimedia network throttling
  - Benefits streaming/recording while gaming

### Timer Resolution
**Important distinction:** Timer resolution is NOT the same as input/render latency.

- **Timer resolution** = System scheduling granularity (how precisely Windows can wake threads)
- **Input/render latency** = What Nvidia overlay shows (0.0-0.1ms is normal with Reflex)

Windows default timer resolution is ~15.6ms. Setting it to 0.5-1ms improves:
- Frame pacing consistency (less microstutter)
- More precise sleep() calls in game loops
- Tighter multimedia scheduling

**This does NOT directly reduce input latency** - that's controlled by:
- Nvidia Reflex / Low Latency Mode
- Frame queue depth
- Display pipeline (VSync, G-Sync)
- USB polling rate

Most modern games automatically request higher timer resolution when running.

```python
# Requires calling NtSetTimerResolution via ctypes
# Or use a utility like TimerTool / ISLC (Intelligent Standby List Cleaner)

import ctypes
ntdll = ctypes.WinDLL('ntdll')
# NtSetTimerResolution(DesiredResolution, SetResolution, CurrentResolution)
# DesiredResolution in 100ns units: 10000 = 1ms, 5000 = 0.5ms
current = ctypes.c_ulong()
ntdll.NtSetTimerResolution(5000, True, ctypes.byref(current))
```

### Nagle's Algorithm (Network Latency)
```python
# Find interface GUIDs first, then for each:
key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{GUID}"
key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_ALL_ACCESS)
winreg.SetValueEx(key, "TcpAckFrequency", 0, winreg.REG_DWORD, 1)
winreg.SetValueEx(key, "TCPNoDelay", 0, winreg.REG_DWORD, 1)
```

---

## Power Plan Management

```python
import subprocess

# List power plans
result = subprocess.run(['powercfg', '/list'], capture_output=True, text=True)

# Create Ultimate Performance plan (if not exists)
subprocess.run(['powercfg', '/duplicatescheme', 'e9a42b02-d5df-448d-aa00-03f14749eb61'])

# Set active plan
subprocess.run(['powercfg', '/setactive', 'SCHEME_GUID'])

# Export plan for backup
subprocess.run(['powercfg', '/export', 'backup.pow', 'SCHEME_GUID'])

# Import plan
subprocess.run(['powercfg', '/import', 'backup.pow'])
```

### Key Power Settings for Gaming
```bash
# Disable USB selective suspend
powercfg /setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0

# Disable PCI Express Link State Power Management
powercfg /setacvalueindex SCHEME_CURRENT 501a4d13-42af-4429-9fd1-a8218c268e20 ee12f906-d277-404b-b6da-e5fa1a576df5 0

# Processor min/max state = 100%
powercfg /setacvalueindex SCHEME_CURRENT 54533251-82be-4824-96c1-47b60b740d00 893dee8e-2bef-41e0-89c6-b55d0929964c 100
powercfg /setacvalueindex SCHEME_CURRENT 54533251-82be-4824-96c1-47b60b740d00 bc5038f7-23e0-4960-96da-33abaf5935ec 100
```

---

## Backup System Implementation

```python
import json
import shutil
from datetime import datetime
from pathlib import Path

class BackupManager:
    def __init__(self, backup_dir: Path):
        self.backup_dir = backup_dir

    def create_backup(self, handlers: list[SettingsHandler]) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_path = self.backup_dir / timestamp
        backup_path.mkdir(parents=True)

        manifest = {
            "timestamp": timestamp,
            "components": {}
        }

        for handler in handlers:
            name = handler.__class__.__name__
            data = handler.backup()

            # Save component backup
            component_path = backup_path / f"{name}.json"
            with open(component_path, 'w') as f:
                json.dump(data, f, indent=2)

            manifest["components"][name] = str(component_path)

        # Save manifest
        with open(backup_path / "manifest.json", 'w') as f:
            json.dump(manifest, f, indent=2)

        return timestamp

    def restore_backup(self, timestamp: str, handlers: dict[str, SettingsHandler]):
        backup_path = self.backup_dir / timestamp
        manifest_path = backup_path / "manifest.json"

        with open(manifest_path) as f:
            manifest = json.load(f)

        for name, path in manifest["components"].items():
            with open(path) as f:
                data = json.load(f)
            handlers[name].restore(data)
```

---

## Game-Specific Profiles

### Slippi Melee (Super Smash Bros. Melee via Dolphin)

**Executable hints:** `Slippi Dolphin.exe`, `Dolphin.exe`

**Critical settings:**
- **Graphics backend:** Vulkan (lowest latency on most systems, test vs D3D12)
- **VSync:** Off in Dolphin
- **Fullscreen mode:** Exclusive OR Borderless (Windows 11 borderless has similar latency)
- **Audio backend:** Cubeb or XAudio2, lowest latency buffer
- **Adapter polling:** 125Hz USB polling minimum; 1000Hz if using overclocked adapter
- **Faster Melee / UCF:** Handled by Slippi, not system-level

**Nvidia profile:**
- Low Latency Mode: On (Ultra may cause stutter in emulators - test first)
- VSync: Off
- Power Management: Prefer Maximum Performance
- Max Frame Rate: Off
- G-Sync: Test on vs off (some report issues with 60fps lock)

**Windows:**
- Fullscreen optimizations: Test with/without on Windows 11
- Game Mode: On
- HAGS: Test (mixed reports for emulators, often helps on 30/40 series)

**Network (for online play):**
- Nagle disabled
- Slippi uses UDP; ensure router QoS prioritizes or doesn't throttle

**In-game recommendations (Dolphin settings):**
```markdown
## Slippi Dolphin Settings

### Graphics
- Backend: Vulkan
- VSync: Off
- Fullscreen: Exclusive (not borderless)
- Internal Resolution: Native or 2x (higher adds no latency but uses GPU)

### Audio
- Backend: Cubeb (or XAudio2)
- Latency: Lowest stable setting

### Controller
- Ensure adapter is in Wii U / Switch mode (not PC mode)
- Background Input: On (if alt-tabbing during matches)
```

---

### Call of Duty: Black Ops 7

**Executable hints:** `cod.exe`, `BlackOps7.exe` (verify actual executable name)

**Priority:** Low latency, high stable FPS

**Nvidia profile:**
- Low Latency Mode: **Off** (Reflex handles this - don't double up)
- Reflex: Enable in-game **On + Boost** (takes priority over driver setting)
- VSync: Off
- Power Management: Prefer Maximum Performance
- Shader Cache: Unlimited (CoD compiles many shaders)

**Important:** When a game has Nvidia Reflex, you should NOT use driver Low Latency Mode.
Reflex is more effective and combining them can cause stuttering.

**In-game recommendations:**
```markdown
## Call of Duty: Black Ops 7 Settings

### Display
- Display Mode: Fullscreen Exclusive (or Borderless on Windows 11)
- VSync: Off
- Nvidia Reflex Low Latency: On + Boost
- Frame Rate Limit: Match monitor Hz or cap 3 below for G-Sync

### Graphics
- Render Resolution: 100% (or use DLSS Performance if GPU-bound)
- On-Demand Texture Streaming: Off (if VRAM allows)
- Shader Quality: Restart game after first launch to compile shaders

### Audio
- Audio Mix: Headphones or appropriate preset
- Reduce unnecessary audio processing
```

---

### Diablo 4

**Executable hints:** `Diablo IV.exe`

**Priority:** Stable FPS, balanced visuals, less latency-critical than competitive shooters

**Nvidia profile:**
- Low Latency Mode: On (not Ultra)
- VSync: On or use frame limiter (screen tearing less critical in ARPG)
- Power Management: Prefer Maximum Performance
- G-Sync: Enabled

**In-game recommendations:**
```markdown
## Diablo 4 Settings

### Display
- Display Mode: Fullscreen
- VSync: Off if using G-Sync, otherwise On
- Limit FPS: 2-3 below monitor refresh (G-Sync sweet spot)
- DLSS/FSR: Quality or Balanced

### Graphics
- Adjust based on GPU headroom
- Prioritize stable frame times over max settings
```

---

## Troubleshooting After Optimization

If you experience issues after applying optimizations:

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Audio crackling/stuttering | SystemResponsiveness = 0 | Restore to 10-20 |
| USB devices disconnecting | Power plan USB settings | Restore power plan |
| Game stuttering | Low Latency Mode Ultra | Change to On or Off |
| Screen tearing | VSync disabled without VRR | Enable VSync or G-Sync |
| System feels sluggish | Aggressive CPU settings | Restore backup |
| Driver crashes | NPI profile incompatibility | Restore NPI backup |

**Use `python -m gametune restore latest` to quickly revert all changes.**

---

## Common Pitfalls

1. **UAC elevation** — Many operations silently fail without admin. Always check and elevate.

2. **Registry paths vary by Windows version** — Test on target Windows 11 build.

3. **Nvidia settings require driver restart** — Some changes only take effect after restarting the Nvidia Display Driver Service or rebooting.

4. **HAGS varies by GPU generation** — Generally beneficial on RTX 30/40 series, test on older GPUs.

5. **VBS requires reboot** — Changes to Memory Integrity don't apply until restart.

6. **Backup before anything** — The #1 rule. Never apply without backup.

7. **Profile Inspector version matters** — Ensure using a version compatible with current drivers.

8. **Game updates change optimal settings** — Profiles may need updates after game patches.

9. **Reflex vs Low Latency Mode** — If a game has Nvidia Reflex, use that instead of driver Low Latency Mode. They can conflict.

---

## Resources

- [Nvidia Profile Inspector GitHub](https://github.com/Orbmu2k/nvidiaProfileInspector)
- [NVAPI Documentation](https://developer.nvidia.com/nvapi)
- [WMI Classes Reference](https://docs.microsoft.com/en-us/windows/win32/cimwin32prov/computer-system-hardware-classes)
- [Windows Registry Gaming Tweaks (Calamity)](https://github.com/djdallmann/GamingPCSetup)
- [Battle(non)sense YouTube](https://www.youtube.com/c/BattleNonSense) — Input lag testing methodology
- [Blur Busters](https://blurbusters.com/) — Display and latency science
- [Slippi Documentation](https://slippi.gg/)
