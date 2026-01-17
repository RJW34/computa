# Rivals 2 Golden Config Checklist
## ~1.2ms Render / 0ms Input Latency - Complete System State

**Last Verified:** 2026-01-16
**Hardware:** RTX 4070, i9-14900F, 32GB RAM, LG UltraGear 300Hz OLED
**Result:** ~1.2ms render latency, 0ms input latency (controller)

---

## CRITICAL REQUIREMENT: SpecialK Injection

**Without SpecialK, UE5/Rivals 2 forces borderless windowed mode during gameplay, adding 2-7ms latency.**

- [ ] SpecialK installed: `C:\Program Files\Special K\`
- [ ] Launch Rivals 2 via SKIF (SpecialK Injection Frontend)
- [ ] Verify injection: SpecialK64.dll loaded in Rivals2-Win64-Shipping.exe
- [ ] Window Style shows `0x94000000` (true exclusive fullscreen)

---

## 1. HARDWARE/DISPLAY

### Monitor Settings
- [ ] **Refresh Rate:** 300Hz (maximum supported)
- [ ] **G-Sync:** Enabled in monitor OSD
- [ ] **Response Time:** Fastest/Instant mode
- [ ] **Connection:** DisplayPort (required for G-Sync)
- [ ] **Resolution:** 2560x1440 native

### GPU
- [ ] **Model:** NVIDIA GeForce RTX 4070
- [ ] **Driver Version:** 32.0.15.9174 (or newer)
- [ ] **Note:** Test new drivers before updating - regressions happen

---

## 2. WINDOWS SETTINGS

### Graphics Settings (Settings > System > Display > Graphics)
| Setting | Value | Why |
|---------|-------|-----|
| **Hardware-Accelerated GPU Scheduling (HAGS)** | ✅ ON | Helps latency when GFE removed |
| **Optimizations for windowed games (VRR)** | ❌ OFF | HURTS latency - tested |
| **Auto HDR** | ❌ OFF | Rivals 2 is SDR game |

**Registry verification:**
```
HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers
  HwSchMode = 2 (2=ON, 1=OFF)

HKCU\Software\Microsoft\DirectX\UserGpuPreferences
  DirectXUserGlobalSettings = VRROptimizeEnable=0;SwapEffectUpgradeEnable=0;AutoHDREnable=0;
```

### Security Settings (Windows Security > Device Security)
| Setting | Value | Why |
|---------|-------|-----|
| **VBS/Memory Integrity** | ❌ OFF | Major latency killer, 5%+ FPS loss |
| **Core Isolation** | ❌ OFF | Part of VBS |

**Registry verification:**
```
HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity
  Enabled = 0
```

### Game Mode & DVR
| Setting | Value | Why |
|---------|-------|-----|
| **Game Mode** | ✅ ON | Prioritizes game resources |
| **GameDVR** | ❌ OFF | Background recording adds latency |
| **GameDVR_FSEBehavior** | 0 | Don't interfere with fullscreen |

**Registry verification:**
```
HKCU\Software\Microsoft\GameBar
  AllowAutoGameMode = 1

HKCU\System\GameConfigStore
  GameDVR_Enabled = 0
  GameDVR_FSEBehavior = 0
  GameDVR_FSEBehaviorMode = 0
  GameDVR_HonorUserFSEBehaviorMode = 0
  GameDVR_DXGIHonorFSEWindowsCompatible = 0
  GameDVR_EFSEFeatureFlags = 0
```

### Fullscreen Optimizations (FSO)
- [ ] **Disabled for Rivals2.exe**
- [ ] **Disabled for Rivals2-Win64-Shipping.exe**

**Registry verification:**
```
HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers
  C:\...\Rivals 2\Rivals2.exe = ~ DISABLEDXMAXIMIZEDWINDOWEDMODE
  C:\...\Rivals2-Win64-Shipping.exe = ~ DISABLEDXMAXIMIZEDWINDOWEDMODE HIGHDPIAWARE
