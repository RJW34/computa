# End-to-end audit: profile truth, local configuration, and runtime cost

Date: 2026-09-06. Starting checkout: `master` at `aeba7bb`.

The program is useful, but neither a clean verifier nor its current profile
catalog establishes the best achievable performance on this PC. This audit
found concrete defects, corrected a substantial set in source, and identified
remaining release and measurement gaps. No gaming performance improvement is
claimed from the source changes alone.

**Initial release blocker (resolved by the deployment below): source/install divergence.**
The checkout began with 38 profiles; the installed backend exposes 44. Recent
Fortnite capture/restore, NVIDIA verification, menu timer, and CPU partitioning
work exists on `feat/core-partitioning-and-optimization-venture`, through
`794a97e`. Relevant commits include `4702387`, `c20bf5f`, `b1433c1`, and
`a71a103`. Separately, `perf/gaming-session-overhead` contains conditional
sanitizer launch suppression and five-minute priority maintenance (`0fbe53b`)
and one-directory packaging (`3b9e144`). The initial audit checkout did not
include those changes. The deployment
below reconciles the installed feature branch; the separate packaging and
conditional-launch experiments remain deferred.

The six installed profiles initially missing from source were the two Fortnite G-SYNC
capture lanes, the two Slippi capture lanes, `rivals2-gsync-capture`, and
`counter-strike-2-gsync-capture`. The initial installed backend SHA256 starts
`42800ee1bd9187ac`; the full hashes/catalog difference are in `provenance.json`.

## Deployment follow-up: 2026-09-06

User explicitly requested deployment. Branch `codex/deploy-audit-20260906`
saves the audit in `0b1e616`, merges the installed feature branch in `349e9e5`,
and fixes GUI backend discovery in `3501e5e`. All 44 profiles are retained.
The GUI now finds the deployed `computa.exe` while retaining legacy Tauri
sidecar compatibility. The separate `perf/gaming-session-overhead` branch
was not merged; it suppresses some launches and performs periodic priority
maintenance, rather than providing a resident sanitizer.

Both release executables were rebuilt, then installed with
`build.py deploy-existing`. The validated idle tray PID 19228 was stopped
only after confirming no game/backend job was running; startup task
`ABSO-Tray-Startup` launched PID 20596. Its runtime marker and all loaded
module hashes match the deployed files. No full profile apply or display reset
was performed. The active CS2 HDR capture profile and original apply timestamp
are unchanged, verification is `all_active: true`, and no reboot is pending.
Backend config and saved profile state are byte-identical; tray preferences
are unchanged except startup bookkeeping fields.

| Artifact | SHA256 |
| --- | --- |
| Backend, 18,389,945 bytes | `c016db68efb61a4ed70913446b439e22308c31575867af720df693eb061c1b82` |
| GUI, 6,026,240 bytes | `cf4c115c1897f20778895806dd0f11e1a281671562f8465995089e9eca6c3ddf` |
| Tray script | `2ca224d31cba4506a69130bd2b93137d8c01867b55cc55a9d2d438d525add51b` |

Validation: 2,782 Python tests passed / 13 integration tests deselected;
Ruff, whitespace checks, 3 GUI state tests, GUI lint, 7 release-mode Rust
resolver tests, and both release builds passed. The existing unknown pytest
asyncio option warning remains. Frozen hardware detection succeeded; frozen
and installed game discovery each found nine games in about 1.1 seconds.
Installed health reports 9 OK / 1 existing topology warning / 0 errors.
The secondary monitor remains at 59.95 Hz; no display mode was changed.
The GUI was compiled and its backend resolver tested, without an interactive
GUI session. These checks do not establish maximum game performance.

Two post-restart 30-second process samples measured 0.16–0.19% of total
32-thread CPU (5.2–6.2% of one core), 278–285 MiB working set and
160–164 MiB private memory. This does not demonstrate lower idle CPU than the
initial audit sample. The startup log is clean and no backend/game/governor
child or repeated launch loop was found. `showQuickPanel` remains enabled;
its 80 ms visible animation is a possible comparison confound, but panel
visibility was not confirmed through the automation helper. Compare identical
UI visibility before attributing the CPU or working-set difference to a code
regression. Private memory was lower than the old sample. Further profiling
and game benchmarks remain necessary for performance claims.

