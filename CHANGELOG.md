# Changelog

All notable changes to A.B.S.O. (Adaptive Battle Station Optimizer) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added (2026-05 — Win11 25H2 26200.8457 cumulative adaptation)
- `abso/utils/os_release.py` — `OsRelease` snapshot with
  `at_least(build, ubr)` build-floor comparisons; cached per-process.
- `abso/settings/xbox_mode.py` — detect-only handler for the Xbox Mode
  rollout in KB5089549. `apply()` refuses until Microsoft documents
  stable registry keys.
- `abso/settings/ai_agents.py` — detect-only handler for the "Agents
  on the Taskbar" rollout in KB5089549; surfaces Copilot policy state
  as an adjacent signal.
- `core/bios_detector.py::SecureBootCertState` — reads `SecureBoot\
  Servicing` for the June 2026 PCA2023 / UEFI CA 2023 cert rollout.
  Recommendation impact escalates past 2026-06-01.
- `core/kb_checker.py` — `superseded_by`, `fixed_in_build`,
  `discovered_in_build` fields plus `LAST_REVIEWED_UTC` staleness
  cadence. KB5083769 entry auto-suppresses when KB5089549 is present.
- `BaseProfile` fields: `min_os_build`, `validated_os_build`,
  `xbox_mode`, `ai_agents`. Reflex shooters / emulators / Rivals 2
  declare `xbox_mode="off"`, `ai_agents="off"`; Diablo 4 declares
  `ai_agents="off"`.
- `core/capabilities.py` — `OS_BUILD_BELOW_FLOOR`,
  `OS_BUILD_UNTESTED_ON_PROFILE`, `OS_RELEASE_UNAVAILABLE` findings.
- `core/linter.py::_check_xbox_mode_conflicts` — fails closed when a
  profile declares `xbox_mode="on"` against a fullscreen-only VRR
  contract.
- `docs/AGENT_PROTOCOL.md` — single forward-looking entry point for
  future agents.

### Added (2026-05 — crude duplication refactor)
- `abso/core/handler_registry.py` — central `HandlerEntry` registry
  with `audit` / `backup` tags. Replaces the parallel handler lists
  that used to live in `auditor._get_handlers()` and
  `backup._get_backup_handlers()`.
- `abso/data/hardware_db.py` — extracted OEM / chassis / G-Sync
  reference tables that were inline in `core/detector.py`.
- `SettingsHandler.is_critical_verify` property. `ComplianceEngine`
  resolves the critical-handler set lazily from the registry instead
  of carrying a hardcoded class-name set.
- Module-level `WIN32_PRIORITY_GAMING_OFFLINE` (`0x2A`) and
  `WIN32_PRIORITY_GAMING_ONLINE` (`0x26`) named constants exported
  from `abso/settings/registry.py`. All callers updated.
- 9 new tests in `tests/test_core/test_handler_registry.py`
  + targeted live registry probes for the May 2026 surfaces.
- Test count: 1331 → 1340 tests.

### Changed
- `core/detector.py` slimmed from 1539 → 1408 lines (data tables
  moved out to `abso/data/hardware_db.py`).
- `core/bios_detector.py::_read_reg_dword` / `_read_reg_value` are
  now thin wrappers over `abso.utils.registry.read_registry_dword` /
  `read_registry_value` (40 lines of duplicate winreg glue removed).
- `ComplianceEngine.CRITICAL_VERIFY_HANDLERS` removed; replaced by
  property-driven resolution.
- README project-structure section updated to match current layout
  (`nvidia/` package, `data/`, `utils/os_release.py`, etc.).
- Three dated handoff docs moved to `docs/archive/` with deprecation
  banners; `docs/AGENT_PROTOCOL.md` is the current entry point.

### Fixed
- Profile switches now restore only native game-config keys owned by each
  handler instead of replacing whole stale files. This preserves Slippi's
  user-selected renderer and unmanaged controls, audio, quality, and future
  game settings across unrelated profile switches.
- Slippi backend detection reads `GFXBackend` from the Ishiiruka build's real
  `Dolphin.ini` location. Guidance now preserves the user's renderer and uses
  D3D11 only as the documented compatibility baseline, not a forced target.
