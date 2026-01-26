# Rivals of Aether 2: Lowest Latency Configuration Guide
## Optimized for 300Hz Monitors

## Purpose
This document provides the **lowest possible latency** configuration for Rivals of Aether 2 on Windows with NVIDIA GPUs and a **300Hz monitor**. Two configurations are provided: absolute minimum latency (accepting tearing) and minimum latency while tear-free.

---

## TL;DR: Lowest Latency Configurations

### DEFAULT: NO-SYNC (Absolute Minimum Latency)
```
NVIDIA CONTROL PANEL:
  G-SYNC ...................... OFF
  Vertical Sync ............... OFF
  Low Latency Mode ............ On
  Max Frame Rate .............. OFF
  Triple Buffering ............ OFF
  Power Management ............ Prefer maximum performance

WINDOWS:
  Refresh Rate ................ 300Hz (CRITICAL - determines scanout)
  Variable Refresh Rate ....... OFF

RIVALS 2 IN-GAME:
  V-SYNC ...................... OFF
  Frame Rate Cap .............. UNCAPPED or 240 (highest preset)
  Display Mode ................ EXCLUSIVE FULLSCREEN
```
**Result:** Absolute minimum input lag. Tearing occurs but is barely visible at 300Hz (~3.33ms tear lines).
**Why default:** Fighting games prioritize latency. At 300Hz, tearing is nearly imperceptible.

---

### ALTERNATIVE: VRR/G-SYNC (Tear-Free)
```
NVIDIA CONTROL PANEL:
  G-SYNC ...................... ON
  Vertical Sync ............... ON (safety net only)
  Low Latency Mode ............ On (NOT Ultra)
  Max Frame Rate .............. OFF
  Power Management ............ Prefer maximum performance

WINDOWS:
  Refresh Rate ................ 300Hz
  Variable Refresh Rate ....... ON

RIVALS 2 IN-GAME:
  V-SYNC ...................... OFF (critical)
  Frame Rate Cap .............. 240 (must cap for G-SYNC)
  Display Mode ................ EXCLUSIVE FULLSCREEN
```
**Result:** Near-minimum latency with zero tearing. Adds ~2-5ms vs no-sync.
**Use if:** Tearing genuinely bothers you.

---

## The 300Hz Problem with Rivals 2

### FPS Cap Limitation
Rivals 2 only offers preset FPS caps: **60, 120, 144, 165, 240**

For optimal VRR on a 300Hz monitor, you'd want **300 FPS** (refresh). But 240 is the highest available preset.

### What You Lose with 240 FPS Cap on 300Hz
| Metric | 300 FPS (optimal) | 240 FPS (available) | Difference |
|--------|-------------------|---------------------|------------|
| Scanout time | 3.33ms | 4.17ms | +0.84ms |
| Refresh utilization | 99% | 80% | -19% |
| VRR headroom wasted | 3 FPS | 60 FPS | 57 FPS |

### Why 240 FPS In-Game is Still Recommended (Tear-Free Option)
Despite losing 60Hz of headroom, the **in-game limiter has ~0.5-1 frame lower latency** than external limiters (RTSS/NVCP). For a 60Hz-logic fighting game:

- You receive new game state only **60 times per second** regardless of render FPS
- The limiter latency savings (~3-4ms) outweighs the scanout difference (~0.84ms)
-- Net result: In-game 240 cap beats RTSS 300 cap for total input lag

### When to Use RTSS 300 Instead
If you're playing other games on the same system that:
- Have uncapped or custom FPS options
- Are not 60Hz-logic locked
- Benefit from the full 300 FPS

Then configure RTSS at 300 globally and disable it per-profile for Rivals 2.

---

## Detailed Configuration: Absolute Lowest Latency

**Use this if:** You prioritize reaction time over visual cleanliness and can tolerate tearing.

### Why This Works
- **No sync = no sync latency** — Frames display immediately when ready
- **Uncapped FPS** — GPU renders as fast as possible
- **At 300Hz+**, tearing is less perceptible (tear lines move faster across screen)

