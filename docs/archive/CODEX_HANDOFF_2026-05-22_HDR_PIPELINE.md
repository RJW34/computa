# Codex Handoff — HDR Display Pipeline Recovery on Insider Build 29591
**Date:** 2026-05-22
**Author:** Claude Opus 4.7
**Machine:** Local PC (LG OLED primary `GSM784C…/0002` + Alienware AW3423DW secondary, RTX 5xxx-series NVIDIA driver)
**OS:** Windows Insider build **29591.1000** (Experimental Future Platforms, `release_branch="experimental_future_platforms"`)

---

## Codex Resolution Update (2026-05-24)

This handoff records the original Claude pause state. It is no longer
the current implementation state.

## Safety Update (2026-05-25)

The post-apply display recovery hook now suppresses automatic recovery by
default to avoid briefly blanking secondary displays. The ``driver-hotkey``
strategy also requires explicit user intent; ``auto`` no longer selects it on
Insider/future-platform builds. Manual recovery remains available through
``abso reset-display --method driver-hotkey`` and the tray ``Reset Display
Pipeline`` action. Advanced users can opt back into automatic recovery with
``ABSO_ENABLE_AUTO_DISPLAY_RECOVERY=1``.

Current code now resolves the SetDisplayConfig-only gap with
`abso/utils/display_reset.py`:

- `refresh_display_pipeline(method="auto")` uses the
  `SetDisplayConfig(SDC_APPLY | SDC_USE_DATABASE_CURRENT)` database
  reapply path. The synthesized `Ctrl+Win+Shift+B` graphics-driver reset
  is available only when explicitly requested.
- The hotkey path uses `SendInput`, not `keybd_event`, and marks
  `VK_LWIN` with `KEYEVENTF_EXTENDEDKEY`.
- `ChangeDisplaySettingsExW(..., CDS_RESET, ...)` remains available
  as a manual diagnostic method.
- `abso reset-display --method driver-hotkey --json` succeeded on the
  live 29595.1000 machine, sending two hotkey chords.
- Focused display-reset tests now cover database, mode-reset,
  driver-hotkey, partial-send failure, and auto-strategy selection.

Remaining proof gap: the current shell is not elevated, so the full
HDR apply/verify/restore loop plus user-visible LG color confirmation
still needs to be run from an elevated shell. Do not read the "NOT
done" and "Unresolved Problem" sections below as current code state;
read them as historical evidence for why the driver-hotkey branch must
not be removed.

---

## Objective

Make ABSO's HDR-affecting profile applies (`overwatch2-gsync-hdr`, `slippi-melee-universal-hdr`, etc.) leave the desktop color pipeline in the **vivid** state the user expects on Windows Insider build 29591+, **without requiring the user to manually press `Ctrl+Win+Shift+B` after every apply**.

The user's empirical workflow today:
1. Apply HDR profile via ABSO tray → colors render washed-out on the LG OLED primary.
2. User manually presses `Ctrl+Win+Shift+B` twice (with several seconds between presses) → colors snap back to vivid.

We need step 2 to happen automatically (or be eliminated) on this Windows build.

---

## What's Already Been Done in This Session (DO NOT redo)

All changes are **committed to working tree only** (no commits yet). Run `git status` to confirm.

### Completed (verified, tests green: 1505 passing)

1. **Removed `nvcontainer.exe` from `ALWAYS_SAFE_LAUNCH_KILLSET`** in `abso/core/process_janitor.py`.
   - Root cause: every prior HDR apply killed nvcontainer via the launch_sweep, which caused NVIDIA driver re-init that reset per-display DVC to hardware minimum (0 = grayscale) ~5 seconds post-apply, AND accumulated cumulative state corruption across multiple apply cycles.
   - With nvcontainer protected, fresh applies no longer accumulate the damage.
   - Inline comment at `abso/core/process_janitor.py` lines 63–86 documents the full discovery.

