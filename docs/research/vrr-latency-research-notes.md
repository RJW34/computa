# VRR/G-SYNC Latency Research Notes

## Document Purpose
Historical research notes for fighting game latency tuning, specifically for Rivals of Aether 2 on 300Hz monitors. This document is not release evidence by itself; product-facing claims still require benchmark artifacts and the quality rubric wins on conflicts.

---

## Key Findings Summary

### Monitor Refresh Rate vs FPS Cap

**Critical Insight:** Scanout behavior differs between G-SYNC and no-sync setups.

| Scenario | Monitor Setting | FPS | Actual Scanout | Why |
|----------|-----------------|-----|----------------|-----|
| **No sync** | 300Hz | Any | **3.33ms** | Fixed by monitor refresh |
| **No sync** | 240Hz | Any | **4.17ms** | Fixed by monitor refresh |
| G-SYNC with cap | 300Hz | 240 | 4.17ms | Matches FPS |
| G-SYNC with cap | 240Hz | 240 | 4.17ms | Matches FPS |

**For No-Sync (DEFAULT for Rivals 2):**
- Monitor refresh rate DIRECTLY determines scanout time
- 300Hz = 3.33ms scanout (faster) vs 240Hz = 4.17ms (slower)
- 300Hz has lower scanout time than 240Hz in no-sync mode when the display path actually runs at 300Hz

**For G-SYNC (Alternative):**
- Scanout matches actual FPS, not monitor max
- 300Hz vs 240Hz setting makes no difference at 240fps
- Keep at 300Hz for VRR headroom only

### Is There Any Reason to Use 240Hz Instead of 300Hz?

**No practical reason.** Theoretical considerations:

| Factor | 240Hz | 300Hz | Winner |
|--------|-------|-------|--------|
| Scanout at 240fps (G-SYNC) | 4.17ms | 4.17ms | Tie |
| VRR headroom | None | 60fps headroom | 300Hz |
| Power consumption | Slightly lower | Slightly higher | 240Hz (negligible) |
| Frame cadence with 60fps logic | 240/60=4 (even) | 300/60=5 (even) | Tie |
| V-SYNC ceiling risk | FPS spike triggers V-SYNC | More headroom | 300Hz |

**Verdict:** Prefer 300Hz for the ABSO no-sync/VRR test path unless a specific
display, power, or stability issue is measured at that refresh rate. The only
general 240Hz benefit identified here is lower power use.

---

## In-Game FPS Limiter Latency

### Rivals 2 Available Presets
- 60, 120, 144, 165, 240 FPS

### Latency by Cap Value

| FPS Cap | Frame Time | Limiter Overhead (~0.5-1 frame) | Total Impact |
|---------|------------|--------------------------------|--------------|
| 60 | 16.67ms | ~8-17ms | Highest |
| 120 | 8.33ms | ~4-8ms | High |
| 144 | 6.94ms | ~3.5-7ms | Medium |
| 165 | 6.06ms | ~3-6ms | Medium-Low |
| 240 | 4.17ms | ~2-4ms | **Lowest** |

**Key insight:** The limiter mechanism doesn't vary between presets. Latency difference comes from frame time — higher caps = shorter frame time = lower latency.

### In-Game vs External Limiters (LDAT Testing)

Source: Blur Busters LDAT testing in Overwatch at 240Hz

| Limiter Type | Latency | Overhead vs In-Game |
|--------------|---------|---------------------|
| In-game (237fps) | 16ms | Baseline |
| RTSS (237fps) | 18ms | +2ms (~0.5 frame) |
| NVCP Max Frame Rate | 18ms | +2ms (~0.5 frame) |
| Reflex auto-limit | 16ms | ~0ms |
| No limiter (V-SYNC kicks in) | 24ms | +8ms (~2 frames) |

**Conclusion:** In-game limiters have ~0.5-1 frame lower latency than external limiters. For 60Hz-logic fighting games, this advantage (~2-4ms at 240fps) outweighs the scanout benefit of higher external cap (RTSS at 297 would only save 0.8ms scanout).

---

## G-SYNC Recommended Configuration

### Blur Busters G-SYNC 101 Recommendations

