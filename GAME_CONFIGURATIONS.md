# A.B.S.O. Game Configuration Reference

**Version:** January 2026
**Purpose:** Complete documentation of game optimization profiles for external review

---

## What is A.B.S.O.?

**A.B.S.O.** (**A**daptive **B**attle **S**tation **O**ptimizer) is a Windows 11 gaming optimization tool designed for enthusiast gamers. It:

- Auto-detects gaming hardware (GPU, CPU, monitor, peripherals)
- Audits system configuration for gaming optimization issues
- Applies game-specific optimization profiles
- Manages backups and rollbacks of all changes (safety-first approach)

**Target User:** Single enthusiast gamer on Windows 11 with NVIDIA GPU.
**Philosophy:** Aggressive latency optimization with comprehensive backup/rollback for safety.

---

## Architecture Overview

ABSO uses a modular **Settings Handler** pattern where each system domain (NVIDIA, Windows, Power, Network, etc.) has a dedicated handler that can:
- **Detect** current state
- **Audit** for problems
- **Apply** profile settings
- **Backup** current settings
- **Restore** from backup

Game profiles combine settings from multiple handlers to achieve specific optimization goals.

---

## Settings Handlers

Each profile configures some or all of these system components:

| Handler | Description |
|---------|-------------|
| **WindowsSettingsHandler** | Game Mode, Game Bar, Game DVR, HAGS, HDR, Auto HDR, VRR Optimize |
| **PowerSettingsHandler** | Power plans, USB suspend, PCIe power saving, processor performance |
| **RegistrySettingsHandler** | System responsiveness, network throttling, process priority, quantum settings |
| **NvidiaSettingsHandler** | Low Latency Mode, VSync, Power Management, Shader Cache, Threaded Optimization, G-Sync |
| **NetworkSettingsHandler** | Nagle's algorithm, TCP optimizations |
| **MouseSettingsHandler** | Mouse acceleration, linear curve |
| **GraphicsSettingsHandler** | Fullscreen Optimizations (FSO), Multi-Plane Overlay (MPO) |
| **ServicesSettingsHandler** | Background services (SysMain, DiagTrack, etc.) |
| **MemorySettingsHandler** | System cache, paging executive |
| **ProcessPriorityHandler** | GPU/CPU/IO priority for game executables |
| **CNMSettingsHandler** | Stops CNM service during gaming (prevents power interference) |
| **DolphinConfigHandler** | Dolphin emulator-specific config fixes |
| **Rivals2ConfigHandler** | Rivals 2-specific game config enforcement |
| **NvidiaNotificationHandler** | Disables NVIDIA notifications that break fullscreen |

---

## NVIDIA Presets

Profiles use predefined NVIDIA presets that configure multiple driver settings:

### `minimum_latency`
**Use:** Fixed framerate games where tearing is acceptable
- Low Latency Mode: **Ultra**
- VSync: **Off**
- Power Management: **Prefer Maximum Performance**
- Shader Cache: **Unlimited**
- G-Sync per-app: **Force Off**
- *Warning: Causes tearing*

### `no_sync_fighting_game`
**Use:** Fighting games prioritizing absolute minimum latency
- Low Latency Mode: **On** (can cause stutter on some systems)
- VSync: **Off**
- Power Management: **Prefer Maximum Performance**
- Shader Cache: **Unlimited**
- Triple Buffering: **Off**
- G-Sync per-app: **Force Off**
- *Warning: Causes tearing. At 300Hz+, tearing is less perceptible.*

### `vrr_fighting_game`
**Use:** Fighting games with tear-free visuals via G-Sync/VRR
- Low Latency Mode: **On** (not Ultra - it overrides FPS caps)
- VSync: **On** (safety net, never activates with proper FPS cap)
- Power Management: **Prefer Maximum Performance**
- Shader Cache: **Unlimited**
- Triple Buffering: **Off**
- *Note: FPS cap at refresh_rate - 3 required*

