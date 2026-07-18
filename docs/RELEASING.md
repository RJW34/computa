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
    --title "ABSO v1.2.0" --notes "Highlights..."
```

Release assets:

- `computa.exe` — the standalone CLI/tray runtime
- `install.ps1` — end-user installer (copies the exe to LocalAppData, adds it
  to the user PATH, launches `computa setup` elevated)

## 4. What users do

1. Download `computa.exe` and `install.ps1` into the same folder.
2. `powershell -ExecutionPolicy Bypass -File .\install.ps1`
3. Follow the setup wizard (hardware detection → baseline backup → profile
   selection → tray autostart).

`computa update-check` tells them when a newer release exists (set
`ABSO_UPDATE_REPO` for forks). Updating is manual: download the new exe and
re-run `install.ps1`.

## Never do this

- **Never zip your working folder as a "release".** Gitignored personal data
  lives there: `backups/` (real system snapshots), `abso.yaml`,
  `workflow.yaml`, personal theme packs, machine-state docs. Release only the
  built `computa.exe` + `scripts/install.ps1`.
- Never build a release from a tree with uncommitted changes — `build.py`
  bundles whatever is on disk.
