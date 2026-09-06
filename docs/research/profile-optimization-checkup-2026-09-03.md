# Per-Game "100% Optimized State" Checkup — 2026-09-03

Successor to `profile-optimization-audit-2026-08-12.md`. That audit settled the
renderer/API and restore-ownership questions per family; this checkup verifies,
lane by lane, that the **machine-side enforcement**, the **sync conditional**
(no-sync / G-SYNC), and the **HDR conditional** (SDR / HDR) each resolve to the
lowest-latency, best-pacing state computa can own — and it draws the honest line
at what remains a user-owned manual step or a benchmark-gated A/B choice.

Method: the full 44-lane catalog was dumped programmatically from the live
`get_settings()` path (no game or display was launched) and cross-checked
against the settled performance verdicts in memory and the 08-12 audit. The
active profile was verified read-only through the installed runtime.

Reference hardware: RTX 4070, i9-14900F (8P/16E, 24C/32T), 32 GB, 2560×1440
300 Hz VRR primary + 59.95 Hz secondary. Driver 610.74.

## Machine-side enforcement — confirmed uniform and correct

Every gaming lane (all except the two productivity lanes) enforces the same
latency floor, and the live verify confirms it is actually active on this PC
(`PowerSettingsHandler` and `RegistrySettingsHandler` both `all_active=true`):

