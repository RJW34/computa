# Cutting a Release

How to publish an ABSO build friends can install without cloning the repo.

## 1. Version bump

Update `abso/__version__.py` (`__version__` and `__version_tuple__`). The
`update-check` command compares release tags against this string, so tag the
release `v<same version>`.

## 2. Build the standalone CLI

From a clean tree on the release commit:

```powershell
.\.venv\Scripts\python.exe build.py cli
```

This produces `dist\computa.exe` — a self-contained executable (bundled Python,
tray scripts, theme packs, and manifests). Verify it on the build machine:

```powershell
.\dist\computa\computa.exe --version
.\dist\computa\computa.exe profiles
```

Note: `dist\computa\` is a one-dir build — `computa.exe` needs the
`_internal\` folder beside it. `dist\computa-portable.exe` is the
single-file portable build for users who want one exe.

Note: the bundle includes every theme folder present under
`abso/tray/themes/` at build time. Build releases from a **clean clone** so
personal/local themes never ship.

## 3. Publish on GitHub

```powershell
git tag v1.2.0
git push origin master --tags
python build.py installer   # dist\computa-setup.exe (needs Inno Setup 6:
                            #   winget install -e --id JRSoftware.InnoSetup --scope user)
gh release create v1.2.0 dist\computa-setup.exe dist\computa-portable.exe `
    scripts\install.ps1 `
    --title "ABSO v1.2.0" --notes "Highlights..."
```

Release assets:

- `computa-setup.exe` — **the** installer: standard Windows wizard
  (per-user, Apps & Features entry, Start Menu shortcuts, optional PATH),
  finish page launches the first-run setup window
- `computa.exe` — the standalone CLI/tray runtime (portable path)
- `install.ps1` — portable console installer for power users

## 4. What users do

1. Download `computa-setup.exe` and double-click it.
2. A familiar installer wizard runs (no console, no admin prompt for the
   install itself), then offers "Run first-time setup now".
3. The first-run window (one UAC prompt) shows what was found on their PC
   and what setup may do (safety snapshot, tray autostart, optional bad-KB
   removal), asks a games/display survey that tunes the tray's profile list
   to what they actually play (via tray-config `hiddenProfiles`), then
   streams progress. Nothing applies a profile — that happens later, from
   the tray.
4. Uninstalling from Apps & Features offers to restore the setup-time
   baseline (`computa uninstall --yes` runs before file removal).

`computa update-check` tells them when a newer release exists (set
`ABSO_UPDATE_REPO` for forks). Updating is manual: download the new exe and
re-run `install.ps1`.

## Never do this

- **Never zip your working folder as a "release".** Gitignored personal data
  lives there: `backups/` (real system snapshots), `abso.yaml`,
  `workflow.yaml`, personal theme packs, machine-state docs. Release only the
  built `computa.exe` + `scripts/install.ps1` + `scripts/Install computa.cmd`.
- Never build a release from a tree with uncommitted changes — `build.py`
  bundles whatever is on disk.
