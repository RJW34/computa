# Changelog

All notable changes to A.B.S.O. (Adaptive Battle Station Optimizer) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- Game detection system - detects games from Steam, Epic, Battle.net, standalone
- `abso games` command to list detected games and suggest profiles
- `abso timer` command with `--resolution` and `--keep-alive` options
- `abso config` command to create/manage `abso.yaml` configuration
- Profile customization via `abso.yaml` (override settings without editing code)
- Handler disabling via `disabled_handlers` config option
- G-Sync/VRR detection improvements:
  - Known G-Sync monitor database matching
  - EDID FreeSync range parsing
  - NVIDIA registry queries
  - High refresh rate heuristics
- GitHub Actions CI pipeline (`ci.yml`)
- Pre-commit hooks (Black, Ruff, pytest)
- `pyproject.toml` for modern Python packaging
- Type checking with mypy (30+ type annotations added)
- Handler unit tests (graphics, memory, mouse, network, power, services, timer)
- CLI smoke tests for all commands
- Test count: 274 -> 359 tests

### Changed
- Refactored `nvidia.py` (822 lines) into `abso/settings/nvidia/` package:
  - `__init__.py` - Main handler
  - `npi.py` - NPI executable operations
  - `profiles.py` - NIP file generation
  - `presets.py` - Setting IDs and presets
  - `parsing.py` - XML parsing utilities
- Game Detection and Profile Customization documentation in TECHNICAL_REFERENCE.md
- Timer CLI documentation in TECHNICAL_REFERENCE.md

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