| Dimension | Enforced value | Confirmed |
| --- | --- | --- |
| Windows Game Mode | On | all 44 lanes |
| Game Bar / Game DVR | Off / Off | all 44 lanes |
| HAGS (Hardware GPU Scheduling) | On | all 44 lanes |
| Power plan | Ultimate Performance, min-state 100, max-perf, core parking off | all gaming lanes (productivity relaxes min-state to 5) |
| Process/IO priority | 3/3 strict, **2/2 on capture lanes** | deliberate — capture lanes keep the game at Normal so OBS/Medal are not starved |
| Win32PrioritySeparation | 42 (short/fixed/high-foreground) gaming; 38 fighting/browser | per-family policy |
| CPU core partitioning | policy `full` (game → fast cores, background → rest) | all gaming lanes (this session's work) |

The 2/2-vs-3/3 split is correct by design: on a capture lane the whole point is
to coexist with the recorder, so the game does not claim High priority. Core
partitioning now does the latency-preserving work there instead (game on
P-cores, OBS on E-cores at full clock).

## Sync conditional — confirmed correct per lane type

- **No-sync lanes** (`*` base, `*-hdr`, `rivals2-nosync*`, all Slippi, Ryujinx):
  `global_vrr_mode=off` + `vrr_app_override=force_off` + a no-sync NVIDIA preset
  (`reflex_no_sync`, or the emulator LLM-on/VSync-off stack). Single untouched
  no-sync pipeline, tear accepted for minimum latency. Correct.
- **Strict G-SYNC lanes** (`*-gsync`, `*-gsync-hdr`): `global_vrr_mode=`
  `fullscreen_only`, `auto_vrr_fps_cap=True`, `reflex_gsync`/`ull_gsync` preset,
  FSO **enabled** per-exe (fullscreen path), `windowed_optimizations=False`.
  Correct G-SYNC + Reflex + auto-cap-below-refresh contract.
- **Capture G-SYNC lanes** (`*-gsync-capture`, `*-gsync-hdr-capture`):
  `global_vrr_mode=fullscreen_and_windowed`, `disable_global_fso=False`,
  FSO-per-exe **off**, `windowed_optimizations=True`, `vrr_optimize=True`.
  Correct borderless-VRR path so the overlay/recorder composits cleanly.
- **Fighting lanes** (Rivals 2): `vrr_cap_policy=fighting_60hz_vrr` (largest
  multiple of 60 below refresh−3 → 240 @ 300 Hz) / `fighting_60hz_nosync` (300).
  Threaded Optimization **On** (CPU-bound UE5, server-authoritative sim).
  Matches the settled Rivals policy.

## HDR conditional — confirmed correct per lane type

- **HDR lanes**: `hdr=True` + `advanced_color=True` + `auto_hdr=False`
  (native game HDR is preferred over Windows Auto-HDR injection) +
  `sdr_white_level_nits=200` (250 for Diablo IV, matching its brighter paper-
  white contract). Game-native HDR output paired with the correct SDR-content
  brightness for desktop legibility.
- **SDR lanes**: `hdr=False`, `auto_hdr=False`, no white-level write. Clean.

The HDR lanes correctly leave `auto_color_management` unset (ACM off) so Windows
does not re-tone-map a game already emitting HDR.

## OW2 — the one place the "optimal" default is an explicit, recorded choice

- G-SYNC lanes use `ull_gsync` + `vrr_cap_policy=ow2_reflex_gsync`
  (`refresh_minus_3`); the no-sync/fullscreen lanes use `reflex_no_sync`.
- This encodes the settled verdict: **Reflex hurts frame pacing under a
  reachable cap, helps only uncapped GPU-bound.** Recommended daily driver is
  `overwatch2-gsync-hdr` (or its capture sibling). The 276 fps you see is the
  intended driver FRL cap, not a bug.

## Slippi backend guidance — corrected this session

The Slippi in-game/post-apply notes previously said "Vulkan first, then test
DX12," carrying mainline Dolphin's advice. The 08-12 audit established the
installed netplay build is **Ishiiruka-derived with a D3D11-first backend
order**, where that advice does not transfer. Guidance now reads "keep your
current backend (D3D11 baseline on Ishiiruka builds); Vulkan/D3D12 are A/B
candidates." computa preserves whatever backend is configured either way — this
was a documentation-honesty fix, not a behavior change. Snapshot golden
regenerated; 334 profile tests green.

## What is deliberately NOT called "100% optimal" yet (benchmark-gated)

Unchanged from the 08-12 audit — these need controlled PresentMon/CapFrameX
captures on the same scene/driver/warm-cache before a default changes, and none
have artifacts under `reports/benchmarks/`:

1. OW2 native Reflex vs the current ULL/driver-cap policy.
2. Slippi D3D11 vs Vulkan vs D3D12, and HAGS per backend.
3. Deadlock DX11 vs Vulkan.
4. Fortnite / Marvel Rivals single native limiter vs same-value driver fallback.
5. The aggressive priority / MMCSS / pinned-core-floor / unlimited-shader-cache
   defaults themselves.

These are genuine A/B forks, not defects. Calling any of them "optimal" without
a capture would violate computa's evidence standard.

## User-owned manual steps (computa cannot write them)

- **NVIDIA per-app profile binding.** Driver 610.74 retired the Control Panel's
  named-profile picker and the NVIDIA App has none, so binding
  `<game>.exe → <profile>` in NVIDIA Profile Inspector (elevated) is the only
  path, and it surfaces as a manual verify step (currently open on the active
  Rivals lane). This is expected on every fresh apply.
- **Game-native video settings** on `system_only` families (CS2, OW2, Fortnite,
  etc.): Display Mode, in-game VSync Off, Reflex, HDR toggle. computa applies
  the machine/driver path and surfaces the exact in-game values in each lane's
  report.

## Live machine state at checkup

Active profile `rivals2-gsync-hdr-capture` (applied 2026-09-03 13:44), verified
read-only: `PowerSettingsHandler` and `RegistrySettingsHandler` active;
remaining mismatches are all expected non-defects — the open NVIDIA binding
manual step, and HDR/refresh reading inactive because the profile is applied at
an idle desktop with Rivals not running (no HDR surface, secondary panel refresh
read). No reboot pending, no pending-apply settings.

## Verdict

Machine-side and driver-side optimization is confirmed live and uniform;
per-lane sync and HDR conditionals are correct; the profile definitions are
sound (one documentation bug fixed). The remaining distance to a literal "100%"
is exactly two honest categories — the user-owned in-game/NVIDIA-binding manual
steps, and the five benchmark-gated A/B choices. Closing the latter is a
measurement task (PresentMon captures), which is the right next venture and
pairs naturally with the network-tuning pass you flagged.
