# Claude Agent Handoff (2026-02-11)

## Scope
This handoff documents a startup/tray reliability hardening pass plus an audit of Rivals of Aether 2 config side-effects.

## Audit Findings (Rivals 2 profile/reset concern)
- The codebase does **not** write to Rivals 2 save/profile identity files (no writes to `Saved\\SaveGames`, tag/profile blobs, or control profile files were found).
- The only Rivals-specific file writer is `abso/settings/rivals2_config.py`, and it edits `GameUserSettings.ini` keys only:
  - `FullscreenMode`
  - `bUseVSync`
  - `bUseRawInput`
- `rivals2-online` does **not** include `Rivals2ConfigHandler`, so online profile application does not touch `GameUserSettings.ini` from this handler path.
- Added regression tests to lock this behavior in place.

## Code Changes
- Startup status plumbing and CLI:
  - `abso/main.py`
  - `abso/tray/__init__.py`
- Startup installer rework and reliability:
  - `abso/tray/Install-Startup.ps1`
  - Added `-Status -Json` support and richer state reporting.
  - Improved install fallback logic when scheduled task update is denied but an existing task is present.
  - Startup shortcut (fallback mode) now targets startup launcher script instead of direct VBS.
- New startup launcher:
  - `abso/tray/ABSO-StartupLaunch.ps1`
  - Waits for Explorer shell, then launches tray; logs to `%TEMP%\\abso_tray_startup.log`.
- Tray runtime hardening:
  - `abso/tray/ABSO-Tray.ps1`
  - Added Explorer-ready wait on startup.
  - Added startup icon self-heal timer and explicit NotifyIcon re-registration helper.
  - Kept apply success animation path (`pokeball -> pop -> Swampert`).
- Icon mapping and themed assets:
  - `abso/tray/ABSO-Icons.ps1`
  - Idle icon now tries `abso/tray/pokemon_pc_idle.ico` first, then falls back to generated computer icon.
  - Applying uses pokeball; Active/Gaming use Swampert; success animation sequence retained.
  - Added `abso/tray/pokemon_pc_idle.ico`.
- Restart helper safety fix:
  - `abso/tray/_restart-tray.ps1`
  - Narrowed kill filter to explicit tray launcher command lines only.
- Tests:
  - Added `tests/test_tray_startup.py`.
  - Updated `tests/test_profiles.py` with Rivals2 handler-scope regression tests.

## Validation Performed
- Script parse checks:
  - `ABSO-Tray.ps1`, `ABSO-Icons.ps1`, `Install-Startup.ps1`, `ABSO-StartupLaunch.ps1`, `_restart-tray.ps1` all parsed successfully.
- Pytest results:
  - `tests/test_tray_startup.py`: passed
  - `tests/test_profiles.py`: passed
  - `tests/test_core/test_applier.py tests/test_core/test_backup.py tests/test_handlers/test_nvidia_profiles.py tests/test_handlers/test_registry_settings.py`: passed
  - `tests/test_handlers/test_services.py tests/test_handlers/test_windows.py tests/test_handlers/test_network.py tests/test_core/test_linter.py`: passed
- Startup status command:
  - `py -3 -m abso tray --startup-status` works and reports current registration.

## Operational Notes
- Current machine has an existing scheduled task `ABSO-Tray-Startup` in `RunLevel=Highest` mode.
- From the current non-elevated shell, task overwrite attempts can return `Access is denied`; installer now handles this by preserving existing task and avoiding false-failure.
- The startup task currently points to `ABSO-Tray.vbs`, but tray runtime now includes additional shell-wait/icon-self-heal protections to reduce "started but icon missing" behavior.

## Files Added
- `abso/tray/ABSO-StartupLaunch.ps1`
- `abso/tray/pokemon_pc_idle.ico`
- `tests/test_tray_startup.py`

## Files Modified
- `abso/main.py`
- `abso/tray/ABSO-Icons.ps1`
- `abso/tray/ABSO-Tray.ps1`
- `abso/tray/Install-Startup.ps1`
- `abso/tray/__init__.py`
- `abso/tray/_restart-tray.ps1`
- `tests/test_profiles.py`