Previous backend and GUI are in the installed `deploy-backups` directory with
suffix `.bak-20260906-165959`; pre-deploy tray/config snapshots, hashes, build
logs and readbacks are under `reports/deployments/2026-09-06-audit/`.

## Evidence and scope

Four coordinated reviews covered every registered source profile and inherited
NVIDIA preset, settings/verification/backup paths, CPU session runtime, tray
startup/timers/process work, GUI state, detection, benchmark storage, and CI.
This is broad source analysis, focused regression testing, and read-only local
evidence, not line-by-line formal verification or a game benchmark campaign.

Detailed local findings, including additional candidates and exact code
anchors, are preserved with raw evidence under
`reports/audits/2026-09-06-end-to-end/`:

- [Profile findings](../../reports/audits/2026-09-06-end-to-end/profiles-findings.md)
  and [expanded effective settings](../../reports/audits/2026-09-06-end-to-end/profiles-effective-settings.json).
- [Tray findings](../../reports/audits/2026-09-06-end-to-end/tray-findings.md).
- [Handler findings](../../reports/audits/2026-09-06-end-to-end/handlers-findings.md).
- Installed detect/state/health/display/profile JSON, saved game configuration
  readbacks, CPU Sets topology, resource samples, and test output.

Raw reports are local and may be gitignored. This document preserves the
principal conclusions in tracked documentation. “Fixed” below means source
and tests, now deployed as described above. Existing unrelated untracked
files were preserved. The audit itself made no live profile apply, restore,
display reset, HDR cycle, game-config write, tray restart, or priority change.
One manual backup captured current state without applying changes.

## This machine, as observed

| Item | Read-only evidence | Implication |
| --- | --- | --- |
| CPU | i9-14900F; Win32 CPU Sets shows 8 physical P-cores/16 P-threads and 16 physical E-cores | Installed summary incorrectly reverses P/E physical core counts. Fixed source arithmetic; CPU-set readback independently confirms the split. |
| GPU / RAM | RTX 4070, driver 616.56, about 12 GB VRAM, 32 GB RAM | No graphics preset or CPU policy is a measured optimum merely because it matches this hardware. |
| OS | Build 29648.1000, experimental future-platform branch | Old Windows tuning and compatibility claims need validation against this build. |
| Displays | Primary 2560x1440 at 300 Hz; Dell secondary 2560x1440 at 59.95 Hz, enumerated capability 144 Hz | Secondary refresh merits deliberate review; topology alone does not prove a fault or authorize changing it. |
| Active profile | `counter-strike-2-gsync-hdr-capture`, no reboot pending | Installed verifier says active; health is 9 OK / 1 topology warning / 0 errors. This is supported setting readback, not proof of game FPS, latency, HDR, or Reflex. |
| Display events | No matching events, no channel errors in the sampled lookback | Does not prove the compositor is optimal or identify the cause of a past black flash. |
| Tray PID 19228 | About 0.052% of one core / 0.0016% total CPU over 30 seconds; 171 MiB working set, 198 MiB private memory | Current installed tray is CPU-quiet in this sample. An idle sample excludes future game-time children and visible animation costs. |
| Native configuration audit | Full `audit --json` refused because this shell is not elevated | Hardware, BIOS, state, health, targeted file reads and hermetic tests succeeded; a privileged full audit was not completed. |

