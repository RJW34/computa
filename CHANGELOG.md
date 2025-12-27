# Changelog

All notable changes to A.B.S.O. (Adaptive Battle Station Optimizer) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- NPI installation instructions in README
- CCD API documentation in TECHNICAL_REFERENCE.md
- Rivals of Aether 2 profile documentation
- CHANGELOG.md

### Changed
- Updated TECHNICAL_REFERENCE.md with correct NPI CLI flags

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