### `vrr_diablo4`
**Use:** Diablo 4 with native NVIDIA Reflex
- Low Latency Mode: **Off** (Reflex handles this)
- VSync: **Off**
- Power Management: **Prefer Maximum Performance**
- Shader Cache: **Unlimited**
- Threaded Optimization: **Off**
- Triple Buffering: **Off**
- *Enable Reflex "On + Boost" in-game*

### `reflex_game`
**Use:** Games with native NVIDIA Reflex (CoD, Apex, Valorant, etc.)
- Low Latency Mode: **Off** (CRITICAL - Reflex replaces this)
- VSync: **Off**
- Power Management: **Prefer Maximum Performance**
- Shader Cache: **Unlimited**
- Threaded Optimization: **On**
- *Never combine driver LLM with in-game Reflex*

### `balanced`
**Use:** Games where visual quality matters as much as latency
- Low Latency Mode: **On**
- VSync: **Adaptive**
- Power Management: **Prefer Maximum Performance**
- Shader Cache: **Unlimited**
- Threaded Optimization: **Auto**

---

## Game Profiles

---

### 1. Super Smash Bros. Melee (Slippi)

**Profile IDs:** `slippi-melee`, `slippi-melee-oled`, `slippi-melee-vrr`
**Executables:** `Slippi Dolphin.exe`, `Dolphin.exe`
**Optimization Target:** Minimum latency for competitive play

#### Key Findings (January 2026)
- **DX12 + HAGS ON = 0.0ms render latency** (confirmed on RTX 4070 + i9-14900F)
- DX11 + HAGS causes micro-stutters - avoid this combination
- Lower internal resolution = measurably lower render latency
- G-Sync/VSync disabled - fixed 60fps games don't benefit from VRR

#### System Settings

| Setting | Value | Reason |
|---------|-------|--------|
| HAGS | **On** | Required for 0.0ms render latency with DX12 |
| Game Mode | On | Prioritizes game processes |
| Game Bar | Off | Reduces overhead |
| Game DVR | Off | Prevents background recording |
| HDR | Off | Melee is SDR content |
| VRR Optimize | **Off (critical)** | Adds ~0.1ms latency even in exclusive fullscreen |

#### Power Settings

| Setting | Value |
|---------|-------|
| Power Plan | Ultimate Performance |
| USB Suspend | Disabled |
| PCIe Power Saving | Disabled |
| Processor Performance | Maximum |

#### NVIDIA Settings (minimum_latency preset)

| Setting | Value | Reason |
|---------|-------|--------|
| G-SYNC | **Off** | Fixed 60fps doesn't need VRR |
| V-SYNC | **Off** | Eliminates sync latency |
| Low Latency Mode | **Ultra** | Just-in-time frame submission |
| Threaded Optimization | Off | Reduces driver overhead for emulation |
| Triple Buffering | Off | Only works with VSync |
| Max Frame Rate | Off | No artificial limiting |

#### Dolphin Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Backend | **Direct3D 12** | Required for HAGS benefit |
| VSync | Off | No sync anywhere |
| Fullscreen Mode | Exclusive | Lower latency than borderless |
| Internal Resolution | Native (1x) or 2x max | Lower res = lower render latency |
| EFB Scale | 1 (Native) | Lowest render latency |
| BackendMultithreading | False | Reduces driver overhead |
| UseScalingFilter | False | Scaling adds GPU overhead |
| UseDePosterize | False | Post-processing adds overhead |
| EFBAccessEnable | False | EFB access is slow |
| EnableGPUTextureDecoding | True | Offloads to GPU |

#### Audio Settings

| Setting | Value |
|---------|-------|
| Backend | Exclusive WASAPI (Ishiiruka) / Cubeb (Mainline) |
| Latency | Lowest stable |

#### Controller Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Adapter Mode | Wii U / Switch mode | Native adapter has lower latency than PC mode |
| Background Input | On | Input works when alt-tabbed |

