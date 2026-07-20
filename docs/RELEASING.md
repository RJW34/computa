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
.\dist\computa.exe --version
.\dist\computa.exe profiles
```

Note: the one-file bundle includes every theme folder present under
`abso/tray/themes/` at build time. Build releases from a **clean clone** so
personal/local themes never ship.

## 3. Publish on GitHub

```powershell
git tag v1.2.0
git push origin master --tags
gh release create v1.2.0 dist\computa.exe scripts\install.ps1 `
    "scripts\Install computa.cmd" `
    --title "ABSO v1.2.0" --notes "Highlights..."
```

Release assets:

- `computa.exe` — the standalone CLI/tray runtime
- `install.ps1` — the guided installer window (also has a `-Console`
  text-mode fallback for power users)
- `Install computa.cmd` — double-clickable shim that opens the installer
  window with no console

## 4. What users do

1. Download all three assets into the same folder.
2. Double-click `Install computa.cmd`.
3. A small setup window shows what was found on their PC and what setup may
   do (safety snapshot, tray autostart, PATH, optional bad-KB removal), asks
   a games/display survey that tunes the tray's profile list to what they
   actually play (via tray-config `hiddenProfiles`), then streams progress.
   Installing never applies a profile — that happens later, from the tray.

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