### NVIDIA Control Panel
```
Set up G-SYNC:
  ☐ Enable G-SYNC, G-SYNC Compatible (UNCHECKED)

Manage 3D Settings → Program Settings → Rivals2.exe:
  Vertical sync: Off
  Low Latency Mode: On
  Max Frame Rate: Off
  Power management mode: Prefer maximum performance
  Triple buffering: Off
```

### Windows Settings
```
Settings → System → Display → Advanced display:
  Refresh rate: 300Hz

Settings → System → Display → Graphics → Change default graphics settings:
  Variable refresh rate: Off (or On, doesn't matter with G-SYNC disabled)
```

### Rivals 2 In-Game
```
V-SYNC: Off
Frame Rate Cap: Uncapped (or highest preset if uncapped unavailable)
Display Mode: Exclusive Fullscreen
```

### Expected Behavior
- FPS will exceed 300 if GPU capable (tearing occurs)
- FPS may fluctuate (no cap smoothing frametimes)
- Absolute minimum click-to-pixel latency
- Visible tearing (horizontal lines, especially during fast motion)

---

## Detailed Configuration: Lowest Latency Tear-Free

**Use this if:** You want competitive-level latency without visual artifacts.

### Why This Works
- **G-SYNC matches refresh to framerate** — No traditional V-SYNC buffer delay
- **NVCP V-SYNC as safety net** — Only engages if FPS exceeds refresh (which the cap prevents)
- **In-game cap at 240** — Stays within VRR range; lower limiter latency than RTSS

### NVIDIA Control Panel
```
Set up G-SYNC:
  ☑ Enable G-SYNC, G-SYNC Compatible
  ● Enable for full screen mode

Manage 3D Settings → Program Settings → Rivals2.exe:
  Monitor Technology: G-SYNC Compatible
  Vertical sync: On
  Low Latency Mode: On (NOT Ultra — Ultra overrides FPS caps)
  Max Frame Rate: Off
  Power management mode: Prefer maximum performance
  Triple buffering: Off
  Preferred refresh rate: Highest available
```

### Windows Settings
```
Settings → System → Display → Advanced display:
  Refresh rate: 300Hz

Settings → System → Display → Graphics → Change default graphics settings:
  Variable refresh rate: On
```

### Rivals 2 In-Game
```
V-SYNC: Off (critical — in-game V-SYNC adds latency)
Frame Rate Cap: 240 (highest available)
Display Mode: Exclusive Fullscreen (or Borderless if G-SYNC windowed enabled)
```

### Expected Behavior
- Steady 240 FPS (capped by in-game limiter)
- Zero screen tearing
- G-SYNC active (monitor refreshes at 240Hz dynamically)
- NVCP V-SYNC never engages (FPS always below 300Hz ceiling)
- Near-minimum latency with perfect visual consistency

---

## 300Hz and Frame Cadence

### Does 300Hz vs 240Hz Matter for 60fps Logic?

**Quick Answer:** Both are fine for cadence. For VRR with 240 FPS cap, scanout is identical.

**Explanation:**
| Refresh | ÷ 60fps | Result |
|---------|---------|--------|
| 240Hz | 4.0 | Even ✓ |
| 300Hz | 5.0 | Even ✓ |

Both divide evenly into 60, so no frame cadence judder occurs with either.

### Critical Insight: G-SYNC Scanout Time

**With G-SYNC active, scanout is determined by your actual frame rate, NOT the monitor's max refresh setting.**

| Scenario | Actual Scanout |
|----------|---------------|
| 240 FPS cap on 300Hz monitor (G-SYNC) | **4.17ms** |
| 240 FPS cap on 240Hz monitor (G-SYNC) | **4.17ms** |
| Uncapped 300+ FPS on 300Hz (no sync) | **~3.33ms** |

**For VRR setup (recommended):** Monitor at 240Hz vs 300Hz makes no latency difference when capped at 240 FPS. Keep at 300Hz for VRR headroom (prevents hitting ceiling on FPS spikes).

**For no-sync setup:** Monitor at 300Hz DOES matter — you get 3.33ms scanout vs 4.17ms at 240Hz.

**Do NOT drop to 240Hz** — It provides no benefit and loses VRR headroom.

---

## In-Game FPS Cap Latency Differences

Each FPS cap preset in Rivals 2 has different latency characteristics:

| FPS Cap | Frame Time | Limiter Overhead* | Total Latency Impact |
|---------|------------|-------------------|---------------------|
| 60 | 16.67ms | ~8-17ms | Highest (but matches game logic) |
| 120 | 8.33ms | ~4-8ms | 2x faster frame delivery |
| 144 | 6.94ms | ~3.5-7ms | Common VRR target |
| 165 | 6.06ms | ~3-6ms | Mid-tier option |
| 240 | 4.17ms | ~2-4ms | **Lowest - always use this** |

*Limiter overhead is ~0.5-1 frame. At higher FPS, a "frame" is shorter in absolute time.

**Key insight:** The limiter mechanism itself doesn't vary between presets — the latency difference comes from frame time. Higher caps = shorter frame time = lower latency.

---

## Latency Comparison Summary

| Configuration | Sync Latency | Limiter Latency | Scanout | Tearing | Total Relative |
|---------------|--------------|-----------------|---------|---------|----------------|
| No sync, uncapped | 0 | 0 | ~3.3ms | Yes | **Lowest** |
| G-SYNC+VSYNC, 240 in-game | ~0 | ~2-4ms | ~4.2ms | No | **Very Low** |
| G-SYNC+VSYNC, 300 RTSS | ~0 | ~4-6ms | ~3.4ms | No | Very Low (but higher limiter overhead) |
| V-SYNC only, 300 cap | High (~16ms) | Low | ~3.3ms | No | High |

**Note:** G-SYNC at 240 FPS has 4.2ms scanout regardless of monitor's max refresh (240Hz or 300Hz).

---

## Fighting Game Context: Why 60Hz Logic Matters

### Rivals 2 Architecture
```
Game Logic:    [====60Hz====] → Frame data, hitboxes, inputs
Rendering:     [====240Hz+===] → Visual output, interpolation
```

You receive **new gameplay information 60 times per second** regardless of render FPS.

### What Higher FPS Actually Provides
1. **Faster frame delivery** — See the current game state sooner
2. **Reduced display latency** — Frame scans to monitor faster
3. **Smoother motion** — Visual interpolation between logic frames