#### Display Notes
- 60fps @ 60Hz = ~17ms scanout, 60fps @ 240Hz = ~4ms scanout
- High refresh benefits from faster pixel refresh, NOT from VRR
- Tearing is minimal at high refresh rates - tears move faster

#### OLED Variant (`slippi-melee-oled`)
Identical to base profile. HDR remains **disabled** because Melee is SDR content - enabling HDR causes washed-out colors.

---

### 2. Rivals of Aether 2

**Profile IDs:** `rivals2`, `rivals2-oled`, `rivals2-oled-vrr`, `rivals2-oled-vrr-multimon`, `rivals2-offline`, `rivals2-online`
**Executables:** `Rivals2-Win64-Shipping.exe`, `RivalsofAether2.exe`, `Rivals2.exe`
**Optimization Target:** Minimum latency for competitive platform fighting

#### Key Characteristics
- Native UE5 game (unlike emulated Melee)
- 60Hz game logic - receives new gameplay info 60 times/sec regardless of render FPS
- Higher FPS provides: faster frame delivery, reduced display latency, smoother motion
- **No NVIDIA Reflex support** - LLM has limited effect in DX12/UE5

#### TWO CONFIGURATIONS PROVIDED

##### Default: No-Sync (Absolute Minimum Latency)
**Setup:** G-SYNC OFF, V-SYNC OFF, 300Hz, Uncapped/240 FPS

| Component | Setting | Value |
|-----------|---------|-------|
| NVCP | Set up G-SYNC | **Unchecked (Disabled)** |
| NVCP | Vertical sync | Off |
| NVCP | Low Latency Mode | On (or Off if stuttering) |
| NVCP | Max Frame Rate | Off |
| NVCP | Power management | Prefer maximum performance |
| NVCP | Triple buffering | Off |
| NVCP | Preferred refresh rate | 300Hz (highest) |
| Windows | Refresh Rate | 300Hz |
| Windows | Variable refresh rate | Off |
| In-Game | V-SYNC | Off |
| In-Game | Frame Rate Cap | 999 (uncapped) |
| In-Game | Display Mode | Exclusive Fullscreen |

*At 300Hz, tearing is barely visible (~3.33ms tear lines). This is the competitive standard for fighting games.*

##### Alternative: VRR (Tear-Free)
**Setup:** G-SYNC ON, V-SYNC ON (NVCP), in-game cap at refresh-3

| Component | Setting | Value |
|-----------|---------|-------|
| NVCP | Set up G-SYNC | Enabled |
| NVCP | Vertical sync | On (safety net only) |
| NVCP | Low Latency Mode | On (not Ultra) |
| In-Game | V-SYNC | **Off (critical)** |
| In-Game | Frame Rate Cap | 297 (for 300Hz) |
| In-Game | Display Mode | Exclusive Fullscreen |

*Adds ~2-5ms latency vs no-sync. V-SYNC never activates with FPS capped below refresh.*

#### System Settings

| Setting | Value | Reason |
|---------|-------|--------|
| HAGS | On | UE5 benefits when GFE removed |
| HDR | **Off** | Rivals 2 is SDR - HDR causes washed colors |
| Auto HDR | Off | Game is SDR |
| VRR Optimize | **Off** | Adds latency even in fullscreen |
| Game Mode | On | Process priority |
| Game Bar | Off | Reduces overhead |
| Game DVR | Off | No recording |

#### Power Settings

| Setting | Value |
|---------|-------|
| Power Plan | Ultimate Performance |
| USB Suspend | Disabled |
| PCIe Power Saving | Disabled |
| Processor Performance | Maximum |

#### Latency Comparison (300Hz Monitor)

| Configuration | Scanout | Limiter | Tearing | Notes |
|---------------|---------|---------|---------|-------|
| No sync, 999 cap | ~3.3ms | ~0ms | Yes | **LOWEST (DEFAULT)** |
| G-SYNC+VSYNC, 297 cap | ~3.4ms | ~0.5ms | No | +2-3ms vs no-sync |

