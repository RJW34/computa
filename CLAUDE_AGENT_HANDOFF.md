# Claude Code Agent Handoff (2.0 Overhaul Pass)

## Scope Completed
This pass implemented the full `2.0 Overhaul` plan from `2.0_OVERHAUL_GUIDE.md` (P0-P7), including code, tests, CI wiring, and checkpoint updates.

## High-Impact Changes
1. Transaction + compliance core
- Added `abso/core/transaction.py` (checkpointed transactional apply, compliance evaluation, critical auto-rollback).
- Added `abso/core/compliance.py` (critical/warning mapping for apply and verify outcomes).
- Wired CLI apply to transaction path in `abso/main.py` (`ProfileTransactionManager.execute(profile_id=...)`).
- JSON apply output now includes `transaction`, `compliance`, and capability metadata payloads.

2. Config safety + Rivals 2 invariants
- Added `abso/core/config_safety.py` (allowed-key validation + deterministic INI patch helpers).
- Hardened `abso/settings/rivals2_config.py`:
  - explicit key allowlist
  - conversion validation
  - protected key invariants for control/profile identity fields
  - verify_active support for post-apply checks
  - optional frame cap key support (`frame_rate_limit`)

3. Capability graph preflight
- Added `abso/core/capabilities.py`.
- Integrated into `abso/core/applier.py`:
  - capability report on apply result
  - blockers fail apply pre-handler
  - warnings surfaced in result metadata

4. Health/watchdog diagnostics
- Added `abso/core/health.py` (health report + zipped diagnostics bundle writer).
- Extended `abso/tray/__init__.py`:
  - `get_tray_processes()`
  - `is_tray_running()`
  - `ensure_tray_running(start_if_missing=...)`
- Added CLI command `abso health` in `abso/main.py`:
  - JSON report mode
  - optional bundle generation
  - optional start-tray-if-missing action

5. Declarative heuristics manifests
- Added manifest loader: `abso/core/manifests.py`.
- Added manifests:
  - `abso/core/manifests/linter_rules.json`
  - `abso/core/manifests/game_detection.json`
  - `abso/core/manifests/integration_test_matrix.json`
- Migrated hardcoded linter/game detector rules to manifest-backed loading with fallback defaults:
  - `abso/core/linter.py`
  - `abso/core/game_detector.py`

6. Integration matrix contract + CI
- Added matrix contract tests:
  - `tests/test_core/test_integration_matrix.py`
- Added CI job in `.github/workflows/ci.yml`:
  - `Integration Matrix Contract`

## New/Updated Tests
- New:
  - `tests/test_core/test_compliance.py`
  - `tests/test_core/test_transaction.py`
  - `tests/test_core/test_config_safety.py`
  - `tests/test_handlers/test_rivals2_config.py`
  - `tests/test_core/test_capabilities.py`
  - `tests/test_core/test_health.py`
  - `tests/test_core/test_manifests.py`
  - `tests/test_core/test_integration_matrix.py`
- Updated:
  - `tests/test_cli.py`
  - `tests/test_core/test_applier.py`
  - `tests/test_tray_startup.py`

## Operational Notes
- Capability blockers (e.g., VRR-required profiles without confirmed VRR) now stop apply in preflight.
- Rivals2 config mutations are now fail-closed for unsupported keys and guarded against accidental profile/control field mutation.
- `abso health --bundle` writes a zipped diagnostics package including report + tray logs when present.

## Validation Performed
- Full tests: `python -m pytest -q` (exit code 0)
- Lint: `python -m ruff check abso tests` (exit code 0)
- Format check: `python -m black --check abso tests` (exit code 0)
- Type check: `python -m mypy abso --ignore-missing-imports --no-error-summary` (exit code 0)

## Checkpoint Source of Truth
- `2.0_OVERHAUL_GUIDE.md` checkpoint table and progress journal now mark `P0-P7` as `COMPLETED`.
