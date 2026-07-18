# Current Agent Briefing

Last updated: 2026-07-17 America/New_York

> **MACHINE-SPECIFIC — read `docs/NEW_MACHINE_SETUP.md` first if this repo was
> just cloned onto a different PC.** Everything below describes the live state of
> one specific Windows 11 gaming PC: active profile, running PIDs, installed
> build hashes, deploy timestamps, and an in-progress Overwatch 2 monitor-flicker
> investigation. On a freshly cloned machine none of that is true yet — no build
> is deployed, no profile is applied, nothing is reboot-pending. Treat this file
> as a **record of the previous session's work**, not as this machine's truth,
> until you have re-verified with read-only commands (`detect` / `audit` /
> `health --json` / `state --json --verify`).

This is the first live-state file for agents arriving with no prior session
context. Historical handoffs and old plans belong in `docs/archive/`; this file
is the current operational truth for this PC.

## 2026-07-17 Counter-Strike 2 profile family added + deployed + tray restarted

User requested a new Counter-Strike 2 variant set added to the live tray with
verification. Shipped `abso/profiles/counter_strike_2.py` mirroring the
Deadlock family (Source 2, Reflex-capable, no native HDR, `system_only` — no
native config handler because CS2 rewrites its Source 2 video config under
Steam userdata):

- `counter-strike-2` (No Sync SDR), `counter-strike-2-hdr` (No Sync, Windows
  HDR composition), `counter-strike-2-gsync` (strict fullscreen-only G-SYNC
  SDR), `counter-strike-2-gsync-hdr` (strict G-SYNC + Windows HDR
  composition). HDR lanes use the Deadlock/Rivals-2 SDR-in-HDR composition
  wording (test-audited: `test_cs2_hdr_catalog_does_not_claim_native_hdr`).
- Wiring: catalog imports + `BUILTIN_TRAY_UI` (group `counter-strike-2`,
  ranks 500-530) + `PROFILE_CATALOG` (Shooters) + `PROFILE_ALIASES`
  short ids (`cs2`, `cs2-hdr`, `cs2-gsync`, `cs2-gsync-hdr`); profiles
  `__init__`; integration matrix scenarios (x4); Steam detection
  (`game_detector.py` + `manifests/game_detection.json`: `cs2.exe`);
  CS2 test blocks in `tests/test_profiles.py`; regenerated
  `tests/snapshot_golden.json` (42 profiles) and
  `abso/tray/profile-catalog-cache.json`. G-SYNC lanes: overlay-free display
  path, exact NVIDIA binding, mixed-refresh fallbacks to the no-sync
  siblings. NVIDIA identity `Counter-Strike 2` (alias: CS:GO-era profile,
  same Steam app 730).
- Offline gates: full `pytest -q` 2393 passed / 13 deselected (integration
  opt-outs), `ruff check .` clean. No tray `.ps1` was modified (menu is
  catalog-driven).
- Deploy: `.\.venv\Scripts\python.exe build.py deploy` at 2026-07-17 ~17:56.
  Backend `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe` now
  18,025,023 bytes; previous backend at
  `deploy-backups\abso.exe.bak-20260717-175632`; tray assets 1 updated
  (profile-catalog-cache.json, byte-identical to repo).
- Tray restarted via `ABSO-Tray-Startup` (old PID 31988 -> new PID 4212).
  NOTE: the pre-restart tray had been running the 2026-07-16 06:07 script
  while tray assets were re-deployed at 06:16 (runtime marker hash
  `e0f3c8d2...` vs installed `6a58d93d...`); this restart cleared that lag —
  marker now records `6a58d93d...`, matching repo and installed.
- Read-only verification only (no profile apply, no display/HDR mutation):
  installed `abso.exe profiles` lists all four CS2 lanes; tray log shows
  `Profile catalog loaded from cache (42 profiles, 17 aliases)` at 17:57:11
  and background refresh `verified cache current (42 profiles)`;
  `health --json` = 7 ok / 3 warning / 0 error with `tray_runtime_marker: ok`.
- Pre-existing warnings unrelated to CS2 (do not chase as regressions):
  `display_events`/`display_stability` are the standing mixed-refresh
  topology warnings; `profile_verify` mismatch on active `overwatch2-hdr`
  is the manual in-game OW2 Reflex step (current Enabled+Boost, lane now
  expects Off after the 0f7e367 inversion) plus an AudioEngineHandler drift
  with empty pending-apply.
- Not committed (user did not request a commit); working tree holds the CS2
  change set on branch `feat/fortnite-gsync-hdr-profile`.

## 2026-07-09 Startup Verification Flicker Trace + Deploy

User reported a black monitor blink after being told no profile apply or
display/HDR change had run. Trace result: no profile apply, display reset, HDR
toggle, or NVIDIA write was found for the reported window, but the tray was
automatically launching `abso.exe state --json --verify` shortly after every tray
startup. Tray log examples:

- 2026-07-08 16:19:11: `Starting read-only state verification:
  C:\Users\mtoli\AppData\Local\AdaptiveBattleStationOptimizer\abso.exe state
  --json --verify`
- 2026-07-08 16:19:15: `Active profile verifies clean on fresh session; surfacing
  verified status`

Follow-up trace after the user challenged "no display/HDR changes": Windows
Kernel-PnP did log real monitor link drops for `DISPLAY\GSM784C`
(`Generic Monitor (LG ULTRAGEAR)`) plus the associated NVIDIA audio endpoints.
The drops occurred at 2026-07-09 16:05:42/16:05:46, 16:15:42/16:15:46,
16:22:14/16:22:18, 16:29:11/16:29:15, and again at 16:46:18/16:46:22 during
the final verification window. The only ABSO profile backup in the same
14:00-16:40 window was the mouse-only backup at 16:30:53; deploy backups at
16:09, 16:16, and 16:23 replaced `abso.exe` and were after the nearest display
drop clusters. There was still no matching evidence of `nvlddmkm`, DWM crash,
HDR toggle, display reset, NVIDIA save, or profile apply. The correct conclusion
is narrower: no ABSO display/HDR/profile write was performed, but the display
link did blink. The repeated Kernel-PnP `surprise removed` records indicate a
real monitor-link/bus drop on `DISPLAY\GSM784C`, and the mixed-refresh VRR/HDR
topology remains an unresolved display-link stability risk independent of the
mouse/DPI fixes.

Fix deployed:

- `abso/tray/ABSO-Tray.ps1` no longer starts full profile verification
  automatically on tray startup. Startup only restores remembered state. Explicit
  same-profile clicks, profile apply success, and pending-fix flows still verify
  before deciding whether anything needs to be written.
- `MouseSettingsHandler` now verifies the X and Y smooth mouse curves against
  their axis-specific linear templates. The old generic check could falsely pass
  swapped/corrupt X/Y curves.
- `CpuAffinityHandler` now token-patches AppCompat affinity values safely. It
  preserves `HIGHDPIAWARE`, `DISABLEDXMAXIMIZEDWINDOWEDMODE`, `RUNASINVOKER`,
  and other Layers tokens, aborts on non-missing registry read errors instead of
  rewriting a truncated value, and deletes marker-only affinity values cleanly on
  restore. This was the direct remaining DPI-risk path after the FSO handler had
  already been fixed.
- Build dependency fixed: `pyinstaller>=6.0.0` added to `requirements.txt` and
  the dev extra, then installed into `.venv` with `ensurepip` + `pip install -r
  requirements.txt`.
- Tests before final deploy: full `pytest -q` = 2366 passed / 3 skipped; `ruff check .`
  passed.
- Gaming mouse profiles now explicitly set `MouseSensitivity=10` (Windows 6/11)
  in addition to acceleration off and axis-correct linear curves. Live readback
  showed this PC was at `MouseSensitivity=11`, which is a pointer-speed scalar
  left outside the old "linear 1:1" target.
- `MouseSettingsHandler` now broadcasts pointer-speed changes with
  `SystemParametersInfoW(SPI_SETMOUSESPEED)` so a profile apply/restore updates
  the active Windows pointer-speed state immediately, not just the registry.
- Repo-only test harness fix: pytest default selection now excludes `integration` tests with
  `-m 'not integration'`. `tests/test_integration` documents that live Windows
  registry/WMI/system-state tests require explicit opt-in, but the previous
  `addopts` did not enforce that policy during a plain full-suite run.
- Final deploy: `.\.venv\Scripts\python.exe build.py deploy` succeeded at
  2026-07-09 16:30 America/New_York. Installed backend:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe`, 18,014,058 bytes,
  SHA256 `4D554FBE0209B0687778AE3E22929D84A1780F9C0004F300D4B6E3A5E7F85A0D`.
  Previous backend backup:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\deploy-backups\abso.exe.bak-20260709-163025`.
  The earlier 16:09 deploy updated 2 tray files; later deploys updated the
  backend only.

Live tray state: the stale elevated tray process PID 30916 was stopped and
restarted through the registered `ABSO-Tray-Startup` scheduled task during the
16:30 fix. A later tray UI refactor was deployed at 2026-07-09 18:41
America/New_York with `.\.venv\Scripts\python.exe build.py deploy`; the current
runtime marker PID is 38588 with script hash
`8162f1b77801cfe0ac9950c6c198e0ae34a8b17271fe61098bc0d0234f4cb640`, matching
the installed tray script. The marker includes the new shared theme module
`ABSO-Theme.ps1` with hash
`ff88222b5b781bd2a9b51cae17a659f4edc12a492824111e91c109551f375110`. Tray log
at 2026-07-09 18:41:47 confirms `Startup profile verification deferred; active
profile restored from remembered state only`; no startup `state --json --verify`
launch followed. Do not run `state --json --verify` merely as a post-deploy
proof on this setup; use file/hash/log evidence unless the user explicitly asks
for live verification.

Tray UI refactor deployed at 18:41:

- Added `abso/tray/ABSO-Theme.ps1` as the shared menu/toast/quick-panel theme
  token source.
- Main tray menu now uses larger section/category headers, neutral owner-drawn
  profile/game-row text, shorter bounded hover/active lanes, and category role
  colors that decorate rails/icons/chips instead of replacing row text.
- `ABSO-Notifications.ps1` and `ABSO-QuickPanel.ps1` now consume the shared
  palette when loaded by the tray.
- Runtime health now hashes `ABSO-Theme.ps1`; `abso.exe health --json` after
  deploy reported `tray_runtime_marker: ok` and summary `10 ok / 0 warning / 0
  error`.
- Verification before deploy: PowerShell parser OK for theme/tray/notification/
  quick-panel scripts; `pytest tests/test_tray_script_static.py
  tests/test_core/test_health.py -q` = 170 passed; `ruff check .` passed.

Read-only live checks after deploy:

- Active state file reports `current_profile: overwatch2-gsync-hdr-capture`,
  applied 2026-07-09 17:03:11, no reboot pending.
- HKCU AppCompat OW2 entry currently reads `Overwatch.exe = ~
  PROCESSORAFFINITYMASK=FFFFFFFF`.
- HKCU AppCompat Rivals 2 shipping path currently includes `~
  PERPROCESSSYSTEMDPIFORCEOFF`; future CPU-affinity writes now preserve that DPI
  token instead of risking truncation on read failure.