#### Troubleshooting
If experiencing micro-stuttering:
1. Set Low Latency Mode to **Off** in NVCP
2. Use NPI to set Max Pre-Rendered Frames to **2**
3. If still stuttering, try Pre-Rendered Frames = 3

---

### 2a. Rivals 2: Offline / Training Profile

**Profile ID:** `rivals2-offline`
**Use Case:** Training mode, local versus, CPU matches, replay review

#### Aggressive Settings (NOT for online)

| Component | Setting | Value |
|-----------|---------|-------|
| NVCP | Vertical Sync | **Fast** |
| NVCP | Low Latency Mode | **Ultra** |
| NVCP | Max Frame Rate | 297 (refresh - 3) |
| Power Plan | Ultimate Performance | With core parking disabled |

**External Tools:** RTSS, frame pacing hooks **ALLOWED**

---

### 2b. Rivals 2: Online / Matchmaking Profile

**Profile ID:** `rivals2-online`
**Use Case:** Ranked, unranked, any rollback-enabled session

#### EXPLICIT PROHIBITIONS
- LLM = Ultra
- V-Sync = Fast
- External FPS caps
- Refresh - 3 logic
- Forced zero-buffer pipelines

*Rationale: A 300Hz display has insufficient timing margin for refresh-3 logic online. 297 FPS WILL fail under rollback conditions. Stability is prioritized over theoretical latency online.*

#### Conservative Settings

| Component | Setting | Value | Reason |
|-----------|---------|-------|--------|
| NVCP | Vertical Sync | **On** (not Fast) | Deterministic frame pacing |
| NVCP | Low Latency Mode | **On** (not Ultra) | Ultra causes rollback contention |
| NVCP | Max Frame Rate | **Disabled** | Let VRR handle naturally |
| Power Plan | Ultimate Performance | Standardized for consistent clocks |
| CPU Priority | Normal-High | Not aggressive |

**External Tools:** RTSS, frame limiters **DISABLED**

---

### 3. Call of Duty: Black Ops 7

**Profile IDs:** `cod-bo7`, `cod-bo7-oled`
**Executables:** `cod.exe`, `BlackOps7.exe`
**Optimization Target:** Low latency with stable high FPS

#### Key Point: Native NVIDIA Reflex
CoD has built-in NVIDIA Reflex. **Driver Low Latency Mode conflicts with Reflex** and can cause stuttering/increased latency.

#### System Settings

| Setting | Value | Reason |
|---------|-------|--------|
| HAGS | On | Helps latency when GFE removed |
| HDR | Off | Competitive play - processing overhead |
| VRR Optimize | Off | Adds latency |
| Game Mode | On | |
| Game Bar | Off | |
| Game DVR | Off | |

#### NVIDIA Settings (reflex_game preset)

| Setting | Value | Reason |
|---------|-------|--------|
| Low Latency Mode | **Off** | Reflex handles this |
| VSync | Off | Game/Reflex handles sync |
| Power Management | Prefer Maximum Performance | |
| Shader Cache | Unlimited | |
| Threaded Optimization | On | |

#### In-Game Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Display Mode | Fullscreen Exclusive | Lower latency than borderless |
| VSync | Off | Use Reflex instead |
| **Nvidia Reflex Low Latency** | **On + Boost** | Hardware-level latency reduction |
| Frame Rate Limit | Match monitor Hz or Unlimited | |
| Render Resolution | 100% (or DLSS Performance if GPU-limited) | |
| On-Demand Texture Streaming | Off | Eliminates pop-in |
| Shaders | Restart after first launch | Let shaders compile |

---

### 4. Diablo 4

**Profile IDs:** `diablo4`, `diablo4-oled`, `diablo4-oled-vrr`
**Executables:** `Diablo IV.exe`
**Optimization Target:** Balanced (stable FPS with visual quality)

