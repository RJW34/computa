# Dolphin Emulator Latency Research Notes

## Document Purpose
Comprehensive research notes for Dolphin emulator latency optimization, specifically for Slippi/Melee competitive play. This document serves as a knowledge base for the computa project.

---

## Key Findings Summary

### Rush Frame Presentation (December 2025)
A major latency feature added to **mainline** Dolphin in late 2025, developed in collaboration with Fizzi (Slippi creator).

> **BUILD GATE — read before acting on any number below.** Rush Frame
> Presentation shipped in *mainline* Dolphin 2512. Slippi Launcher's `netplay`
> Dolphin is historically **Ishiiruka**-based and does not have this option.
> Fizzi collaborating on the mainline feature does not mean the Slippi netplay
> build carries it. ABSO's `DolphinConfigHandler` upserts the `RushPresentation`
> key whether or not the build understands it, so **the key's presence in
> `Dolphin.ini` is not evidence the feature exists**. Confirm it appears in
> Graphics > Advanced before expecting any of the gains below.
>
> Quick lineage check: if `GFX.ini` contains `SimBumpEnabled`,
> `ForcePhongShading`, `PredictiveFifo`, `TextureScalingType`, `EnableOpenCL`,
> or `TessellationEarlyCulling`, the build is Ishiiruka-derived. `abso detect`
> reports this as `build_lineage`.

**What It Does:**
- Skips the presentation queue entirely when GPU is ready
- Reduces end-to-end latency by 8-14ms in testing
- Works best when GPU is not bottlenecked

**Testing Results (Dolphin + Fizzi collaboration):**
| Configuration | Estimated End-to-End Latency |
|---------------|------------------------------|
| Console (CRT) | ~33-50ms (game logic + frame buffer + CRT scanout) |
| Dolphin (tuned profile path) | ~25-40ms (varies by system) |
| Rush Presentation | May reduce by 8-14ms (test for your system) |

**Note:** CRT phosphor response is near-instantaneous (~0ms pixel response). The
console baseline depends heavily on measurement methodology. These are reference
estimates, not precise measurements from a controlled test environment.

**When to Use:**
- Recommended for competitive play when latency is priority
- May cause frame pacing variance on slower GPUs
- Test both ON and OFF for your specific system

### Immediately Present XFB (External Frame Buffer)
Skips the frame buffer queue and presents frames as soon as they're ready.

**Status:** Enabled by default for Melee in Slippi builds

**Effect:**
- Reduces latency by eliminating buffering
- Already active for most Slippi users
- No configuration needed

### Smooth Frame Presentation
Frame pacing optimization designed for VRR displays.

**Mechanism:** Dolphin deliberately **delays presentation by ~1-2ms**, using
previous frame times as a heuristic, so frames come out more evenly. It exists
to stop badly paced games from falling out of a VRR monitor's operating range.

**This is a pacing aid that COSTS latency — it is not a latency feature.**

**When to Use:**
- Only when paired with G-SYNC/VRR *and* you are seeing range dropouts or flicker
- Never for no-sync competitive setups — you are paying 1-2ms for nothing

**Known drift:** Slippi Launcher has been observed with `SmoothPresentation =
True` against an ABSO target of `False`. Every Slippi profile targets it off and
`DolphinConfigHandler.audit()` now checks it.

---

## Graphics Backend Comparison

Backend advice must be scoped to the emulator build. Current mainline Dolphin
guidance is not proof for Slippi Launcher's older Ishiiruka-derived netplay
build. In Slippi Ishiiruka v3.6.4, the Windows backend list/default order is
**D3D11, D3D12, D3D9, OpenGL, Vulkan**. That is compatibility evidence, not a
benchmark ranking, but it makes D3D11 the honest baseline for this exact build.

| Backend | Slippi v3.6.4 posture | Evidence class |
| --- | --- | --- |
| D3D11 | Compatibility baseline and first Windows backend | documented |
| D3D12 | Supported, but its fork backend has little recent maintenance | compatibility / heuristic |
| Vulkan | Supported; test locally if D3D11 has issues | heuristic |
| OpenGL | Supported troubleshooting alternative | compatibility |

