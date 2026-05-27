# Rivals of Aether 2: Lowest Latency Configuration Guide
## Optimized for 300Hz Monitors

## Purpose
This document provides the **lowest possible latency** configuration for Rivals of Aether 2 on Windows with NVIDIA GPUs and a **300Hz monitor**. Two configurations are provided: absolute minimum latency (accepting tearing) and minimum latency while tear-free.

## Current ABSO Profile Alignment (2026-05)

The shipped profiles are the source of truth:

- `rivals2-offline` / `rivals2-online`: no-sync, VRR off, NVCP Max Frame Rate off, Rivals 2 `FrameRateLimit=999`.
- `rivals2-gsync` / `rivals2-online-gsync`: strict fullscreen-only G-SYNC, NVCP VSync safety net, and matching in-game + driver refresh-scaled caps (`285 @ 300Hz`, `233 @ 240Hz`, `141 @ 144Hz`).
- HDR siblings use Windows HDR composition only. Steam currently advertises `hdr_support=0` for Rivals 2, so ABSO keeps Rivals 2 `bUseHDRDisplayOutput=False`.

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
  Frame Rate Cap .............. UNCAPPED / Engine Max (ABSO writes 999)
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
  Max Frame Rate .............. Auto refresh-scaled cap (285 @ 300Hz)
  Power Management ............ Prefer maximum performance

WINDOWS:
  Refresh Rate ................ 300Hz
  Variable Refresh Rate ....... ON

RIVALS 2 IN-GAME:
  V-SYNC ...................... OFF (critical)
  Frame Rate Cap .............. Auto refresh-scaled cap (285 @ 300Hz)
  Display Mode ................ EXCLUSIVE FULLSCREEN
```
**Result:** Near-minimum latency with zero tearing. Adds ~2-5ms vs no-sync.
**Use if:** Tearing genuinely bothers you.

---

## The 300Hz Cap Detail

### UI Presets vs Config Values
Rivals 2's UI may expose preset FPS caps such as **60, 120, 144, 165, 240**. ABSO writes `FrameRateLimit` in `GameUserSettings.ini` directly, so the G-SYNC profiles use the same custom refresh-scaled cap as the NVIDIA driver safety cap.

For a 300Hz monitor, the current ABSO VRR cap is **285 FPS**. This replaces the older `refresh - 3` / `297 FPS` guidance, which was too tight for high-refresh frame-time variance.

### Why ABSO Uses Matching Game + Driver Caps

The in-game limiter is the preferred limiter when the config value sticks. Rivals 2 can rewrite `GameUserSettings.ini` on exit, so ABSO also keeps the NVIDIA driver cap as a safety net. Both caps resolve to the same value, preventing dueling limiter targets.

Do not add RTSS on top of these profiles. Online no-sync also forbids external frame caps because rollback timing is more important than frametime smoothing.

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
- **Matching game + driver caps** — Stays within VRR range with one refresh-scaled target

### NVIDIA Control Panel
```
Set up G-SYNC:
  ☑ Enable G-SYNC, G-SYNC Compatible
  ● Enable for full screen mode

