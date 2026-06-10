# Codex Handoff — ABSO / Overwatch 2 "locked at 150 FPS" investigation

**Author:** Claude (handing off after several wrong turns — see §4)
**Date:** 2026-06-09, evening session
**Status:** ~~UNSOLVED~~ **RESOLVED 2026-06-09 (late session) — root cause found and fixed. See §11 below.** Sections 0–10 are preserved as the historical investigation record.

---

## 11. RESOLUTION (2026-06-09, late session)

**Root cause: a stale `profile_overrides` block in `abso.yaml` (repo + installed copy)
forced `graphics.disable_mpo: true` on both OW2 G-SYNC HDR lanes.** It was written
2026-05-30 00:50 — four minutes before commit 51552de flipped the profiles to the
optimized borderless path (`disable_mpo: False`). Config overrides win over the
profile in applier PHASE 6, so every OW2 apply silently re-wrote
`DisableOverlays=1` + `OverlayTestMode=5`, and verification compared live state
against the *overridden* target — which is why `state --verify` always looked
clean and why reasoning from profile source kept failing (§4's "pattern to learn
from" was exactly right).

**Why it broke when it did:** MPO disable is boot-gated. The poisoned registry
target sat pending for days (the 06-04 briefing recorded
`reboot_pending: mpo_disabled`); the first reboot in the Process-Lasso work
window committed it (and the 2026-06-09 22:53 boot re-committed it). With MPO
dead on this Canary build + HDR + mixed-refresh topology, the borderless window
loses independent flip → windowed G-SYNC cannot engage → the OW2 DRS profile's
forced V-SYNC backstop (double-buffered, `triple_buffering=0`) takes over → the
in-game 297 cap (3.367 ms > 3.333 ms refresh interval) misses **every** vblank →
exactly 150 fps. The Process Lasso runtime was a timing coincidence (your §3
stop-test rule-out was correct).

**Evidence (no experiments needed):** the backup chain — every apply makes a
`pre_switch` + `pre_apply` pair — showed `mpo_disabled` flipping False→True
across each OW2 apply but not the Rivals apply; the tray log recorded
`mpo_disabled {'target': True, ...}` warnings on the 16:28 and 20:32 applies;
the 20:32:33 pre-apply backup captured `mpo_disabled: false` while the registry
held both disable values afterward.

**Fixes shipped (all tested, 2117 passed, deployed via `build.py deploy`):**
1. `abso.yaml` (repo; installed copy updated by deploy): overrides removed,
   incident documented inline.
2. `abso/core/applier.py`: apply now emits a `Config override conflict` warning
   whenever a config override replaces an explicitly declared profile value
   (`_collect_override_conflicts`; tests in
   `tests/test_core/test_applier_override_conflicts.py`). This makes the silent
   failure mode of this incident impossible to repeat quietly.
3. `abso/core/detector.py`: the `1-48Hz` VRR range (§2) was an ABSO EDID parser
   bug, not driver state — v2+ AMD FreeSync VSDBs carry min/max at +6/+7, not
   +5/+6. The LG 27GS95QE's real FreeSync range is 48–240 (panel range-limits
   descriptor: 48–300). Fixed with the real LG block as a test fixture.
4. `overwatch2-gsync-hdr` reapplied → the MPO-disable registry values are
   deleted; a reboot commits the MPO-on compositor path.

**Corrections to earlier claims in this document:**
- §2/§7 "two cpu-balance instances (duplicate-spawn bug)": **not a bug.**
  `abso.exe` is a PyInstaller one-file binary — every invocation shows a
  bootloader parent + child with identical command lines (same stop-file).
- Paired backups per apply are the designed `pre_switch`/`pre_apply` two-stage
  flow, not duplicate applies.
- §5 experiments were rendered unnecessary; the forensic chain above answered
  them. §5.8's question resolved as "ABSO artifact" (now fixed).

**Verification after the user reboots:** launch OW2 (fresh process picks up DRS
+ DX flags at launch) → expect ~276 fps with Reflex On+Boost (the validated
ceiling), or high-and-variable in GPU-heavy scenes. If it is STILL 150 after a
reboot, fall back to §5.1/§5.2/§5.3 (fullscreen A/B, driver-VSync-off A/B,
G-SYNC indicator).

**OUTCOME (2026-06-10): USER-CONFIRMED FIXED.** After the Windows reboot
committed the MPO-enable target, the user reports OW2 back at **276 fps**
(the Reflex On+Boost ceiling). Post-reboot `state --json --verify` is fully
clean (`all_active: true`, no pending or reboot-gated settings) and both MPO
registry values remain absent. Root cause, fix, and prediction all validated
end-to-end.

