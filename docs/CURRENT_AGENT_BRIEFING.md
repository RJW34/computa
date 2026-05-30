# Current Agent Briefing

Last updated: 2026-05-30 00:52 America/New_York

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

## Current User Objective

- Stop occasional secondary-monitor black flashes while keeping Overwatch 2
  usable. The user found that `overwatch2-gsync-hdr-capture` performed better
  than the overlay-free `overwatch2-gsync-hdr` lane; root cause was the
  profiles using different display paths, not overlays improving performance.
- Continue end-to-end repo cleanup: remove bloat, centralize duplicated policy,
  harden profile/apply behavior, keep docs accurate, and deploy verified builds
  to this local machine.

## Live Machine State

- Active profile: `overwatch2-gsync-hdr-capture`.
- Active display topology from installed `display-diagnostics --json`:
  two monitors: a 2560x1440 300 Hz VRR-capable primary plus
  `Dell S2719DGF(Displayport)` at 2560x1440 59.95 Hz. The secondary is below
  its detected 144 Hz capability, and the topology remains mixed-refresh.
- Installed backend:
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe`
  length `17894806`, last write `2026-05-30 00:50:00`, SHA256
  `FDFB1D0237B6AC4E858F50DA8018272A209F60703E9F10EE6C1AEBA63693EEC0`.
- Tray runtime: scheduled-task startup is installed and enabled. Live tray PID
  `17172` is running installed script
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso\tray\ABSO-Tray.ps1`.
  `health --json` reports `tray_runtime_marker: ok`.
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
- The FPS cap is already correct for the active 300 Hz path:
  `frame_rate_cap` target `297`, current `297`, active `true`.
- Any remaining MPO warning is the PC-local mixed-refresh compositor
  mitigation waiting for a normal reboot, not an OW2 display-mode or cap
  problem.

## 2026-05-29 VRR Cap / Reflex Clarification

The Overwatch 2 cap policy is now documented in source, README,
troubleshooting docs, and this briefing:

- ABSO's persisted static VRR safety cap is `refresh - 3`.
- On this PC's 300 Hz Overwatch path, ABSO should write `297`, not `276`,
  `277`, or any 280 Hz-derived value.
- NVIDIA Reflex may dynamically pace the effective runtime FPS below that
  static ceiling, often around the mid/high 270s on a 300 Hz path. That is
  Reflex queue control, not the value ABSO should persist to NVCP or OW2 config.
- Current installed/source policy keeps the OW2 config cap at `297`
  target/current. Borderless/windowed mode is now intentional for OW2 G-SYNC
  HDR; do not treat it as display-mode drift for that profile family.

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

For the current strict profile, `reapply --json` should be a no-op if state
verification remains active. Prefer `state --json --verify` or `health --json`
first; do not run a full apply/reapply to chase black flashes.

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
deployed, the tray is restarted, and the branch is clean after commit
`87b4393`.

- Installed backend was rebuilt and deployed at `2026-05-29 16:52:04`:
  length `17892269`, SHA256
  `B2D481C5F875010AB215E27127E45370ECB75FF09BAC055835F03C0F398D2026`.
- Tray is operational and running the installed tray script at PID `21832`;
  `health --json` reports `tray_runtime_marker: ok`.
- Installed tray profile cache byte-content matches source by SHA256:
  `4EC4C8816CD40E4AB318E63C0FAB5F13F00D3A0AF19D628D6FC7DCE84F1258FB`.
- Active profile state:
  `overwatch2-gsync-hdr-capture`, `reboot_pending: true` for the local MPO
  mitigation.
- Current source makes the overlay-free and capture-safe OW2 G-SYNC HDR
  profiles share the same borderless/windowed VRR display path. The FPS cap is
  correct: `frame_rate_cap` target/current `297`.
- `display-diagnostics --json` should report one 300 Hz VRR-capable monitor.
  If it reports an MPO/compositor next action, treat that as the local
  reboot-gated mitigation, not as a reason to force exclusive fullscreen.

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
  fullscreen with cap `297`. Do not force exclusive fullscreen for this path.
- If flicker continues, collect fresh
  `display-diagnostics --json` and event evidence before applying another
  mitigation.

## Worktree Rule

This worktree has many local changes from prior sessions. Never revert files
wholesale unless the user explicitly asks. If a local change is unrelated,
leave it alone. If it affects the current task, understand it and build on it.