2. **Profile audit + rebase** (vibrance, productivity split, deadlock HDR re-categorization):
   - `profile_bases.py` now exposes `SDR_WIDE_GAMUT_VIBRANCE = 45` and `NEUTRAL_VIBRANCE = 50` constants. All SDR profiles default to 45 (wide-gamut compensation), all HDR profiles override to 50 (HDR composition owns gamut).
   - `productivity` split into `productivity` (pure SDR / HDR OFF) + `productivity-hdr` (opt-in OLED HDR variant).
   - Deadlock HDR profile descriptions + in-game guidance updated: Valve has not shipped native HDR for Deadlock, so it's documented as SDR-in-HDR composition (settings unchanged, just clarifies intent).
   - Linter rule `COLOR_HDR_SRGB_CLAMP` documented with empirical rationale.
   - Snapshot golden + tray catalog cache refreshed.

3. **Created `abso/utils/display_reset.py`** — currently uses `SetDisplayConfig(SDC_APPLY | SDC_USE_DATABASE_CURRENT)` via `refresh_display_pipeline()`.
   - Earlier in the session this module used `keybd_event` to synthesize `Ctrl+Win+Shift+B`. That implementation had a real bug (missing `KEYEVENTF_EXTENDEDKEY` flag on `VK_LWIN`) and was replaced. Git history within the session shows both implementations — see the file for the current shape.

4. **Wired post-apply display refresh** in `abso/main.py`:
   - `_HDR_PIPELINE_KEYS` (around line 318) — set of handler/setting keys that may need display recovery.
   - `_profile_touches_hdr_pipeline(profile)` (around line 343) — detects whether the requested settings touch HDR.
   - `_run_post_apply_display_reset(profile_name, tx, result)` (around line 365) — now skips by default unless `ABSO_ENABLE_AUTO_DISPLAY_RECOVERY=1`; multi-monitor paths still skip under that opt-in.
   - Invoked in the apply flow around line 1106.
   - Surfaced in JSON output under `display_reset`; human-readable output is only shown when recovery actually fires or errors.

5. **Added `abso reset-display` CLI command** + **tray menu item** ("Reset Display Pipeline" under Actions) for manual recovery.

6. **Unit tests** for `display_reset` in `tests/test_utils/test_display_reset.py`; apply-level tests cover the manual-by-default and multi-monitor suppression guards.

### Historical NOT done (pause-reason for this handoff)

The post-apply auto-refresh (currently `SetDisplayConfig`) **does not actually restore vivid colors on build 29591**. Verified empirically on the live machine — user looked at the LG after the auto-refresh fired and reported "still washed".

---

## The Original Unresolved Problem

**`SetDisplayConfig(SDC_APPLY | SDC_USE_DATABASE_CURRENT)` is insufficient on build 29591 to clear the stale color pipeline state that this build produces after an HDR-touching apply.**

### What was tried in this session and rejected

| Approach | Result | Why insufficient |
|---|---|---|
| Synthesized `Ctrl+Win+Shift+B` via `keybd_event` | Black flash visible, colors stayed washed | Either missing `KEYEVENTF_EXTENDEDKEY` flag on `VK_LWIN` made the Win key not register (combo became `Ctrl+Shift+B`), OR timing relative to apply state was wrong (DWM rebuilt mid-transition state). NOT verified which. |
| `SetDisplayConfig(SDC_APPLY \| SDC_USE_DATABASE_CURRENT)` | API returns status 0, no visible flash, colors stayed washed | This API only nudges DWM to re-read the database — it does NOT tear down/rebuild the pipeline the way `Ctrl+Win+Shift+B` does. |
| Manual `Ctrl+Win+Shift+B` twice (user-physical) | Black flash twice, colors restored to vivid | This is the working baseline. Whatever the keyboard shortcut does internally is what we need to replicate. |

### Probable root cause (Claude's working hypothesis, NOT verified)

The `Ctrl+Win+Shift+B` shortcut is processed by a GPU/Win32k filter driver and triggers a kernel-side `DxgkResetDisplay` that fully tears down and rebuilds the display pipeline. **No documented user-mode Windows API exposes this same kernel call.** The closest API options:

- `SetDisplayConfig(SDC_APPLY | SDC_USE_DATABASE_CURRENT)` — soft re-read of DB, what we currently call. Insufficient.
- `ChangeDisplaySettingsEx(NULL, NULL, NULL, CDS_RESET, NULL)` — mode reset, untested in this session.
- `taskkill /F /IM dwm.exe` — kills DWM, Session Manager respawns it, forces full pipeline rebuild. **MOST LIKELY to work** but more disruptive (window state flicker, tray icon re-register).
- Synthesized `Ctrl+Win+Shift+B` with **correct `KEYEVENTF_EXTENDEDKEY` flag on `VK_LWIN`** — never tested with the corrected flag.

The user explicitly asked Claude to **stop guessing and not test on their machine** in the final exchange. Codex should determine the right approach objectively first.

### Why the cumulative state happens in the first place on 29591

The codebase already documents a related Win11 25H2 issue at `abso/settings/windows.py:1816` — on 25H2+, `SET_HDR_STATE` is asymmetric: the OFF leg is honored but the subsequent ON leg silently no-ops. The handler currently SKIPS the off-on cycle when live state already matches target (`skip_hdr_cycle = live_hdr_on == bool(target_hdr)`). **That skip means idempotent HDR applies do not refresh DWM** — which is fine on 25H2 but appears insufficient on 29591 because some OTHER state (probably ICC association or colorSelectionPolicy=USER write) leaves DWM with stale composition state that only a full pipeline rebuild clears.

---

## Files to Read First (in order)

1. `abso/utils/display_reset.py` — current refresh implementation.
2. `abso/main.py` lines 318–425 — `_HDR_PIPELINE_KEYS`, detection helper, `_run_post_apply_display_reset`.
3. `abso/main.py` around line 1106 — where it's invoked in the apply flow.
4. `abso/settings/windows.py` lines 1306–1326 (`_kick_display_config_database_reapply`) and 1777–1900 (`_set_advanced_color_with_refresh`, the asymmetric SET_HDR_STATE workaround). **Critical prior-art context.**
5. `abso/core/process_janitor.py` lines 63–86 — nvcontainer removal rationale.
6. Git history: `git show e19d18c -- abso/settings/windows.py` — the commit that introduced the 25H2 asymmetric-SET workaround. The commit message describes the prior discovery in detail.

---

## What Codex Should Determine and Implement

### Decision 1: What's the right Windows API to fully rebuild the display pipeline?

Research (not guess) whether any of these reliably trigger the same kernel-side reset as `Ctrl+Win+Shift+B` from user-mode on Win11 29591:
- `ChangeDisplaySettingsEx(NULL, NULL, NULL, CDS_RESET, NULL)`
- `DxgkResetDisplay` exposure via any documented user-mode path (unlikely but worth confirming).
- Killing `dwm.exe` and relying on Session Manager respawn — known-working but disruptive.
- The corrected synthesized `Ctrl+Win+Shift+B` (with proper `KEYEVENTF_EXTENDEDKEY` flag on `VK_LWIN`, see `winuser.h`).
- Wait-for-quiescence (poll `_get_hdr_state_summary().any_active == target` with timeout) THEN fire one of the above.
- Some combination (e.g., SetDisplayConfig + sleep + synthesized combo + sleep + SetDisplayConfig).

### Decision 2: Should the auto-refresh fire at all when no actual mutation happened?

Currently fires when ANY of `{hdr, auto_hdr, advanced_color, sdr_white_level_nits, disable_auto_color_management, icc_profile, dynamic_range}` is in the profile's requested settings — even if all values are already at target. Consider only firing when the handlers report actual state changes (would require WindowsSettingsHandler / GraphicsSettingsHandler / ColorProfileSettingsHandler to return a `state_mutated: bool` field).

### Decision 3: Build-version-aware behavior?

`abso/utils/os_release.py` already exposes `is_experimental_future_platform` (build >= 29000). If the right Win11 25H2 recovery (`SetDisplayConfig`) is insufficient on 29xxx, the post-apply hook should branch: do the soft kick on 25H2, and the harder recovery (`taskkill dwm.exe` or synthesized combo with correct flags or some sequence) on 29xxx.

### Decision 4: User notice when auto-recovery would be too disruptive