---

## 0. Your mission

Overwatch 2 is locked at a flat **150 fps** on a **300 Hz** monitor. The user wants the
**actual** root cause found, "no matter what it is." I cycled through several confident
wrong diagnoses; the user correctly said I was hallucinating. **Do not reason forward from
the profile config — it has repeatedly *said* the right thing while reality differs.**
Design decisive experiments (§5) and isolate empirically.

Key meta-clue from the user: *"this issue only popped up recently after the Process Lasso
changes; the profile was working fine before that."* Before = ~276 fps. After a redeploy +
re-apply of the `overwatch2-gsync-hdr` profile (~16:28 today) = 150.

---

## 1. The symptom

- OW2 reports a steady **150 fps**, described as "150 capped."
- 150 = **exactly half** of the 300 Hz panel.
- User's historical normal on this rig: **~276 fps** (recorded as "Reflex Boost", validated 2026-05-28).
- Rig: **i9-14900F + RTX 4070 + 300 Hz 1440p (LG UltraGear) primary + 60 Hz Dell S2719DGF secondary.**

---

## 2. HARD FACTS (measured this session — trust these)

### Load while OW2 running at 150 fps
- **GPU utilization: 64%**, 149.4 W / 200 W limit, core 2910 MHz, 63 °C, mem util 32%.
- **CPU total: 23%.**
- => Massive head-room on both. This is a **deliberate cap / frame-pacing lock, NOT a GPU- or CPU-bound limit.**

### Display
- `Win32_VideoController.CurrentRefreshRate` = **299 Hz**, 2560×1440. (Panel IS at 300 Hz.)
- System DPI = **96 (100% scaling)**. (No DPI weirdness.)
- `abso detect`: primary = **"Generic PnP Monitor"**, refresh 300, `vrr_supported=true`,
  `vrr_type=gsync_compatible`, **`vrr_range="1-48Hz"`**, `max_refresh_rate=null`.
  Secondary Dell = 59.95 Hz, max 144, `vrr_range=null`. **Mixed-refresh dual-monitor.**
  - The `1-48Hz` range + `Generic PnP Monitor` + null max are SUSPICIOUS. Unknown whether this
    is the *real* driver VRR range (which would mean G-SYNC only works ≤48 fps → VSync above)
    or an ABSO EDID-parse artifact. **NOT yet verified against a second source (e.g. NVCP UI,
    `monitor.GetVrrRange` NVAPI, or the EDID).**

### OW2 in-game config (`%USERPROFILE%\Documents\Overwatch\Settings\Settings_v0.ini`)
```
FrameRateCap        = "297"      DesiredFrameRate = "300"
LimitToRefresh      = "0"        UseCustomFrameRates = "1"
VerticalSyncEnabled = "0"        (in-game VSync OFF)
ReflexMode          = "2"        (Reflex on/boost)
WindowMode          = "1"        WindowedFullscreen = "1"  (BORDERLESS windowed)
FullScreenRefresh   = "300"      WindowedRefresh = "300"
```
No literal `150` anywhere in the file. (`FPS="60"` is the highlight-recording rate, irrelevant.)

### NVIDIA driver (NVAPI DRS — read via `DRSProfileManager`)
- **Global/base profile:** `vrr_mode=2` (fullscreen_and_windowed), `frame_rate_limiter_v3=0`
  (global FRL OFF), `vsync_mode=0x08416747` (OFF).
- **"Overwatch 2" profile:** `frame_rate_limiter_v3=297`, **`vsync_mode=0x47814940` (VSYNC FORCE ON)**,
  `vrr_app_override=0` (allow G-SYNC), `low_latency_mode=0`, `triple_buffering=0`, `vsync_vrr_control=1`.
- => The only cap values present are **297**, never 150. The OW2 profile force-enables driver VSync
  (intended as a G-SYNC tear backstop), with **triple buffering OFF** (so VSync is double-buffered:
  binary 300-or-150).