- Mouse-only live correction was applied through `MouseSettingsHandler` after a
  mouse-only backup at
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\backups\2026-07-09_163053`.
  Before correction, registry `MouseSensitivity=11` and active
  `SPI_GETMOUSESPEED=11`. After correction, registry `MouseSensitivity=10`,
  active `SPI_GETMOUSESPEED=10`, acceleration remains disabled, and
  SmoothMouseXCurve/SmoothMouseYCurve match ABSO's axis-specific linear
  templates.

## 2026-06-19 (session 2) Implemented all A/B/C/D improvements + live-verified (not committed/deployed)

Follow-on to the audit below: the user asked to "act out every single improvement
listed for A, B, C, D and use this PC to verify everything works." Done. Every
handler was unit-tested AND live read-only `detect()`-verified on this PC.
**No commit / no deploy; installed runtime unchanged.** Offline: full pytest suite
**2290 passed / 0 failed**, `ruff check .` clean. Live verification was read-only
`detect()` per handler (this shell is non-admin, so the elevated apply+restore of
a wired ReflexShooter profile is the remaining user-run step).

### A - Benchmark capture/store/compare flow (rubric "measured" path)
- New `abso/core/benchmark_store.py` (artifact persistence + before/after compare +
  verdict) and a profile-aware `abso benchmark-capture <profile>` CLI command that
  stores durable JSON artifacts under `reports/benchmarks/<profile>/`. The existing
  `benchmark`/`benchmark-compare` commands were ephemeral; this is the persisting,
  profile-aware flow the rubric needs.
- Hardened `benchmark.py` CSV parsing for PresentMon 2.x (`MsBetweenPresents`) vs
  1.x (`msBetweenPresents`) casing.
- Verified on this PC: store hermetic tests write real JSON; `--list` + graceful
  "PresentMon not installed" path confirmed live (process resolved from the
  profile's executable hints). The live game-capture step needs PresentMon
  installed + a running game (inherently unverifiable now).

### B - Profile fact fixes (verified against game facts, not assumed)
- Deadlock `graphics_api`: KEPT `dx11` (web-confirmed Deadlock exposes both DX11 and
  Vulkan; DX11 is the stability-preferred path) - the audit's "switch to vulkan" was
  wrong; comment corrected.
- Diablo 4: pinned `processor_max_performance`/`processor_min_state=100`/
  `disable_core_parking` to match every other gaming base (fallback robustness).
- Pokemon Auto Chess + PACDeluxe: replaced the contradictory adaptive-VSync+VRR with
  the canonical G-SYNC + VSync-On pairing; aligned both catalog subtitles + sync_mode.
- Fortnite `PreferredFullscreenMode`: VERIFIED correct (live config showed `1` /
  Windowed-Fullscreen; a competitive community config uses `0` = Fullscreen, the stock
  UE enum). ABSO writing `0` is right; documented the enum so it isn't re-flagged.
- (Rivals 2 `frame_rate_limit` 999->0 was already done in session 1.)

### C - Safety/behavior
- ProcessJanitor + OverlayManager: dropped `taskkill /T` (tree-kill could reach a
  NEVER_KILL child); `/IM` already stops the named image.
- VPN route-holding daemons (`tailscaled`, `wireguard`, `openvpn`, `nordvpn-service`,
  `ProtonVPNService`, `mullvad-daemon`, `ZeroTier One`) moved from always-safe to the
  OPT_IN killset tier (kill-switch blackhole safety); VPN UIs/CLIs stay always-safe.
- cpu_balancer: added game-process-subtree exclusion (parent-PID chain) so anti-cheat
  child processes are never demoted; enumeration now captures parent PID.
- C10 (admin-gate hoist): VERIFIED the pending fast path already fails closed before
  any write (`apply_pending` admin-gates internally) and a test asserts the fast path
  doesn't call `is_admin` - the audit's premise was wrong, so NO change (reverted).

### D - Seven new latency-stack handlers (all registered audit+backup, unit-tested, live detect-verified)
- `GameDvrHandler` - hard-off `GameDVR_Enabled` + `AllowGameDVR` policy (the master
  keys the existing `AppCaptureEnabled` write missed). Live: already 0/0 here.
- `InterruptModeHandler` - GPU MSI mode (`MSISupported=1`, reboot-gated), GPU PCI
  instance resolved via WMI. Live: RTX 4070 already MSI=1.
- `AudioEngineHandler` - disable the audio enhancement (APO) chain on the active
  render device. Live: active device detected.
- `NicDriverHandler` - InterruptModeration off / RSS on / FlowControl off / EEE off on
  the active NIC. Live: read "Ethernet 2" (InterruptModeration currently 1).
- `DefenderExclusionsHandler` - add game-folder exclusions, gated on Defender being
  the active AV; restore reverts to the backed-up exclusion snapshot. Live: Defender
  active, 2 existing exclusions.
- `PagefileHandler` - fixed pagefile (1.5x/2x RAM, 32 GB cap), ACKNOWLEDGEMENT-GATED
  (won't mutate without `acknowledge_pagefile_change=True`), `restore_guarantee=partial`.
  Live: auto-managed, 32 GB. Correctly NOT auto-wired into any profile.
- `HypervisorAuditHandler` - AUDIT-ONLY: flags an idle Hyper-V root partition only when
  VBS is not running; ABSO never edits BCD. Live: hypervisor Auto + VBS running -> finding
  correctly silent.
- WIRING: the four apply-capable handlers (GameDvr/MSI/AudioEngine/NIC) are wired into
  `ReflexShooterBaseProfile` -> they now apply on the flagship strict online lanes
  (Overwatch 2, Marvel Rivals, Deadlock, Fortnite). Verified OW2 get_handlers/get_settings.
  This closes most of the AGENT_PROTOCOL §6.1 latency-stack backlog (MSI mode, Game DVR
  hard-off, audio APO, NIC tuning; pagefile + hypervisor delivered as opt-in/audit-only).
- HARDENING (edge cases found pre-commit): the four wired handlers are best-effort on
  apply AND on restore (a failed tweak/revert is a warning, never rolls back or blocks a
  profile switch); `is_critical_verify=False` + `restore_guarantee='partial'` on them so a
  verify miss is a WARNING not CRITICAL. Pagefile + Defender are `backup=False` (audit-only,
  never auto-applied - matches `VBSOptInHandler`) so they add no per-switch backup/restore
  overhead. NIC `Set` uses `-NoRestart` so the per-switch revert never bounces the link.

## 2026-06-19 Recursive static audit + verified bug/accuracy fixes (offline only; not committed/deployed)

User ran an overnight `/goal` to recursively audit and bug-fix ABSO, verify
profile accuracy, and push toward "state of the art." Four parallel read-only
auditors swept core/apply, settings handlers, profiles, and CLI/launch/display.
Every finding was re-verified against the real code before acting (several
agent findings were rejected — see below). Tests were explicitly authorized for
this session because the user was away from the PC. **No commit and no deploy
were performed; the installed runtime is unchanged.** All work is in the working
tree, offline-validated: full pytest suite **2155 passed / 0 failed**
(Python 3.12.10), `ruff check .` clean.

### Fixes shipped (working tree, unit-tested)

Restore-symmetry / correctness (settings handlers):
- `audio.py` — `restore()` re-ran the high-priority apply path, rewriting four
  MMCSS Audio values (`Priority`→2, `Background Only`→False, SFIO) on *every*
  `restore`, even when no profile touched audio. Now captures a full Audio-task
  snapshot and faithfully reverts only managed values (or deletes ones absent at
  backup); apply's mislabeled `Priority` 2→8.
- `color.py` — backup captured only the active ICC entry while a `"native"`
  apply deletes the whole `ICMProfile` multi-string; multi-ICC users lost
  secondary associations on restore. Now backs up/restores the full list, and
  `restore_guarantee` is honestly `"partial"` (registry note added).
- `storage.py` — `disablelastaccess` was collapsed to a bool, so restore
  rewrote a default Win11 `2` (system-managed) to `0` on every rollback. Now
  captures/restores the exact 0-3 value.
- `tasks.py` — restore keyed off `Status: Ready` (runtime readiness) instead of
  the authoritative `Scheduled Task State` (Enabled/Disabled), so a
  disabled-but-ready task would be wrongly re-enabled. Verified the two fields
  are distinct on this box (`ABSO-Tray-Startup`: Status Ready / State Enabled).
- `power.py` — active-plan restore now falls back to matching a plan by name
  when the backed-up GUID was deleted (custom plans get fresh GUIDs).
- `monitor_adaptive_sync.py` — declared Win64-correct ctypes prototypes
  (`MonitorFromPoint` HMONITOR restype + dxva2 argtypes) to stop HANDLE
  truncation; `_get_primary_physical_monitor` documented as caller-owns-handle.
- `amd.py` — `_write_reg_dword` uses `CreateKeyEx` (HKCU Radeon `CN`/`DVR`
  often absent). Note: `AmdSettingsHandler` is unregistered/dormant (NVIDIA rig).

Core / CLI / display / process:
- `apply` success JSON now includes `reboot_pending`/`reboot_reasons` (matched
  the no-op and pending payloads; GUI/tray schema consistency).
- `state_store.read_state_file` reads `utf-8-sig` (BOM-tolerant).
- New `abso/utils/proc.py::no_window_creationflags()` + wired into the apply-path
  `tasklist`/`taskkill` calls (process_janitor, overlay_manager, multimon,
  benchmark check) to stop console-window flashes when running windowless.
- `process_janitor.sweep` no longer mislabels an unverifiable kill as "stopped"
  (tri-state `_query_process_running`; unproven → failed, per the rubric).
- `apply_hooks.live_monitor_count` fails closed when monitor detection used its
  single-monitor fallback (`DisplayEnvironment.detection_confident=False`), so
  opt-in auto display recovery can't fire on a real multi-monitor rig.
- `crash_detector` records the concrete pre-apply backup id and rolls back to it
  instead of `"latest"` (dormant feature; future-proofed).
- `display-diagnostics --json` guards `payloads[0]`; `bios` GPU-probe bare-except
  now logs.

Profile accuracy:
- Fortnite SDR: removed inert `hdr_nits: 1000` (HDR output off → value ignored;
  matches the prior Marvel SDR cleanup).
- Rivals 2 (all four no-sync lanes): `frame_rate_limit` 999 → 0 (UE true
  uncapped; the comment/catalog already said "uncapped"). *Confirm if you want a
  hard thermal cap instead.*
- UE base (`ue_game_user_settings`): `auto_vrr_fps_cap` now surfaces a notice
  when refresh detection fails (mirrors Diablo 4) so Marvel Rivals et al. no
  longer silently skip the in-game cap.
- Regenerated `tests/snapshot_golden.json` for the five intended profile diffs.

### Findings re-verified as NOT bugs (do not re-flag)
- `backup.py` `_NON_BLOCKING_GUARANTEES` excluding `"partial"`: correct.
  `DisplayColorRangeHandler.restore` already skips offline monitors without
  failing, and fail-closed-on-partial matches the QUALITY_RUBRIC.
- `display_reset.py` missing ctypes argtypes: not a defect at those call sites
  (only NULL pointers, a ctypes Array, and small int flags — no pointer-as-int
  truncation, no handles).
- Slippi console-parity `vsync_tear_control: "disable"` with `vsync: "on"`:
  intentional (forces hard double-buffered VSync, no adaptive tear fallback).
- `rollback_guard` `passed=True` in override mode: cosmetic and test-locked;
  left as-is.

### Open decisions for the user (require approval / a game fact)
See the session's question list. Highest-value: **no profile has a benchmark
artifact in `reports/benchmarks/`** despite the full PresentMon harness in
`abso/core/benchmark.py` — capturing before/after frame-time + latency on this
rig is the single biggest step toward rubric "measured"/"optimal" grading.
Other open items: Fortnite `PreferredFullscreenMode` enum (confirm before
changing), Deadlock `graphics_api` dx11-vs-vulkan, Diablo 4 CPU-floor omission,
Pokemon/PACDeluxe windowed sync model, OW2 no-sync-HDR FSO posture, ProcessJanitor
`/T` tree-kill + VPN-daemon killset tier, cpu_balancer anti-cheat child exclusion,
and the §6.1 latency-stack handlers (MSI mode, Game DVR hard-off, Defender game
exclusions, etc.).

## 2026-06-17 Win11 Insider 29610 upgrade — full re-verification (PASS) + MMCSS drift repaired

The user updated this PC to **Windows Insider build 29610.1000** (Experimental
Future Platforms / Canary, June 12 flight) and asked for full re-verification of
every facet of ABSO against the new build. Result: **ABSO is healthy on 29610;
no code break.** One OS-update-induced registry drift was found and repaired.

- **No build-gate flips.** 29610 sits in the same band as the previously
  validated 29595: `is_windows_11`, `is_25h2_or_newer`, and
  `is_experimental_future_platform` are all True (unchanged); Xbox Mode / AI
  Agents / Shared Audio min-build floors still pass; no profile declares
  `min_os_build`/`validated_os_build`; there are no `at_most`/exact-build gates
  anywhere. Logical branch behavior on 29610 is identical to 29595.
- **Offline:** `ruff check .` clean; full suite **2128 passed / 0 failed**
  (Python 3.12.10).
- **Read-only live (all clean on 29610):** `detect` (full hardware map),
  `os_release` (reads 29610.1000 despite the "Windows 10 Home / Dev" registry
  quirk), `profiles`, `audit` (experimental banner fires; Xbox/AI/Shared-Audio
  detect-only handlers correctly report "rollout not yet active"), `bios`
  (ReBAR on, VBS on, Secure Boot on, TPM 2.0), `backup-create`.
- **The one real change the update caused:** the 29610 feature update
  re-provisioned the MMCSS `Games` task key
  (`HKLM\...\Multimedia\SystemProfile\Tasks\Games`) back to Windows defaults:
  `game_priority.priority` 6 -> 2 and `game_priority.scheduling_category`
  High -> Medium (GPU Priority 8 and Win32PrioritySeparation 42 survived).
  ABSO detected it correctly as a `RegistrySettingsHandler` mismatch with
  **empty** `pending_apply_settings` (the narrow `apply-pending` path does not
  cover MMCSS priority, so the repair requires a full apply).
- **Repaired (user chose "fix and keep"):** baseline backup
  `2026-06-17_200631`, then `apply overwatch2-gsync-hdr-capture` (the
  already-current idempotent path wrote the registry fix and skipped the
  redundant display/color reset, so no flicker risk was taken). Post-apply:
  `state --json --verify` reports `status: active`, `all_active: True`,
  `reboot_pending: False`, zero mismatched/pending/reboot-gated settings. All
  21 OW2 INI keys incl. `frame_rate_cap=276` verify active.
- **KB list reviewed for June (`abso/core/kb_checker.py`):** bumped
  `LAST_REVIEWED_UTC` to 2026-06-17 covering the June 2026 Patch Tuesday GA
  cumulatives (KB5094126 -> 26100.8655 / 26200.8655; KB5093998 -> 22631.7219;
  MS reports no known issues) and the 29610 bug-fix flight. No gaming-impacting
  regression on either track, so no new `KNOWN_BAD_KBS` entries.
- **Open/minor:** `health` still reports the expected mixed-refresh
  `display_stability` high-risk warning and `display_events` noise that is
  actually the post-update **reboot** (Kernel-Power shutdown/boot + ACPI thermal
  enum at 19:09-19:10, not flicker). `tray_runtime_marker` warns because the
  post-reboot tray (PID 19252) has not written a runtime marker; restart the
  tray into the installed `ABSO-Tray.ps1` to clear it (no apply/display action
  needed). The active profile itself is fully clean.
- Uncommitted working-tree changes from this session: `abso/core/kb_checker.py`
  and this briefing (29610 verification), plus a follow-on profile
  optimality/consistency audit (all 35 user-facing profiles) that fixed:
  Fortnite no-sync lanes now use `reflex_no_sync` (force VRR off at the driver
  instead of deferring to the global NVCP toggle); Rivals 2 G-SYNC lanes assert
  `vrr_app_override: allow`; the two online Rivals 2 lanes share the ONLINE
  `Win32PrioritySeparation`; Diablo 4 now manages `Win32PrioritySeparation`;
  the WebGL lanes (pokemon/pacdeluxe) wire windowed VRR + use the `balanced`
  preset; Reflex in-game guidance says "manually" (OW2/Deadlock/Fortnite);
  stale preset notes + Marvel SDR inert `hdr_nits` cleaned up. Files touched:
  `abso/profiles/{fortnite,pokemon_auto_chess,pacdeluxe,rivals2_gsync,diablo4,
  marvel_rivals,overwatch2,deadlock,profile_bases}.py`,
  `abso/settings/nvidia/presets.py`, `tests/test_profiles.py`,
  `tests/test_profile_coverage_invariants.py`, regenerated
  `tests/snapshot_golden.json`. Full suite 2133 passed, ruff clean. No
  catastrophic bugs were found in the audit; these were consistency/correctness
  gaps. Not committed (user did not request a commit).

## Current User Objective

- Optimize the current tray app for responsiveness and stale information
  resistance. The user clarified on 2026-06-03 that the tray app is the
  priority surface; do not continue desktop-GUI changes unless explicitly
  requested. Prioritize false restart notices, repeated status fragments,
  tray active-profile drift, blocking tray actions, and unnecessary shell-out
  churn. Deploy verified tray fixes immediately to this local runtime.
- Stop occasional secondary-monitor black flashes while keeping Overwatch 2
  usable. The user found that `overwatch2-gsync-hdr-capture` performed better
  than the overlay-free `overwatch2-gsync-hdr` lane; root cause was the
  profiles using different display paths, not overlays improving performance.
- Continue end-to-end repo cleanup: remove bloat, centralize duplicated policy,
  harden profile/apply behavior, keep docs accurate, and deploy verified builds
  to this local machine.

## 2026-06-09 Tray Stale-Data Audit (PS 5.1 ExitCode defect + catalog log honesty)

User-reported "discrepancies and stale data even after tray restart". Audited
every tray data source against backend truth. Findings and fixes (deployed,
tray restarted as PID 27916, `tests/test_tray_script_static.py` 137 passed):

- FIXED — PS 5.1 `Start-Process -PassThru` reads `.ExitCode` as `$null` unless
  the process handle is cached before the child exits. This made
  `Get-StartupStatus` fall back with a WARN on every tray start (the installer
  actually succeeded with valid JSON and exit 0) and would have made
  `Toggle-Startup` throw on success (`$null -ne 0` is true). All 11 backend
  shell-out sites that consume ExitCode now cache the handle immediately
  (`$null = $proc.Handle`); `Invoke-StartupInstallerJson` also got a
  finalizing parameterless `WaitForExit()`, `$args` → `$psArgs` (automatic-
  variable shadowing), and null-exit-tolerant success checks. Static coverage:
  `test_start_process_exitcode_consumers_cache_process_handle`.
- FIXED — the background catalog refresh logged "wrote cache" even when
  `Write-ProfileCatalogCache` skipped an identical write moments after the
  "cache unchanged; skipping write" line. The function now returns
  $true/$false and the refresh logs "verified cache current" vs "wrote cache".
  Static coverage: `test_background_catalog_refresh_logs_honest_write_state`.
- VERIFIED CORRECT (not stale): the installed profile-catalog-cache.json is
  byte-identical to the repo copy and content-matches the live backend
  catalog (35 profiles); tray profile names are internally consistent via the
  `Format-TrayDisplayCopy` G-SYNC normalizer (existing static test); the
  persistent "Windows restart required: Graphics settings (MPO)" banner is
  TRUTHFUL until the pending Windows reboot commits the MPO-enable target —
  it is not stale data and clears after reboot; lastProfileState/recents are
  refreshed by the startup resolver (picked up the 23:29 CLI apply correctly).
- Optional follow-up (not done): backend display names say "GSYNC" while the
  tray normalizes to "G-SYNC" — renaming the backend (overwatch2/rivals2/
  deadlock display_names + snapshot_golden.json + test assertions) would give
  tray/GUI/CLI parity. Cosmetic only; the tray is already self-consistent.
- 2026-06-10 post-reboot addendum: the user briefly saw the pre-reboot
  "Windows restart required" notice right after logging in — `reboot_pending`
  in the state file is only cleared when the first backend command after boot
  runs the state reconcile (the tray's startup verification, ~15 s in). FIXED
  surface: the first clean verification of a fresh session now writes
  "Verified active: <profile>" to the durable status line instead of leaving
  it empty (`test_clean_verification_surfaces_verified_status_on_fresh_session`,
  138 tray static tests green; deployed, tray PID 13876).

## 2026-06-10 OW2 fix outcome: USER-CONFIRMED — 276 fps restored

After the Windows reboot committed the MPO-enable target, the user confirmed
Overwatch 2 is back at 276 fps (the validated Reflex On+Boost ceiling).
Post-reboot `state --json --verify`: `all_active: true`, zero pending and zero
reboot-gated settings; both MPO-disable registry values remain absent. The
2026-06-09 root-cause chain (stale abso.yaml override → boot-committed MPO
disable → dead borderless windowed G-SYNC → forced V-SYNC half-refresh lock)
is validated end-to-end.

## 2026-06-09 OW2 150-fps Lock SOLVED (stale abso.yaml MPO override) — supersedes conflicting live-state claims below

Full record: `docs/CODEX_HANDOFF_OW2_150FPS.md` §11 and memory
`project_mpo_override_150fps`. Short version:

- Root cause: `abso.yaml` `profile_overrides` (written 2026-05-30, minutes
  before commit 51552de flipped the profiles to the borderless path) forced
  `graphics.disable_mpo: true` on both OW2 G-SYNC HDR lanes, silently beating
  the profiles' `disable_mpo: False` on every apply (PHASE 6 override merge).
  Verify compared against the overridden target, so everything reported clean.
  The first reboot that committed the boot-gated MPO disable killed the
  borderless independent-flip path → windowed G-SYNC could not engage → the
  forced driver V-SYNC backstop + 297 in-game cap produced an exact
  half-refresh 150 fps lock on the 300 Hz panel. The Process Lasso runtime was
  a timing coincidence and is exonerated.
- Fixes shipped this session: overrides removed from `abso.yaml` (repo +
  installed via deploy); applier now warns on any config-override-vs-profile
  contradiction (`_collect_override_conflicts` + tests in
  `tests/test_core/test_applier_override_conflicts.py`); EDID FreeSync range
  parser fixed (the "1-48Hz" reading was a +5/+6 vs +6/+7 byte bug — the LG's
  real range is 48-240 FreeSync / 48-300 panel); full suite 2117 passed;
  deployed via `build.py deploy` (backend 17,997,481 bytes, 2026-06-09 ~23:28);
  `overwatch2-gsync-hdr` reapplied (MPO-disable registry values deleted,
  reboot pending to commit MPO-on).
- Live state after this session: active profile `overwatch2-gsync-hdr`
  (NOT the capture lane mentioned in older sections below), reboot pending to
  commit the MPO-enable compositor path. After reboot + OW2 relaunch, expected
  fps is ~276 (Reflex On+Boost ceiling), not 150.
- Corrected false leads: "duplicate cpu-balance daemons" are PyInstaller
  one-file bootloader parent + child pairs (identical command lines) — not a
  bug; paired backups per apply are the designed `pre_switch`/`pre_apply`
  stages. The repo `.venv` was missing and has been recreated (Python 3.12.10).

## 2026-06-08 Process Lasso-Class Feature Port (CPU/process/power session tuning)

A complete in-house equivalent of Process Lasso's useful features was built and
**live-verified on this i9-14900F**. Full reference (features, every
config/tray-config flag, online-safety, enablement):
**[`PROCESS_LASSO_FEATURES.md`](./PROCESS_LASSO_FEATURES.md)**.

State: **all code done + tested (hermetic + live); nothing is enabled.** Every
runtime feature is gated OFF in tray-config (`cpuBalancer` / `cpuSets` /
`ecoMode` / `watchdog` default false); Keep-Awake is allowed but only emulator
profiles assert it. The user deferred the live flag-flip to themselves.

- The ProBalance governor (`abso/core/cpu_balancer.py`) hosts the runtime
  features (CPU Sets steer, EcoQoS herd, watchdog) and is spawned by the tray on
  game launch, stopped via a stop-file sentinel so its cleanup restores
  everything. Hardened exclusions (NEVER_KILL + `process_overrides.protect`):
  never demotes anti-cheat / game / protected images.
- "Highest Performance" power: `power.py` core-parking knob (CPMINCORES, read via
  `/qh` — `/query` is blind to hidden settings) + min-state 100 on the
  Reflex/Emulator/Rivals2 bases; the productivity profile relaxes the floor to 5.
- New modules: `cpu_sets`, `efficiency_mode`, `cpu_limiter`, `watchdog`,
  `watchdog_engine`, `proc_actions`. All Win32 calls are dependency-injected for
  hermetic tests and prototype-hardened for Win64 (HANDLE truncation).
- To enable for this PC: set `cpuBalancer: true` (+ optional `cpuSets` / `ecoMode`
  / `watchdog`) in `%APPDATA%\ABSO\tray-config.json`, restart the tray, play, and
  watch the 1%-low / frame-time graph.

## 2026-06-05 Source-Only Tray UI/UX Handoff

The user asked to bookmark progress and stop. Do not continue feature work from
this session unless the user resumes it.

Hard boundary for the next agent:

- The user clarified the scope: change the tray app, not the main/desktop app.
  Keep edits in `abso/tray/*.ps1`, tray assets/cache only when necessary, and
  `tests/test_tray_script_static.py` unless the user explicitly expands scope.
- The user objected after a previous live/runtime command. Do not deploy,
  restart/launch the tray, run the installed ABSO binary, run live
  `state`/`verify`/`health`/`display-diagnostics`, apply/reapply profiles,
  reset displays, toggle HDR/G-SYNC, open runtime folders, or otherwise mutate
  or inspect live PC state unless the user explicitly authorizes that exact
  command.
- Overwatch was reported running during this work. Do not treat profile drift
  or live verification noise as apply failure while the game is live. Prefer
  build/static validation.
- Allowed verification for this paused work: PowerShell parser over
  `abso/tray/*.ps1`, focused/static pytest, `ruff check .`, and
  `git diff --check`.

Current dirty tray-only work:

- `abso/tray/ABSO-Notifications.ps1`: upgraded profile/action-themed toast and
  progress visuals, action medallions, and popup-setting behavior.
- `abso/tray/ABSO-Icons.ps1`: expanded stylized game identity marks and
  fallback marks, including additional common game aliases.
- `abso/tray/ABSO-QuickPanel.ps1`: richer active/fix/restart/check card states,
  right-side state rails, restored Quick Panel visibility state, and a truthful
  animated header chip.
- `abso/tray/ABSO-Settings.ps1`: settings header and section visuals, tray
  surface controls, startup-reminder preview, hotkey/status copy cleanup, and a
  `N/3 ON` header chip for toast popups, Quick Panel restore, and audio cues.
- `abso/tray/ABSO-Tray.ps1`: many stale-copy/status fixes, menu command pills,
  section/header chips, backup count chips, profile/game/group visuals,
  startup stale-action copy, restart-marker hardening, and folder/status action
  cleanup.
- `tests/test_tray_script_static.py`: static coverage for the tray-only UI and
  stale-information fixes.

Latest source-only validation before stopping:

- PowerShell parser over `abso/tray/*.ps1`: passed.
- Focused backup/folder/status static slice:
  `30 passed, 103 deselected`.
- Full tray static suite:
  `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`
  reported `133 passed`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for the last touched tray/test files passed with only
  LF-to-CRLF warnings.
- No deploy, tray restart, installed runtime command, live diagnostics, profile
  apply/verify, or display mutation was run after the user's correction.

Recommended next pickup:

- Start with the paused inspection around the Backups empty-state row in
  `ABSO-Tray.ps1`. The parent Backups command now has a truthful dynamic chip,
  and the empty toast now says only that the current backups folder is missing,
  but the disabled submenu row is still a plain row. A good next tray-only
  improvement is to give that row a dedicated visual state, e.g. an
  `__empty_state_row__` or similar renderer path with an `EMPTY`/`NO BACKUPS`
  chip, subtle animated accent, precise tooltip, and static coverage in
  `test_tray_backups_submenu_has_empty_state_row`.
- After that, run only source/static checks unless the user explicitly approves
  live/deploy verification:
  PowerShell parser over `abso/tray/*.ps1`, focused static tests for the touched
  area, full `tests/test_tray_script_static.py`, `ruff check .`, and
  `git diff --check`.
- Do not mark the active goal complete until the original objective has been
  deployed and visually/runtime verified with explicit user permission.

## Live Machine State

- Active profile: `overwatch2-gsync-hdr-capture`.
- Latest active display topology from installed
  `display-diagnostics --json` at
  `2026-06-04 01:54 America/New_York`: two monitors, mixed refresh.
  Primary is `Generic PnP Monitor`, 2560x1440 at 300 Hz, VRR-capable
  (`gsync_compatible`). Secondary is `Dell S2719DGF(Displayport)`,
  2560x1440 at 59.95 Hz with detected 144 Hz capability. No display events or
  overlays were detected, but `risk_level: high` and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.
  The earlier one-monitor 21:34 snapshot is no longer current.
- Installed backend:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe`
  length `17899514`, last write `2026-06-03 23:15:11`, SHA256
  `E457758A7739ADB6E2B8E0EB57C836076233BCE85136C787EA4A6AFB56A02294`.
- Installed GUI:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso-gui.exe`
  length `5062144`, last write `2026-06-03 22:46:50`, SHA256
  `2EC9785600189812EB4F3B2C288C20F36191D3AF8579A3442FCC116D8791414F`.
- Tray runtime: scheduled-task startup is installed and enabled. Live tray PID
  `57948` is running installed script
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso\tray\ABSO-Tray.ps1`
  with SHA256
  `4798A3F2D0B7F1600B6DCF5637005099F90D71ADDEF4F03FDC9D940EC9494FBB`.
  The live `tray-runtime.json` marker confirms that PID/hash and includes five
  loaded tray module hashes.
- Installed tray settings script
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso\tray\ABSO-Settings.ps1`
  matches source with SHA256
  `E3FB034F09BEA77E9227413A69DF35353FFB7B213E5E5ABBFCEB4293E81DB9E0`.
- Installed tray icon script SHA256:
  `CCCBA47EB98096D07F2D446253065A4B86524967B147831EADAD931924443520`.
- Installed tray notifications script SHA256:
  `C310372DA9B1CAC71A087C0AA9E81CF6F386F560BEFFCA7074510B2D21843B1E`.
- Installed tray quick panel script SHA256:
  `9E1DBD4B38E80C5B7630F3E1EA7BD03D5AC2C1BD365581EEB90AE39A219BA024`.
- Installed tray cache matches source:
  `abso\tray\profile-catalog-cache.json` SHA256
  `0B5EF40DC2412869855085E0A45CB020D227DA0BF17A59DAE74B26ED07F9D304`.
- Current installed state reports `current_profile:
  overwatch2-gsync-hdr-capture` with `reboot_pending: true` for
  `GraphicsSettingsHandler.mpo_disabled`.
- Current source fixes the OW2 strict/capture inversion: both Overwatch 2
  G-SYNC HDR profiles intentionally target the optimized borderless/windowed
  VRR path. `overwatch2-gsync-hdr` is still overlay-free by process policy;
  `overwatch2-gsync-hdr-capture` keeps capture/overlay processes alive.
- The deployed FPS cap target for the active 300 Hz OW2 G-SYNC path is now the
  OW2 Reflex/G-SYNC policy value: target `276`. Read-only verification after
  deploy still reports the pre-change live values (`NvidiaSettingsHandler`
  `max_frame_rate` current `297`, `OW2ConfigHandler.frame_rate_cap` current
  `297`) because no profile apply was run while Overwatch/live display state
  may be active.
- Current health has two warnings: the expected reboot-gated
  `GraphicsSettingsHandler.mpo_disabled` profile state and the live
  mixed-refresh multi-monitor display topology. Neither is an OW2 FPS-cap
  problem.
- As of 2026-06-04 02:00, the user stated Overwatch is currently running. Do
  not interpret profile verification drift as an apply failure while the game
  is live. Prefer build/static validation and tray runtime-marker verification;
  keep live diagnostics minimal unless explicitly requested.

## 2026-06-04 Tray Verifier Stale-Action Pass

Continued the tray-only stale-information objective:

- The tray verifier now replaces stale `Needs apply:` or `Restart required:`
  last-action text when a later read-only verification says the active profile
  is clean.
- The replacement is narrow: it writes `Verified active: <profile>` only when
  the previous durable action was verifier-generated pending/restart text. It
  does not overwrite useful recent action text such as `Applied:`, `Fixed:`, or
  settings/folder actions.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `45 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1880 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1`,
  `tests\test_tray_script_static.py`, and this briefing passed with only
  expected CRLF normalization warnings before the briefing edit.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `9364` to `57948`.
- Live `tray-runtime.json` reports root script SHA256
  `4798A3F2D0B7F1600B6DCF5637005099F90D71ADDEF4F03FDC9D940EC9494FBB`.
- `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\tray-restart-pending.json`
  did not exist before the restart, and no manual restart token was involved.
- Per the user's note that Overwatch is currently running, this pass did not
  run the usual post-deploy `state --json --verify` or
  `display-diagnostics --json` checks. Do not use live game-state drift from
  this moment as failure evidence.

## 2026-06-04 Tray No-Op Status Pass

Continued the tray-only stale-information objective:

- Profile-not-found and apply-timeout paths now update the durable tray status
  before returning, so the status bar cannot continue showing an older profile
  action after a visible failure toast.
- `Apply Pending Fix` no-op paths now write durable status for `No active
  profile to repair` and `No pending profile fixes found`.
- `Run System Audit` now writes `Audit already running` when the user invokes
  it while an audit is already in flight.
- The default-profile startup reminder now writes `Startup reminder: <profile>`
  to the tray status line after its reminder toast, while still not applying
  anything automatically.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `44 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1879 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1`,
  `tests\test_tray_script_static.py`, and this briefing passed with only
  expected CRLF normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `44668` to `9364`.
- Live `tray-runtime.json` reports root script SHA256
  `356BF633FF6877276F585B75C1B6F0FAAEDF85665ABB1289B1CDDFCC24AF15DF`.
- `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\tray-restart-pending.json`
  does not exist after restart.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings and reboot-gated
  `GraphicsSettingsHandler.mpo_disabled`.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Status Surface Pass

Continued the tray-only stale-information objective:

- Audit completion now writes a specific durable status:
  `Audit clean: no issues in scope`, `Audit issues found: <count>`, or
  `Audit completed: no details`, instead of the generic `Audit completed`.
- Folder/log actions now update the status line on success and failure:
  backups, tray log, tray settings folder, installed runtime folder, and user
  profiles folder.
- Settings toggles and saves now update durable status for notifications,
  sound effects, and saved tray settings, so the status bar does not keep an
  older profile/apply message after a visible settings change.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `43 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1878 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1`,
  `tests\test_tray_script_static.py`, and this briefing passed with only
  expected CRLF normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `57616` to `44668`.
- Live `tray-runtime.json` reports root script SHA256
  `1786EBBDBCB57A4B696AA13A7E3E684E3ED952D76607A090868E26225079C934`.
- `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\tray-restart-pending.json`
  does not exist after restart.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings and reboot-gated
  `GraphicsSettingsHandler.mpo_disabled`.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Restart Marker Pass

Continued the tray-only stale-information objective:

- Manual `Restart Tray` now creates a one-time restart token and stores that
  token in `tray-restart-pending.json`.
- The restarted tray process must be launched with the matching token before it
  consumes the marker and plays the restart success sound.
- Unrelated tray starts, scheduled-task starts, abandoned restart attempts, and
  stale pre-token markers now ignore/remove the marker instead of producing a
  false restart-success cue.
- The manual restart path now launches the replacement tray directly through
  hidden PowerShell with `-RestartToken`; the scheduled startup task remains
  unchanged.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `42 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1877 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1`,
  `tests\test_tray_script_static.py`, and this briefing passed with only
  expected CRLF normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `5936` to `57616`.
- Live `tray-runtime.json` reports root script SHA256
  `0BB79FA56AB22342E57A2BE2EC893B22CE1D3BA182ACACBD83F9AF198F5CC6DE`.
- `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\tray-restart-pending.json`
  does not exist after the scheduled-task restart, proving no stale manual
  restart marker was left pending.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings and reboot-gated
  `GraphicsSettingsHandler.mpo_disabled`.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Action Status Pass

Continued the tray-only stale-information objective:

- Tray menu actions that already showed notifications now also update durable
  last-action status, so the tray status line does not keep showing stale
  previous actions after user-visible work completes.
- `Toggle-Startup` now records enabled, disabled, unchanged, missing-installer,
  and failed-install outcomes before refreshing menu state.
- `Reset Display Pipeline` now records success counts and CLI/JSON/exception
  failures instead of leaving the old status line in place.
- Quick panel open/close/empty outcomes, profile refresh success/failure, and
  standby-list clear start/success/failure now write durable action status.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `41 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1876 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `48272` to `5936`.
- Live `tray-runtime.json` reports root script SHA256
  `2397AD54BC9CD972653E725E7F5734E21C78624563DF46385FC1E1F9F5C149F8`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings and reboot-gated
  `GraphicsSettingsHandler.mpo_disabled`.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Log Action Pass

Continued the tray-only stale-information objective:

- The Settings flyout now labels the log action as `View Tray Log File` instead
  of the generic `View Log File`.
- `Open-LogFile` now creates the tray log on demand through `Write-TrayLog`
  before opening it, so the menu action cannot silently do nothing just because
  the log file did not exist yet.
- Notepad launch failure is now reported through the tray notification system
  and logged as an error instead of failing silently.
- Manual path check confirmed the current tray log exists at
  `%TEMP%\abso_tray.log`.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `40 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1875 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `6756` to `48272`.
- Live `tray-runtime.json` reports root script SHA256
  `1BD273E34CD3D0D42EA88AA1DB9B70A1B85834D71953FF59E9B71859D4B3A4E5`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Settings Folder Label Pass

Continued the tray-only stale-information objective:

- The Settings flyout no longer exposes the vague `Open Config Folder` action.
  That action opened `%APPDATA%\ABSO`, which is specifically the tray settings
  storage for `tray-config.json`, not the installed runtime config folder.
- The menu now labels that path as `Open Tray Settings Folder` and shows a
  tooltip pointing at `tray-config.json` storage.
- The Settings flyout now also includes `Open Installed Runtime Folder`, which
  opens `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer` where `abso.yaml`,
  installed binaries, backups, and deployed tray assets live.
- Manual path check on this PC confirmed `%APPDATA%\ABSO\tray-config.json` and
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.yaml` both exist.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `39 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1874 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `64024` to `6756`.
- Live `tray-runtime.json` reports root script SHA256
  `629EA1D86A898DF8B67AB3F7ECD6EF323A7DB01CDDC1E7DDEFB3FBD9A1E4FDFB`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Backup Root Pass

Continued the tray-only stale-information objective:

- The tray backup status/menu no longer reads the workspace `backups` mirror as
  the primary source. On this PC the workspace mirror's newest visible entries
  were from 2026-05-26, while installed runtime backups under
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\backups` have 2026-06-03
  entries.
- `Open Backups Folder`, `Backups (<age>)`, and the recent-backup submenu now
  use a shared root-aware resolver that prefers installed local backups, falls
  back to the workspace mirror if needed, and dedupes matching backup ids across
  roots.
- Manual PowerShell harness confirmed the tray resolver orders roots as
  `installed` then `workspace`, and its latest three backups are
  `2026-06-03_171528`, `2026-06-03_171515`, and `2026-06-01_215136` from the
  installed root.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `38 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1873 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `27968` to `64024`.
- Live `tray-runtime.json` reports root script SHA256
  `A5E6CBE30BC5C77F289F71581FBD9F7FFAC350598CF3A1C3C3A5380FC3D77A94`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. Health also
  confirms the current backup primary root is
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\backups` with latest backup
  `2026-06-03_171528`.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Restore Status Pass

Continued the tray-only stale-information objective:

- The tray status bar no longer displays a bare `HH:mm` fragment for the last
  action. It stores a real `DateTime` and renders a labeled compact timestamp
  such as `Action: Jun 4 00:58`.
- Main restore timeout, restore failure, and restore exception paths now update
  durable tray last-action state, so a failed restore toast cannot leave the
  status bar showing an older successful action.
- Backup submenu restore success and failure paths now update durable
  last-action state, clear active-profile verification state after a successful
  backup restore, and restore the normal tray tooltip after the transient
  `Restoring...` hover text.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `37 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1872 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `49556` to `27968`.
- Live `tray-runtime.json` reports root script SHA256
  `765B12C781B599232B9DB8DBE1138984B57C811CE9C386D3F1C7A461CA4D2078`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Multi-Display System Line Pass

Continued the tray-only stale-information objective after the user clarified
the tray app is the intended scope:

- The tray menu's always-visible system line no longer presents a single
  `Win32_VideoController.CurrentRefreshRate` value as if it describes the whole
  desktop.
- `ABSO-Tray.ps1` now reads current refresh per
  `[System.Windows.Forms.Screen]::AllScreens` display through
  `EnumDisplaySettings`, formats common Windows fractional/rounded reporting
  noise (`59`/`60`, `299`/`300`), and summarizes multi-display mixed refresh as
  a topology line such as `2 displays - 300Hz/60Hz mixed`.
- The line still avoids backend shell-out during menu open; if the per-display
  reader is unavailable it falls back to monitor count plus the adapter-reported
  refresh, explicitly labeled as adapter data.
- Manual API probe on this PC returned `\\.\DISPLAY1` primary at `300Hz` and
  `\\.\DISPLAY2` at `59Hz`, matching the installed diagnostics' 300 Hz primary
  plus 59.95 Hz secondary after tray formatting.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `36 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1871 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `64560` to `49556`.
- Live `tray-runtime.json` reports root script SHA256
  `23C0BB3626B655754EE5EECDA86D4648432958AA6CB9D5E581DE33D0D7AF2986`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Recent/Backup Label Pass

Continued the tray-only stale-information objective:

- Recent profile tooltips now use a shared tray timestamp formatter and show
  `Last applied: <compact time>` instead of leaking the raw persisted
  `timestamp` field.
- Backup menu labels now use profile display names from the loaded profile
  catalog instead of raw profile ids from `manifest.json`.
- Backup menu timestamps now use the same compact formatter while continuing to
  sort by manifest `created_at`, then timestamp-style directory name, then
  filesystem time only as fallback.
- Backup restore actions still pass the same backup id to the CLI; this pass
  changes only the tray label and tooltip text.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `35 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1870 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `32536` to `64560`.
- Live `tray-runtime.json` reports root script SHA256
  `9AA1A531A49C769E8EC1B698A2054C9F2715D52F08F9F8CDA5F687BCB4C4AB47`
  and installed `ABSO-QuickPanel.ps1` SHA256
  `9E1DBD4B38E80C5B7630F3E1EA7BD03D5AC2C1BD365581EEB90AE39A219BA024`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Tooltip State Pass

Continued the tray-only stale-information objective:

- Tray notifications now write only a short transient hover tooltip.
- A one-shot WinForms timer restores the persistent tray tooltip from current
  active-profile state after the transient notification window.
- Menu-state refresh now owns the durable tooltip text through
  `Restore-TrayTooltipFromState`, so stale action strings like startup toggles,
  audit results, profile-refresh results, or memory-clear notices do not remain
  as the long-lived tray hover state.
- Tooltip truncation now goes through one helper capped to the Windows
  `NotifyIcon.Text` limit.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `34 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1869 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-Tray.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `34516` to `32536`.
- Live `tray-runtime.json` reports root script SHA256
  `E0D8EF09D901DA30393F6A94A64B87F02D78D6B340C3EE77D100944D3B0C7869`
  and installed `ABSO-QuickPanel.ps1` SHA256
  `9E1DBD4B38E80C5B7630F3E1EA7BD03D5AC2C1BD365581EEB90AE39A219BA024`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root script hash live. The warnings
  are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Quick Panel Visibility Pass

Continued the tray-only stale-information objective:

- Quick Panel rebuilds now clear `QuickPanelVisible` when the old form is
  disposed and when there are no renderable cards, so the tray does not report
  a panel as open after it returned without showing a form.
- The tray Quick Panel toggle now saves `showQuickPanel` from actual runtime
  visibility after `Show-QuickPanel`, not from the user's click intent.
- If the toggle cannot show anything because there is no active profile and no
  favorites, the tray leaves the setting unchecked and shows an accurate
  one-line notice.
- Startup auto-open now allows the active-only panel path introduced in the
  prior pass; it no longer requires at least one favorite when an active
  profile exists.

Validation:

- PowerShell parser check for `ABSO-QuickPanel.ps1` and `ABSO-Tray.ps1`:
  passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `33 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1868 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-QuickPanel.ps1`, `ABSO-Tray.ps1`, and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.
- Rendered `%TEMP%\abso-quickpanel-active-only-preview.png` from the WinForms
  Quick Panel with active `overwatch2-gsync-hdr-capture` and no favorites. The
  panel rendered one active Overwatch card. A second no-active/no-favorites
  harness call returned `QuickPanelVisible: false` and no form.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated two tray assets.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `63348` to `34516`.
- Live `tray-runtime.json` reports root script SHA256
  `395CBE857BD9FD67FFBA484BAD9C0B78C8508D538A0B2F65CF6B98A76085B160`
  and installed `ABSO-QuickPanel.ps1` SHA256
  `9E1DBD4B38E80C5B7630F3E1EA7BD03D5AC2C1BD365581EEB90AE39A219BA024`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new root and Quick Panel hashes live.
  The warnings are still the expected reboot-gated graphics setting and the
  current mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-04 Tray Quick Panel Active Pin Pass

Continued the tray-only stale-information objective:

- Quick Panel now pins the currently active profile as the first card when it
  exists in the profile catalog, even if that profile is not favorited.
- The favorite cards then fill the remaining slots without duplicating the
  active profile, preserving the existing three-card panel size.
- When an active card is pinned, the header changes to
  `ACTIVE / QUICK LAUNCH` so the tray surface reflects current state instead
  of implying it is only a favorites list.
- Fixed Quick Panel paint handlers to capture palette colors before WinForms
  repaint callbacks. The prior paint-time script-scope lookups could throw
  during redraw and leave the panel partially painted.

Validation:

- PowerShell parser check for `ABSO-QuickPanel.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `31 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`:
  `1866 passed`, `3 skipped`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `git diff --check` for `ABSO-QuickPanel.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.
- Rendered `%TEMP%\abso-quickpanel-active-preview.png` from the WinForms Quick
  Panel with active `overwatch2-gsync-hdr-capture` not in favorites. The panel
  rendered cleanly with card order
  `overwatch2-gsync-hdr-capture,slippi-melee,rivals2`.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`; live tray PID
  changed from `24432` to `63348`.
- Live `tray-runtime.json` reports root script SHA256
  `95CF580735B57C7D6D42040E8603BE784F4B819CAA053714129148BF9D0F63ED`
  and installed `ABSO-QuickPanel.ps1` SHA256
  `13A2E646B1CC4DA0A734186325056E74CD2C97320F6F2CB73A89039C2029B6A0`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, with the new Quick Panel module hash live. The
  warnings are still the expected reboot-gated graphics setting and the current
  mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.
- Installed `display-diagnostics --json` remains read-only and reports zero
  display events, two monitors, `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## 2026-06-03 Tray Profile Progress Overlay Pass

Continued the tray-only UI/UX objective:

- Profile apply progress overlays now accept optional profile visual metadata,
  while generic progress overlays such as restore keep the old layout.
- Profile apply and pending-fix overlays now show the selected profile's game
  mark, category-colored rail/spinner/progress motion, and active badge where
  appropriate.
- The progress overlay disposes generated profile bitmaps on close so repeated
  applies do not leak GDI images.

Validation:

- PowerShell parser check for `ABSO-Notifications.ps1` and `ABSO-Tray.ps1`:
  passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `29 passed`.
- `.\.venv\Scripts\python.exe -m ruff check tests\test_tray_script_static.py`:
  passed.
- `git diff --check` for `ABSO-Notifications.ps1`, `ABSO-Tray.ps1`, and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.
- Rendered `%TEMP%\abso-profile-progress-preview.png` from the WinForms
  progress overlay and visually inspected it; the Overwatch mark, active badge,
  headline, step text, and progress line fit cleanly.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated two tray assets.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`.
- Live tray PID `24432` wrote `tray-runtime.json` with root script SHA256
  `95CF580735B57C7D6D42040E8603BE784F4B819CAA053714129148BF9D0F63ED`
  and installed `ABSO-Notifications.ps1` SHA256
  `C310372DA9B1CAC71A087C0AA9E81CF6F386F560BEFFCA7074510B2D21843B1E`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, `module_count: 5`. The warnings are still the
  expected reboot-gated graphics setting and the current mixed-refresh display
  topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.

## 2026-06-03 Tray Profile Toast Visual Pass

Continued the tray-only UI/UX objective:

- The themed toast engine now accepts optional profile visual metadata while
  preserving the generic toast API for audit/startup/system notifications.
- Profile apply, apply-warning/caution, failure, pending-fix success, and
  pending-fix failure toasts now pass the selected profile's game group,
  category color, footer metadata, and active badge state.
- Profile-aware toasts render a 36 px game mark beside the headline and dispose
  the generated bitmap on toast close, including queued-toast paths.

Validation:

- PowerShell parser check for `ABSO-Notifications.ps1` and `ABSO-Tray.ps1`:
  passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `28 passed`.
- `.\.venv\Scripts\python.exe -m ruff check tests\test_tray_script_static.py`:
  passed.
- `git diff --check` for `ABSO-Notifications.ps1`, `ABSO-Tray.ps1`, and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.
- Rendered `%TEMP%\abso-profile-toast-preview.png` from the WinForms toast
  surface and visually inspected it; the Overwatch mark and active badge were
  readable, and headline/body/footer text still fit.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated two tray assets.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`.
- Live tray PID `66420` wrote `tray-runtime.json` with root script SHA256
  `C83ED08E3D8DFC91A7CBD5104473EE100E8489A27A9B743CAC439045B2B8345B`
  and installed `ABSO-Notifications.ps1` SHA256
  `1437BF05467A866F1BCC01592F05BB649FED4795F3BE0B97F2F79E99B1CBC71A`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, `module_count: 5`. The warnings are still the
  expected reboot-gated graphics setting and the current mixed-refresh display
  topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.

## 2026-06-03 Tray Settings Preview Pass

Continued the tray-only UI/UX objective:

- The Settings dialog now shows a selected default-profile preview card under
  `Default Profile (startup reminder):`.
- The preview uses the same game-mark pipeline as the tray menu, displays the
  selected variant/category, and explicitly says
  `Startup reminder only. Nothing is applied automatically.`
- The `(None)` state also says `No profile is applied automatically.`
- The preview updates immediately when the combo selection changes and disposes
  its generated bitmap when the Settings form closes.

Validation:

- PowerShell parser check for `ABSO-Settings.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `27 passed`.
- `.\.venv\Scripts\python.exe -m ruff check tests\test_tray_script_static.py`:
  passed.
- `git diff --check` for `ABSO-Settings.ps1` and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.
- Rendered `%TEMP%\abso-settings-preview.png` from the WinForms Settings panel
  and visually inspected it; the preview row is readable and the bottom buttons
  fit inside the dialog.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated one tray asset.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`.
- Live tray PID `36048` wrote `tray-runtime.json` with root script SHA256
  `6387C85A1D9C51C768241BA4E74D28DFA3CE9141C67B5328210628E09E1CA6AF`
  and installed `ABSO-Settings.ps1` SHA256
  `E3FB034F09BEA77E9227413A69DF35353FFB7B213E5E5ABBFCEB4293E81DB9E0`.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`;
  `tray_runtime_marker: ok`, `module_count: 5`. The warnings are the expected
  reboot-gated graphics setting and the current mixed-refresh display topology.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.

## 2026-06-03 Tray Active-Badge / Refresh Pass

Continued the tray-only UI/UX objective:

- Active profile rows in the tray menu now keep their game-specific mark and
  receive a compact active badge overlay instead of replacing the game mark
  with a generic check icon.
- Tray profile refresh now uses shared menu image/text helpers, so submenu
  rows keep concise variant labels and inactive flyout rows keep sync badges
  after active-state refreshes.

Validation:

- PowerShell parser check for `ABSO-Tray.ps1` and `ABSO-Icons.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `26 passed`.
- `.\.venv\Scripts\python.exe -m ruff check tests\test_tray_script_static.py`:
  passed.
- `git diff --check` for `ABSO-Tray.ps1`, `ABSO-Icons.ps1`, and
  `tests\test_tray_script_static.py` passed with only expected CRLF
  normalization warnings.
- Generated `%TEMP%\abso-active-game-badges.png` and visually inspected the
  normal/active tray marks; the active badge stayed readable without burying
  game silhouettes.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` reported backend and
  desktop GUI already current and updated two tray assets.
- Tray was restarted through scheduled task `ABSO-Tray-Startup`.
- Live tray PID `49676` wrote `tray-runtime.json` with root script SHA256
  `6387C85A1D9C51C768241BA4E74D28DFA3CE9141C67B5328210628E09E1CA6AF`
  and installed `ABSO-Icons.ps1` SHA256
  `CCCBA47EB98096D07F2D446253065A4B86524967B147831EADAD931924443520`.
- Installed `health --json` reports `9 ok`, `1 warning`, `0 error`;
  `tray_runtime_marker: ok`, `module_count: 5`. The remaining warning is the
  expected reboot-gated `GraphicsSettingsHandler.mpo_disabled` state.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with zero
  pending-apply settings.

## 2026-06-03 Tray Game-Mark / Runtime Marker Pass

Continued the UI/UX objective on the tray app only:

- Added a custom Deadlock tray game mark so the shipped Deadlock profiles no
  longer fall back to generic shooter category art.
- Quick Panel favorite cards now use the same game-specific tray marks as the
  main tray menu instead of generic category icons.
- Quick Panel active favorite cards now have a subtle pulsing active indicator
  driven by a WinForms timer; the timer is cleaned up on panel close/rebuild.
- Tray runtime marker now records hashes for loaded helper modules:
  `ABSO-Icons.ps1`, `ABSO-Notifications.ps1`, `ABSO-Settings.ps1`,
  `ABSO-StartupState.ps1`, and `ABSO-QuickPanel.ps1`.
- Installed `health --json` now compares those helper module hashes against
  disk, so a tray-asset-only deploy cannot be falsely reported current when the
  live process still has old helper code loaded.

Validation:

- Generated a local sprite-sheet preview of all current tray game marks and
  visually inspected it; the marks are legible at tray scale, including
  Deadlock.
- PowerShell parser check for `ABSO-Tray.ps1`, `ABSO-QuickPanel.ps1`, and
  `ABSO-Icons.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py
  tests\test_core\test_health.py -q`: `46 passed`.
- `.\.venv\Scripts\python.exe -m ruff check abso\core\health.py
  tests\test_core\test_health.py tests\test_tray_script_static.py`: passed.
- `git diff --check` for the touched tray/health/test files passed with only
  expected CRLF normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy` rebuilt and deployed the
  backend:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe`, length
  `17899514`, SHA256
  `E457758A7739ADB6E2B8E0EB57C836076233BCE85136C787EA4A6AFB56A02294`,
  previous backend backup
  `deploy-backups\abso.exe.bak-20260603-231511`.
- The same deploy copied current tray assets and left the desktop GUI already
  current.
- Tray was restarted via scheduled task `ABSO-Tray-Startup`.
- Live tray PID `40796` wrote `tray-runtime.json` with root script SHA256
  `CA2AF49C69DDAB220EDAD0CD18390E8A14C12E17D36077EBF9B223B83A8F72F7`
  and five module hashes.
- Installed `health --json` reports `9 ok`, `1 warning`, `0 error`;
  `tray_runtime_marker: ok`, `module_count: 5`. The remaining warning is the
  expected reboot-gated `GraphicsSettingsHandler.mpo_disabled` state.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture`, `status: pending_reboot`, with no
  `pending_apply_settings`.

## 2026-06-03 Tray Wording Accuracy Pass

The user clarified that the tray app is the priority UI surface. Fixed and
deployed a tray-only wording pass:

- Tray status, bottom status bar, same-active-profile clicks, apply-warning
  summaries, and apply-failure summaries now format backend handler identifiers
  into user-facing labels. Example: `GraphicsSettingsHandler` displays as
  `Graphics settings`; `GraphicsSettingsHandler.mpo_disabled` displays as
  `Graphics settings (MPO)`.
- The pending-fix toast now includes the friendly setting name, e.g.
  `Pending fix applied: Graphics settings (MPO). Restart required.`
- The Settings panel no longer claims the default profile will "apply on
  startup". It now says `Default Profile (startup reminder)`, matching the
  actual notify-only startup behavior.
- The tray startup status no longer says `Startup restore [...]` for the normal
  cached active-profile load. It now says `Startup state loaded: <profile>` so
  the tray does not imply that settings were restored or reapplied.

Validation:

- PowerShell parser check for `abso\tray\ABSO-Tray.ps1` and
  `abso\tray\ABSO-Settings.ps1`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_tray_script_static.py -q`:
  `22 passed`.
- `git diff --check -- abso\tray\ABSO-Tray.ps1
  abso\tray\ABSO-Settings.ps1 tests\test_tray_script_static.py`: passed with
  only expected CRLF normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy-existing` updated two tray
  assets and reported the backend and desktop GUI were already current.
- Tray was restarted via scheduled task `ABSO-Tray-Startup`.
- Live tray PID `62112` is running the installed tray script with SHA256
  `2F3FA50E2B19197DBE1D7EF79B4E82B4250BCE312427EF7C8193096E992B83C4`.
- Installed `ABSO-Settings.ps1` SHA256:
  `5BFD20B406ED6ECF5B167ACC2175A41D1B779FCFAE6DBBF8A86FCE8FE1E0C7E5`.
- Installed `health --json` reports `9 ok`, `1 warning`, `0 error`;
  `tray_runtime_marker: ok`. The remaining warning is the expected
  reboot-gated `GraphicsSettingsHandler.mpo_disabled` state.

## 2026-06-03 GUI Visual System Upgrade

Fixed and deployed a broad GUI/UX pass:

- Added a shared title-art component with stylized game marks for the real
  profile groups: Desktop, Slippi, Rivals 2, SSBU/Ryujinx, Diablo 4,
  Fortnite, Marvel Rivals, Deadlock, Overwatch 2, Pokemon Auto Chess, and
  PACDeluxe.
- Reworked the global visual system into a darker command-console surface:
  sticky header, animated grid/scan treatments, status dock, glass panels,
  action tiles, game roster tiles, and reduced-motion support.
- Home now starts with the live profile, accurate restart reason, hardware
  state, audit/backups metrics, and a profile roster built from the backend
  catalog. Native installed render shows `11 title groups / 35 variants`.
- Profile Wizard now has a title-art hero, step rail, category filters,
  game-group panels, variant chips, and selected-profile review panels.
- Reports now uses title art and a compact profile selector instead of long
  generic buttons.
- Audit, Backups, Settings, and Timer pages were brought onto the same panel
  system for visual consistency.
- Plain-browser preview no longer calls the Tauri event listener when the
  Tauri bridge is absent, avoiding the `transformCallback` crash during visual
  QA outside the desktop shell.
- Tauri backend/python/network helper command spawns now use a hidden
  `CREATE_NO_WINDOW` helper so backend checks do not show a stray black
  `abso.exe` console window over the GUI.

Validation:

- `npm run lint`: passed.
- `npm run build`: passed.
- `cargo check`: passed.
- `.\.venv\Scripts\python.exe build.py gui`: passed after stopping the
  temporary native QA process that held the release executable lock.
- `git diff --check`: passed with only expected CRLF normalization warnings.
- Browser preview via Playwright: desktop and 390px mobile screenshots captured
  under `output/playwright/`; fixed wizard title-mark overlap and mobile header
  crowding found during that pass.
- Native Computer Use render check against the built release showed live
  backend data. The installed GUI render after deploy shows
  `Overwatch 2 - GSYNC HDR Capture-Safe`, accurate
  `Restart required: Graphics settings`, detected `RTX 4070 @ 300Hz`,
  `11 title groups / 35 variants`, and the new game mark roster.
  Computer Use could capture the WebView but did not reliably deliver clicks
  into it, so native interaction automation is limited to render verification
  for this pass.

Deployment:

- `.\.venv\Scripts\python.exe build.py gui` rebuilt the Tauri GUI release.
- `.\.venv\Scripts\python.exe build.py deploy-existing` copied the installed
  GUI executable:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso-gui.exe`, length
  `5062144`, SHA256
  `2EC9785600189812EB4F3B2C288C20F36191D3AF8579A3442FCC116D8791414F`,
  previous GUI backup
  `deploy-backups\abso-gui.exe.bak-20260603-224708`.
- Installed `health --json` still reports `9 ok`, `1 warning`, `0 error`.
  The only warning is the accurate reboot-gated
  `GraphicsSettingsHandler.mpo_disabled` state.

## 2026-06-03 Soft Warning Accuracy Pass

Fixed and deployed user-facing soft-warning accuracy issues found in installed
health and display diagnostics:

- `Microsoft-Windows-UserModePowerService` event ID `12` rows generated by
  `powercfg.exe reset policy scheme` are now classified as benign power-policy
  reset evidence instead of actionable display/driver events.
- Health and plain console output now split display event counts into
  actionable and benign counts. The current installed health report shows
  `0 actionable display/driver/power event(s), 5 benign event(s), 0 channel
  error(s)`.
- A single VRR-capable monitor is now treated as display context, not a soft
  topology warning by itself. The current installed topology is one 300 Hz
  G-SYNC-compatible monitor, `risk_level: low`, with no detector warnings.
- `display-diagnostics --json` now reports clean event logs from actionable
  event count, not raw benign event count.
- `compositor_black_flash_likely` now requires concrete compositor evidence.
  On this PC the concrete evidence is the active graphics/MPO setting waiting
  for normal reboot, so the likely path is
  `windows_compositor_mpo_pending_reboot`.

Validation:

- Focused CLI/core regression slice: `138 passed`.
- Full unit suite: `1854 passed, 3 skipped`.
- Python lint: `ruff check .` passed.
- Frontend: `npm run lint` passed; `npm run build` passed.
- Tauri shell: `cargo check` passed.
- `git diff --check` passed with only expected CRLF normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy` rebuilt and deployed the
  backend:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe`, length
  `17895482`, previous backend backup
  `deploy-backups\abso.exe.bak-20260603-213214`.
- `.\.venv\Scripts\python.exe build.py gui` rebuilt the Tauri GUI release.
- `.\.venv\Scripts\python.exe build.py deploy-existing` copied the installed
  GUI executable:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso-gui.exe`, length
  `5056512`, previous GUI backup
  `deploy-backups\abso-gui.exe.bak-20260603-213357`.
- Tray runtime marker is already current; live tray PID `49660` is running the
  installed tray script with SHA256
  `0C96D8146895A424C61BAC244A96216CFEBE4C8F25D24C89D86ABACA9995277E`.
- Installed `health --json` succeeds with `9 ok`, `1 warning`, `0 error`.
  The only remaining warning is the accurate reboot-gated
  `GraphicsSettingsHandler.mpo_disabled` state.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture` with `reboot_pending: true` for
  `GraphicsSettingsHandler.mpo_disabled`.
- Installed `display-diagnostics --event-timeout 2 --json` reports
  `event_count: 0`, `actionable_event_count: 0`, `benign_event_count: 0`,
  `risk_level: low`, and
  `likely_black_flash_path: windows_compositor_mpo_pending_reboot`.

## 2026-06-03 UI/Tray Responsiveness Optimization

Fixed and deployed responsiveness/staleness issues across the tray and GUI:

- PowerShell tray active-profile verification is now single-flight. Duplicate
  refresh requests coalesce into the running `state --json --verify` process
  instead of killing it and starting over.
- PowerShell tray launch sanitizer no longer blocks the WinForms UI thread
  while `launch-sweep` runs. The tray still checks game-process liveness on a
  cheap timer, but the backend sweep is now a unique-temp-file background
  process with a poll timer and duplicate suppression.
- PowerShell tray audit is now non-blocking and single-flight. The menu reports
  `Audit running` while the read-only backend audit completes, then updates the
  issue count/status without freezing tray interaction.
- GUI backend-state refreshes preserve the last known active profile identity
  while verification is loading or unavailable, so the UI does not briefly
  claim "no active profile" during normal readback.
- GUI backend-state sync is ordered by request sequence. Older overlapping
  reads cannot overwrite newer active-profile state after tray/wizard apply
  events.
- GUI wizard syncs the Tauri tray active-profile cache from post-apply backend
  state when available, not only the requested/apply-result id.
- Tauri tray profile menu loading is cache-first, then refreshes CLI metadata
  in the background so the tray menu appears promptly without giving up
  freshness.

Validation:

- PowerShell parser check for `abso\tray\ABSO-Tray.ps1`: passed.
- Focused regression tests:
  `tests/test_tray_script_static.py tests/test_core/test_profile_status.py tests/test_cli.py`:
  `105 passed`.
- Full unit suite: `1847 passed, 3 skipped`.
- Frontend: `npm run lint` passed; `npm run build` passed.
- Tauri shell: `cargo check` passed.
- Python lint: `ruff check .` passed.
- `git diff --check` passed with only existing CRLF normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy` rebuilt and deployed the
  backend:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe`, length
  `17896129`, previous backend backup
  `deploy-backups\abso.exe.bak-20260603-195208`; one tray asset updated.
- `.\.venv\Scripts\python.exe build.py gui` rebuilt the Tauri GUI release.
- `.\.venv\Scripts\python.exe build.py deploy-existing` copied the installed
  GUI executable:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso-gui.exe`, length
  `5056512`, previous GUI backup
  `deploy-backups\abso-gui.exe.bak-20260603-195344`.
- Tray was restarted through the installed scheduled task and is running the
  deployed script as PID `49660`; `health --json` reports
  `tray_runtime_marker: ok`.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture` with `reboot_pending: true` for
  `GraphicsSettingsHandler.mpo_disabled`.
- Installed `health --json` succeeds with `7 ok`, `3 warning`, `0 error`.
  Remaining warnings are the expected reboot-gated profile/display diagnostics
  and recent display/power events; there is no stale tray runtime warning.

## 2026-06-03 UI Truthfulness Cleanup

Fixed and deployed stale user-facing status surfaces:

- GUI active-profile state no longer hydrates from old browser storage. Theme
  and settings mode still persist, but active profile status is read from
  backend `state --json --verify` before the UI claims active/no-active state.
- GUI status bar and home banner now derive active, pending apply, pending
  restart, mismatch, error, loading, and unavailable states from a shared
  backend-state helper instead of treating any profile id as green-active.
- GUI apply wizard now uses post-apply backend state for restart cards, does
  not call no-op applies fresh applies, and marks backend state unavailable if
  post-apply state read fails instead of fabricating local active state.
- GUI apply now sends `--no-fallback`, matching manual tray profile selection:
  selected profiles either apply as requested or fail clearly.
- Tauri tray quick-apply also sends `--no-fallback` and updates its active
  profile cache from the backend-returned `profile` field, not the requested
  menu id.
- PowerShell tray restart text now suppresses stale persisted
  `reboot_pending` when live verification is clean, and the bottom status bar
  deduplicates repeated `Restart required` / `Needs apply` fragments.

Validation:

- Focused regression tests:
  `tests/test_tray_script_static.py tests/test_core/test_profile_status.py`:
  `21 passed`.
- Full unit suite: `1845 passed, 3 skipped`.
- Frontend: `npm run lint` passed; `npm run build` passed.
- Tauri shell: `cargo check` passed.
- Python lint: `ruff check .` passed.
- `git diff --check` passed with only existing CRLF normalization warnings.

Deployment:

- `.\.venv\Scripts\python.exe build.py deploy` rebuilt and deployed the
  backend:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe`, length
  `17895394`, previous backend backup
  `deploy-backups\abso.exe.bak-20260603-173011`; one tray asset updated.
- `.\.venv\Scripts\python.exe build.py gui` rebuilt the Tauri GUI release.
- `.\.venv\Scripts\python.exe build.py deploy-existing` copied the installed
  GUI executable:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso-gui.exe`, length
  `5048320`, previous GUI backup
  `deploy-backups\abso-gui.exe.bak-20260603-173219`.
- Tray was restarted through the installed scheduled task and is running the
  deployed script as PID `36604`; `health --json` reports
  `tray_runtime_marker: ok`.
- Installed `state --json --verify` succeeds and reports active profile
  `overwatch2-gsync-hdr-capture` with `reboot_pending: true` for
  `GraphicsSettingsHandler.mpo_disabled`.
- Installed `health --json` succeeds with `7 ok`, `3 warning`, `0 error`.
  Remaining warnings are the expected reboot-gated profile/display diagnostics
  and recent display/power events; there is no stale tray runtime warning.

## 2026-05-29 VRR Cap / Reflex Clarification

The Overwatch 2 cap policy is now documented in source, README,
troubleshooting docs, and this briefing:

- ABSO's default VRR safety cap remains `refresh - 3` for generic VRR
  profiles.
- Overwatch 2 G-SYNC profiles are an explicit exception. They persist the OW2
  Reflex/G-SYNC policy value to both the NVIDIA profile and OW2 config; on this
  PC's 300 Hz path that target is `276`.
- No-sync Overwatch 2 profiles remain at the game's `600` FPS ceiling with
  VRR/G-SYNC off.
- Borderless/windowed mode is intentional for OW2 G-SYNC HDR; do not treat it
  as display-mode drift for that profile family.

Validation and deployment for the cleanup:

- Commit `87b4393 Align VRR cap validation with 300Hz profile path` is pushed
  to `origin/master`.
- `pytest tests\ -q`: `1843 passed, 3 skipped`.
- `ruff check .`: passed.
- `git diff --check`: passed.
- `build.py deploy` completed at `2026-05-29 16:52`, updating the backend and
  one tray asset.
- Tray was restarted after deploy and is running as PID `21832`.

## 2026-05-30 OW2 G-SYNC Display-Path Correction

The previous OW2 strict G-SYNC profiles targeted the legacy exclusive /
fullscreen-only lane, while the capture-safe profiles targeted the modern
borderless/windowed VRR lane. On this PC that made capture-safe benchmark
better even though it keeps overlays and capture hooks alive.

Root-cause fix:

- `overwatch2-gsync` and `overwatch2-gsync-hdr` now use the same optimized
  borderless/windowed VRR path as their capture-safe siblings:
  `global_vrr_mode=fullscreen_and_windowed`, Windows windowed optimizations
  on, per-exe FSO-disable cleared, and OW2 `window_mode=1`.
- The strict/capture distinction is now process policy, not display path:
  overlay-free profiles still stop Medal/Discord/OBS/RTSS-style hooks;
  capture-safe profiles keep them alive.
- On this PC, the local `abso.yaml` MPO mitigation should cover both HDR
  G-SYNC variants if the overlay-free HDR profile is applied. The remaining
  MPO state is reboot-gated and should not be confused with an FPS-cap issue.

## 2026-05-29 Tray Switch Failure Fix

Root cause of the user's "back to competitive" failure:

- The tray correctly sent
  `apply overwatch2-gsync-hdr --json --no-fallback`.
- The backend captured `pre_switch` and `pre_apply` backups and completed the
  strict profile apply.
- Post-apply transaction verification read the old active profile's
  reboot-pending state from `.abso_state.json`.
- `GraphicsSettingsHandler` then reported a reboot-gated
  `mpo_disabled` verification gap even though the strict profile's registry
  target was already written.
- `ComplianceEngine` treated that reboot-only gap as critical, so
  `ProfileTransactionManager` auto-rolled back to the capture-safe state and
  the tray surfaced a failure.

Fix deployed in source and installed backend:

- `ProfileApplier.verify_profile()` accepts an explicit `reboot_pending`
  override.
- `ProfileTransactionManager` verifies a just-applied profile with
  `apply_result.requires_reboot` instead of stale previous-profile state.
- `ComplianceEngine` classifies a written reboot-gated-only verification gap as
  `VERIFY_PENDING_REBOOT` warning, not rollback-critical. Missing registry
  targets and unrelated handler mismatches remain critical.

Validation:

- Focused regression tests:
  `71 passed` for compliance, transaction, and applier tests.
- `ruff check` on touched files passed.
- `git diff --check` on touched files passed, with only existing CRLF warnings.
- Full `pytest tests/ -q` was run and found unrelated baseline failures already
  present on current `master`: NVIDIA auto VRR cap expectation drift, profile
  snapshot drift, and tray profile catalog cache drift.
- Full `ruff check .` was run and found one unrelated existing
  `SIM102` in `abso/data/monitor_osd.py`.
- Local deploy completed with `.\.venv\Scripts\python.exe build.py deploy`.
- Safe installed checks after deploy: `state --json --verify` and
  `health --json` both succeeded.

## Flicker Root Cause

Current evidence points to Windows compositor/MPO/VRR mixed-refresh behavior,
not a physical monitor disconnect.

Read-only diagnostics at `2026-05-26 22:05` reported:

- `display_events.count: 0`
- `display_events.channel_error_count: 0`
- `display_stability.monitor_count: 2`
- `display_stability.risk_level: high`
- `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`
- two monitors:
  - secondary Dell S2719DGF, 2560x1440, 59.95 Hz, detected capability
    144 Hz, VRR-capable
  - primary Generic PnP Monitor, 2560x1440, 300 Hz, VRR-capable
- warning `MULTIMON_REFRESH_BELOW_CAPABILITY`: secondary is running below its
  detected refresh capability
- `graphics_reboot_pending: false`
- active profile display context:
  - `is_capture_safe: true`
  - `graphics_disable_mpo: true`
  - `nvidia_global_vrr_mode: fullscreen_and_windowed`
  - `windows_hdr: true`
  - `ow2_window_mode: 1`
- `display-diagnostics --json` `summary.recommended_actions`:
  - `review_secondary_refresh_rate`
  - `review_capture_mpo_performance`
  - `avoid_redundant_profile_apply`
- `health --json` also includes these actions under
  `checks.display_stability.data.recommended_actions`.

Note: one earlier read-only sample at `2026-05-26 18:50` saw only one display.
The display detector has since been hardened so a partial non-empty hardware
probe is supplemented by active desktop monitor enumeration.

Post-reboot flicker appears improved, but the FPS regression point is not just
"MPO is slower". The corrected assessment is that the profile/apply policy had
two real defects: the strict G-SYNC HDR profile could be silently converted to
capture-safe because mixed refresh was treated as a hard blocker, and the OW2
config handler only wrote `WindowMode` instead of the complete display-mode key
tuple. MPO disabled on the capture-safe HDR VRR path
(`HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\DisableOverlays=1` and
`HKLM\SOFTWARE\Microsoft\Windows\Dwm\OverlayTestMode=5`). On this mixed
300 Hz + 59.95 Hz desktop, that can trade the one-second black flash for extra
DWM/compositor cost.

At 22:27, the user selected what they understood as the strict
`overwatch2-gsync-hdr` profile. Tray logs prove the tray sent
`overwatch2-gsync-hdr`; the backend then silently fell back to
`overwatch2-gsync-hdr-capture` because the strict fullscreen-only VRR path is
blocked on the current mixed-refresh topology. That made "both profiles" behave
like the capture/compositor lane. The latest deployed code fixes this in two
ways: manual tray profile clicks use `apply --no-fallback`, and mixed-refresh
strict VRR is now a warning, not a blocker/fallback trigger. Selecting strict
G-SYNC HDR from the tray should now apply strict G-SYNC HDR unless another real
blocker exists, such as detected overlays or missing VRR/HDR capability.

At 23:08, an elevated CLI apply of `overwatch2-gsync-hdr --no-fallback`
succeeded and verified active. A later tray restart exposed a separate startup
state bug: stale tray cache (`lastProfileState` plus `recentProfiles`) was
treated as stronger than the newer backend state file, so startup reconciliation
rewrote `.abso_state.json` back to `overwatch2-gsync-hdr-capture`. The repair
writer also used PowerShell `Set-Content -Encoding UTF8`, which added a BOM and
made Python state parsing fail. That bug is fixed and deployed:

- newer backend state-file candidates now beat older corroborated tray cache;
- older lone state-file candidates still lose to newer corroborated tray cache;
- startup state repair writes UTF-8 without BOM;
- live LocalAppData state/tray config were repaired to strict
  `overwatch2-gsync-hdr`.

Additional FPS audit evidence:

- Overwatch log at 22:36 saw primary LG at 299.993 Hz HDR and secondary
  S2719DGF at 59.951 Hz.
- Parsec Virtual Display Adapter attached after the reboot and is present as an
  active display adapter; it may add compositor/display stack overhead even
  when it is not the selected OW2 GPU.
- A large NVIDIA DX shader cache file was written at OW2 launch time
  (`DXCache\ecc4a93befac14d8.nvph`, 512 MB, 22:36), so the first session after
  driver/cache churn may run below normal while shaders warm.
- At that point, OW2 config was fullscreen (`WindowMode=0`) while the active
  profile was still the capture-safe profile whose FSO policy had cleared the
  strict AppCompat FSO-disable flag. That was not the same as the strict
  profile's true exclusive lane.
- OW2 display mode is now written and verified as a key tuple:
  `WindowMode`, `FullscreenWindow`, `FullscreenWindowEnabled`, and
  `WindowedFullscreen`. Observed local fullscreen is `0/0/1/0`; observed
  capture-safe/windowed-fullscreen is `1/0/0/1`.

## Safe Commands

These commands are read-only or no-op guarded for the current state:

```powershell
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" health --json
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" display-diagnostics --event-timeout 2 --json
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" state --json --verify
```

For the current active profile, prefer `state --json --verify` or
`health --json` first; do not run a full apply/reapply to chase black flashes.

## Do Not Run Unless User Explicitly Asks

- Full profile apply/reapply meant to force the same active profile.
- Live display reset.
- HDR off/on cycling.
- DWM restart.
- Graphics-driver reset hotkey.
- Reboot.

Keep validation source-level or read-only unless the user authorizes disruptive
display/profile actions. A profile or MPO change can alter flicker/FPS behavior
and may require another reboot.

## Deploy And Verify

Use the deploy helper instead of hand-copying installed runtime files:

```powershell
.\.venv\Scripts\python.exe build.py deploy
.\.venv\Scripts\python.exe build.py deploy-existing
```

After runtime code changes:

1. Run focused tests for touched behavior.
2. Run `py -3 -m ruff check ...` for touched Python files.
3. Run `git diff --check`.
4. Deploy with `build.py deploy`.
5. Run the safe installed checks above.

Avoid full live profile transactions unless the user explicitly chooses a
profile/display-path change to address the FPS-vs-flicker tradeoff.

## Current Bookmark

Work can stop here without leaving the program mid-transition. The runtime is
deployed, safe installed checks pass, and no disruptive display/profile action
was run.

- Installed backend was rebuilt and deployed at `2026-06-03 23:15:11`:
  length `17899514`, SHA256
  `E457758A7739ADB6E2B8E0EB57C836076233BCE85136C787EA4A6AFB56A02294`.
- Installed GUI was already current during the latest deploy. Current installed
  GUI remains length `5062144`, last write `2026-06-03 22:46:50`, SHA256
  `2EC9785600189812EB4F3B2C288C20F36191D3AF8579A3442FCC116D8791414F`.
- Tray is operational and running the installed tray script at PID `64560`;
  `health --json` reports `tray_runtime_marker: ok`. Installed tray root
  script SHA256:
  `9AA1A531A49C769E8EC1B698A2054C9F2715D52F08F9F8CDA5F687BCB4C4AB47`.
  The runtime marker includes five loaded helper module hashes, so helper-only
  tray asset changes are now covered by stale-runtime health checks.
- Installed tray settings script SHA256:
  `E3FB034F09BEA77E9227413A69DF35353FFB7B213E5E5ABBFCEB4293E81DB9E0`.
- Installed tray icon script SHA256:
  `CCCBA47EB98096D07F2D446253065A4B86524967B147831EADAD931924443520`.
- Installed tray notifications script SHA256:
  `C310372DA9B1CAC71A087C0AA9E81CF6F386F560BEFFCA7074510B2D21843B1E`.
- Installed tray quick panel script SHA256:
  `9E1DBD4B38E80C5B7630F3E1EA7BD03D5AC2C1BD365581EEB90AE39A219BA024`.
- Installed tray profile cache byte-content matches source by SHA256:
  `0B5EF40DC2412869855085E0A45CB020D227DA0BF17A59DAE74B26ED07F9D304`.
- Active profile state:
  `overwatch2-gsync-hdr-capture`, `reboot_pending: true` for the local MPO
  mitigation.
- Current source makes the overlay-free and capture-safe OW2 G-SYNC HDR
  profiles share the same borderless/windowed VRR display path. The FPS cap is
  correct when `frame_rate_cap` target/current is `276` on the 300 Hz path.
  Immediately after the 2026-06-10 deploy, read-only verification showed the
  new target `276` and old current `297`; apply the active OW2 profile when
  live mutation is appropriate to write the new cap.
- Installed `health --json` reports `8 ok`, `2 warning`, `0 error`. The
  warnings are the accurate reboot-gated
  `GraphicsSettingsHandler.mpo_disabled` state and the current high-risk
  mixed-refresh multi-monitor topology.
- Installed `display-diagnostics --json` reports a
  300 Hz VRR-capable primary plus a 59.95 Hz secondary,
  `risk_level: high`, and
  `likely_black_flash_path: windows_compositor_mpo_vrr_mixed_refresh`.

## Latest Verified Slice

At `2026-05-26 23:20`, the strict competitive profile was applied and the tray
startup-state regression was fixed/deployed:

- Elevated apply succeeded for `overwatch2-gsync-hdr --json --no-fallback`;
  backup id `2026-05-26_230821`; no failed settings; no reboot pending.
- Installed `state --json --verify` after apply reported
  `overwatch2-gsync-hdr`, verification `active`, `all_active: true`.
- Root cause of the post-apply tray confusion: startup reconciliation preferred
  stale tray cache for `overwatch2-gsync-hdr-capture` over the newer backend
  state file for `overwatch2-gsync-hdr`, then wrote a BOM-prefixed state file.
- `abso/tray/ABSO-StartupState.ps1` now prefers a newer backend state file over
  stale tray corroboration and writes repaired JSON with UTF-8 no BOM.
- `tests/test_tray_state_resolution.py` now covers newer CLI state over stale
  tray cache and BOM-free startup repair.
- Deploy used `.\.venv\Scripts\python.exe build.py deploy-existing`; backend
  and GUI were already current, one tray asset was updated.
- Tray was restarted after deploy. Installed verification stayed strict:
  `overwatch2-gsync-hdr`, `active`, `all_active: true`, `reboot_pending: false`.
- Validation evidence: focused tray test passed (`7 passed`), full suite passed
  (`1836 passed, 3 skipped`), and `ruff check .` passed.

At `2026-05-26 22:58`, the "maybe this assertion is too coarse" audit was
completed and deployed:

- Corrected conclusion: the FPS problem was directionally related to
  capture-safe borderless HDR VRR + MPO disabled, but the codebase also had
  incorrect profile behavior that made the situation harder to reason about.
- `abso/core/capabilities.py` no longer treats mixed-refresh multi-monitor
  strict fullscreen VRR as a hard blocker. It remains a warning because the
  topology is risky, but it no longer triggers capability fallback by itself.
- `abso/settings/ow2_config.py` now exposes and verifies the full OW2 display
  mode tuple: `WindowMode`, `FullscreenWindow`,
  `FullscreenWindowEnabled`, and `WindowedFullscreen`.
- `abso/profiles/overwatch2.py` at that point declared strict fullscreen as
  `0/0/1/0` and capture-safe/windowed fullscreen as `1/0/0/1`; this has since
  been superseded for OW2 G-SYNC HDR by the 2026-05-30 borderless-path fix.
- `abso/tray/profile-catalog-cache.json` and the golden profile snapshot were
  regenerated so the installed tray starts with the updated profile manifest.
- `abso/tray/ABSO-StartupState.ps1` now treats an explicitly empty
  state-candidate list as empty instead of falling back to this PC's real
  LocalAppData state, keeping tests hermetic.
- Runtime deploy completed with installed backend length `17887429`, last write
  `2026-05-26 22:57:30`; previous backend backup:
  `deploy-backups\abso.exe.bak-20260526-225730`.
- A follow-up `deploy-existing` pass updated the installed tray profile cache;
  source and installed cache compare equal.
- Tray was restarted after deploy and is operational at PID `24484`, script
  hash `af5d8eeb7cb63ea02f844478b7ad55becc977693a15c3253169059da9f9e8c0a`.
- Installed health reports `7 ok`, `3 warning`, `0 error`. The warnings were
  expected for that captured state: active profile reboot pending, profile verify
  mismatch in `OW2ConfigHandler`, and display topology risk.
- Installed `state --json --verify` reports active profile
  `overwatch2-gsync-hdr-capture`, `reboot_pending: true`, and verification
  mismatch in `OW2ConfigHandler`.

Validation evidence:

- Focused tests passed: 41 tests covering OW2 config, capabilities, profile
  snapshot, and OW2 profile loading.
- Full test suite passed: `1834 passed, 3 skipped`.
- `ruff check .` passed.

At `2026-05-26 22:40`, manual tray fallback behavior was fixed and deployed:

- Root cause of the apparent tray profile miswire: the tray did send
  `overwatch2-gsync-hdr`, but the backend silently applied
  `overwatch2-gsync-hdr-capture` as a capability fallback because the strict
  fullscreen-only VRR path is blocked on this 300 Hz + 59.95 Hz mixed-refresh
  topology.
- `abso/main.py` now exposes `apply --no-fallback`.
- `abso/core/transaction.py` now lets callers disable capability fallback.
- `abso/tray/ABSO-Tray.ps1` now uses `apply <profile> --json --no-fallback`
  for manual profile clicks. Selecting strict G-SYNC HDR from the tray will now
  either apply strict G-SYNC HDR or fail clearly; it will not silently commit
  capture-safe.
- Runtime deploy completed with installed backend length `17891733`, last write
  `2026-05-26 22:40:13`; previous backend backup:
  `deploy-backups\abso.exe.bak-20260526-224013`.
- Tray was restarted after deploy and is operational at PID `23568`, script
  hash `af5d8eeb7cb63ea02f844478b7ad55becc977693a15c3253169059da9f9e8c0a`.
- Installed `abso.exe apply --help` includes `--no-fallback`.
- Installed health reports `7 ok`, `3 warning`, `0 error`. The warnings were
  expected for that captured state: active profile reboot pending, profile verify
  mismatch in `OW2ConfigHandler`, and display topology risk.
- Installed `state --json --verify` reports active profile
  `overwatch2-gsync-hdr-capture`, `reboot_pending: true`, and verification
  mismatch in `OW2ConfigHandler`.

Validation evidence:

- `.\.venv\Scripts\python.exe -m pytest tests\test_core\test_transaction.py tests\test_cli.py::TestCLIApply::test_apply_json_no_fallback_disables_capability_fallback tests\test_cli.py::TestCLIApply::test_apply_json_reports_and_persists_fallback_profile tests\test_cli.py::TestCLIApply::test_apply_json_marks_failed_preflight_as_error tests\test_cli.py::TestCLIApply::test_apply_json_marks_soft_environment_warnings_as_caution tests\test_tray_script_static.py::test_tray_manual_profile_apply_disables_backend_fallback -q`
  passed: 21 tests.
- `.\.venv\Scripts\python.exe -m ruff check abso\core\transaction.py abso\main.py tests\test_cli.py tests\test_core\test_transaction.py --output-format concise`
  passed.
- `git diff --check -- abso\core\transaction.py abso\main.py abso\tray\ABSO-Tray.ps1 tests\test_cli.py tests\test_core\test_transaction.py tests\test_tray_script_static.py docs\CURRENT_AGENT_BRIEFING.md`
  was clean aside from existing CRLF warnings.

At `2026-05-26 22:06`, a one-time Overwatch FPS regression audit was completed
and the installed runtime/tray were redeployed:

- Root cause at that time: after the reboot, the MPO-disable override was
  committed while the active profile remained `overwatch2-gsync-hdr-capture`, which is
  capture-safe, borderless (`ow2_window_mode: 1`), HDR, and
  `fullscreen_and_windowed` VRR. This is the likely reason flicker improved but
  FPS dropped.
- `abso/settings/ow2_config.py` now expands `auto_vrr_fps_cap` during
  verification, not only apply. Health now verifies concrete OW2
  `frame_rate_cap: 285` and `use_custom_frame_rates: 1`.
- `abso/settings/nvidia/__init__.py` now honors `require_exact_binding` during
  live verification and can use the safe predefined-profile binding probe.
- `abso/profiles/overwatch2.py` now makes capture-safe G-SYNC variants require
  NVIDIA binding verification too; capture-safe no longer means driver binding
  can be weakly verified.
- `abso/core/display_diagnostics.py` now emits
  `review_capture_mpo_performance` when a capture-safe borderless profile has
  MPO disabled on this mixed-refresh VRR topology.
- Runtime deploy completed with installed backend length `17892011`, last write
  `2026-05-26 22:05:12`; previous backend backup:
  `deploy-backups\abso.exe.bak-20260526-220512`.
- Tray was restarted after deploy and is operational at PID `18448`.
- Installed health reports `8 ok`, `2 warning`, `0 error`.
- Installed `display-diagnostics --event-timeout 2 --json` reports
  `event_count: 0`, `channel_error_count: 0`, `monitor_count: 2`,
  `risk_level: high`, path `windows_compositor_mpo_vrr_mixed_refresh`, and
  secondary `59.95Hz` with detected max `144Hz`. Recommended actions now include
  `review_secondary_refresh_rate`, `review_capture_mpo_performance`, and
  `avoid_redundant_profile_apply`.
- Installed `state --json --verify` reports active profile
  `overwatch2-gsync-hdr-capture`, verification `active`, `all_active: true`,
  and `reboot_pending: false`.
- Installed `reapply --json` remains no-op guarded:
  `success: true`, `changed: false`, `changed_settings: []`,
  `transaction: null`.

Validation evidence:

- `.\.venv\Scripts\python.exe -m pytest tests\test_handlers\test_ow2_config.py tests\test_handlers\test_nvidia.py tests\test_profiles.py tests\test_core\test_display_diagnostics.py -q`
  passed: 293 tests.
- `.\.venv\Scripts\python.exe -m ruff check abso\settings\ow2_config.py abso\settings\nvidia\__init__.py abso\profiles\overwatch2.py abso\core\display_diagnostics.py tests\test_handlers\test_ow2_config.py tests\test_handlers\test_nvidia.py tests\test_profiles.py tests\test_core\test_display_diagnostics.py --output-format concise`
  passed.
- `git diff --check -- abso\settings\ow2_config.py abso\settings\nvidia\__init__.py abso\profiles\overwatch2.py abso\core\display_diagnostics.py tests\test_handlers\test_ow2_config.py tests\test_handlers\test_nvidia.py tests\test_profiles.py tests\test_core\test_display_diagnostics.py`
  was clean aside from existing CRLF warnings.

## Recently Deployed Capabilities

- Passive display diagnostics:
  `abso/core/display_events.py`, `display_stability.py`,
  `display_diagnostics.py`, and `health_console.py`.
- Display topology detection now fills partial hardware monitor results from
  active desktop monitor enumeration.
- Display stability diagnostics now preserve monitor max-refresh and VRR
  metadata when hardware detection provides it.
- Mixed-refresh classification now normalizes fractional 60Hz reporting noise
  before flagging compositor risk.
- Overlay detection now parses exact tasklist image names and deduplicates
  overlay labels before display-stability risk scoring.
- Overlay detection and overlay remediation now share
  `abso/core/overlay_policy.py` so process maps and tasklist parsing cannot
  drift.
- Generic tasklist CSV parsing now lives in `abso/core/process_list.py` and is
  used by apply warnings, game watcher polling, process janitor checks, overlay
  detection/remediation, timer process holds, benchmark baseline detection, and
  diagnostics overlay audits.
- Display diagnostics now emit structured recommended actions for no-context
  agents and plain CLI output.
- Display diagnostics now flag the active `review_capture_mpo_performance`
  tradeoff when MPO is disabled on a capture-safe borderless VRR profile.
- OW2 config verification now checks the concrete auto VRR FPS cap and
  `UseCustomFrameRates` state.
- NVIDIA live verification now enforces exact/safe binding requirements for
  profiles that request them.
- Display action code strings are centralized in
  `abso/core/display_diagnostics.py`.
- Plain health output now surfaces high-signal nested display warning details.
- Health JSON now carries the same structured display action records as
  `display-diagnostics --json`.
- Plain health output now prints compact stable display action codes.
- Same-profile no-op guards for `apply`, `reapply`, tray apply, and launch
  paths when the current profile verifies active or only needs reboot commit.
- Targeted pending-apply routing for supported non-reboot settings.
- DirectXUserGlobalSettings exact parsing and deterministic writes.
- Narrow Windows detection/verification to avoid unnecessary HDR/display
  probing for unrelated settings.
- Build/deploy helper that byte-compares installed backend, GUI sidecars, tray
  assets, and config before copying.
- Build/deploy helper can replace a transiently locked installed executable by
  renaming the old target aside before copying the new one.
- Shared profile helpers now cover Fullscreen Optimizations override-map
  construction.
- Applier finalization now reuses the shared NVIDIA profile identity injector,
  reducing drift between direct profile settings and apply/verify settings.
- Profile overrides now support registry settings and recursively merge nested
  maps, so small user overrides do not accidentally erase sibling defaults.
- Profile override handler routing now lives beside the config schema and is
  covered by a schema drift test.
- Profile override handler lookup and nested merge semantics now live beside
  the config schema and are covered by config-layer tests.
- Profile override config load now fails clearly on malformed override maps,
  unknown section names, and non-mapping section values.
- Applier and config override lookup now resolve aliases to canonical profile
  ids consistently.
- Productivity SDR/HDR settings now use the shared profile merge pipeline and
  stable direct NVIDIA profile identity.
- User profile hardening:
  - shared profile-base merge helpers
  - nested profile settings isolation
  - shared profile metadata literal validation
  - shared sync-mode validation
  - fail-fast custom YAML tray/sync metadata validation
  - fail-fast custom YAML metadata key validation
  - fail-fast custom YAML top-level field validation
  - canonical custom YAML literal metadata values
  - route-safe profile IDs
  - reserved built-in/alias conflict checks
  - robust `profile-create` YAML generation
  - shared tray-category validation
  - typed metadata validation
- Documentation cleanup:
  - root `AGENTS.md` is the zero-context entrypoint
  - this briefing is now the compact live-state file
  - stale historical notes are isolated under `docs/archive/`

## Code Map

- CLI apply/state/profile commands: `abso/main.py`
- Apply orchestration and profile overrides:
  `abso/core/applier.py`, `abso/core/config.py`, `abso.yaml`
- Active state and profile verification:
  `abso/core/state_store.py`, `abso/core/state_reconcile.py`,
  `abso/core/profile_status.py`
- Pending apply and apply feedback:
  `abso/core/pending_apply.py`, `abso/core/apply_feedback.py`,
  `abso/core/apply_hooks.py`
- Display/flicker diagnostics:
  `abso/core/display_events.py`, `abso/core/display_stability.py`,
  `abso/core/display_diagnostics.py`, `abso/core/health.py`,
  `abso/core/health_console.py`
- Display-sensitive handlers:
  `abso/settings/windows.py`, `abso/settings/graphics.py`,
  `abso/settings/color.py`, `abso/settings/display_range.py`
- Profile catalog and YAML loading:
  `abso/profiles/catalog.py`, `abso/profiles/yaml_loader.py`,
  `abso/profiles/profile_bases.py`, `abso/profiles/user_profile_template.py`
- Tray behavior:
  `abso/tray/ABSO-Tray.ps1`, `abso/tray/ABSO-StartupState.ps1`,
  `abso/tray/ABSO-Icons.ps1`, `abso/tray/Install-Startup.ps1`
- GUI backend-state reporting:
  `gui/src/App.tsx`, `gui/src/stores/appStore.ts`,
  `gui/src/pages/ProfileWizard.tsx`, `gui/src/components/StatusBar.tsx`
- Packaging/deploy:
  `build.py`, `abso.spec`, `gui/src-tauri/tauri.conf.json`,
  `gui/src-tauri/src/main.rs`

## Backlog For Next Agent

Continue with small, verifiable slices:

- Keep source cleanup focused on duplicated policy, overgrown CLI/tray logic,
  and custom-profile validation.
- Prefer shared helpers over repeating policy in `main.py`, tray scripts, and
  profile loaders.
- If the user wants the overlay-free Overwatch G-SYNC HDR profile active, apply
  `overwatch2-gsync-hdr` and verify that OW2 remains borderless/windowed
  fullscreen with cap `276` on the 300 Hz path. Do not force exclusive
  fullscreen for this path.
- If flicker continues, collect fresh
  `display-diagnostics --json` and event evidence before applying another
  mitigation.

## Worktree Rule

This worktree has many local changes from prior sessions. Never revert files
wholesale unless the user explicitly asks. If a local change is unrelated,
leave it alone. If it affects the current task, understand it and build on it.
