# Dolphin Emulator Latency Research Notes

## Document Purpose
Comprehensive research notes for Dolphin emulator latency optimization, specifically for Slippi/Melee competitive play. This document serves as a knowledge base for the A.B.S.O. project.

---

## Key Findings Summary

### Rush Frame Presentation (December 2025)
A major latency feature added to Dolphin in late 2025, developed in collaboration with Fizzi (Slippi creator).

**What It Does:**
- Skips the presentation queue entirely when GPU is ready
- Reduces end-to-end latency by 8-14ms in testing
- Works best when GPU is not bottlenecked

**Testing Results (Dolphin + Fizzi collaboration):**
| Configuration | End-to-End Latency |
|---------------|-------------------|
| Console (CRT) | 62ms baseline |
| Dolphin + Rush Presentation | 37ms |
| Improvement | ~25ms faster than console |

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

**When to Use:**
- Useful when paired with G-SYNC/VRR
- Improves frame pacing consistency
- Not recommended for no-sync competitive setups

---

## Graphics Backend Comparison

### Vulkan
**Best for:** NVIDIA (Turing+), AMD (RDNA+)

| Aspect | Rating | Notes |
|--------|--------|-------|
| Latency | Excellent | Native low-latency path |
| Stability | Very Good | Mature implementation |
| HAGS Compatibility | Good | Works but HAGS benefit varies |
| Recommendation | **Often Best** | Test against DX12 on your system |

### DirectX 12
**Best for:** NVIDIA with HAGS enabled

| Aspect | Rating | Notes |
|--------|--------|-------|
| Latency | Excellent | Especially with HAGS |
| Stability | Good | Some edge case issues |
| HAGS Compatibility | **Excellent** | HAGS designed for DX12 |
| Recommendation | **Good Alternative** | Best if HAGS works well on your system |

### OpenGL
**Best for:** Legacy systems, troubleshooting

| Aspect | Rating | Notes |
|--------|--------|-------|
| Latency | Good | Higher driver overhead |
| Stability | Excellent | Most mature backend |
| HAGS Compatibility | Poor | HAGS doesn't help OpenGL |
| Recommendation | **Fallback Only** | Use if Vulkan/DX12 have issues |

### Backend Recommendation
**Test both Vulkan and DX12 on your specific system.** Vulkan is often best on modern NVIDIA/AMD, but DX12 + HAGS can achieve similar results. The difference is typically 0-2ms between the two.

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
| DX12 + NVIDIA Turing+ | Often beneficial | 0-2ms improvement possible |
| DX12 + AMD RDNA+ | Mixed results | Test both settings |
| Vulkan (any GPU) | Minimal effect | Vulkan has own scheduling |
| DX11 | Avoid | Can cause micro-stutters |

**Recommendation:**
- Enable HAGS if using DX12 backend
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

### Slippi Dolphin (Optimized) vs Console

| Component | Console (CRT) | Dolphin (Optimized) |
|-----------|---------------|---------------------|
| Game Logic | 16.7ms | 16.7ms |
| Frame Buffer | ~8ms | ~0ms (Immediate XFB) |
| Display Processing | ~33ms (CRT) | ~4ms (240Hz LCD) |
| Rush Presentation | N/A | -8 to -14ms |
| **Total** | **~62ms** | **~37ms** |

**Note:** These are reference values from Dolphin/Fizzi testing. Actual results vary by system configuration.

---

## Recommended Configuration

### For Competitive Melee (Slippi)
```
Backend: Experiment (Vulkan often best on NVIDIA/AMD)
HAGS: ON (with DX12) or OFF (with Vulkan)
LLM: On (test Ultra, but may cause issues)
VSync (everywhere): OFF
G-SYNC: OFF
Rush Presentation: Optional (test for 8-14ms reduction)
Immediately Present XFB: Enabled by default
Internal Resolution: 1x (Native)
Backend Multithreading: OFF
```

### Important Caveats
- **Results vary by system** - always test configurations
- **Backend choice matters** - don't assume DX12 is always best
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
- **Purpose:** A.B.S.O. project knowledge base
- **Applies to:** Slippi Dolphin, Competitive Melee, NVIDIA/AMD GPUs
- **Related files:**
  - `abso/profiles/slippi_melee.py`
  - `abso/settings/dolphin.py`
  - `rollback.md`