- Stateful peripheral daemons (Logitech G HUB, Corsair iCUE) are never
  launch-kill targets; closing them mid-game can drop DPI/button mappings.
- The launch sanitizer takes one bulk process snapshot per sweep instead of
  one `tasklist` call per killset image (~4.2s -> ~0.3s per sweep).
- `config --show` renders every `profile_overrides` section from the schema
  (registry, cpu_affinity and the per-game config sections were hidden).
- Ordinary profile application, switching, rollback, and uninstall restore no
  longer write Memory Integrity from `WindowsSettingsHandler`. New backups omit
  the legacy `vbs` field, old backups ignore it during restore, and direct or
  configured generic HVCI targets fail closed in favor of the explicit
  acknowledgement-gated VBS opt-in handler.
- Em-dash / en-dash in user-visible CLI strings (cp1252 mojibake in
  `abso bios` and `abso audit` output). `bios_detector.py` and
  `multimon_detector.py` strings replaced with hyphens.

### Earlier in this cycle
- Game detection system — detects games from Steam, Epic, Battle.net,
  standalone.
- `abso games` command to list detected games and suggest profiles.
- `abso timer` command with `--resolution` and `--keep-alive` options.
- `abso config` command to create/manage `abso.yaml` configuration.
- Profile customization via `abso.yaml`.
- Handler disabling via `disabled_handlers` config option.
- G-Sync/VRR detection improvements: known monitor database matching,
  EDID FreeSync range parsing, NVIDIA registry queries, refresh-rate
  heuristics.
- GitHub Actions CI pipeline (`ci.yml`); pre-commit hooks (Black,
  Ruff, pytest); `pyproject.toml` modern packaging; mypy annotations.
- Handler unit tests across the full handler set; CLI smoke tests.

### Changed (earlier)
- Refactored `nvidia.py` (822 lines) into `abso/settings/nvidia/`
  package: `__init__.py`, `npi.py`, `profiles.py`, `presets.py`,
  `parsing.py`.

---

## [1.0.0] - 2025-12-27

### Added
- CCD API for accurate high refresh rate detection (240Hz+, VRR displays)
- Max refresh rate detection for monitors
- NPI (NVIDIA Profile Inspector) silent import support
- Correct NIP XML format generation (decimal IDs/values)

### Fixed
- NPI import using correct `-silent` flag (was `-import`)
- Monitor detection pywintypes.error handling
- NIP XML format now matches real NPI format

### Changed
- Renamed package from `gametune` to `abso`
- Cleaned up .gitignore (removed garbage entries, added reports/, tools/)

---

## [0.3.0] - 2025-12-26

### Added
- Polish and code quality improvements
- Comprehensive test suite (274 tests)
- Rich terminal UI for interactive mode

### Changed
- Profile settings verified against technical documentation
- Improved error messages and user feedback

---

## [0.2.0] - 2025-12-25

### Added
- Input validation to prevent registry injection attacks
- Custom exception hierarchy (26 exception types)
- Registry utilities with safe read/write operations
- Validation module for user inputs

### Security
- Added path traversal protection
- Added null byte injection protection
- Added DWORD value range validation

---

## [0.1.0] - 2025-12-24

### Added
- Initial release of A.B.S.O.
- Hardware detection (GPU, CPU, RAM, monitors)
- Configuration auditor (15+ system areas)
- Game profiles: Slippi Melee, Rivals of Aether 2, CoD BO7, Diablo 4
- Settings handlers: Windows, Power, Registry, NVIDIA, Network, Timer, Mouse, Graphics, Services, Memory, Visual, Audio, Storage, Updates, Tasks, Process Priority
- Backup and restore system with timestamped backups
- CLI interface with Click
- Interactive menu mode
- In-game settings report generation

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 1.0.0 | 2025-12-27 | CCD API, NPI fixes, package rename |
| 0.3.0 | 2025-12-26 | Polish, 274 tests, verified profiles |
| 0.2.0 | 2025-12-25 | Security hardening, validation |
| 0.1.0 | 2025-12-24 | Initial release |