Manage 3D Settings → Program Settings → Rivals2.exe:
  Monitor Technology: G-SYNC Compatible
  Vertical sync: On
  Low Latency Mode: On (NOT Ultra — Ultra overrides FPS caps)
  Max Frame Rate: Auto refresh-scaled cap (285 @ 300Hz)
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
Frame Rate Cap: Auto refresh-scaled cap (285 @ 300Hz)
Display Mode: Exclusive Fullscreen
```

### Expected Behavior
- Steady 285 FPS on 300Hz (capped by matching in-game and driver caps)
- Zero screen tearing
- G-SYNC active (monitor refreshes at the capped framerate dynamically)
- NVCP V-SYNC never engages (FPS always below 300Hz ceiling)
- Near-minimum latency with perfect visual consistency

---

## 300Hz and Frame Cadence

### Does 300Hz vs 240Hz Matter for 60fps Logic?

**Quick Answer:** Both divide evenly into 60Hz game logic, but keep the monitor at 300Hz for no-sync scanout and VRR headroom.

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
| 285 FPS cap on 300Hz monitor (G-SYNC) | **~3.51ms** |
| 233 FPS cap on 240Hz monitor (G-SYNC) | **~4.29ms** |
| Uncapped 300+ FPS on 300Hz (no sync) | **~3.33ms** |

**For VRR setup:** Keep the monitor at its maximum refresh. ABSO scales the cap with refresh so the VRR path gets headroom without leaving the display at a lower scanout ceiling.

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
| 240 | 4.17ms | ~2-4ms | Best manual UI preset if custom INI writes are unavailable |
| 285 | 3.51ms | ~1.8-3.5ms | ABSO 300Hz G-SYNC profile target |

*Limiter overhead is ~0.5-1 frame. At higher FPS, a "frame" is shorter in absolute time.

**Key insight:** The limiter mechanism itself doesn't vary between presets — the latency difference comes from frame time. Higher caps = shorter frame time = lower latency.

---

## Latency Comparison Summary

| Configuration | Sync Latency | Limiter Latency | Scanout | Tearing | Total Relative |
|---------------|--------------|-----------------|---------|---------|----------------|
| No sync, uncapped | 0 | 0 | ~3.3ms | Yes | **Lowest** |
| G-SYNC+VSYNC, 285 game+driver cap | ~0 | ~1.8-3.5ms | ~3.5ms | No | **Very Low** |
| G-SYNC+VSYNC, 300 RTSS | ~0 | ~4-6ms | ~3.4ms | No | Very Low (but higher limiter overhead) |
| V-SYNC only, 300 cap | High (~16ms) | Low | ~3.3ms | No | High |

**Note:** ABSO no longer uses the older 240-only guidance for the profile path; 240 remains the manual fallback when the game UI is the only thing being changed.

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
3. FPS should stay near the ABSO VRR cap, such as 285 at 300Hz (tear-free), or 300+ (no sync)

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
- Check NVCP Max Frame Rate (off for no-sync, ABSO auto cap for G-SYNC)
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
- Verify no extra RTSS/global limiter is layered over the profile's intended cap
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
│   G-SYNC: OFF | V-SYNC: OFF | LLM: On | Cap: Engine max / 999   │
│   Monitor: 300Hz (CRITICAL) | Scanout: 3.33ms                   │
├─────────────────────────────────────────────────────────────────┤
│ ALTERNATIVE: VRR (Tear-Free, +2-5ms)                            │
│   G-SYNC: ON | V-SYNC: ON (NVCP) | LLM: On | Cap: 285 @ 300Hz   │
│   Monitor: 300Hz (for headroom) | Scanout: ~3.51ms              │
├─────────────────────────────────────────────────────────────────┤
│ BOTH SETUPS:                                                    │
│   In-game V-SYNC: OFF | Power: Prefer maximum performance       │
│   Display Mode: Exclusive Fullscreen | Triple Buffering: OFF    │
└─────────────────────────────────────────────────────────────────┘
```

---

## FAQ: Common Questions

### Should I set my monitor to 240Hz to "match" a 240 FPS cap?

**No.** There is no benefit to matching monitor refresh to FPS cap because:

1. **ABSO's G-SYNC profiles scale the cap to the monitor** — 300Hz gets a 285 cap, not 240
2. **No "sync harmony" benefit** — G-SYNC dynamically matches refresh to frame rate
3. **300Hz gives VRR headroom** — If FPS spikes above a lower manual cap, you stay in VRR range instead of triggering V-SYNC
4. **Power difference is negligible** — The only theoretical benefit of 240Hz

**Always keep monitor at 300Hz.**

### Why not use RTSS at 300 FPS for better scanout?

ABSO already uses a 285 FPS cap at 300Hz for the G-SYNC profile. RTSS adds another limiter layer and breaks the profile's single-target cap contract. Use RTSS only for manual experiments outside the shipped profiles.

### Does the specific FPS cap value affect limiter latency?

Yes, but it's frame time, not limiter mechanism. The limiter adds ~0.5-1 frame overhead:
- At 60fps: 0.5 frame = ~8ms
- At 240fps: 0.5 frame = ~2ms
- At 285fps: 0.5 frame = ~1.75ms

Use the highest stable cap that still leaves VRR headroom. In ABSO's 300Hz G-SYNC profile that is 285 FPS.

---

## Document Metadata
- **Target**: Windows Gaming Optimization Tool (A.B.S.O.)
- **Game**: Rivals of Aether 2
- **Monitor**: 300Hz
- **Priority**: Lowest possible latency
- **GPU**: NVIDIA with G-SYNC Compatible support
- **Sources**: Blur Busters G-SYNC 101, community testing, LDAT measurements
- **Related**: `docs/research/vrr-latency-research-notes.md`
