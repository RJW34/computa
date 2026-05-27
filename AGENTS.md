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

As of 2026-05-26, this PC is debugging secondary-monitor black flashes on the
active `overwatch2-gsync-hdr-capture` profile. The local profile override has
already written the MPO-disable registry target, and verification reports the
profile active with `GraphicsSettingsHandler` reboot-pending.

The remaining commit step is a normal Windows reboot. Do not run full profile
apply, live display reset, HDR off/on cycling, DWM restart, or the graphics
driver hotkey just because the monitor flickers unless the user explicitly asks.

Safe evidence commands:

```powershell
%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe display-diagnostics --json
%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe state --json --verify
%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe health --json
%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\abso.exe reapply --json
```

Expected current `reapply --json` behavior for the active profile is a no-op:
`changed: false`, `changed_settings: []`, and `transaction: null`.

## Deploy And Verify

Use the deploy helper instead of hand-copying installed runtime files:

```powershell
.\.venv\Scripts\python.exe build.py deploy
.\.venv\Scripts\python.exe build.py deploy-existing
```

After code changes, run focused tests for the touched area, then `ruff check .`.
Run the full pytest suite before a deploy when behavior changed. Avoid live
display/profile transaction tests while the current flicker investigation is
reboot-gated unless the user explicitly authorizes them.

## Worktree Rule

This worktree may contain many uncommitted changes from prior agent sessions.
Do not revert files wholesale. If a local change is unrelated, leave it alone.
If it affects your task, understand it and build on it.
