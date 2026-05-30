# Agent Start Here

> **Freshly cloned onto a new PC? Read `docs/NEW_MACHINE_SETUP.md` FIRST.**
> The live-state docs below (this file's "Current Live-PC Constraint" section and
> `docs/CURRENT_AGENT_BRIEFING.md`) describe one specific machine that was
> mid-debug on Overwatch 2 monitor flicker. On a fresh clone, nothing is deployed
> or applied yet — re-establish this machine's state before trusting any
> live-state claim, and do not assume the live-PC mutation exception transfers.

This repository is usually edited by agents that arrive with no prior session
context. Read these files before making behavior changes:

1. `docs/NEW_MACHINE_SETUP.md` - fresh-clone / new-PC onboarding. What ABSO is,
   how to set up the dev environment, how to establish this machine's real state,
   and why the live-state docs may describe a different box.
2. `docs/CURRENT_AGENT_BRIEFING.md` - live truth for the machine it was last
   updated on, including active profile, installed build, monitor-flicker state,
   deploy evidence, and the immediate safe next action. Re-verify before trusting.
3. `docs/AGENT_PROTOCOL.md` - durable workflow, architecture patterns, live-PC
   testing policy, and open backlog.
4. `README.md` and `docs/INDEX.md` - current product surface and documentation
   map.
5. `docs/TROUBLESHOOTING.md` - user-facing runtime guidance, especially for
   secondary-monitor black flashes.

`docs/archive/` is historical. Do not use archived handoffs or deprecated
snapshots as current state unless the active briefing explicitly tells you to.

## Current Live-PC Constraint

As of 2026-05-30, this PC is on `overwatch2-gsync-hdr-capture` with
`GraphicsSettingsHandler.mpo_disabled` reboot-gated by a local mixed-refresh
stability override. The active topology currently detects a 2560x1440 300 Hz
VRR-capable primary plus a 2560x1440 59.95 Hz secondary, so ABSO's expected
static VRR cap for Overwatch is still `297` (`primary refresh - 3`). NVIDIA
Reflex may dynamically pace the runtime FPS lower; do not replace the
persisted cap with a Reflex-observed value such as `276`.

The Overwatch 2 G-SYNC HDR profiles now intentionally share the same optimized
borderless/windowed VRR display path. `overwatch2-gsync-hdr` is the
overlay-free lane and should still stop capture/overlay processes;
`overwatch2-gsync-hdr-capture` keeps those processes alive. Do not treat
windowed/borderless OW2 mode as drift for these G-SYNC HDR profiles. Do not run
full profile apply, live display reset, HDR off/on cycling, DWM restart, or the
graphics driver hotkey just because the monitor flickers unless the user
explicitly asks.

Safe evidence commands:

```powershell
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" display-diagnostics --json
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" state --json --verify
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" health --json
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" verify overwatch2-gsync-hdr --json
```

Expected current `verify overwatch2-gsync-hdr --json` behavior after deploy:
the OW2 display-mode keys should target borderless/windowed fullscreen and
`frame_rate_cap` should be `297` target/current. Any remaining MPO warning is
the PC-local reboot-gated mitigation, not an OW2 FPS-cap problem.

## Deploy And Verify

Use the deploy helper instead of hand-copying installed runtime files:

```powershell
.\.venv\Scripts\python.exe build.py deploy
.\.venv\Scripts\python.exe build.py deploy-existing
```

After code changes, run focused tests for the touched area, then `ruff check .`.
Run the full pytest suite before a deploy when behavior changed. Avoid live
display/profile transaction tests for the flicker/FPS investigation unless the
user explicitly authorizes them; prefer read-only verify/health diagnostics.

## Worktree Rule

This worktree may contain many uncommitted changes from prior agent sessions.
Do not revert files wholesale. If a local change is unrelated, leave it alone.
If it affects your task, understand it and build on it.