*Less latency-critical than shooters/fighters*

#### System Settings

| Setting | Value |
|---------|-------|
| HAGS | On |
| Game Mode | On |
| Game Bar | Off |
| Game DVR | Off |

#### Power Settings

| Setting | Value |
|---------|-------|
| Power Plan | Ultimate Performance |
| USB Suspend | Disabled |
| PCIe Power Saving | Disabled |

#### NVIDIA Settings (balanced preset)

| Setting | Value |
|---------|-------|
| Low Latency Mode | On (not Ultra) |
| VSync | Adaptive |
| Power Management | Prefer Maximum Performance |
| Shader Cache | Unlimited |
| Threaded Optimization | Auto |

#### In-Game Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Display Mode | Fullscreen | Better than windowed |
| VSync | Off (if G-Sync) / On (otherwise) | G-Sync handles sync |
| Limit FPS | 2-3 below monitor refresh | G-Sync sweet spot |
| DLSS/FSR | Quality or Balanced | Good quality + performance |
| Effects | Medium-High | High can cause drops in combat |

#### OLED VRR Variant (`diablo4-oled-vrr`)
Uses `vrr_diablo4` preset with:
- Native HDR **enabled** (Diablo 4 has excellent HDR)
- Reflex **On + Boost** in-game
- Threaded Optimization **Off**

---

### 5. SSBU / HewDraw Remix (Ryujinx)

**Profile IDs:** `ryujinx-ssbu`, `ryujinx-ssbu-oled`, `ryujinx-ssbu-vrr`
**Executables:** `Ryujinx.exe`, `Ryujinx.Ava.exe`, `Ryujinx.Headless.SDL2.exe`
**Optimization Target:** Minimum latency for competitive SSBU/HDR

*HewDraw Remix (HDR) is a comprehensive gameplay mod making SSBU play more like traditional platform fighters.*

#### Key Points
- SSBU runs at 60fps - same optimization approach as Melee
- Ryujinx uses Vulkan which works well with HAGS
- First run has shader compilation stutter - cached by PPTC

#### System Settings

| Setting | Value | Reason |
|---------|-------|--------|
| HAGS | On | Vulkan benefits from HAGS |
| HDR | Off | SSBU is SDR content |
| VRR Optimize | Off | Adds compositor overhead |
| Game Mode | On | |

#### NVIDIA Settings (minimum_latency preset)

| Setting | Value | Reason |
|---------|-------|--------|
| G-SYNC | Off | Fixed 60fps doesn't need VRR |
| V-SYNC | Off | Eliminates sync latency |
| Low Latency Mode | On or Ultra | Stable for locked 60fps |
| Shader Cache Size | **Unlimited** | Critical for emulators! |
| Threaded Optimization | On | Benefits shader compilation |

#### Ryujinx Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Graphics Backend | **Vulkan** | Better performance than OpenGL |
| Enable VSync | Off | Let NVCP handle (which we disable) |
| Resolution Scale | Native (1x) or 2x | Prioritize latency |
| Anti-Aliasing | None | Adds overhead |
| Scaling Filter | Bilinear or Nearest | Simple = low overhead |
| **Enable PPTC** | **On** | Critical - caches compiled code |
| FS Integrity Checks | Off | Speeds loading |
| Memory Manager Mode | Host Unchecked | Fastest mode |

#### Controller Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Controller Type | Pro Controller | Best SSBU mapping |
| Input Device | Wired or 2.4GHz | Bluetooth adds 10-20ms+ |

#### HewDraw Remix Installation
- Place mod files in: `mods/contents/01006A800016E000/`
- Use Skyline or ARCropolis mod framework
- Training mode features: frame data display, input display

---

### 6. Pokemon Auto Chess (Browser)