The CPU specification also agrees with
[Intel's published core counts](https://www.intel.com/content/www/us/en/products/compare.html?productIds=236853%2C236777%2C236786%2C236854).
The earlier briefing's claim that persistent tray CPU must be PowerShell's
message pump was not proven by a profiler. Later timer fixes and this low
current sample make that an unsuitable premise for a rewrite decision.

## Principal source corrections

| Area | Defect or false claim | Correction |
| --- | --- | --- |
| OW2 G-SYNC | Driver 276/native 297, Ultra LLM, Reflex Off, with an unsupported claim of measured Reflex regressions | Built-in static ceilings both use refresh minus three; native Reflex-compatible preset and expected On+Boost. At 300 Hz the saved cap is 297. Dynamic runtime pacing remains separate. |
| OW2 streaming aliases | Old streaming names selected capture-terminating profiles | Resolve to matching capture siblings; regression tests check process policy. |
| CPU governor | Numeric priority identifiers were treated as an ordered scale, missing Normal/High offenders | Explicit semantic priority ordering. |
| CPU accounting | Divided accumulated CPU time by a fixed poll interval even after longer gaps; PID reuse polluted samples | Use elapsed samples and process creation identity; check restoration results. |
| Tray state | CLI/GUI switches could leave an old profile's killset running | Adopt current backend state before session work; stop obsolete session work on profile changes; pause on unreadable state. |
| Tray animation | 90 ms menu timer ran while hidden | Gate on visibility/open lifecycle and deduplicate invalidation. |
| Tray catalog | A delayed callback still blocked the UI for up to 25 seconds | Polled asynchronous subprocess stages, deadlines, coalescing, and cleanup. |
| Tray priority guard | Idle/BelowNormal background processes could be raised to Normal | Demote only genuinely higher classes. |
| Tray cache | Write failure could be logged as current; destination could be truncated | Atomic replacement, preserve old cache on failure, distinguish failed refresh. |
| Tray sessions | Empty killset prevented unrelated governor/keep-awake features | Separate game-session lifecycle from killset eligibility. |
| Game discovery | Repeated recursive scan for every executable; comment falsely promised depth three | One bounded scan per install across wanted names, depth/directory budgets, no junction traversal. |
| Local configuration | `cpu_affinity` in this PC's Slippi overrides was rejected, preventing normal config load | Add the existing handler's override field/mapping and a loader/handler regression test. This does not prove the affinity handler's runtime behavior. |
| Hardware summary | Reversed P/E physical-core formula | Correct arithmetic; omit invented splits when SMT totals cannot establish them. |
| GUI state | Saved profile with missing or incomplete verification fell through to Active | Show unknown until verification is clean; surface explicit errors. |
| UE restore | Restoring a complete old file could erase later unrelated user settings | Restore mapped managed keys atomically; preserve unrelated current content; report missing/unresolved configuration honestly. |
| NVIDIA ABI/verification | Wrong application structure layouts and missing readbacks could produce failure or false success | Correct V1-V4 layouts; require actual driver readback and handle failures. |
| Audio/Game DVR/NIC/interrupt rollback | Exceptions were swallowed and restore still returned true | Propagate failure, including native false return/nonterminating PowerShell errors. |
| Power rollback | Failed plan restoration still wrote captured values into the wrong active plan | Abort sub-setting writes when the captured scheme cannot be reactivated. |
| Memory purge | Outer JSON success could hide inner failure; available-memory delta called bytes freed | Propagate failure and exit status; label available-memory change accurately; tray checks both layers. |
| MMCSS | GPU Priority 8 written and described as accelerating GPU work | Remove unused declarations from built-in profiles and correct registry prose. |
| Performance prose | Unmeasured VBS/XMP FPS percentages, HAGS/cache guarantees, HDR eye-strain claims, boolean Reflex called Boost, static reports claiming prior successful apply | Remove or qualify claims; distinguish requests, readbacks, compatibility choices, and measured outcomes. |
| Display advice | Said “after the pending reboot” when none was pending and implied HAGS cures mixed-refresh issues | Conditional, evidence-limited advice without an invented pending reboot. |

The most visible scan result: installed `games --json` exceeded the 100-second
observation limit; updated source completed in 0.53 seconds and found the
expected eight game families (with duplicate Slippi install roots). These are
different builds and execution contexts, not a controlled same-binary speedup
ratio. Tests separately prove bounded traversal and one visit per directory.
The bounded fallback can omit unusually deep custom installs; launcher
metadata remains preferred and discovery is not proof of absence.

## Remaining high-impact findings

| Priority | Finding | Required follow-up |
| --- | --- | --- |
| Resolved | Source/install/branch divergence | Installed 44-profile feature set and audit fixes reconciled and deployed. Separate sanitizer-launch suppression and packaging experiments remain deferred. |
| P1 | Full Windows restore uses a detect dictionary as apply input | Implement captured per-display state restoration. Aggregate HDR and truthy `max_refresh_rate` can restore different display targets; unknown values must not become false writes. |
| P1 | Backup creation can return an ID while important components failed or cannot restore | Validate manifest completeness/restorability for intended mutations before transactions proceed. This audit's manual capture explicitly said NVIDIA restore was unavailable. A successful capture is not a full rollback guarantee. |
| P1 | Some native handlers still restore full old files | Extend ownership-aware restore beyond shared UE to OW2, Rivals, Diablo and Dolphin, with tests for later keybind/graphics/calibration edits. |
| P1 | Remaining streaming aliases discard capture intent | Fortnite, Ryujinx and other aliases lacking equivalent source capture lanes must not silently resolve to capture-terminating profiles. Restore/reconcile missing lane contracts first. |
| P1 | Tray operations permit reentrancy and a cross-process state/start race | One transaction coordinator; backend automatic sweep should check expected active profile before acting. |
| P2 | Governor stop blocks up to 3 seconds then hard-kills | Asynchronous stop acknowledgement and recovery evidence; forced termination can skip cleanup. |
| P2 | Session sanitizer starts a frozen backend every 10 seconds | Evaluate conditional launches and periodic priority maintenance; benchmark tray and children together. Do not skip launches solely on kill-target presence because the command also enforces priority. |
| P2 | CPU-affinity persistence/readback does not prove scheduling | The existing handler uses AppCompat markers and suppresses live affinity errors. Validate Win32 affinity and launch behavior before claiming the local Slippi override works. |
| P2 | Audio/NIC selectors can choose the wrong endpoint | First active audio endpoint is not necessarily default; first Up NIC is not necessarily the game's route. Resolve actual default endpoint/route. NIC `-NoRestart` writes also need effective-state semantics. |
| P2 | Display diagnostics invent capability certainty | `MultiMonitorDetector` hardcodes `is_hdr_capable=False`; installed primary also reports a 48–240 VRR range while running 300 Hz. Preserve unknowns and distinguish capability, enabled state, and engagement. |
| P2 | “Online” metadata is inferred from rollback optimization target | Separate network-play safety policy from optimization labels; many shooters bypass the intended online watchdog restriction. |
| P2 | Shared gaming defaults are broadly aggressive and unmeasured | CPU minimum 100%, disabled parking, high CPU/I/O priority, MSI, audio and NIC tuning need isolated comparison. More settings do not establish better performance. |
| P2 | Color and HDR defaults are not calibration | Fixed vibrance/white point/nits and global SDR changes can conflict with the actual panel. Windows HDR, native game HDR, Auto HDR, and RTX HDR must have separate contracts. |
| P2 | Native-game verification is incomplete | CS2/Deadlock lack native handlers; a saved boolean does not prove Boost, frame generation, HDR, or game recognition. Surface unverified native prerequisites explicitly. |
| P2 | Benchmark evidence is insufficient | No matching baseline/comparison artifacts were found in the repository or installed benchmark locations. Storage lacks enough driver/CPU/game-build/scene/settings provenance to guarantee comparable runs. Zero valid frame samples currently become a zero-valued analysis. Reject unusable captures and compare equivalent workloads. |
| P2 | Quality rubric promises gates not represented in CI | CI runs Python tests/lint/type checks but does not enforce all claimed GUI/build/benchmark/per-setting evidence gates. Document implemented gates and add missing checks. |
| P3 | Catalog refresh, startup state repair and discovery cadence remain imperfect | New menu rows do not fully refresh; historical metadata can manufacture backend state; idle game detection can lag by 30 seconds. See detailed tray report. |

Several of these are release blockers, not recommended live experiments.
The detailed domain reports retain more findings than this principal register.

## Per-game priorities on this PC

Saved configuration below is a file readback, not a claim that a non-selected
profile is drifting or that a game is currently running.

| Game | Observed state / audit priority | Next evidence needed |
| --- | --- | --- |
| CS2 | Selected installed capture G-SYNC HDR lane verifies clean | Confirm renderer, native VSync/Reflex, fullscreen mode and whether capture is active. Compare native sync path and sustainable cap in the same scene; there is no automated native-handler proof. |
| Fortnite | Saved borderless, VSync on, engine limit 0, native HDR off; installed capture lanes exist but source lacks them | Preserve the newer capture path and user-owned graphics. Record actual DLSS/quality/renderer and GPU load before tuning; do not call Windows HDR native game HDR. |
| Overwatch 2 | Saved cap 297 and borderless mode; saved Reflex 0/off | Before next OW2 validation, review native Reflex against the intended On+Boost contract. This audit changed source expectations, not this file. Compare On vs Boost if power/headroom matters; dynamic lower FPS is not a wrong saved cap. |
| Rivals 2 | Saved fullscreen mode 0, VSync off, cap 999, HDR off | Reconcile the intended lane when selected. Compare current rendering limit, 300/no-sync, and 240/297 VRR candidates; 60 Hz simulation alone does not prove a 240 FPS render cap is best. |
| Slippi | Installed, explicit local P-core override preserved | Verify actual process CPU sets/affinity and emulator backend. Measure frame pacing at the game's fixed simulation rate; avoid raising caps as a substitute for consistent emulation. |
| Diablo IV | Saved foreground cap 297, background 60, Reflex true, HDR true; saved refresh 144 while Windows primary is 300 | Confirm actual borderless/exclusive presentation and whether that saved refresh field is used. Do not force a display change merely to reconcile a potentially inactive field. |
| Deadlock | Installed; source offers sync/HDR lanes but no native handler or capture sibling | Establish current renderer/Reflex/quality and capture needs; driver verification alone cannot certify native settings. |
| PACDeluxe | Installed native wrapper; WebView/browser image scope is broad | Identify the rendering subprocess and game-specific binding; avoid changing unrelated browser/desktop workloads. |

Marvel Rivals, Ryujinx, productivity and remaining families were also reviewed
in the complete source matrix; this scan did not establish they are all
installed or currently used.

## Performance acceptance and verification

The next tuning pass should start from a reconciled build and recoverable
baseline, then capture repeated identical scenes after shader warm-up.
Record game/build, settings, renderer, presentation, capture status, CPU/GPU
load, clocks, power, temperatures and driver. Compare FPS and frame-time
tails; measure end-to-end latency separately. Test native graphics/upscaling
and sustainable caps before low-evidence OS tweaks. Promote a local override
only when results repeat and the user accepts the image-quality/power tradeoff.

Useful primary references: NVIDIA describes
[Reflex and automatic below-refresh pacing](https://www.nvidia.com/en-gb/geforce/guides/system-latency-optimization-guide/);
Microsoft documents that
[MMCSS GPU Priority is unused](https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service),
[CPU Sets are selected processor sets](https://learn.microsoft.com/en-us/windows/win32/procthread/cpu-sets),
and [HAGS is not a guaranteed visible improvement](https://devblogs.microsoft.com/directx/hardware-accelerated-gpu-scheduling/).
[PresentMon's own console documentation](https://github.com/GameTechDev/PresentMon/blob/main/README-ConsoleApplication.md)
defines its metrics; frame presentation intervals must not be presented as
end-to-end input latency.

Initial audit validation, before integration: **2,580 Python tests passed, 13 deselected** (the repository's
configured exclusions); Ruff and diff-whitespace checks passed. The only
pytest warning was the existing unrecognized `asyncio_default_fixture_loop_scope`
configuration option. **Three GUI state tests, GUI lint, TypeScript/Vite build,
and `cargo check` passed.** Cargo's first offline attempt lacked a cached
dependency; the normal check fetched dependencies and completed. No frozen
runtime was built or deployed during that initial audit; the deployment
follow-up above records the integrated release.

Read-only detect, BIOS, installed state/health, native-config reads, CPU Sets
and manual backup capture completed. The full elevated machine audit was
unavailable, and no game benchmark or live mutation/restore loop was run.
Final installed state still names the same CS2 capture profile and apply
timestamp, with no pending reboot.

Validation results are recorded in the local test logs and final handoff.
Focused tests cover real failure/restore paths, Win32 ABI layouts, CPU sampling,
effective profile contracts, actual extracted PowerShell callbacks, bounded
filesystem traversal, and GUI verification state. No disruptive live test was
used to satisfy an offline regression check.
