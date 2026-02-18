# Claude Agent Handoff - 2026-02-18

## Objective
Implement dual Overwatch 2 profiles so users can choose deterministic `No-SYNC` or `G-SYNC`, and confirm whether the previous OW2 profile was truly optimal for no-sync.

## Key Outcome
The old OW2 profile was **not fully deterministic no-sync** because it relied on `reflex_game` (which did not explicitly force VRR/G-SYNC off).  
The new split makes behavior explicit and predictable:
- `overwatch2` -> **No-SYNC** (`reflex_no_sync`)
- `overwatch2-gsync` -> **G-SYNC** (`reflex_gsync`)

## Code Changes
- `abso/profiles/overwatch2.py`
  - Refactored into shared `_Overwatch2BaseProfile`.
  - Updated `Overwatch2Profile` display and behavior for explicit no-sync.
  - Added `Overwatch2GSyncProfile`.
- `abso/settings/nvidia/presets.py`
  - Added `reflex_no_sync` preset.
  - Added `reflex_gsync` preset.
- `abso/profiles/__init__.py`
  - Exported and registered `Overwatch2GSyncProfile`.
- `abso/core/applier.py`
  - Added `overwatch2-gsync` to `ProfileApplier.PROFILES`.
- `abso/core/linter.py`
  - Added `reflex_no_sync` and `reflex_gsync` to `REFLEX_PRESETS`.
- `abso/tray/ABSO-Tray.ps1`
  - Renamed OW2 entry to `Overwatch 2 - No-Sync`.
  - Added tray entry for `Overwatch 2 - GSYNC`.
- `abso/core/game_detector.py`
  - Added Battle.net detection entry for `Overwatch 2` (`Overwatch.exe`).
- `README.md`
  - Added both OW2 profile variants to profile table.
- `docs/API.md`
  - Added both OW2 profile variants to API docs.
- `.gitignore`
  - Added `.abso_state.json` to ignore local runtime state file.

## Test Updates
- `tests/test_profiles.py`
  - Added load tests for both OW2 profile classes.
  - Added preset assertions for both variants.
  - Added executable hint assertions for both variants.
- `tests/test_core/test_applier.py`
  - Added assertions that both OW2 profile IDs are registered.
- `tests/test_core/test_game_detector.py`
  - Added Battle.net registry detection test for Overwatch 2.

## Validation Performed
- Targeted:
  - `py -m pytest tests/test_profiles.py tests/test_core/test_applier.py tests/test_core/test_game_detector.py tests/test_handlers/test_nvidia_profiles.py`
  - Result: `208 passed`
- Full:
  - `py -m pytest`
  - Result: `863 passed` (1 pre-existing pytest config warning)

## Operational Notes
- No-SYNC profile is now deterministic even if global VRR is enabled.
- G-SYNC profile uses Reflex + NVCP VSync safety-net model; users should cap in-game FPS to refresh-3.

## Follow-up Fixes (Post-Initial Commit)
- Root cause found: custom profile `Overwatch 2 - GSYNC` could be created with correct settings but no executable binding (`num_apps=0`) on some drivers, resulting in no in-game effect.
- Fixes implemented:
  - OW2 variants now target NVIDIA's existing predefined profile name via:
    - `profile_name: "Overwatch 2"` in `abso/profiles/overwatch2.py`
  - NVIDIA handler now honors optional `profile_name` override:
    - `abso/settings/nvidia/__init__.py`
  - DRS manager improved binding logic:
    - Detects zero-app silent binding failures.
    - For explicitly targeted existing profiles with existing app bindings, treats CreateApplication version issues as non-fatal and proceeds.
    - File: `abso/settings/nvidia/nvapi_drs.py`
  - Added OW2 profile tests for `profile_name` override:
    - `tests/test_profiles.py`
- Runtime verification after fix:
  - `Overwatch 2` profile now reflects expected GSYNC values (`vsync=on`, `vrr_app_override=allow`, `low_latency_mode=off`).

## Follow-up Fixes (Global G-SYNC Enforcement + NVAPI Enum Corrections)
- User-impacting issue addressed:
  - Switching `Overwatch 2 - No-Sync` <-> `Overwatch 2 - GSYNC` previously only changed per-app DRS state.
  - It did **not** explicitly enforce base/global G-SYNC mode, so transition behavior could look inconsistent.
- New behavior:
  - `Overwatch 2 - No-Sync` now sets `global_vrr_mode=off`.
  - `Overwatch 2 - GSYNC` now sets `global_vrr_mode=fullscreen_only`.
  - This is wired through `NvidiaSettingsHandler` into a new NVAPI DRS base-profile apply path.
- Files changed:
  - `abso/profiles/overwatch2.py`
    - Added `global_vrr_mode` override in both OW2 variants.
  - `abso/settings/nvidia/__init__.py`
    - Added global settings extraction and application (`global_vrr_mode`, `global_gsync_mode`, `global_gsync`, `vrr_mode` aliases).
    - Applies global settings via `DRSProfileManager.apply_settings_to_global()` before per-app profile changes.
  - `abso/settings/nvidia/nvapi_drs.py`
    - Added base-profile method `apply_settings_to_global(settings)`.
    - Added VRR global setting IDs and aliases:
      - `vrr_mode` (`VRR_MODE_ID`, `0x1194F158`)
      - `vrr_request_state` / `vrr_requested_state` (`VRRREQUESTSTATE_ID`, `0x1094F1F7`)
      - `vrr_app_override_request_state` (`0x10A879AC`)
    - Fixed `vsync_mode` enum mapping to true NVAPI constants from `NvApiDriverSettings.h`:
      - `off=0x08416747`, `on=0x47814940`, etc.
    - Fixed `vsync_tear_control` enum mapping:
      - `disable=0x96861077`, `enable=0x99941284`.
    - Fixed minor DRS logic bugs:
      - removed duplicate `existing_profile_num_apps` assignment in `apply_settings_to_app`.
      - initialized `existing_profile_num_apps` in `apply_settings_to_profile` (prevented NameError path).
- Tests added/updated:
  - `tests/test_profiles.py`
    - Assert OW2 No-Sync has `global_vrr_mode == "off"`.
    - Assert OW2 GSYNC has `global_vrr_mode == "fullscreen_only"`.
  - `tests/test_handlers/test_nvidia.py`
    - Added test proving handler routes `global_vrr_mode` through global apply path.
  - `tests/test_handlers/test_nvidia_nvapi_drs.py` (new)
    - Validates NVAPI constant resolution for VSync and tear-control.
    - Validates global alias resolution and global apply call flow.
- Validation:
  - Full suite passed: `871 passed, 1 warning`.