- Whether Overwatch.exe is actually *bound* to the "Overwatch 2" DRS profile is **not confirmed**
  (`get_app_settings("Overwatch.exe")` falls back to base profile because it guesses the name
  `"ABSO - Overwatch"`; the real binding wasn't proven).

### Windows windowed-VRR flags (`HKCU\...\DirectX\UserGpuPreferences\DirectXUserGlobalSettings`)
- `AutoHDREnable=0; SwapEffectUpgradeEnable=1; VRROptimizeEnable=1`.
- Per-app entry for `...\Overwatch.exe` = only `"AppStatus=0;"` (no VRR/optimization override).

### Processes
- `dwm.exe`: **NOT** in EcoQoS, priority High, full affinity — compositor is fine.
- `Overwatch.exe`: priority **High**, ~120 threads. Anti-cheat blocks `OpenProcess`/`ProcessorAffinity`
  reads, so its EcoQoS state and core affinity could NOT be read directly.
- **No RTSS / MSI Afterburner / RivaTuner running.** `nvcontainer.exe` ×3 running (NVIDIA app/driver).
- Process Lasso daemon that was running: `abso.exe cpu-balance --pid 12024 --stop-file ...tmp5FBD.tmp
  --cpu-sets --eco --watchdog` — **two instances** (duplicate-spawn bug). **Now stopped (see §6).**

---

## 3. What's been RULED OUT (with evidence)

| Hypothesis | How it was ruled out |
|---|---|
| GPU-bound | GPU at 64% |
| CPU-bound | CPU at 23% |
| 3rd-party frame limiter (RTSS/Afterburner) | none running |
| OW2 in-game cap = 150 | config shows 297, no 150 anywhere |
| NVIDIA driver FRL = 150 | global FRL 0, OW2 profile FRL 297 |
| **Process Lasso runtime (cpu-balance daemon: cpu-sets/eco/watchdog)** | **STOPPED ALL of it (0 daemons, 0 tray, 0 abso.exe) → STILL 150.** Definitively not the running daemon. |
| The 3 "VRR enablers" being wrong | I set them correct (`vrr_mode=2`, both Windows flags on) and verified they held → STILL 150 |

---

## 4. Hypotheses I tried — DO NOT TRUST THESE (several were wrong)

1. **WRONG — "NVIDIA backup is broken → applier skips the NVIDIA handler → NVIDIA never applies."**
   Disproven: NVIDIA `apply()` works via NVAPI DRS; the "Overwatch 2" profile exists with correct
   settings. The "Skipping NvidiaSettingsHandler" log line is from the baseline-*restore* step
   (`backup.py:299`), not the apply.

2. **UNCONFIRMED / probably incomplete — "3 borderless-VRR enablers (NVIDIA `vrr_mode`,
   Windows `SwapEffectUpgradeEnable`, `VRROptimizeEnable`) get dropped during apply → G-SYNC
   doesn't engage → 150."** I found all three live-wrong and corrected them. fps stayed 150. So
   either they weren't the cause, or G-SYNC still isn't engaging for another reason. (I shipped a
   `vrr_reconcile.py` fix for the drop anyway — see §7 — but it did NOT fix the fps.)

3. **UNCONFIRMED — current best guess — "double-buffered VSync force-on locks to half-refresh
   (150) because G-SYNC isn't actually engaging."** The 64% GPU util is *consistent* with a
   double-buffer VSync half-lock (a ~4.3 ms frame just misses the 3.3 ms needed for 300, so it
   drops to the 6.7 ms / 150 step and idles). **But I never directly verified G-SYNC's active
   state, nor ran the VSync-off or Fullscreen experiment.** This is a hypothesis, not a finding.

4. **WRONG aim — Process Lasso daemon.** Ruled out by the user's stop-test (§3).

**Pattern to learn from:** every time I reasoned from "the profile declares X," reality differed.
Stop trusting declared config. Measure the effective state and run experiments.

---

## 5. DECISIVE experiments NOT yet run (this is the actual work)

Each isolates a variable. Prefer these over more config reading.

1. **Fullscreen vs Borderless.** Set OW2 → Display Mode → **Fullscreen (exclusive)**. Exclusive
   fullscreen bypasses DWM. If fps jumps off 150 → the borderless/DWM/compositor path is the
   problem. (Instant, no game restart.)
2. **Driver VSync OFF.** Set the "Overwatch 2" DRS `vsync_mode` to off (or NVCP per-app VSync
   = Off), restart OW2. If fps jumps to ~234 *with tearing* → it IS the VSync half-lock and the
   real problem is G-SYNC not engaging. If still 150 → VSync is NOT the cap; look elsewhere.
   (DRS changes are read at game launch — needs an OW2 restart.)
3. **G-SYNC Indicator.** NVCP → Display → Set up G-SYNC → "Enable indicator for G-SYNC" — shows
   on-screen whether G-SYNC is *actually active* in OW2. Most direct answer to "is G-SYNC engaging."
