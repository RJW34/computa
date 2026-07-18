# Local-Only Files

Some files are expected to exist on a configured machine but are deliberately
kept out of git, because they describe **one specific PC** — its monitor
controller, its peripheral software, its live agent-session state — or contain
media that cannot be redistributed. Inheriting them from someone else's
machine ranges from confusing to actively harmful (a stale `profile_overrides`
block silently wins over profile improvements on every apply).

| Path | What it is | Fresh-clone behavior |
|------|------------|----------------------|
| `abso.yaml` | This machine's config: DDC/CI controller override, protected peripheral processes, per-profile experiments | Absent — ABSO runs on built-in defaults; create one from `abso.yaml.example` or `abso config --init` |
| `workflow.yaml` | Owner's private multi-project orchestration manifest (Citadel ecosystem) | Absent — nothing in ABSO reads it |
| `abso/tray/themes/<name>/` (except `default/`) | Personal tray theme packs, possibly containing non-redistributable media | Absent — tray uses the self-contained `default` theme |
| `docs/CURRENT_AGENT_BRIEFING.md` | Live-machine state journal for coding agents (active profile, deploy status, monitor-flicker history) | Absent — see `docs/NEW_MACHINE_SETUP.md` |
| `docs/CODEX_HANDOFF_OW2_150FPS.md` | A machine-specific historical investigation | Absent |
| `docs/archive/` | Historical handoffs/plans containing machine specifics | Absent |
| `backups/`, `reports/`, `tools/`, `*.log`, `.abso_state.json` | Live system snapshots, generated reports, third-party binaries, runtime state | Created on demand |

## If you maintain one of these machines

`git merge` / `git checkout` of a branch that untracked one of these files
will **delete your local working copy** if the file is still tracked on the
branch you're standing on (a tracked→deleted transition removes the file from
the working tree). Before merging such a branch, copy your local versions
somewhere safe (outside the repo or into a gitignored folder), merge, then put
them back. After that one-time transition the files are gitignored and no git
operation touches them again.