If the only working recovery is `taskkill dwm.exe`, that's invasive. ABSO could surface a clear post-apply notice ("Press Ctrl+Win+Shift+B to commit HDR pipeline — automatic recovery unsupported on Insider 29xxx") instead of doing it silently, and only auto-bounce on user opt-in via config.

---

## Live Machine State at Handoff

(captured after the last successful `abso apply overwatch2-gsync-hdr` in this session)

```
Profile: overwatch2-gsync-hdr (committed, transaction state=committed)
Primary monitor: MONITOR\GSM784C\{4d36e96e-…}\0002 (LG OLED)
ICC primary: None (native; matches OW2-HDR convention; correct per profile)
DVC primary: user 52 / internal 32 (matches NEUTRAL_VIBRANCE; correct)
HDR active: True
Advanced color (WCG): True
SDR white nits: 200.0
ACM (auto_color_management.global): False
launch_sweep: stopped=['lghub_updater.exe'] — nvcontainer NOT attempted ✓
display_reset (auto-fired): SetDisplayConfig status=0, elapsed 1.5s
USER PERCEPTION: LG OLED still rendering washed-out / desaturated.
USER WORKAROUND: manual Ctrl+Win+Shift+B ×2 restores vivid colors.
```

All ABSO-side state is correct. The gap is purely in the recovery mechanism after the apply.

---

## Test Procedure for Verifying a Recovery Fix

This procedure applies only if automatic recovery is intentionally re-enabled
with `ABSO_ENABLE_AUTO_DISPLAY_RECOVERY=1`. The current safe default is
manual-only recovery, so `display_reset.fired` should normally be false.

1. With the LG in "vivid" state (after manual `Ctrl+Win+Shift+B ×2`), run `python -m abso apply slippi-melee-universal-hdr --json` (any HDR profile works).
2. Apply must commit. With opt-in enabled on a single-monitor path, `display_reset.fired` should be True in the JSON. Without opt-in, expect `display_reset.skipped_reason == "auto_display_recovery_disabled"`.
3. **Critical**: ask the user to look at the LG. If it stays vivid without them touching the keyboard, the fix worked. If colors fall back to washed, the fix is insufficient.
4. Re-apply `overwatch2-gsync-hdr` — same verification.
5. Re-apply `slippi-melee-universal-hdr` (alternating). The damage we're fixing accumulates across multiple back-to-back apply cycles, so a single apply succeeding isn't enough — verify across 3-4 alternating applies.

---

## Test Suite

Currently green: **1505 passing**. Run with:
```
.venv/Scripts/python.exe -m pytest tests/ -q
```

New tests added in this session:
- `tests/test_utils/test_display_reset.py` (display recovery strategies)
- `tests/test_cli.py` apply tests for `auto_display_recovery_disabled` and multi-monitor suppression

Tests will need updating when the recovery mechanism changes.

---

## What NOT to do

- **Don't re-introduce `nvcontainer.exe` to the killset.** It causes both an immediate DVC=0 reset and cumulative driver state corruption (documented at `abso/core/process_janitor.py:63`).
- **Don't revert the `productivity` SDR split.** That was an explicit user-policy decision (productivity profile should not silently force HDR).
- **Don't change `digital_vibrance=45` for SDR profiles back to 50.** That's the documented `SDR_WIDE_GAMUT_VIBRANCE` policy.
- **Don't bypass the `COLOR_HDR_SRGB_CLAMP` lint rule** for slippi-melee-hdr / similar SDR-in-HDR profiles by adding back `icc_profile="srgb"`. Empirically `icc=native` looks LESS washed than `icc=srgb` on the reference LG OLED setup (verified earlier in this session).

---

## Audit Pointers

The user mentioned this issue may have been "stumbled across" in a prior session. Search history:
- `git log -p -S "skip_hdr_cycle"` — surfaces commit `e19d18c` (the Win11 25H2 asymmetric-SET workaround).
- `git log --grep "HDR" --oneline` — broader HDR-related commits.
- `grep -rn "MonitorDataStore" abso/ docs/` — related state-rebuild discussions.

If a prior session has a different angle on this same problem, that's the place to look.
