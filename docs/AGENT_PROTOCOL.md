# A.B.S.O. Agent Protocol

**Freshly cloned onto a new PC? Read `docs/NEW_MACHINE_SETUP.md` first** to set
up the dev environment and establish this machine's real state. This is a
single-developer, single-machine project: there is no multi-machine role split
(see §2), and live-PC mutation always needs the user's go-ahead (see §3).

**On an already-configured machine, read `docs/CURRENT_AGENT_BRIEFING.md`
first.** That file is the current live-machine handoff, including the active
profile, installed build, monitor-flicker repair state, and any reboot-gated
work. It is machine-specific; on a fresh clone, re-verify before trusting it.

This file is the durable forward-looking protocol for any agent (Claude Code,
Codex, or otherwise) picking up work on this project. It replaces the dated
per-agent handoffs that previously sat in `docs/` and codifies the practices
that have stuck after multiple remediation passes.

When a procedure or convention here disagrees with anything in an
archived handoff (`docs/archive/...`), this document wins. When live machine
state in this document disagrees with `CURRENT_AGENT_BRIEFING.md`, the briefing
wins.

---

## 1. Reading order

1. **`docs/CURRENT_AGENT_BRIEFING.md`** - current live-machine state, installed
   build/deploy status, monitor-flicker precautions, and immediate next action
2. **This file** (`docs/AGENT_PROTOCOL.md`) - durable agent workflow and
   repo conventions
3. **`README.md`** — current product surface and what built-in profiles
   actually do (truth-passed; do not let it drift)
4. **`CLAUDE.md`** — project-rooted Claude Code instructions (kept short
   on purpose; it points back here)
5. **`docs/QUALITY_RUBRIC.md`** — the shipping bar and forbidden claims
6. **`docs/REMEDIATION_ROADMAP.md`** — the long-running grade lift plan;
   completed PRs are marked inline
7. **`docs/API.md`** — module-level reference for the core/handler API
8. **`docs/TROUBLESHOOTING.md`** — runtime issues, mostly user-facing

Skip the docs in `docs/archive/` unless you specifically need history
context. Those are frozen handoffs from past agents (HERMES, Opus 4.7
xhigh, earlier Claude generations) and reference machine names, dates,
and PR slices that have since changed.

---

## 2. Development & test machine

A.B.S.O. is a single-developer project. Whatever PC the repo is checked out on
is the one machine that does everything — coding, tests, live validation, and
release signoff. There is no multi-machine role split and no cross-machine
coordination; treat the machine you're operating on as a standalone testing
ground. Do not assume any particular GPU, monitor, or OS build — detect the
actual hardware with `python -m abso detect` first.

Because one machine wears every hat, **discipline replaces geography**:

- Do not upgrade a setting's evidence to `measured` without an actual
  benchmark artifact in `reports/benchmarks/`.
- Do not call a profile `optimal` without recorded before/after frame data on
  the hardware you actually ran it on.
- VRR, HDR, refresh-rate, and NVIDIA claims are only valid on a machine that
  actually exposes those capabilities — confirm with `detect` before claiming.

---

## 3. Live-PC test policy

Live-PC actions are always subordinate to the user's latest instruction and to
`docs/CURRENT_AGENT_BRIEFING.md`. If the briefing says a change is reboot-gated,
do not keep re-applying profiles to force it.

The user treats the machine they are actively developing ABSO on as a testing
ground, so the read-only and apply/restore ABSO operations below are in scope on
that machine. This is narrower than blanket access: run read-only commands
first, confirm before anything disruptive, and always pair `apply` with a
`restore`. When unsure, fall back to the standing rule — read-only by default,
ask before mutating.

What's pre-authorized:

- Read-only PowerShell / `winreg` probes (registry, WMI, `Get-HotFix`,
  Secure Boot servicing keys, etc.)
- `python -m abso detect|audit|bios|profiles|state|backups|health|games|
  config|profile-aliases|report` — all read-only CLI surfaces
- `python -m abso backup-create` — pure capture, no system mutation
- `python -m abso apply <profile>` followed by `python -m abso restore latest`
  — provided you immediately restore afterward
- Targeted remediation commands such as `python -m abso apply-pending <profile>`
  when the current briefing says the profile has pending apply settings

What still needs explicit approval:

- Long-running `apply` without a planned `restore`
- Full profile apply, HDR cycling, DWM restart, display reset, or driver reset
  when the current issue is monitor flicker and the briefing says the MPO
  target is already written
- Tray `Reset Display Pipeline...` is manual-only and must keep a warning
  confirmation with `No` as the default before it can send driver-reset
  hotkeys.
- Mutations outside the ABSO apply surface (`bcdedit`, `wusa`, group policy)
- Anything that modifies user files outside `backups/`, `reports/`, or
  the per-game config paths ABSO already owns

