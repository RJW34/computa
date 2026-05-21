# A.B.S.O. Agent Protocol

**Start here.** This is the single forward-looking document for any agent
(Claude Code, Codex, or otherwise) picking up work on this project. It
replaces the dated per-agent handoffs that previously sat in `docs/` and
codifies the practices that have stuck after multiple remediation passes.

When a procedure or convention here disagrees with anything in an
archived handoff (`docs/archive/...`), this document wins.

---

## 1. Reading order

1. **This file** (`docs/AGENT_PROTOCOL.md`)
2. **`README.md`** — current product surface and what built-in profiles
   actually do (truth-passed; do not let it drift)
3. **`CLAUDE.md`** — project-rooted Claude Code instructions (kept short
   on purpose; it points back here)
4. **`docs/QUALITY_RUBRIC.md`** — the shipping bar and forbidden claims
5. **`docs/REMEDIATION_ROADMAP.md`** — the long-running grade lift plan;
   completed PRs are marked inline
6. **`docs/API.md`** — module-level reference for the core/handler API
7. **`docs/TROUBLESHOOTING.md`** — runtime issues, mostly user-facing

Skip the docs in `docs/archive/` unless you specifically need history
context. Those are frozen handoffs from past agents (HERMES, Opus 4.7
xhigh, earlier Claude generations) and reference machine names, dates,
and PR slices that have since changed.

---

## 2. Machine roles (current)

The roadmap historically described an "implementation host = MAGNETON,
validation host = primary gaming PC" split. **That naming is stale.**
The current host this project lives on is `MIRAIDON` (Windows 11 25H2
Home, build 26200.8457 at time of writing, RTX 4070, MSI Aegis R2 14th).

For practical purposes:

| Role | Machine | Allowed |
|---|---|---|
| Implementation | `MIRAIDON` | structural code changes, refactors, tests, tray/GUI work, CI work |
| Validation | `MIRAIDON` (same box) | live registry/WMI probes, CLI smoke runs, apply/verify/restore round trips against a real profile |
| Release signoff | `MIRAIDON` | benchmark artifacts, "optimal" claim support |

Because the same machine wears all three hats, **discipline replaces
geography**:

- Do not upgrade a setting's evidence to `measured` without an actual
  benchmark artifact in `reports/benchmarks/`.
- Do not call a profile `optimal` without recorded before/after frame
  data on this hardware.
- Treat "no validation host" as the constraint, not the excuse.

---

## 3. Live-PC test policy

The user has explicitly granted **read-only and state-mutating** access
to this machine for ABSO work specifically. This is an exception to the
broader "never run system commands on live PC without permission" rule
that lives in the user's auto-memory.

What's pre-authorized:

- Read-only PowerShell / `winreg` probes (registry, WMI, `Get-HotFix`,
  Secure Boot servicing keys, etc.)
- `python -m abso detect|audit|bios|profiles|state|backups|health|games|
  config|profile-aliases|report` — all read-only CLI surfaces
- `python -m abso backup-create` — pure capture, no system mutation
- `python -m abso apply <profile>` followed by `python -m abso restore latest`
  — provided you immediately restore afterward

What still needs explicit approval:

- Long-running `apply` without a planned `restore`
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

This sequence has been validated end-to-end on `MIRAIDON` — it does not
leave the machine in a broken state.

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

---

## 6. Backlog: what's actually open right now

Updated 2026-05-21 after the launch-time process janitor +
Deadlock + HDR-Slippi merge (commit `2d7005c`) and the OW2 latency-
stack audit done the same evening.

### Real open work

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

### 6.1 OW2 / Reflex latency-stack closure (audit 2026-05-21)

Standing audit against `overwatch2-gsync-hdr` after the launch-time
process janitor landed. These are the knobs ABSO still does not tune
that would measurably move click-to-photon latency on a competitive
RTX 4070 / 14th-gen / 240 Hz OLED rig. Ordered by impact. Most of
these benefit every Reflex shooter profile (Marvel Rivals, Deadlock,
Fortnite, Rivals 2 G-SYNC), not just OW2 — wire them through
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

### 6.2 Experimental (Future Platforms) / Canary 29xxx scaffolding (planted 2026-05-21)

The user is installing Win11 Insider Preview build 29591.1000 on the
Canary 29xxx / Experimental (Future Platforms) channel — the
pre-27H2 (Strontium) branch. ABSO's existing detection paths target
the 25H2 Germanium track and have only best-effort awareness of the
new branch. To keep the tool functional after reboot, this commit
plants:

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

**What still needs follow-up once the user reboots into 29591.1000:**

1. **Live smoke pass** — run `python -m abso detect`, `python -m abso
   audit`, `python -m abso bios`, `python -m abso backup-create` on
   the experimental build. Confirm the new banner fires, no handler
   crashes on the new build number, and the backup manifest still
   accepts the SharedAudio handler.
2. **Shared Audio key surface** — the candidate paths in
   `_SHARED_AUDIO_HKCU_CANDIDATES` / `_SHARED_AUDIO_HKLM_CANDIDATES`
   are guesses. After enabling Shared Audio via Quick Settings on the
   live machine, dump the BT-related registry to find the real keys,
   then update the candidate list (or wire the apply path).
3. **NPU detection** — build 29591.1000 added NPU columns to Task
   Manager. `HardwareDetector` does not currently surface NPU
   presence. Out of scope for the current rig (RTX 4070 / 14th-gen
   with no NPU), but record as a future detection extension if the
   user moves to a Copilot+ machine.
4. **Xbox Mode / AI Agents revalidation** — these handlers fire on
   any build >= 26100.8457, which 29591 satisfies. Their candidate
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
  (`build >= 26200` — 29591 satisfies it) and callers use it as a
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
python -m pytest -q           # full unit suite (1340+ tests)
# (npm run lint / build and cargo check only if you touched GUI)
```

And for any user-visible change, **manually run on this machine**:

```bash
python -m abso detect            # confirm hardware detection still clean
python -m abso audit             # confirm new audit findings reasonable
python -m abso bios              # confirm BIOS recommendations sane
python -m abso backup-create     # confirm backup pipeline accepts the handlers
```

For state-mutating changes, run the full apply/verify/restore loop
described in §3.

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
- Never include `abso/tray/profile-catalog-cache.json` in a commit
  unless the change is intentional — it's a regenerated cache file
  that almost always shows up as a pre-existing modification.

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

When you finish a meaningful session and want to leave a clean state
for the next agent, prefer **updating this file** over creating a new
`docs/AGENT_HANDOFF_<date>.md`. The dated handoffs always go stale and
the project has accumulated a graveyard of them in `docs/archive/`.

Update §6 (Backlog) to reflect what's still open vs newly closed. If
you introduced a pattern that future agents should follow, add a §5.x
entry describing it. If you found a stale doc, fix it or archive it.

This protocol document is the version of "what's true now" that future
agents read first. Keep it current.
