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

As of 2026-05-29, this PC is on the strict Overwatch 2 profile
`overwatch2-gsync-hdr` with no reboot pending. The active display path is a
single 2560x1440 300 Hz VRR-capable display, so ABSO's expected static VRR cap
for Overwatch is `297` (`refresh - 3`). NVIDIA Reflex may dynamically pace the
runtime FPS lower; do not replace the persisted cap with a Reflex-observed
value such as `276`.

Current verification is not fully clean only because `OW2ConfigHandler` sees
display-mode drift: OW2 is currently windowed/borderless while the strict
profile expects exclusive fullscreen. The FPS cap verifies as `297`
target/current. Do not run full profile apply, live display reset, HDR off/on
cycling, DWM restart, or the graphics driver hotkey just because the monitor
flickers unless the user explicitly asks.

Safe evidence commands:

```powershell
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" display-diagnostics --json
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" state --json --verify
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" health --json
& "$env:LOCALAPPDATA\AdaptiveBattleStationOptimizer\abso.exe" verify overwatch2-gsync-hdr --json
```

Expected current `verify overwatch2-gsync-hdr --json` behavior: all handlers
active except `OW2ConfigHandler` display-mode keys; `frame_rate_cap` should be
`297` target/current.

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