4. **No-sync profile A/B.** Apply `overwatch2` or `overwatch2-hdr` (no-sync variants: exclusive
   fullscreen, VSync off, VRR off, uncapped 600). If fps is high there but 150 on the G-SYNC
   borderless variants → isolates to the G-SYNC/borderless/VSync path. If it ALSO caps ~150 →
   something more fundamental (power/display/system).
5. **Second monitor.** Disable the 60 Hz Dell (or set it to 144 Hz) and retest borderless. Mixed
   refresh + DWM is a classic borderless-VRR killer.
6. **Reboot.** There's a pending reboot-gated graphics change (MPO) from the 16:28 apply, AND the
   monitor is enumerating as "Generic PnP Monitor" with a degraded `1-48Hz` VRR range — a reboot
   (or DisplayPort unplug/replug) re-handshakes the monitor's real VRR range. The enablers I set
   persist through reboot. Strong candidate, untested.
7. **Revert the Process-Lasso-era persistent changes and retest.** The daemon is ruled out, but
   the same work applied **`processor_min_state=100` + `disable_core_parking`** (powercfg, PERSISTENT)
   at 16:28. Revert those (`powercfg` back to defaults) and retest — the user's "after the changes"
   timing could be a persistent power/display setting, not the runtime daemon.
8. **Verify the real monitor VRR range.** Is `1-48Hz` real or an ABSO artifact? Check NVCP's
   G-SYNC range display / NVAPI `NvAPI_DISP_GetMonitorCapabilities` / the EDID. If the driver
   genuinely thinks VRR max is 48, G-SYNC dies above 48 fps → VSync → 150. That would be THE cause.
