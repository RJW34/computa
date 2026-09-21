# Manual setup and restore upgrades, 2026-09-21

The OW2 settings session exposed two gaps: the backend could report managed
settings active while the tray and desktop app hid the unmet manual Reflex
step, and a later profile switch could restore an old full OW2 settings file
over the user's newer graphics, HDR calibration, or audio choices.

## Changes

- Preserve manual verification steps through no-op apply, reapply, targeted
  pending repair, compact health, and plain CLI output. Unknown and unmet
  steps remain visible; a positively satisfied readback clears them. Managed
  `all_active` and apply/reboot routing retain their existing meaning.
- Show manual reminders with current/expected values and available instructions
  in the tray, Quick Panel, desktop home/status, and apply completion. Manual
  differences never trigger reapply. OW2 Reflex guidance names the observed
  Options > Video > General > NVIDIA Reflex path and remains visible when the
  saved config or Reflex value is unavailable.
- Refresh stale tray verification asynchronously on menu opening, with a
  30-second freshness window, retry cooldown, and coalesced requests. There is
  no new idle polling loop. A stale same-profile click checks before choosing
  a repair; Quick Panel rebuilds only when displayed verification changes.
  The desktop home page provides a read-only Verify profile button, rejecting
  an older response if a newer profile/readback has replaced its source state.
- Restore only owned OW2 render keys into an existing file, including restoring
  a baseline key's absence. Preserve other live keys and sections, including
  Reflex, shadows/reflections, controls, audio, and HDR calibration. Validate
  the baseline before writes and avoid an identical write. Missing-file
  recovery retains its previous behavior, excluding stale Reflex.
- Keep application restart notices separate from Windows reboot gates. The
  OBS handler's restart message now uses informational notices instead of
  promoting `requires_restart` to a Windows reboot requirement.
- Separate Effects Low from the manual Shadow Off/Low preference, add manual
  Local Reflections and Damage FX guidance, and remove unmeasured shadow
  performance claims. Correct the tray fallback's stale OW2 Reflex Off label
  and the GUI's obsolete shader-cache size type.

## Saved ceiling versus runtime FPS

OW2 G-SYNC guidance now explains the persisted refresh-minus-three cap as a
fallback ceiling. On the current 300 Hz setup this is 297, while Reflex can
pace lower. If runtime pacing is 276, the higher 297 ceiling is not limiting
that frame rate; retaining it has no demonstrated extra performance benefit
while the lower limiter is active. Neither value promises gameplay FPS.
No cap, synchronization policy, or live setting was changed by this upgrade.

[NVIDIA's latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)
documents automatic below-refresh pacing with G-SYNC, VSync, and Reflex. It
does not establish a universal 276 FPS target or measured optimal settings for
this machine. The legacy explicit `ow2_reflex_gsync` policy test was relabeled
as compatibility coverage; shipped OW2 profiles retain `refresh_minus_3`.

## Validation and limits

Focused tests cover manual true/false/unknown values, preserved no-op behavior,
fresh targeted repair results, stale result rejection, cooldown/coalescing,
Quick Panel refresh and clearing, app-versus-Windows restart handling, and
managed-key restoration with calibration/graphics/audio preservation.

The desktop preview used the real Home, StatusBar, and manual-list components
with a strict state-only mock. An unmet Reflex reminder appeared, then cleared
after clicking Verify profile; no mutation command was permitted. Layout was
inspected at 1280 and 800 pixels wide. Evidence is under `output/playwright/`.
Temporary preview files and its browser/server were removed or stopped.

Final test logs are under `reports/upgrades/2026-09-21-manual-setup/`.
The full Python run passed 2,941 tests with 13 integration tests deselected;
its sole failure was the old guidance snapshot. Before regenerating it, all
44 profiles were compared: only `in_game_settings` in the six OW2 lanes differed,
and all actual handler/settings maps were identical. Both snapshot tests then
passed, as did the 363-test OW2/profile/cache/snapshot focused run. The existing
pytest asyncio configuration warning remains. GUI tests passed 8/8, GUI lint
and production build passed, `cargo check --locked` passed, and repository Ruff
and diff checks passed. The GUI build retains the existing Browserslist data
age notice.

No live profile apply, display reset, game restart, or gameplay test was run.
These are correctness and responsiveness improvements; no game FPS, latency,
tray idle CPU, or memory improvement is claimed without measurements.
The installed runtime was not replaced in this follow-up; OW2 remained running.