### What Higher FPS Does NOT Provide
- More frequent input polling (that's controller/game dependent)
- Faster reaction windows (still 60Hz logic)
- Competitive advantage beyond the latency reduction

---

## Verification Steps

### Confirm G-SYNC is Active (Tear-Free Option)
1. Enable "G-SYNC Indicator" in NVIDIA Control Panel (Display → G-SYNC Indicator)
2. Launch Rivals 2 in fullscreen
3. Look for green "G-SYNC On" overlay in corner
4. Disable indicator after confirming

### Confirm FPS Cap is Working
1. Enable Steam FPS counter (Steam → Settings → In-Game → FPS Counter)
2. Or use RTSS overlay (shows frametime graph too)
3. FPS should stay at 240 (tear-free) or 300+ (no sync)

### Confirm No Tearing (Tear-Free Option)
1. Move camera rapidly left/right in training mode
2. Look for horizontal lines cutting across screen
3. If visible: Check NVCP V-SYNC is On, in-game V-SYNC is Off

### Test Input Latency (Subjective)
1. Use training mode
2. Perform fast inputs and observe response
3. Compare feel between configurations if desired

---

## Troubleshooting

### Issue: FPS stuck at 60
- Check in-game FPS cap setting
- Check NVCP Max Frame Rate (should be Off)
- Check for V-SYNC forcing 60Hz lock
- Verify monitor is set to 300Hz in Windows

### Issue: Tearing despite G-SYNC setup
- Verify G-SYNC is enabled for the display in NVCP
- Ensure in-game V-SYNC is **Off** (some implementations conflict)
- Check if running in true fullscreen (not borderless without windowed G-SYNC)
- Confirm FPS isn't exceeding 300 (cap should prevent this)

### Issue: G-SYNC indicator shows "Off"
- Game may not be in true fullscreen
- G-SYNC windowed mode may be disabled
- Display may not be set as primary G-SYNC display
- Try toggling G-SYNC off and on in NVCP

### Issue: Micro-stuttering
- FPS may be hitting cap inconsistently — lower cap further
- Check for background processes consuming resources
- Verify Power Management is set to "Prefer maximum performance"
- Try disabling Game Mode in Windows

### Issue: Higher latency feel than expected
- Ensure in-game V-SYNC is OFF (most common mistake)
- Check Low Latency Mode is "On" not "Ultra" or "Off"
- Verify no frame rate limiting in NVCP
- Check GPU isn't thermal throttling (monitor temps)

---

## Final Recommendation for 300Hz + Lowest Latency

### DEFAULT: No-Sync for Fighting Games
Use **No-Sync (G-SYNC OFF, V-SYNC OFF)** — Fighting games prioritize input latency above all else. At 300Hz, tearing is barely visible (~3.33ms tear lines). The latency savings matter in fighting games where single frames determine outcomes.

### Alternative: VRR if Tearing Bothers You
Use **VRR/G-SYNC** only if tearing genuinely distracts you. Adds ~2-5ms latency. Rollback netcode does benefit from consistent frame delivery, but the latency tradeoff is real.

### The Honest Truth
At 300Hz with a 60Hz-logic game, the difference between these configurations is **small** — likely 2-5ms total. However, for competitive fighting games, the no-sync setup is the standard because every millisecond counts.

---

## Configuration Summary Box

```
┌─────────────────────────────────────────────────────────────────┐
│            300Hz LOWEST LATENCY - RIVALS OF AETHER 2            │
├─────────────────────────────────────────────────────────────────┤
│ DEFAULT: NO-SYNC (Minimum Latency)                              │
│   G-SYNC: OFF | V-SYNC: OFF | LLM: On | Cap: UNCAPPED/240       │
│   Monitor: 300Hz (CRITICAL) | Scanout: 3.33ms                   │
├─────────────────────────────────────────────────────────────────┤
│ ALTERNATIVE: VRR (Tear-Free, +2-5ms)                            │
│   G-SYNC: ON | V-SYNC: ON (NVCP) | LLM: On | Cap: 240 in-game   │
│   Monitor: 300Hz (for headroom) | Scanout: 4.17ms               │
├─────────────────────────────────────────────────────────────────┤
│ BOTH SETUPS:                                                    │
│   In-game V-SYNC: OFF | Power: Prefer maximum performance       │
│   Display Mode: Exclusive Fullscreen | Triple Buffering: OFF    │
└─────────────────────────────────────────────────────────────────┘
```

---

## FAQ: Common Questions

### Should I set my monitor to 240Hz to "match" my 240 FPS cap?

**No.** There is no benefit to matching monitor refresh to FPS cap because:

1. **G-SYNC determines scanout by actual FPS** — At 240fps, scanout is 4.17ms regardless of whether monitor is set to 240Hz or 300Hz
2. **No "sync harmony" benefit** — G-SYNC dynamically matches refresh to frame rate
3. **300Hz gives VRR headroom** — If FPS spikes to 245, you stay in VRR range instead of triggering V-SYNC
4. **Power difference is negligible** — The only theoretical benefit of 240Hz

**Always keep monitor at 300Hz.**

### Why not use RTSS at 300 FPS for better scanout?

The math doesn't favor it for 60Hz-logic fighting games:
- RTSS 300 FPS: 3.33ms scanout + ~4-6ms limiter overhead = ~7-9ms
- In-game 240 FPS: 4.17ms scanout + ~2-4ms limiter overhead = ~6-8ms

In-game limiter's lower overhead outweighs the scanout benefit.

### Does the specific FPS cap value (60/120/144/165/240) affect limiter latency?

Yes, but it's frame time, not limiter mechanism. The limiter adds ~0.5-1 frame overhead:
- At 60fps: 0.5 frame = ~8ms
- At 240fps: 0.5 frame = ~2ms

**Always use 240** — highest available = lowest absolute latency.

---

## Document Metadata
- **Target**: Windows Gaming Optimization Tool (A.B.S.O.)
- **Game**: Rivals of Aether 2
- **Monitor**: 300Hz
- **Priority**: Lowest possible latency
- **GPU**: NVIDIA with G-SYNC Compatible support
- **Sources**: Blur Busters G-SYNC 101, community testing, LDAT measurements
- **Related**: `docs/research/vrr-latency-research-notes.md`
