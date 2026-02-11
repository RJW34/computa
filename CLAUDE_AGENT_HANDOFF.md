# Claude Code Agent Handoff

## Purpose
This file is a concise handoff for another CLI agent (including Claude Code) to understand what was done in the latest Codex audit/assist pass and what was committed.

## Repository State at Time of Handoff
- Branch: `fix/slippi-rivals-profile-accuracy`
- Remote: `origin` -> `https://github.com/RJW34/A.B.S.O..git`
- Worktree before this handoff already contained many modified and untracked files (feature work in progress).

## What Codex Changed In This Turn
- Added this document: `CLAUDE_AGENT_HANDOFF.md`
- Did **not** modify source logic during this specific turn.
- At user request, committed and pushed **all currently uncommitted changes** in the repo (including pre-existing user changes) in one commit.

## Audit Findings Previously Reported (No Code Changes Applied Yet)
1. Backup/restore handler coverage mismatch:
   - `abso/core/backup.py` does not include all handlers used by active profiles (e.g. `ProcessPriorityHandler`, `CNMSettingsHandler`, `OBSSettingsHandler`, `Rivals2ConfigHandler`, `DolphinConfigHandler`, `NvidiaNotificationHandler`).
2. `ProcessPriorityHandler.restore()` truthiness bug:
   - May re-apply empty settings instead of removing IFEO keys.
3. `NetworkSettingsHandler.restore()` incomplete:
   - Restores interface registry values but not `tcp_global` settings that are backed up/applied.
4. Tray applies can be surfaced as success on partial failure:
   - `abso/tray/ABSO-Tray.ps1` treats any applied settings as success in some partial-failure cases.
5. GUI/Tauri drift:
   - `gui/src-tauri/src/main.rs` and `gui/src/lib/api.ts` include outdated profile IDs/command usage compared to current CLI.

## Rivals 2 Symptom Context (from audit)
- User issue: online profile use sometimes corresponds with Rivals 2 tag/control profile seeming unset.
- `rivals2-online` profile does not include `Rivals2ConfigHandler` override in current profile class.
- `Rivals2ConfigHandler` only edits `GameUserSettings.ini` keys (`FullscreenMode`, `bUseVSync`, `bUseRawInput`), not `.sav` tag/control files.
- No direct code path was found in this repo that writes Rivals tag/control `.sav` data.

## Suggested Next Work Item
- Implement the restore/backup coverage and restore logic fixes above, then add regression tests for:
  - backup handler coverage expectations
  - `ProcessPriorityHandler.restore()` empty-state behavior
  - `NetworkSettingsHandler.restore()` tcp global restoration
  - tray apply success/failure semantics.