9. **NVIDIA app runtime cap.** `nvcontainer` is running; the new NVIDIA app can apply a "Max Frame
   Rate" at runtime that does NOT appear in the DRS database I read. Check NVIDIA app → Settings →
   Max Frame Rate (global) AND Graphics → Overwatch 2 → Max Frame Rate, and its on-disk store under
   `%LOCALAPPDATA%\NVIDIA Corporation\NVIDIA App\`.
10. **Does 150 survive a fresh OW2 relaunch with the tray/ProcessLasso permanently off?** (It's off
    now.) Confirms whether the cap is a persistent driver/OS/game setting vs anything ABSO-runtime.

**Also consider (things I did NOT explore):** Windows Dynamic Refresh Rate / per-app refresh
limiting; MPO/flip-mode giving the borderless window a 150 Hz presentation while the desktop is 300;
a GPU power-state/clock cap (2910 MHz / 149 W — looks normal, but verify P-state isn't pinned);
OW2-specific behavior on the current driver; Frame Generation/Smooth Motion; the OW2 "Reduce
Buffering"/Reflex interaction; whether the in-game fps counter itself is reading something odd.

---

## 6. Current LIVE machine state (I changed things — IMPORTANT)

- **NVIDIA global `vrr_mode` = 2** (I set it; it was 1/fullscreen-only).
- **Windows `SwapEffectUpgradeEnable=1`, `VRROptimizeEnable=1`** (I set them; were 0).
- **Process Lasso is fully STOPPED:** I killed the tray and stopped both `cpu-balance` daemons via
  the graceful stop-sentinel (`...\Temp\tmp5FBD.tmp`). **The system tray is currently NOT running.**
  (Re-launch with scheduled task `ABSO-Tray-Startup`, or `powershell -File <installed>\abso\tray\ABSO-Tray.ps1`.)
- **OW2 was running** (pid 12024, launched 20:33 today). May still be.
- **Pending reboot-gated graphics change (MPO)** from the 16:28 apply; `.abso_state.json`
  `reboot_pending` may be set. Machine has NOT been rebooted since that apply.
- The "Overwatch 2" DRS profile still has **VSync FORCE ON**.

---

## 7. Code changes made this session (repo + deploy state)

All under `C:\Users\mtoli\Documents\Code\windowsoptimizerabso`. Backend deployed to
`%LOCALAPPDATA%\AdaptiveBattleStationOptimizer` via `build.py deploy` / `deploy-existing`.

1. **`abso/core/state_reconcile.py`** — fixed reboot-pending reconcile (`boot_commits_reboot_gated_writes`)
   + `tests/test_core/test_state_reconcile.py`. DEPLOYED. (Unrelated to fps; fixed a stale "restart
   required" banner.)
2. **`abso/core/vrr_reconcile.py` (NEW)** + applier wiring (`applier.py` "PHASE 7.5") +
   `WindowsSettingsHandler.get_windowed_vrr_flags()` + `abso.spec` hiddenimport +
   `tests/test_core/test_vrr_reconcile.py`. DEPLOYED. **Post-apply re-assert/verify of the 3 VRR
   enablers. Did NOT fix the 150 fps** (enablers are correct; fps still 150).
3. **`abso/tray/ABSO-Tray.ps1`** — standardized owner-draw chip right-inset `Width-10 → Width-24`
   (UI clipping fix, unrelated to fps). DEPLOYED via `deploy-existing`.
4. **Earlier (the "Process Lasso changes" the user refers to):** `cpu_balancer.py`, `cpu_sets.py`,
   `efficiency_mode.py`, `cpu_limiter.py`, `watchdog.py`, `watchdog_engine.py`, `proc_actions.py`,
   config, tray wiring. Daemon spawns `cpu-balance --cpu-sets --eco --watchdog`. **Known bug:
   duplicate daemons spawn per game (one per tray restart).** Ruled out as the fps cause but should
   be fixed.
5. **Power settings added to the Reflex latency base profiles:** `processor_min_state=100`,
   `disable_core_parking=True` (`abso/profiles/profile_bases.py`). Applied to the live power plan at
   16:28. PERSISTENT. Candidate for experiment §5.7.

Full suite was green (2112 passed) after the vrr_reconcile work.

---

## 8. Key files & where to look

- OW2 profiles: `abso/profiles/overwatch2.py` — `Overwatch2GSyncHDRProfile` (`overwatch2-gsync-hdr`,
  the one in play), `...HDRCaptureProfile` (`-hdr-capture`, what the user ran before). All G-SYNC
  variants declare `global_vrr_mode: fullscreen_and_windowed`, `disable_mpo: False`,
  `_windowed_vrr_windows_settings()` = `{windowed_optimizations, vrr_optimize}`.
- NVIDIA: `abso/settings/nvidia/nvapi_drs.py` (`DRSProfileManager`, `VSYNC_VALUES`,
  `VRR_MODE_VALUES`, `get_app_settings`, `apply_settings_to_global`, `get_setting`/`set_setting`),
  `abso/settings/nvidia/__init__.py` (handler), `abso/settings/nvidia/presets.py`
  (`reflex_gsync` preset — defines the **vsync force-on**; verify this is what you want with G-SYNC).
- Windows VRR flags: `abso/settings/windows.py` (`DIRECTX_FLAG_NAMES`, `_set_directx_flag`,
  `get_windowed_vrr_flags`).
- State file: `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\.abso_state.json`.
- OW2 config: `%USERPROFILE%\Documents\Overwatch\Settings\Settings_v0.ini`.
- Memory (Claude's notes, point-in-time, may be stale): the project memory dir has
  `project_vrr_enabler_fix.md`, `project_ow2_reflex_276.md`, `project_user_rig.md`,
  `project_process_lasso_gaps.md`.

### Handy read commands (run from repo root, `$env:PYTHONPATH = (Get-Location).Path`)
```powershell
# DRS state
python -c "from abso.settings.nvidia.nvapi_drs import DRSProfileManager as M; print(M().get_app_settings()); print(M().get_app_settings(profile_name='Overwatch 2'))"
# Windows VRR flags
python -c "from abso.settings.windows import WindowsSettingsHandler as H; print(H().get_windowed_vrr_flags())"
# GPU load
& "$env:ProgramFiles\NVIDIA Corporation\NVSMI\nvidia-smi.exe" --query-gpu=utilization.gpu,clocks.current.graphics,power.draw --format=csv
```

---

## 9. Constraints & gotchas

- **CLAUDE.md constraint #6:** do NOT run full profile apply / live display reset / HDR cycling /
  DWM restart / driver reset just because the secondary monitor flickers. (Display churn during
  apply is itself a suspect for the degraded monitor VRR state.)
- Single-user gaming rig; OW2 may be running. Always back up before apply. Deploy only via `build.py`.
- Overwatch.exe is anti-cheat protected — `OpenProcess` and affinity reads fail; don't rely on them.
- `Win32_Process` searches for `cpu-balance` will match *your own query's command line* — filter by
  `Name='abso.exe'` to find real daemons (this bit me; produced phantom "respawning daemons").
- The user is (rightly) skeptical of narrative reasoning. Lead with experiments and measured deltas.

---

## 10. The single most important next step

Run experiment **§5.1 (Fullscreen)** and **§5.2 (VSync off)** — together they tell you in two
minutes whether this is a VSync-half-lock that depends on G-SYNC engagement, or a hard 150 cap
from some other source. Everything else branches off that answer. Do not write more code or apply
more profiles until one experiment has moved the number off 150.