**Profile ID:** `pokemon-auto-chess`, `pokemon-auto-chess-oled`
**Executables:** `chrome.exe`, `msedge.exe`, `firefox.exe`, `brave.exe`
**Optimization Target:** Balanced (stable WebGL performance)

*Browser-based WebGL auto-battler - less latency-sensitive than competitive games*

#### System Settings

| Setting | Value |
|---------|-------|
| HAGS | On |
| Game Mode | On |
| Power Plan | Ultimate Performance |

#### NVIDIA Settings

| Setting | Value |
|---------|-------|
| Low Latency Mode | On |
| VSync | Off |
| Shader Cache | Unlimited (WebGL uses many shaders) |
| Triple Buffering | Off |

#### Chrome/Browser Settings

| Setting | Value | Location |
|---------|-------|----------|
| Hardware Acceleration | Enabled | chrome://gpu |
| Use Angle Backend | D3D11 (often fastest) | chrome://flags/#use-angle |
| WebGL Developer Extensions | Enabled | chrome://flags |
| GPU Rasterization | Enabled | chrome://flags |

#### Browser Optimization
- Close/suspend inactive tabs
- Disable heavy extensions while playing
- Use F11 for fullscreen

---

### 7. PACDeluxe (Tauri Desktop Client)

**Profile ID:** `pacdeluxe`, `pacdeluxe-oled`
**Executables:** `PACDeluxe.exe`, `msedge.exe`
**Optimization Target:** Smooth framerate for WebGL auto-battler

*Native Windows 11 desktop client wrapping Pokemon Auto Chess in Tauri v2 shell using WebView2.*

#### Internal App Optimizations (already applied by PACDeluxe)
- ABOVE_NORMAL_PRIORITY_CLASS
- 1ms timer resolution via timeBeginPeriod
- DWM transition animations disabled
- Priority boost disabled for consistent timing

#### System Settings

| Setting | Value |
|---------|-------|
| HAGS | On (works well with WebView2) |
| Power Plan | Ultimate Performance |

#### NVIDIA Settings (balanced preset)

| Setting | Value | Reason |
|---------|-------|--------|
| Preferred GPU | High-performance NVIDIA | Ensure discrete GPU |
| Power Management | Prefer Maximum Performance | |
| Shader Cache Size | Unlimited | WebGL generates many shaders |
| Vertical Sync | Adaptive (or Off) | |
| Low Latency Mode | On | |

#### In-App Features
- Performance Overlay: `Ctrl+Shift+P`
- Fullscreen: `Alt+Enter` or `F11`

---

### 8. Productivity (OLED + HDR)

**Profile ID:** `productivity-oled`
**Executables:** Code.exe, devenv.exe, chrome.exe, firefox.exe, msedge.exe, etc.
**Optimization Target:** Productivity (NOT gaming)

*For multi-monitor browsing and coding with HDR enabled.*

#### Key Differences from Gaming Profiles
- HDR **enabled** (OLED panels excel at HDR)
- VRR **enabled** (smooth scrolling)
- Background services **remain enabled** (snappy app launching)
- No aggressive latency optimizations
- Balanced power (lower heat/noise)

#### System Settings

| Setting | Value | Reason |
|---------|-------|--------|
| HAGS | On | Smooth desktop compositing |
| **HDR** | **On** | OLED benefit |
| Auto HDR | Off | Not gaming |
| **VRR Optimize** | **On** | Smooth scrolling |
| Game Mode | On | Compatibility |
| Game Bar | Off | |

#### NVIDIA Settings (balanced preset)

| Setting | Value |
|---------|-------|
| Low Latency Mode | On |
| VSync | Adaptive |
| Threaded Optimization | Auto |

#### Display Recommendations

| Setting | Value | Reason |
|---------|-------|--------|
| SDR content brightness | 40-50% | Comfortable for coding |
| Night Light | Scheduled (evening) | Reduces blue light |
| Refresh Rate | Maximum | Smoother scrolling/cursor |