```

### Multi-Plane Overlay (MPO)
| Setting | Value | Why |
|---------|-------|-----|
| **MPO** | ✅ ENABLED | Required for VRR to work |

**Registry verification:**
```
HKLM\SOFTWARE\Microsoft\Windows\Dwm
  OverlayTestMode = (not set, or not 5) = ENABLED
  OverlayTestMode = 5 = DISABLED
```

### Power Plan
- [ ] **Active Plan:** Ultimate Performance
- [ ] **GUID:** `0b998857-5256-4da3-b351-ddeeba884573`

```powershell
# Verify with:
powercfg /getactivescheme
```

---

## 3. NVIDIA CONTROL PANEL

### Set up G-SYNC (Display section)
| Setting | Value |
|---------|-------|
| **Enable G-SYNC, G-SYNC Compatible** | ✅ Checked |
| **Enable for** | Windowed and full screen mode |
| **Selected Display** | Your primary gaming monitor |

### Manage 3D Settings > Global Settings
| Setting | Value | Why |
|---------|-------|-----|
| **Low Latency Mode** | On | Not Ultra - SpecialK handles aggressive latency |
| **Power Management Mode** | Prefer maximum performance | Prevent downclocking |
| **Vertical Sync** | Off | SpecialK + G-Sync handles sync |
| **Triple Buffering** | Off | Adds frame queue latency |
| **Threaded Optimization** | Off | CRITICAL - reduces render latency |
| **Max Frame Rate** | Off | Use in-game limiter |
| **Shader Cache Size** | Unlimited | Reduce stutters |

### Manage 3D Settings > Program Settings (Rivals 2)
Same as global, but per-application ensures it sticks.

**Note:** Driver updates can reset these. Re-verify after updates.

---

## 4. SPECIALK CONFIGURATION

### Location
`C:\Program Files\Special K\Profiles\Rivals of Aether II\SpecialK.ini`

### Critical Settings
```ini
[Compatibility.General]
DisableBloatWare_NVIDIA=true        # Blocks NVIDIA overlay bloat

[NVIDIA.API]
DisableHDR=true                      # Rivals 2 is SDR

[Window.System]
RenderInBackground=true              # Continue Rendering ON (tested: helps)
AlwaysOnTop=1

[Render.FrameRate]
TargetFPS=0.000000                   # Frame limiter DISABLED (use game's)
PreRenderLimit=-1                    # Let driver/game decide
WaitForVBLANK=false
PresentationInterval=0
EnableMMCSS=true
UseMaxTimerResolution=true           # High-res timers
ForceHighResTimers=true

[Scheduler.Boost]
RaisePriorityInForeground=true       # Priority boost when focused
DenyForeignChanges=true              # Prevent other apps from lowering priority
MinimumRenderThreadPriority=1

[Render.DXGI]
UseFlipDiscard=true                  # Optimal flip model
AllowTearingInDWM=true               # VRR tearing support
DropLateFrames=true                  # Drop late frames for lower latency
DisableVirtualizedBlanking=true
SkipRedundantModeChanges=true

