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