```
NVIDIA Control Panel:
  G-SYNC: ON (fullscreen or fullscreen+windowed)
  V-SYNC: ON (acts as safety net, not active V-SYNC)
  Low Latency Mode: On (NOT Ultra with manual cap)
  Max Frame Rate: Off (use in-game limiter)

In-Game:
  V-SYNC: OFF (critical)
  FPS Cap: Highest preset below refresh rate
```

### Why V-SYNC ON with G-SYNC?

V-SYNC ON in NVCP with G-SYNC is NOT traditional V-SYNC:
- Within VRR range: V-SYNC is inactive, G-SYNC handles sync
- Above VRR ceiling: V-SYNC prevents tearing (safety net)
- With a stable FPS cap below the ceiling: V-SYNC should not engage during normal play

**Common misconception:** "V-SYNC ON always adds latency" — too broad when FPS is capped below refresh rate in a VRR path.

### Why Low Latency Mode "On" not "Ultra"?

- **Ultra** auto-caps FPS and overrides manual caps
- **On** reduces render queue without interfering with caps
- For DX12 games (like Rivals 2/UE5), LLM has limited effect anyway

---

## Fighting Game Specific Considerations

### 60Hz Game Logic

Rivals 2 (and most fighting games) run game logic at 60Hz:
- Hitboxes update 60 times per second
- Input polling tied to game logic rate
- Render FPS provides visual smoothness, not gameplay advantage

### What Higher FPS Provides

1. **Faster frame delivery** — See current game state sooner
2. **Reduced scanout latency** — Frame scans to display faster
3. **Smoother motion** — Visual interpolation between logic frames
4. **Lower limiter overhead** — 0.5 frame at 240fps = 2ms vs 8ms at 60fps

### What Higher FPS Does NOT Provide

- More frequent input polling (game logic dependent)
- Faster reaction windows (still 60Hz logic)
- Frame advantage in neutral (same game state rate)

### Frame Cadence at High Refresh

Both 240Hz and 300Hz divide evenly into 60fps:
- 240 ÷ 60 = 4 (even)
- 300 ÷ 60 = 5 (even)

No cadence judder with either. VRR handles frame delivery dynamically anyway.

---

## Latency Budget Breakdown

### VRR Tear-Free Setup (Recommended)

| Component | Latency |
|-----------|---------|
| Game logic processing | Variable |
| Render queue (LLM On) | ~1 frame |
| In-game limiter overhead | ~0.5-1 frame (~2-4ms @ 240fps) |
| G-SYNC sync | ~0ms (within VRR range) |
| Scanout (240fps) | 4.17ms |
| Display processing | Monitor dependent (~1-3ms) |
| **Total sync-related** | **~6-8ms** |

### No-Sync Competitive Setup

| Component | Latency |
|-----------|---------|
| Game logic processing | Variable |
| Render queue (LLM On) | ~1 frame |
| No limiter | 0ms |
| No sync | 0ms |
| Scanout (300fps+) | ~3.33ms |
| Display processing | Monitor dependent (~1-3ms) |
| **Total sync-related** | **~4-5ms** |

### Difference

**~2-5ms total latency difference** between setups. At 60Hz game logic (16.67ms per game frame), this is a fraction of a game frame.

---

## Tearing Visibility at High Refresh

| Refresh Rate | Tear Visibility Duration | Perception |
|--------------|-------------------------|------------|
| 60Hz | 16.67ms | Very visible |
| 144Hz | 6.94ms | Noticeable |
| 240Hz | 4.17ms | Minor |
| 300Hz | 3.33ms | Barely visible |
| 360Hz+ | <2.8ms | Nearly imperceptible |

At 300Hz+, tearing is "almost impossible to notice most of the time" per Blur Busters testing.

---

## NVIDIA Reflex Note

**Rivals of Aether 2 does NOT support NVIDIA Reflex.**

Combined with UE5/DX12 (where Low Latency Mode has limited effect), there's no driver-level latency reduction available. Optimization relies on:
- Proper FPS cap (in-game limiter)
- G-SYNC configuration
- System-level optimizations

---

## HAGS Testing Results (2025-2026)

### Average Gaming Performance Impact
Based on testing across multiple systems and games:

| Metric | With HAGS ON | Notes |
|--------|--------------|-------|
| Average FPS gain | ~0.3% | Minimal improvement |
| Latency reduction | 0-2ms | Highly variable |
| Stability | System-dependent | Some report micro-stutters |