ABSO therefore preserves the user's renderer. It does not write
``GFXBackend``. Prefer D3D11 as the initial stability baseline on this Slippi
build, then move to Vulkan or D3D12 only when repeatable frame-time captures on
the same machine show a benefit. The earlier ``0-2ms`` backend-difference claim
had no benchmark artifact in this repository and has been removed.

Primary implementation sources:

- [Slippi Ishiiruka v3.6.4 backend order](https://github.com/project-slippi/Ishiiruka/blob/v3.6.4/Source/Core/VideoCommon/VideoBackendBase.cpp#L70-L116)
- [Slippi stores GFXBackend in Dolphin.ini](https://github.com/project-slippi/Ishiiruka/blob/v3.6.4/Source/Core/Core/ConfigManager.cpp#L690-L696)
- [Current mainline Dolphin graphics guide](https://dolphin-emu.org/docs/guides/settings/)

---

## NVIDIA Low Latency Mode with Dolphin

### Recommended Setting: ON (not Ultra)

| Setting | Effect | Recommendation |
|---------|--------|----------------|
| Off | Full render queue | Not recommended |
| On | Reduced queue (1 frame) | **Recommended** |
| Ultra | Just-in-time submission | **Test both** |

**Ultra Considerations:**
- Can work well for fixed 60fps emulation
- May cause frame drops on slower systems
- Some users report micro-stutters with Ultra
- The "Ultra is safe for emulators" claim is oversimplified

**Recommendation:** Start with "On", test "Ultra" to see if it works for your system. Results vary by GPU and driver version.

---

## HAGS (Hardware Accelerated GPU Scheduling)

### Testing Results (2025-2026)
HAGS results are highly system-dependent:

| System Type | HAGS Effect | Notes |
|-------------|-------------|-------|
| DX12 + NVIDIA Turing+ | Unmeasured here | Test both settings |
| DX12 + AMD RDNA+ | Unmeasured here | Test both settings |
| Vulkan (any GPU) | Minimal effect | Vulkan has own scheduling |
| DX11 | Avoid | Can cause micro-stutters |

**Recommendation:**
- Treat HAGS-on for DX12 as a heuristic, not a measured universal win
- Test both ON and OFF for your specific system
- Monitor for micro-stutters if issues occur

---

## Dolphin.ini Settings

### Core Section
```ini
[Core]
; Immediately Present XFB - skip frame buffer queue
ImmediateXFBEnable = True

; Rush Frame Presentation - experimental latency reduction
; Test both True and False for your system
RushPresentation = False

; Smooth Frame Presentation - for VRR displays
; OFF for no-sync competitive setups
SmoothPresentation = False

; GPU Sync - adds latency, disable
SyncGPU = False

; Timing variance reduction (Ishiiruka-specific)
ReduceTimingDispersion = True
TimingVariance = 8
```

### GFX.ini Settings
```ini
[Settings]
; Backend multithreading - disable for lower overhead
BackendMultithreading = False

; Internal resolution - lower = less latency
EFBScale = 1

; VSync in Dolphin - OFF for competitive
VSync = False
```

---

## Latency Budget Comparison

### Slippi Dolphin (Tuned Profile Path) vs Console

| Component | Console (CRT) | Dolphin (tuned, 240Hz LCD) |
|-----------|---------------|--------------------------------|
| Game Logic | 16.7ms (1 frame @ 60fps) | 16.7ms (1 frame @ 60fps) |
| Frame Buffer | ~8ms (console frame buffer) | ~0ms (Immediate XFB) |
| Display Scanout | ~16.7ms (CRT full scan @ 60Hz) | ~4.2ms (240Hz scanout) |
| Pixel Response | ~0ms (CRT phosphor) | ~1-4ms (LCD GtG) |
| Rush Presentation | N/A | -8 to -14ms (if enabled) |

**Important caveats:**
- CRT phosphor response is near-instantaneous; CRT latency advantage comes from
  no frame buffer processing, not from display processing speed.
- CRT scanout is progressive — the top of the image appears before the bottom,
  so effective latency depends on where on screen the action occurs.
- These are rough estimates, not controlled measurements. Actual latency depends
  on specific hardware, drivers, and measurement methodology.
- The Rush Presentation figures are from Dolphin development notes and may not
  be reproducible on all systems.

---

## Recommended Configuration

### For Competitive Melee (Slippi)
```
Backend: Experiment (Vulkan often best on NVIDIA/AMD)
HAGS: ON (with DX12) or OFF (with Vulkan)
LLM: On (test Ultra, but may cause issues)
VSync (everywhere): OFF
G-SYNC: OFF (tearing preference — latency-neutral at fixed 60fps, see below)
Rush Presentation: MAINLINE BUILDS ONLY — verify it exists, then A/B
Smooth Presentation: OFF (costs ~1-2ms; VRR pacing aid only)
Immediately Present XFB: Enabled by default
Internal Resolution: 1x (Native)
Backend Multithreading: OFF
```

### On G-SYNC / VRR at fixed 60fps

The reflexive "VRR adds latency, turn it off" rule does **not** apply at this
operating point, and the profiles should not claim it does.

- The latency penalty people measure comes from running VRR at or near the
  **refresh ceiling**, where the driver's VSync-on fallback engages. Fixed-60
  content on a high-refresh panel runs far below the ceiling, so the fallback
  never engages.
- Blur Busters' position: on average G-SYNC has the same latency as VSync off.
  It will not go *below* VSync off, but it does not add lag either.
- No-sync at high refresh: the frame flips mid-scan, so content below the tear
  appears immediately and content above waits up to one scan period. Averaged
  across the screen that is a small, *randomised* delay.
- G-SYNC at ~60fps: scanout begins as soon as the frame is presented, and the
  panel still scans at its maximum rate. Same average, but deterministic.

**Conclusion:** choose on tearing preference, not on latency. Melee is 59.94fps,
so against a refresh that is not an exact integer multiple the tear line crawls
the panel on a repeating cycle rather than sitting still.

### The biggest online lever is not on this page

`SlippiOnlineDelay` (Slippi netplay "Delay Frames", default 2) is ~33.4ms of
deliberate input buffer — larger than every display-path term on this page
combined. Lowering it to 1 removes ~16.7ms at the cost of more frequent
rollbacks. It is a connection-quality tradeoff, not a free win, and ABSO does
not currently manage it.

### Important Caveats
- **Results vary by system** - always test configurations
- **Backend choice matters** - don't assume DX12 is always best
- **On Ishiiruka builds, D3D12 is the least-maintained backend** - D3D11 and
  Vulkan are the mature ones. Check lineage before trusting mainline advice.
- **LLM Ultra is not universally safe** - test for your setup
- **HAGS benefit is inconsistent** - test both settings

---

## Sources

### Primary Sources
- [Dolphin Progress Report December 2025](https://dolphin-emu.org/blog/2025/12/) - Rush Frame Presentation details
- [Dolphin Performance Guide](https://wiki.dolphin-emu.org/index.php?title=Performance_Guide) - Backend recommendations
- [melee.tv Latency Guide](https://melee.tv/) - Competitive Melee optimization

### Secondary Sources
- [Blur Busters G-SYNC 101](https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/) - LLM and HAGS research
- [Fizzi's Slippi Development Notes](https://github.com/project-slippi) - Immediate XFB implementation

---

## Document Metadata

- **Created:** 2026-02-02
- **Purpose:** computa project knowledge base
- **Applies to:** Slippi Dolphin, Competitive Melee, NVIDIA/AMD GPUs
- **Related files:**
  - `abso/profiles/slippi_melee.py`
  - `abso/settings/dolphin.py`
  - `rollback.md`