#### OLED Care
- Screen timeout: 5-10 minutes
- Dark mode in Windows and apps
- Consider taskbar auto-hide
- Run pixel refresh periodically

---

## Common Settings Across All Gaming Profiles

These settings appear in most/all gaming profiles:

### Windows Settings
| Setting | Value | Reason |
|---------|-------|--------|
| Game Mode | On | Prioritizes game processes |
| Game Bar | Off | Reduces overlay overhead |
| Game DVR | Off | Prevents background recording |

### Network Settings
| Setting | Value | Reason |
|---------|-------|--------|
| Nagle's Algorithm | Disabled | Reduces network latency |
| Preset | Gaming | TCP optimizations |

### Mouse Settings
| Setting | Value | Reason |
|---------|-------|--------|
| Acceleration | Disabled | Consistent muscle memory |
| Linear Curve | Enabled | 1:1 input mapping |

### Memory Settings
| Setting | Value | Reason |
|---------|-------|--------|
| Large System Cache | 0 | Optimize for applications |
| Disable Paging Executive | 1 | Keep kernel in RAM |

### Registry Settings
| Setting | Value | Reason |
|---------|-------|--------|
| System Responsiveness | 0 | Maximum game priority |
| Network Throttling | 0xFFFFFFFF | Disabled |
| Win32PrioritySeparation | 0x2A | Short fixed quantum, max foreground boost |

---

## Important Notes

### G-Sync/VRR Decision Tree

```
Is the game FIXED framerate (e.g., 60fps emulator)?
├── YES → G-Sync OFF, VSync OFF, run at max refresh
│         (High refresh = faster scanout, not VRR benefit)
│
└── NO → Is minimum latency more important than tear-free?
         ├── YES → G-Sync OFF, VSync OFF (No-Sync setup)
         └── NO → G-Sync ON, VSync ON in NVCP,
                  FPS cap at refresh-3,
                  VSync OFF in-game
```

### Low Latency Mode Notes
- **Only works in DX9/DX11** - limited effect in DX12/Vulkan
- **"Ultra" auto-caps FPS** - use "On" with manual caps
- **Can cause stutter** on some systems - try "Off" or Pre-Rendered Frames = 2
- **Never combine with NVIDIA Reflex** - causes conflicts

### HAGS (Hardware Accelerated GPU Scheduling)
- **Enable for:** DX12 games, Vulkan games, emulators using DX12/Vulkan
- **Can cause issues with:** Some DX11 games
- **Test both:** If experiencing stutter, try toggling HAGS

### VRR Optimize (Windows Setting)
- **Almost always OFF for gaming** - adds latency even in exclusive fullscreen
- **Only ON for:** Productivity/desktop use where smooth scrolling matters

### HDR
- **Only enable if:** Game has native HDR support
- **Disable for:** SDR games (emulators, older games, Rivals 2)
- **SDR + HDR enabled =** washed-out colors

---

## Backup and Restore

ABSO creates timestamped backups before any changes:
- Location: `/backups/` directory
- Contains: `manifest.json` tracking all components
- Restore: `python -m abso restore latest`

**Safety Philosophy:** Always backup before apply. Never modify without a restore point.

---

## Quick Reference: Profile Selection

| Game | Profile | Key Setting |
|------|---------|-------------|
| Slippi Melee | `slippi-melee` | DX12 + HAGS ON |
| Rivals 2 (training) | `rivals2-offline` | LLM Ultra allowed |
| Rivals 2 (ranked) | `rivals2-online` | Conservative/stable |
| CoD BO7 | `cod-bo7` | Use in-game Reflex |
| Diablo 4 | `diablo4` | Balanced preset |
| SSBU/HDR (Ryujinx) | `ryujinx-ssbu` | Vulkan + PPTC |
| Pokemon Auto Chess | `pokemon-auto-chess` | Browser optimizations |
| Productivity | `productivity-oled` | HDR + VRR enabled |

---

*Document generated from ABSO codebase - January 2026*