### Key Findings

**HAGS benefits are inconsistent:**
- Works best with DX12 titles (designed for DX12 scheduling model)
- Minimal effect on Vulkan (has its own scheduling)
- Can cause issues with DX11 (micro-stutters reported)
- Newer GPUs (Turing+, RDNA+) see more benefit

**Recommendation:**
- Default to ON for DX12 games
- Test both ON and OFF for your specific system/game combination
- If experiencing micro-stutters, try disabling HAGS

### Sources
- Hardware Unboxed HAGS Testing (2025)
- Blur Busters Forums HAGS discussions
- Community testing reports

---

## Recommended Configurations

**Important:** Results are system-dependent. The configurations below are starting points - test both HAGS ON/OFF for your specific setup.

### DEFAULT: No-Sync (Tearing-Accepting Latency Path)

```
Monitor: 300Hz for the tested high-refresh path
NVCP G-SYNC: OFF
NVCP V-SYNC: OFF
NVCP Low Latency Mode: On
NVCP Max Frame Rate: Off
NVCP Triple Buffering: Off
In-Game V-SYNC: OFF
In-Game FPS Cap: Uncapped or 240 (highest preset)
Display Mode: Exclusive Fullscreen
Windows VRR: Off
```

**Expected latency:** Low sync overhead with ~3.3ms scanout at 300Hz on the tested display path
**Tearing:** Yes (barely visible at 300Hz - ~3.33ms tear lines)
**Best for:** Fighting games where the no-sync latency path is priority

**Why no-sync is default for Rivals 2:**
- Fighting games prioritize input latency over visual polish
- At 300Hz, tearing is barely perceptible
- No-sync avoids the VRR/VSync queueing path but accepts tearing; the exact latency difference must be measured per setup
- Rivals 2 lacks Reflex, LLM has limited effect in DX12/UE5

### ALTERNATIVE: VRR/G-SYNC (Tear-Free)

```
Monitor: 300Hz (for VRR headroom)
NVCP G-SYNC: ON
NVCP V-SYNC: ON (safety net only)
NVCP Low Latency Mode: On (NOT Ultra)
NVCP Max Frame Rate: Off
In-Game V-SYNC: OFF (critical)
In-Game FPS Cap: 240
Display Mode: Exclusive Fullscreen
Windows VRR: On
```

**Expected latency:** Very low (~4.2ms scanout + ~2-4ms limiter = ~6-8ms)
**Tearing:** None
**Best for:** Players who find tearing distracting
**Tradeoff:** Adds ~2-5ms vs no-sync setup

---

## Sources

### Primary Sources
- [Blur Busters G-SYNC 101](https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/) - Authoritative VRR guide
- [Blur Busters Forums - LDAT Testing](https://forums.blurbusters.com/viewtopic.php?t=9151) - Frame limiter latency measurements
- [Blur Busters Forums - Fighting Game Settings](https://forums.blurbusters.com/viewtopic.php?t=4627) - Genre-specific recommendations

### Secondary Sources
- [Guru3D Forums - G-SYNC Cap Discussion](https://forums.guru3d.com/threads/should-you-cap-more-frames-beneath-monitor-refresh-with-g-sync-when-the-monitor-is-high-refresh.439469/) - High refresh VRR discussion
- [Blur Busters Forums - RTSS vs In-game](https://forums.blurbusters.com/viewtopic.php?t=12472) - Limiter comparison
- [Blur Busters Forums - 300Hz No G-SYNC](https://forums.blurbusters.com/viewtopic.php?t=6803) - High refresh without VRR

### Game-Specific
- [Rivals 2 Launch Feedback - FPS Settings](https://rivals-of-aether-ii-launch.nolt.io/1407) - Community FPS cap requests
- UE5/DX12 architecture implies limited LLM effectiveness

---

## Document Metadata

- **Created:** 2024-12-31
- **Purpose:** computa project knowledge base
- **Applies to:** Rivals of Aether 2, 300Hz monitors, NVIDIA GPUs
- **Related files:**
  - `rivals2-300hz-lowest-latency-guide.md`
  - `abso/profiles/rivals2.py`
  - `abso/settings/nvidia/presets.py`