[NVIDIA.Reflex]
Enable=true                          # Reflex ON
LowLatency=true
LowLatencyBoost=true                 # Boost mode
OverrideNativeMode=true              # Override game's Reflex
DisableNative=true                   # Disable game's (broken) Reflex
UseFramerateLimiter=false            # Use game's limiter instead
OptimizeByMarkers=true
EngagementPolicy=1
```

### SpecialK Version
- [ ] **Current:** 25.12.2.5
- [ ] Check for updates at [special-k.info](https://www.special-k.info/)

---

## 5. RIVALS 2 GAME SETTINGS

### Location
`%LOCALAPPDATA%\Rivals2\Saved\Config\Windows\GameUserSettings.ini`

### Video Settings
| Setting | Value | Why |
|---------|-------|-----|
| **Display Mode** | Exclusive Fullscreen (0) | SpecialK enforces this |
| **Resolution** | 2560x1440 | Native resolution |
| **V-Sync** | ❌ OFF | G-Sync handles sync |
| **Frame Rate Limit** | 297 | Refresh rate - 3 for G-Sync headroom |
| **bUseFrameRateLimit** | True | Enable the cap |
| **Dynamic Resolution** | ❌ OFF | Fixed resolution |

**INI verification:**
```ini
[/Script/Engine.GameUserSettings]
bUseVSync=False
FullscreenMode=0
PreferredFullscreenMode=0
FrameRateLimit=297.000000
bUseFrameRateLimit=True
ResolutionSizeX=2560
ResolutionSizeY=1440
bUseDynamicResolution=False
sg.ResolutionQuality=100
```

### Graphics Quality
Set to whatever your GPU can handle while maintaining 297+ FPS.

---

## 6. STEAM SETTINGS

### Launch Options (Right-click > Properties > General > Launch Options)
```
-nooverlay -fullscreen -dx12 -PREFERREDDEVICE=0 -notexturestreaming -nomansky -NoVerifyGC
```

| Flag | Purpose |
|------|---------|
| `-nooverlay` | Disable Steam overlay (SpecialK provides overlay) |
| `-fullscreen` | Request fullscreen (UE5 ignores this, but set anyway) |
| `-dx12` | Force DirectX 12 |
| `-PREFERREDDEVICE=0` | Use primary GPU |
| `-notexturestreaming` | Disable texture streaming (reduces hitches) |
| `-nomansky` | Disable procedural sky effects |
| `-NoVerifyGC` | Skip garbage collection verification |

### Steam Overlay
- [ ] **Disabled** for Rivals 2 (Properties > General > Enable Steam Overlay = OFF)

---

## 7. SERVICES & BACKGROUND PROCESSES

### MUST BE DISABLED/UNINSTALLED
| Service/App | Status | Why |
|-------------|--------|-----|
| **GeForce Experience** | ❌ UNINSTALLED | Adds latency overhead (not just disabled!) |
| **NVIDIA Shield/Broadcast** | ❌ STOPPED + DISABLED | Background processing |

**Verify GFE uninstalled:**
```powershell
Test-Path "C:\Program Files\NVIDIA Corporation\NVIDIA GeForce Experience"
# Should return False
```

**Verify Broadcast stopped:**
```powershell
Get-Service NvBroadcast.ContainerLocalSystem
# Status should be Stopped
```

### RUNNING (OK)
| Service | Status | Notes |
|---------|--------|-------|
| NVDisplay.ContainerLocalSystem | Running | Required for display |
| NvContainerLocalSystem | Running | Required for driver |
| GamingServices | Running | OK if not causing issues |

### NVIDIA Overlay (Latency Monitoring)
- [ ] NVIDIA overlay enabled for latency display (Alt+R to toggle)
- [ ] Shows: Render Latency, Input Latency, FPS

---

## 8. INPUT SETTINGS

### Controller
- [ ] **Connection:** Wired USB (not Bluetooth)
- [ ] **Polling Rate:** Maximum supported by controller
- [ ] SpecialK Input: XInput 1.4 Win32

### SpecialK Input Settings
```ini
[Input.Gamepad]
DisabledToGame=0                     # Don't block gamepad
DisableRumble=true                   # Optional: disable for less overhead
MaxHIDPollingBuffers=3
```

---

## 9. VERIFICATION CHECKLIST

### Before Each Session
1. [ ] Launch SKIF first
2. [ ] Launch Rivals 2 through SKIF
3. [ ] Verify SpecialK overlay appears (Ctrl+Shift+Backspace)
4. [ ] Check NVIDIA overlay shows latency (Alt+R)
5. [ ] Confirm ~1.2ms render / 0ms input latency

### After Windows Updates
- [ ] Re-check VBS/Memory Integrity (often re-enabled)
- [ ] Re-check HAGS setting
- [ ] Re-check power plan
- [ ] Re-verify FSO disabled for Rivals

### After NVIDIA Driver Updates
- [ ] Re-verify NVCP 3D settings
- [ ] Test latency in-game
- [ ] Roll back if regression

### After SpecialK Updates
- [ ] Backup working SpecialK.ini
- [ ] Test after update
- [ ] Restore backup if issues

---

## 10. POTENTIAL 2026 OPTIMIZATIONS TO CONSIDER

Based on current research, these may provide additional benefits:

### Already Optimal (No Changes Needed)
- ✅ HAGS ON with GFE uninstalled (confirmed helps)
- ✅ SpecialK Reflex On+Boost (optimal for UE5)
- ✅ In-game frame limiter (lower latency than RTSS/NVCP)
- ✅ MPO enabled (required for VRR)

### Potentially Worth Testing
| Setting | Current | Potential Change | Risk |
|---------|---------|------------------|------|
| **SpecialK Latent Sync** | Not used | Test if G-Sync fails | Medium |
| **Waitable SwapChain** | Default | Enable in SpecialK | Low |
| **Timer Resolution** | Default | Force 0.5ms globally | Low |
| **NVIDIA driver** | 32.0.15.9174 | Test newer versions | Medium |

### NOT Recommended (Tested/Researched)
- ❌ Continue Rendering OFF (tested: hurts latency)
- ❌ Windows VRR ON (tested: hurts latency)
- ❌ HAGS OFF (tested: helps when GFE removed)
- ❌ Low Latency Mode Ultra (conflicts with manual FPS cap)
- ❌ VSync Fast (OFF is better with SpecialK + G-Sync)

### Monitor for Future Updates
- [ ] Windows 11 24H2+ changes to HAGS/VBS
- [ ] SpecialK VRR optimization improvements
- [ ] NVIDIA driver G-Sync latency improvements
- [ ] Rivals 2 patches affecting fullscreen behavior

---

## 11. TROUBLESHOOTING

### Latency Increased
1. Check Window Style (should be 0x94000000)
2. Verify SpecialK injection active
3. Check NVIDIA overlay not showing N/A
4. Restart SKIF and relaunch game

### G-Sync Not Engaging
1. Verify MPO is ENABLED (not disabled in registry)
2. Check NVCP G-Sync settings
3. Verify monitor connected via DisplayPort
4. Check refresh rate is at maximum

### Stuttering/Hitches
1. Check shader cache (set to Unlimited)
2. Verify power plan (Ultimate Performance)
3. Check background processes
4. Disable texture streaming (-notexturestreaming)

### N/A Showing in Overlay
1. Restart game via SKIF
2. Toggle NVIDIA overlay off/on (Alt+R twice)
3. Check SpecialK Reflex settings
4. Verify game is in foreground

---

## 12. QUICK REFERENCE CARD

```
╔══════════════════════════════════════════════════════════════╗
║              RIVALS 2 GOLDEN CONFIG - QUICK REF              ║
╠══════════════════════════════════════════════════════════════╣
║ WINDOWS:                                                     ║
║   HAGS: ON │ VRR: OFF │ VBS: OFF │ MPO: ON │ FSO: DISABLED  ║
╠══════════════════════════════════════════════════════════════╣
║ NVCP:                                                        ║
║   VSync: OFF │ LLM: ON │ Thread Opt: OFF │ Triple Buf: OFF  ║
╠══════════════════════════════════════════════════════════════╣
║ SPECIALK:                                                    ║
║   Reflex: On+Boost │ Limiter: OFF │ Continue Render: ON     ║
║   FlipDiscard: ON │ AllowTearing: ON │ DropLateFrames: ON   ║
╠══════════════════════════════════════════════════════════════╣
║ GAME:                                                        ║
║   VSync: OFF │ FPS Cap: 297 │ Fullscreen: Exclusive         ║
╠══════════════════════════════════════════════════════════════╣
║ UNINSTALLED: GeForce Experience                              ║
║ DISABLED: NVIDIA Broadcast/Shield, Steam Overlay             ║
╚══════════════════════════════════════════════════════════════╝
```

---

**Document Version:** 1.0
**Created:** 2026-01-16
**Last Updated:** 2026-01-16
