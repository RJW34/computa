# Deprecated Rivals 2 VRR Snapshot

> **DEPRECATED**: This document is an auto-generated snapshot from an earlier session and
> contains inaccurate claims. The "~1.0ms display latency" figure is **physically
> implausible** (scanout alone at 300Hz is 3.33ms). Several settings here
> (LLM Ultra, VSync Fast + G-Sync) conflict with the current shipped profile
> policy.
>
> **Do not use this document as a reference.** Use
> `rivals2-300hz-lowest-latency-guide.md`, `python -m abso profiles --json`,
> and the live profile modules instead.

## ~~Achieved: ~1.0ms display latency at stable 297fps~~ (INACCURATE — see note above)

Generated: 2026-01-15 17:16:41

## 1. Process Status
- **Process**: Rivals2-Win64-Shipping
  - PID: 86556
  - Priority: High
  - RAM: 3390 MB
  - Threads: 132

## 2. IFEO Registry Settings (Persistent Priority)
- **Rivals2-Win64-Shipping.exe**
  - CpuPriorityClass: 3 (3=High)
  - GpuPriority: 8 (8=Max)
  - IoPriority: 3 (3=High)
- **RivalsofAether2.exe**
  - CpuPriorityClass: 3 (3=High)
  - GpuPriority: 8 (8=Max)
  - IoPriority: 3 (3=High)
- **Rivals2.exe**
  - CpuPriorityClass: 3 (3=High)
  - GpuPriority: 8 (8=Max)
  - IoPriority: 3 (3=High)

## 3. Fullscreen Optimizations
- **FSO: ENABLED** (stale snapshot value - not the current ABSO Rivals 2 policy)

## 4. Windows Gaming Settings
- Game Mode: ENABLED
- Allow Auto Game Mode: YES
- Game DVR/Capture: DISABLED
- HAGS (HwSchMode): ENABLED (Value: 2)

## 5. Rivals 2 GameUserSettings.ini
- FullscreenMode=0
- LastConfirmedFullscreenMode=0
- bUseVSync=False
- FrameRateLimit=297.000000
- bUseFrameRateLimit=True
- bUseRawInput=True
- sg.ResolutionQuality=100

## 6. Display Settings
- Monitor: LG 27GS95QE (300Hz OLED)
- Resolution: 2560x1440
- Refresh Rate: 300Hz
- G-Sync: ENABLED
- Response Time: Fast (OLED instant response)

## 7. NVIDIA Control Panel Settings
*(Applied by profile - verify in NVCP)*

| Setting | Value |
|---------|-------|
| Vertical Sync | **Fast** |
| Low Latency Mode | **Ultra** |
| Power Management | Prefer Maximum Performance |
| Max Frame Rate | Off |
| Triple Buffering | Off |
| Shader Cache | Unlimited |
| Threaded Optimization | On |

## 8. Key Configuration Summary

| Component | Setting | Why |
|-----------|---------|-----|
| G-Sync | ON | VRR for tear-free |
| VSync (NVCP) | **Fast** | Better than On for UE5 (no FPS cap issues) |
| Low Latency Mode | **Ultra** | Works with VSync Fast (no conflict) |
| Fullscreen Opts | **ENABLED** | Helps performance with G-Sync |
| In-game VSync | OFF | Let NVCP handle sync |
| In-game FPS Cap | 297 | refresh_rate - 3 for G-Sync headroom |
| Process Priority | High | Ensures CPU time over background tasks |
| HAGS | ON | Hardware GPU scheduling |
| Game Mode | ON | Windows gaming optimizations |
| Game DVR | OFF | No capture overhead |

## 9. Results (INACCURATE)
- **Display Latency**: ~~~1.0ms~~ (this figure is physically impossible — see deprecation notice)
- **FPS**: Stable 297fps
- **Tearing**: None (G-Sync + VSync Fast)
- **Input Feel**: Excellent responsiveness