**Required protocol when testing in prod:**

1. Run the read-only commands first (`detect`, `audit`, `bios`).
2. Take a manual baseline backup via `abso backup-create`.
3. Apply the target profile.
4. Run `abso verify <profile>` and `abso state`.
5. Restore via `abso restore latest`.
6. Confirm `abso state` shows no active profile (or the prior state).

This sequence has been validated end-to-end and does not leave the machine in a
broken state.

**Required protocol for automated tests that invoke CLI mutations:**

- Patch `abso.main.STATE_FILE` or `abso.main._state_file_targets` to a temp
  path before invoking commands such as `restore`, `apply`, `launch`, or any
  path that calls `clear_current_profile()` / `set_current_profile()`.
- If a test exercises packaged/LocalAppData behavior, redirect `LOCALAPPDATA`
  to `tmp_path`. Do not let tests use the real
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer` state root.
- A restore smoke test previously removed this PC's live `.abso_state.json`
  because it invoked `restore latest` against the default state target. Keep
  mutation tests hermetic.

### 3.1 Current monitor-flicker safety rule

As of 2026-05-26, the active repair path for the secondary-monitor black-flash
issue is:

1. Keep `overwatch2-gsync-hdr-capture` active.
2. Keep the local override
   `profile_overrides.overwatch2-gsync-hdr-capture.graphics.disable_mpo: true`.
3. Use `display-diagnostics --json`, `state --json --verify`, `health --json`,
   or `apply-pending --json` for verification/remediation.
4. Do not run full profile apply, live display reset, HDR cycle, DWM restart,
   or driver hotkey unless the user explicitly asks.
5. Reboot normally to let the written MPO registry target become live, then
   verify.

The tray must keep already-active profile selection verify-gated. Pending
apply state should route to the narrow `apply-pending` action, active or
reboot-pending state should be a no-op notice, and only mismatch/error
verification states should reach the safer `reapply --json` fallback.
Tray startup state reconciliation must treat backend state-file timestamps as
authoritative when they are newer than tray cache. `lastProfileState` and
`recentProfiles` corroborate each other only for older or equal state; they must
not overwrite a newer CLI/backend apply. Any repaired `.abso_state.json` must be
written as UTF-8 without BOM.
The backend `apply <current-profile> --json` path must keep the same invariant:
when live verification reports the current profile active with no pending apply
or mismatches, it returns a no-op payload instead of running a transaction.
When live verification reports pending apply settings for the current profile,
backend `apply` must route through the narrow `apply-pending` policy and fail
closed for unsupported pending settings.
When live verification reports only pending reboot-gated settings and those
settings cover the mismatched handlers, treat that as a no-apply state. A full
apply/reapply/launch apply cannot commit it; reboot is the commit mechanism.
Backend `reapply --json` must preserve the same guard: active and reboot-gated
current-profile states no-op, supported pending apply settings route through
`apply-pending`, and unsupported pending settings fail closed instead of
running a full transaction.
Backend `launch <current-profile>` must keep the same behavior when
`--restore-on-exit` is not requested: skip profile transactions for verified
active state, route supported pending settings through `apply-pending`, and
fail closed for unsupported pending settings.

`display-diagnostics --json` is the narrowest read-only flicker evidence path:
it samples display/driver/power event logs, active monitor topology, and
read-only active-profile reboot context without profile verification, profile
apply, display reset, or state writes. Use
`display-diagnostics --samples 6 --interval 10 --json` for a short observation
window when the user is watching for a black flash. Use `--jsonl` instead of
`--json` when redirecting an observation window to a log; each sample is
emitted as one complete JSON object immediately after collection.
The plain command output includes active profile and reboot-pending state
before the display evidence, so it is suitable for quick human status checks.

`health --json` includes `checks.display_events`, a read-only Windows System
event-log scan for Display, `nvlddmkm`, Kernel-PnP, UserModePowerService, and
Kernel-Power evidence plus DxgKrnl Admin/Operational channels. Use that before
disruptive display actions when broader app health is also relevant. The
display-event payload includes `channel_errors` and `channel_error_count` for
optional channel query failures; normal no-matching-events results are not
channel failures. It is
compact by default: profile verification omits the full per-handler map, and
backup health reports roots plus a latest backup row instead of five recent
rows. In backup health, `count` is unique backup IDs, `entry_count` is rows
across all roots, and `mirror_count` is duplicate mirror rows. Use
`health --json --full-verify`, `health --json --full-backups`,
`state --json --verify`, or `backups --json` when that detail is required.
It also includes `checks.tray_runtime_marker`: a warning there means the live
tray has not proven it loaded the deployed tray script. Treat that as a tray
restart/version-staleness signal, not as evidence that a profile apply failed.
The marker check should validate the installed script hash, script path, and
that the recorded tray PID still exists.

`display-diagnostics --json` and `health --json` also include a read-only
multi-monitor topology snapshot. Use it to separate physical disconnect
evidence from compositor risk. If event logs are clean while
`display_stability.risk_level` or `checks.display_stability.data.risk_level`
is `high`, treat the black flash as likely Windows compositor/MPO/VRR
mixed-refresh behavior until stronger evidence says otherwise.
If `display-diagnostics` reports `active_state.graphics_reboot_pending: true`,
do not run a full apply to fix that state; the next action is the normal reboot
reported in `summary.next_action` / `display_stability.next_action`.

Prefer structured action codes when deciding what to do next:

- `display-diagnostics --json`: read `summary.recommended_actions`.
- `health --json`: read
  `checks.display_stability.data.recommended_actions`.

Current display action codes are:

- `reboot_to_commit_graphics_settings`
- `review_secondary_refresh_rate`
- `review_capture_mpo_performance`
- `avoid_redundant_profile_apply`

These are advisory records. The diagnostics commands remain read-only and do
not change display modes, reapply profiles, reset DWM, or reboot the machine.

Mixed-refresh multi-monitor strict fullscreen VRR should be treated as a
risk warning, not a hard fallback trigger. A user deliberately selecting a
strict G-SYNC profile should not be silently moved to the capture-safe profile
just because the secondary display is running a different refresh rate. Overlay
blockers, missing VRR/HDR capability, and exact NVIDIA binding failures can
still block strict profiles.

This rule is here because a full no-op-looking profile apply used to rewrite
display-sensitive state and could blank the secondary monitor for one to two
seconds.

---

## 4. Console-safe strings (cp1252 mojibake protection)

The Windows console codepage cannot render U+2013 (–) or U+2014 (—).
Both render as `�` in CLI output, which is confusing in user-visible
audit / bios / apply messages.

Rule: **No em-dashes or en-dashes in strings that reach `print`,
`click.echo`, `Issue.title`, `Issue.explanation`, `Warning.message`,
`BiosRecommendation.current_value`, or any other CLI-rendered surface.**

Em-dashes in docstrings, comments, and Markdown are fine — those don't
hit the console.

If you need range syntax in CLI output, use `" - "` (space-hyphen-space)
instead of `"–"` or `"—"`. Two real bugs of this shape were found and
fixed in commit `ab1a17f`; the cp1252 console will keep biting if you
let dashes through.

---

## 5. Patterns introduced and what they replace

Several patterns in the current codebase are the result of deliberate
refactors. Use them; don't reintroduce the older shapes they replaced.

### 5.1 Central handler registry

`abso/core/handler_registry.py` holds **one** list of every settings
handler ABSO talks to, tagged with `audit` and `backup` booleans. Each
entry is a `HandlerEntry`.

Old shape (do not reintroduce): parallel handler lists in
`abso/core/auditor.py` and `abso/core/backup.py`. They drifted, and
adding a handler in one place silently missed the other.

To add a new handler:

1. Implement the handler in `abso/settings/<your_handler>.py`.
2. Add one `HandlerEntry(YourHandler, audit=..., backup=...)` row in
   `abso/core/handler_registry.py::_all_entries()`.
3. Override `is_critical_verify = True` on the handler class if a
   post-apply verify mismatch should escalate to `CRITICAL` (state-
   mutating system handlers and per-game config handlers should
   override; detect-only / opt-in surfaces should not).

### 5.2 `is_critical_verify` property

`SettingsHandler.is_critical_verify` (default `False`) drives the
`ComplianceEngine`'s severity escalation for verify mismatches. The
engine resolves the set lazily from the registry and caches it
per-process.

Old shape (do not reintroduce): a hardcoded class-name set named
`CRITICAL_VERIFY_HANDLERS` inside `ComplianceEngine`. Renaming a
handler silently downgraded its criticality.

### 5.3 OS introspection

`abso/utils/os_release.py::detect_os_release()` is the single source of
truth for Windows build/UBR/edition. Don't reach into
`HKLM\Software\Microsoft\Windows NT\CurrentVersion` directly.

`OsRelease.at_least(build, ubr)` is the only correct way to gate code
on a Windows build floor. Capability checks (`min_os_build`,
`validated_os_build`) on profiles plug into this.

### 5.4 Hardware lookup tables

`abso/data/hardware_db.py` owns the static lookup tables —
`OEM_MANUFACTURERS`, `OEM_MOTHERBOARD_LOOKUP`, `SMBIOS_CHASSIS_TYPES`,
`GSYNC_NATIVE_PATTERNS`, `GSYNC_ULTIMATE_PATTERNS`, etc.

Add new OEM / monitor entries here, not inline in `detector.py`.

### 5.5 KB checker discipline

`abso/core/kb_checker.py` tracks known-bad Windows updates. Two
patterns make it self-policing:

- `ProblematicKB.superseded_by` / `fixed_in_build` — when a regression
  is patched in a later cumulative, the warning auto-suppresses on
  machines that have the fix.
- `LAST_REVIEWED_UTC` — bump this constant whenever the list is
  touched. The auditor surfaces an info issue if more than
  `STALENESS_DAYS` (60) elapse without a refresh.

After each Patch Tuesday, check the cumulative for gaming-impacting
regressions, add or supersede entries, and bump `LAST_REVIEWED_UTC`.

### 5.6 Detect-only handler pattern for feature-flag rollouts

When Microsoft ships a feature flag (Xbox Mode, AI taskbar agents,
etc.) before publishing key names, follow the pattern in
`abso/settings/xbox_mode.py` and `abso/settings/ai_agents.py`:

- `detect()` probes candidate registry paths and reports
  `feature_present: False` when none match
- `apply()` returns `{"success": False, "error": "...not yet
  implemented..."}` — never write to an undocumented key
- `restore_guarantee = "none"` so backup/restore stays non-blocking
- Gate via `OsRelease.at_least(...)` so older builds skip the audit
- Register with `audit=True, backup=True` in the handler registry

Apply-path implementation lands later, once Microsoft documents the
key surface.

### 5.7 Named registry constants

`abso/settings/registry.py` exports module-level
`WIN32_PRIORITY_GAMING_OFFLINE` (`0x2A`) and
`WIN32_PRIORITY_GAMING_ONLINE` (`0x26`) plus class-level legacy
aliases. Profiles and the stability gate import these by name.

Don't reintroduce raw `0x2A` / `0x26` literals in profile or linter
code.

### 5.8 State, path, and pending-apply modules

Several 2026-05-26 repairs extracted live-state logic out of the oversized CLI
module. Keep future work on these paths inside the shared helpers:

- `abso/core/app_paths.py` owns the installed
  `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer` root and active-profile
  state-file path.
- `abso/core/state_store.py` owns active-profile state reads, newest-target
  selection, primary writes, and best-effort mirror writes.
- `abso/core/state_reconcile.py` owns reboot-pending reconciliation after a
  later boot.
- `abso/core/profile_status.py` owns compact profile verification summaries
  shared by `state --json --verify`, health, tray, and GUI status.
- `abso/core/pending_apply.py` owns narrow targeted remediations such as
  `GraphicsSettingsHandler.mpo_disabled`.
- `abso/core/config.py` owns default config discovery. Keep source checkout
  behavior (`./abso.yaml`) and installed tray/GUI behavior
  (`%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.yaml`) aligned before
  changing profile overrides.

Old shape (do not reintroduce): duplicate LocalAppData path construction,
duplicate `.abso_state.json` reads/writes in `main.py` and health, or broad
profile apply logic for a single pending reboot-gated graphics setting.

---

## 6. Backlog: what's actually open right now

Updated 2026-05-26 after the monitor-flicker repair, targeted
`apply-pending` path, state-store/path extraction, deployed tray/GUI rebuild,
startup-action self-repair, and installed config-path fallback. For live
machine status, installed build timestamps, scheduled-task action state,
installed config/backup state, local deploy command status, and the current
reboot-gated MPO state, read `docs/CURRENT_AGENT_BRIEFING.md` first.

### Real open work

- **Monitor-flicker final validation** — the MPO registry target is written for
  `overwatch2-gsync-hdr-capture`, but Windows has not rebooted since that
  write. The next step is a normal reboot, followed by installed
  `state --json --verify` and `health --json`. Do not re-run full profile apply
  to solve this state.
- **Tray runtime-marker warning after deploys** — if installed health warns
  `tray_runtime_marker` after a future tray script deploy, restart the tray
  into the deployed LocalAppData `ABSO-Tray.ps1`. This does not require profile
  apply or display actions.
- **Xbox Mode / AI Agents apply paths** — handlers are detect-only.
  When Microsoft publishes stable registry keys for these features,
  flip `apply()` from `NotImplementedError`-equivalent to an actual
  registry write. See `abso/settings/xbox_mode.py:142` and
  `abso/settings/ai_agents.py:179`.
- **Secure Boot cert reboot** — `BiosDetector.detect_secure_boot_cert_state()`
  reports `updated_reboot_pending` on this machine. Not an ABSO bug;
  the user just needs to reboot to finalize PCA2023 before June 2026.
- **Ryujinx config enforcement** — still inherits the generic emulator
  base; no native config handler. Tracked in
  `docs/REMEDIATION_ROADMAP.md` PR-19. Acceptable to keep as
  `system_only` scope per `NEXT_IMPLEMENTATION_PHASE.md`.
- **Benchmark artifacts** — no profile currently has a benchmark
  artifact in `reports/benchmarks/`. Required before any profile can
  legitimately be called `optimal` per the quality rubric.

### 6.0 Local Deploy Rule

Use `.\.venv\Scripts\python.exe build.py deploy` for build+deploy and
`.\.venv\Scripts\python.exe build.py deploy-existing` when `dist\abso.exe` is
already current. Do not hand-copy the backend, installed GUI executable, tray
assets, GUI sidecars, config, or backups unless the deploy helper is broken and
the repair is documented in `CURRENT_AGENT_BRIEFING.md`. If a different
interpreter lacks PyInstaller, `build.py` now exits before cleaning `build/` or
`dist/`. Deprecated ad-hoc tray diagnostics with broad process-kill behavior
must stay out of both the installed tray tree and the PyInstaller tray data
bundle.

### 6.1 OW2 / Reflex latency-stack closure (audit 2026-05-21)

Standing audit against `overwatch2-gsync-hdr` after the launch-time
process janitor landed. These are the knobs ABSO still does not tune
that would measurably move click-to-photon latency on a competitive
300 Hz VRR primary plus mixed-refresh secondary setup.
Ordered by impact. Most of these benefit every Reflex shooter profile (Marvel
Rivals, Deadlock, Fortnite, Rivals 2 G-SYNC), not just OW2 — wire them through
`BaseProfile` traits, not into OW2 specifically.

**High impact:**

1. **GPU MSI mode** — write `MSISupported = 1` under
   `HKLM\SYSTEM\CurrentControlSet\Enum\PCI\<GPU>\Device Parameters\
   Interrupt Management\MessageSignaledInterruptProperties`. Real
   input-to-photon delta on some boards. Needs a new
   `InterruptModeHandler` with audit + backup + verify; must resolve
   the GPU instance path via WMI (`Win32_PnPEntity` GUID class
   `4d36e968`). Reboot required.
2. **NIC driver tuning** — Interrupt moderation off, RSS on, EEE
   off, flow control off, larger receive/transmit buffers. Per-NIC
   (Intel I225-V vs Realtek vs Killer). ABSO has `network.py` for
   TCP/Nagle but no NIC-driver layer. New `NicDriverHandler`
   keyed off `Get-NetAdapterAdvancedProperty`; gate behind a
   `nic_tuning` profile trait so productivity / browser profiles
   skip it.
3. **Focus Assist auto-set during game session** — force "Alarms
   only" while the active profile's game binary is alive; restore
   on exit. Belongs in the tray's `LaunchSanitizer` next to the
   process sweep, not in a handler. Registry key:
   `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\
   Settings\Windows.SystemToast.FocusAssist` (volatile across Win11
   builds — guard with `OsRelease.at_least`).
4. **Windows Defender exclusions for game install folders** — adds
   the game's install dir to `Add-MpPreference -ExclusionPath` so
   real-time AV scans do not fire on shader-cache writes during
   play. Discovery via `core/game_detector.py` which already
   resolves install paths per platform. Reverse on profile exit
   or `restore latest`. Must guard against the user running a
   non-Defender AV — detect via `Get-MpComputerStatus`.
5. **Audio engine APO chain** — Disable audio enhancements
   (`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\
   Audio\Render\<deviceId>\FxProperties` — `{1da5d803-...},5 = 0`),
   disable spatial sound, pin default sample rate to 48 kHz. Pairs
   with the existing Nahimic / Sonic Studio process-level kill in
   the janitor's always-safe tier. New `AudioEngineHandler`.

**Medium impact:**

6. **Game DVR registry hard-off** —
   `HKCU\System\GameConfigStore\GameDVR_Enabled = 0`,
   `HKCU\SOFTWARE\Microsoft\GameBar\AutoGameModeEnabled = 1`,
   `UseNexusForGameBarEnabled = 0`. Defensive — the janitor kills
   the *processes* but does not disarm the *setting*, so Windows
   respawns them next session. Likely belongs in
   `settings/windows.py` next to the existing Game Mode handling.
7. **Pagefile sizing** — pin to a fixed min/max via
   `wmic computersystem set AutomaticManagedPagefile=False` +
   `wmic pagefileset` set to a fixed size (recommend 1.5x RAM
   minimum, 2x maximum, capped at 32 GB). Avoids runtime resize
   stutter. New `PagefileHandler`; restore symmetry must capture
   the original auto-managed state.
8. **Memory hygiene** — `Set-MMAgent -PageCombining $false`,
   `-MemoryCompression $false` on 32 GB+ rigs. Detect RAM via
   existing `HardwareDetector` and gate the apply on a minimum
   floor.
9. **Hyper-V root** — `bcdedit /set hypervisorlaunchtype off`,
   separate from VBS. Some configurations leave the root partition
   active even with VBS off. Reboot required. Surfaces in
   `bios_detector.py` already? Verify; if not, add an audit
   finding that escalates when VBS is off but `hypervisorlaunchtype
   = auto`.
10. **Dynamic tick / HPET** — `bcdedit /set disabledynamictick yes`,
    `bcdedit /deletevalue useplatformclock`. Mostly placebo on
    Win11 24H2+ but still in tuning guides. Land as an *audit-only*
    finding first; do not auto-apply until a benchmark artifact
    proves a frame-time delta on this hardware.

**Pattern for the OW2 closure work:**

- New handlers register one `HandlerEntry` in
  `abso/core/handler_registry.py`, override
  `is_critical_verify` if a verify miss should escalate.
- Backup symmetry is non-negotiable per `REMEDIATION_ROADMAP.md`
  PR-06. Every handler must capture pre-apply state and round-trip
  through `restore latest`.
- Profile opt-in via new `BaseProfile` traits (e.g.
  `requires_msi_mode_gpu`, `nic_tuning_scope`, `audio_engine_strict`).
  Default to most aggressive for Reflex-shooter VRR strict lanes,
  off for productivity / browser / capture-safe variants.
- Tests: unit coverage for handler + a profile-level invariant test
  that the strict OW2/Deadlock/Marvel-Rivals/Diablo-4 G-SYNC lanes
  all turn the new knob on.

**Out of scope for the latency closure:**

- BIOS-level knobs (XMP/EXPO, resizable BAR, C-states, Above-4G).
  Already surfaced via `bios_detector.py` recommendations; ABSO
  cannot apply these and should not pretend to.
- Mouse polling rate, monitor overdrive — surfaced via
  `monitor_osd.py` recommendations; firmware-side.
- OW2 INI keys we deliberately do not write
  (`Reflex`, `MaxThreads`, `WorkerThreads`) — Blizzard rotates them
  across patches. Documented in `Overwatch2GSyncProfile.get_in_game_settings()`.

### 6.2 Experimental (Future Platforms) / Canary 29xxx live status

Updated 2026-05-26 after a live smoke run. The dev machine at that time was on
Windows Insider build 29595.1000 with
`release_branch="experimental_future_platforms"` and
`OsRelease.is_experimental_future_platform == True`. Windows still
reports `product_name="Windows 10 Home"` / `display_version="Dev"` on
this branch, so use `abso/utils/os_release.py` rather than display
strings for gating.

The 2026-05-21 scaffolding planted:

- `OsRelease.is_experimental_future_platform` (build >= 29000),
  `release_branch` label, and `_FUTURE_PLATFORMS_BUILD_FLOOR` constant
  in `abso/utils/os_release.py`. `to_dict()` includes the branch.
- `abso/settings/shared_audio.py` — detect-only handler for Shared
  Audio (BT LE Audio broadcast). Matches the xbox_mode / ai_agents
  pattern: probes candidate registry paths, returns
  `feature_present: False` when none match, refuses to apply, and
  reports `restore_guarantee = "none"`. Registered in the central
  handler registry.
- `ConfigurationAuditor.audit_all()` now emits a single info banner
  Issue (category `os_release`) when the OS is on the
  experimental/future-platforms branch, so audit output is explicitly
  caveat'd.
- `kb_checker.LAST_REVIEWED_UTC` bumped to 2026-05-21 with a comment
  noting the 29591.1000 review (no gaming-impacting regressions).

The 2026-05-24 HDR recovery pass adds:

- `abso/utils/display_reset.py`, a strategy-based display recovery
  helper.
- `refresh_display_pipeline(method="auto")` keeps the softer
  `SetDisplayConfig(SDC_APPLY | SDC_USE_DATABASE_CURRENT)` path. The
  documented `Ctrl+Win+Shift+B` graphics-driver reset shortcut via
  `SendInput` is manual-only because it can briefly blank secondary
  displays.
- Profile apply does not run automatic display recovery unless
  `ABSO_ENABLE_AUTO_DISPLAY_RECOVERY=1` is set; multi-monitor paths still
  suppress automatic recovery even under that opt-in.
- `WindowsSettingsHandler._set_hdr()` must prune known SDR-only active targets
  before calling `DisplayConfigSetDeviceInfo`, while preserving the fallback
  for targets whose capability could not be read. This avoids pointless CCD
  writes on mixed HDR/SDR monitor setups.
- WCG-only applies must preserve the live HDR active mode (`any_active`), not
  sticky per-monitor `Use HDR` intent (`any_enabled`). On mixed-monitor
  systems, stale user intent on an inactive/SDR target must not trigger an HDR
  enable/cycle.
- WCG-only applies must not write `HDREnabled` or call HDR SET as an implicit
  side effect. Only profiles with an explicit `hdr` setting may mutate HDR
  registry intent or live HDR state.
- WCG-only applies should return after their AdvancedColorEnabled registry
  write and avoid HDR refresh sleeps/final HDR probes when no explicit HDR
  management was requested.
- WCG-only applies should reuse HDR state from `detect()` and pass it through
  to the refresh helper. Do not add a second live HDR probe just to preserve
  current HDR state.
- WCG-only no-op detection should ignore sticky HDR intent entirely. If
  `advanced_color` already matches and no explicit `hdr` setting was supplied,
  do not enumerate MonitorDataStore just because `hdr` and `hdr_active`
  disagree.
- `WindowsSettingsHandler.apply()` should keep using narrow pre-apply
  detection. Non-display registry settings must not run the full
  `detect()` path and should not enumerate refresh rate, HDR, WCG, or
  SDR-white state just to decide whether a registry toggle already matches.
- `WindowsSettingsHandler.verify_active()` should keep the same narrow
  detection shape. It should verify known values for Game Mode, Game Bar, Game
  DVR, windowed optimizations, VRR optimize, explicit refresh rate, and max
  refresh rate, but undetectable registry/readback values should stay
  non-blocking unless the setting already had stricter semantics. Avoid turning
  unknown readback into a full display-sensitive reapply.
- DirectXUserGlobalSettings readback should stay grouped in the hot paths.
  `detect()`, pre-apply detection, and verification should parse Auto HDR,
  windowed optimizations, and VRR optimize from one registry query; keep
  single-flag getters only as compatibility helpers.
- DirectXUserGlobalSettings parsing should stay exact-token based. Do not use
  substring checks that can treat malformed values such as `AutoHDREnable=10`
  as enabled; duplicate tracked values should resolve deterministically.
- DirectXUserGlobalSettings writes should stay deterministic. Preserve unknown
  tokens, but normalize all ABSO-owned tracked flags (`AutoHDREnable`,
  `SwapEffectUpgradeEnable`, and `VRROptimizeEnable`) to one canonical token
  each on every write. Malformed tracked values are ignored, duplicate tracked
  values resolve by last valid `0`/`1`, and the requested target override is
  applied last. Do not append duplicate/conflicting tracked flags.
- Refresh-rate profile settings should no-op before entering the display mode
  setter when the current rate already equals the target or is already at the
  enumerated maximum.
- The synthesized Windows-key events mark `VK_LWIN` with
  `KEYEVENTF_EXTENDEDKEY`; do not regress to `keybd_event` or omit
  the extended-key flag.
- `ChangeDisplaySettingsExW(..., CDS_RESET, ...)` is retained as a
  manual diagnostic method, not the default.
- `abso reset-display --method driver-hotkey --json` succeeded on the
  live 29595 machine with two hotkey chords sent.

**What still needs follow-up on the experimental branch:**

1. **Elevated apply/verify/restore plus human color check** - the
   current non-admin shell can run `detect`, `bios`, `backup-create`,
   `health`, `verify`, and `reset-display`, but `audit` / `apply`
   require elevation. To prove the HDR pipeline fix end to end, run
   the §3 sequence from an elevated shell against at least
   `overwatch2-gsync-hdr` and `slippi-melee-universal-hdr`, then have
   the user confirm the primary display stays vivid after each apply
   without a manual hotkey press.
2. **Shared Audio key surface** — the candidate paths in
   `_SHARED_AUDIO_HKCU_CANDIDATES` / `_SHARED_AUDIO_HKLM_CANDIDATES`
   are guesses. After enabling Shared Audio via Quick Settings on the
   live machine, dump the BT-related registry to find the real keys,
   then update the candidate list (or wire the apply path).
3. **NPU detection** — build 29591+ added NPU columns to Task
   Manager. `HardwareDetector` does not currently surface NPU
   presence. Out of scope on non-NPU hardware, but record as a future
   detection extension for Copilot+ machines.
4. **Xbox Mode / AI Agents revalidation** — these handlers fire on
   any build >= 26100.8457, which 29595 satisfies. Their candidate
   registry paths were chosen on the 25H2 branch and may need
   additional candidates once the experimental branch reveals where
   the keys actually live.
5. **Update channel awareness** — the auditor banner is currently
   purely informational. If the user wants stricter behavior (e.g.
   refusing to apply latency-critical profiles on an experimental
   build), gate that in `core/capabilities.py` next to the existing
   `min_os_build` / `validated_os_build` checks rather than in the
   auditor.

**Out of scope here:**

- Forking profile metadata for the future-platforms branch. The
  current `min_os_build` check on profiles still works — they just
  apply to a build the user accepts is pre-release. Do not split the
  profile catalog by branch.
- Renaming `is_25h2_or_newer`. The semantic is still correct
  (`build >= 26200` — 29595 satisfies it) and callers use it as a
  lower bound.

### Closed by recent work (do not re-open)

- ~~PR-09 in `REMEDIATION_ROADMAP.md` — make criticality data-driven~~
  → done via `is_critical_verify` property + `ComplianceEngine`
  lazy resolution
- ~~PR-03 capability metadata~~ → partially done via
  `is_critical_verify` and the handler registry's `HandlerEntry`
- ~~Stale `_get_handlers()` / `_get_backup_handlers()` duplication~~
  → unified via `abso/core/handler_registry.py`
- ~~Hardcoded class-name strings in `ComplianceEngine.CRITICAL_VERIFY_HANDLERS`~~
  → replaced with property + lazy resolution
- ~~`bios_detector.py` private registry helpers duplicating
  `utils/registry.py`~~ → bios_detector now wraps the utility

### Deferred for stated reasons

- **`restore_guarantee` enum** — strings are serialized into backup
  manifest JSON. Converting to enum without breaking the on-disk
  format adds compat shim complexity that exceeds the polish win.
  Keep as strings.
- **CCD API struct dedup between `detector.py` and `settings/windows.py`**
  — same Win32 API → byte-identical layouts at runtime. Source-only
  duplication; touching the 2K-line `settings/windows.py` for cosmetic
  cleanup is poor risk/reward.

---

## 7. Release gates

Every PR touching handler, profile, tray, or GUI behavior must pass:

```bash
python -m pytest -q           # full unit suite (1600+ tests)
# (npm run lint / build and cargo check only if you touched GUI)
```

And for any user-visible change, **manually run on this machine**:

```bash
python -m abso detect            # confirm hardware detection still clean
python -m abso audit             # elevated shell required
python -m abso bios              # confirm BIOS recommendations sane
python -m abso backup-create     # confirm backup pipeline accepts the handlers
```

For state-mutating changes, run the full apply/verify/restore loop described in
§3 unless the current briefing or user instruction narrows the safe verification
surface. For the active monitor-flicker work, prefer read-only verify and
targeted `apply-pending`; do not use display resets or full profile applies as
routine verification.

The quality-string scan and forbidden-claims rules from
`docs/QUALITY_RUBRIC.md` still apply. Read that file before adding any
new claim to CLI / tray / GUI surfaces.

---

## 8. Commit and push discipline

- One themed commit per logical change. Don't bundle the May 2026
  cumulative adaptation with a refactor.
- Co-author trailer on every commit:
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
  (or the current model).
- The user explicitly authorizes `git push` for ABSO work. Other
  destructive git operations (`reset --hard`, `push --force`, branch
  deletion) still require explicit per-request approval.
- `abso/tray/profile-catalog-cache.json` is a shipped tray startup cache and
  belongs in the PyInstaller/deploy payload. Commit it only when profile
  catalog content intentionally changed; do not commit timestamp-only
  rewrites.

---

## 9. When something breaks live

Unit tests pass + live CLI breaks is the most common failure mode
because unit tests can't catch console-codepage issues, real WMI/
registry edge cases, or backup-manifest schema drift.

When this happens:

1. Reproduce on the live machine with `python -m abso <command>`.
2. Capture the failing output verbatim.
3. Fix the root cause; don't add a `try: except: pass` shim.
4. Add a unit test if the failure mode can be characterized with
   mocks. If it can only be caught by live invocation, document
   that in `docs/QUALITY_RUBRIC.md`'s release gates.
5. Re-run the full unit suite and the relevant live smoke commands
   from §7.

---

## 10. Hand-off template (for future agents)

When you finish a meaningful session and want to leave a clean state for the
next agent, update `docs/CURRENT_AGENT_BRIEFING.md` for live-machine state and
update this file only for durable process or architecture changes. Prefer that
over creating a new `docs/AGENT_HANDOFF_<date>.md`. The dated handoffs always
go stale and the project has accumulated a graveyard of them in `docs/archive/`.

Update §6 (Backlog) to reflect what's still open vs newly closed. If
you introduced a pattern that future agents should follow, add a §5.x
entry describing it. If you found a stale doc, fix it or archive it.

`CURRENT_AGENT_BRIEFING.md` is the version of "what's true now" for the live
machine. This protocol document is the durable workflow and architecture guide.
Keep both current for their scopes.
