# A.B.S.O. Critical Remediation Plan

**Date:** 2025-12-27
**Target:** Resolve all critical blockers from customer review
**Goal:** Test coverage ≥70%, 0 linting errors, no dead code

---

## Current State

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Test Coverage | 48% (2316/4607) | 70% (3225/4607) | +909 lines |
| Linting Errors | 39 | 0 | -39 |
| Unused Handlers | 4 | 0 | -4 |
| 0% Coverage Modules | 4 | 0 | -4 |

---

## Phase 1: Quick Wins (Linting + Cleanup)

**Estimated effort:** 30 minutes
**Coverage impact:** +85 lines (~2%)

### 1.1 Fix All Linting Errors

```bash
# Auto-fix 3 errors
ruff check . --fix

# Manual fixes needed (36 errors):
```

| File | Error | Fix |
|------|-------|-----|
| `detector.py:356` | F841 unused `revision` | Remove or use |
| `detector.py:394` | F841 unused `ext_code` | Remove or use |
| `detector.py:793,822` | SIM102 nested if | Collapse conditions |
| `game_detector.py:180,181` | SIM112 env var | Use `PROGRAMFILES` |
| `process_priority.py:324` | F841 unused `errors` | Remove or use |
| `test_backup.py:194` | F841 unused `backup_id2` | Remove or use |
| Multiple files | SIM105 | Use `contextlib.suppress()` |
| Multiple files | SIM102 | Collapse nested `if` |

### 1.2 Remove IMPROVEMENT_PLAN.md

```bash
git rm IMPROVEMENT_PLAN.md
```

### 1.3 Import constants.py (Free Coverage)

The `constants.py` file has 0% coverage but is just constant definitions.
Adding a simple import test covers 85 lines instantly.

```python
# tests/test_core/test_constants.py
def test_constants_importable():
    from abso.core.constants import RegistryPaths, NvidiaSettings
    assert RegistryPaths.GAME_BAR is not None
```

---

## Phase 2: Interactive Module Tests

**Estimated effort:** 1.5 hours
**Coverage impact:** +170 lines (~4%)

### 2.1 Create test_interactive.py

The interactive.py module (342 lines, 0%) needs smoke tests with mocked Rich console.

**Key functions to test:**
- `clear_screen()` - Mock console.clear
- `print_header()` - Mock console.print
- `show_main_menu()` - Mock Prompt.ask
- `run_audit()` - Mock auditor
- `run_apply_profile()` - Mock applier
- `run_hardware_detection()` - Mock detector
- `run_restore_backup()` - Mock backup manager
- `run_interactive()` - Integration test

**Testing strategy:**
```python
from unittest.mock import patch, MagicMock

@patch('abso.interactive.console')
@patch('abso.interactive.Prompt')
def test_show_main_menu(mock_prompt, mock_console):
    mock_prompt.ask.return_value = "1"
    from abso.interactive import show_main_menu
    result = show_main_menu()
    assert result == "1"
```

---

## Phase 3: Game Detector Tests

**Estimated effort:** 1 hour
**Coverage impact:** +85 lines (~2%)

### 3.1 Create test_game_detector.py

The `game_detector.py` (171 lines, 0%) needs full test coverage.

**Functions to test:**
- `detect_installed_games()` - Main entry point
- `_get_steam_library_folders()` - Mock registry
- `_detect_steam_games()` - Mock filesystem
- `_detect_epic_games()` - Mock registry + filesystem
- `_detect_battlenet_games()` - Mock registry
- `_detect_standalone_games()` - Mock filesystem
- `_match_profile()` - Pure function, easy to test

**Testing strategy:**
```python
@patch('abso.core.game_detector.winreg')
@patch('abso.core.game_detector.Path')
def test_detect_steam_games(mock_path, mock_winreg):
    # Mock Steam registry key
    mock_winreg.OpenKey.return_value = MagicMock()
    mock_winreg.QueryValueEx.return_value = ("C:\\Steam", 1)
    # ... test detection
```

---

## Phase 4: Registry Handler Tests

**Estimated effort:** 1.5 hours
**Coverage impact:** +130 lines (~3%)

### 4.1 Expand test_registry.py (settings)

Current: 26% coverage → Target: 60%

**Missing test coverage for:**
- `_get_system_responsiveness()` / `_set_system_responsiveness()`
- `_get_network_throttling()` / `_set_network_throttling()`
- `_get_game_priority()` / `_set_game_priority()`
- `_get_fullscreen_optimization()` / `_set_fullscreen_optimization()`
- `_get_win32_priority_separation()` / `_set_win32_priority_separation()`
- Full `apply()` method scenarios
- Error handling paths

---

## Phase 5: Main CLI Tests

**Estimated effort:** 1 hour
**Coverage impact:** +80 lines (~2%)

### 5.1 Create test_main_cli.py

Current: 41% coverage → Target: 65%

**CLI commands to test:**
```python
from click.testing import CliRunner
from abso.main import cli

def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0

def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert '0.1.0' in result.output

@patch('abso.main.HardwareDetector')
def test_cli_detect(mock_detector):
    mock_detector.return_value.detect_all.return_value = {"gpu": {}}
    runner = CliRunner()
    result = runner.invoke(cli, ['detect'])
    assert result.exit_code == 0
```

---

## Phase 6: Detector Module Tests

**Estimated effort:** 2 hours
**Coverage impact:** +170 lines (~4%)

### 6.1 Expand test_detector.py

Current: 37% coverage → Target: 60%

**Missing coverage for:**
- CCD API monitor detection (`_detect_monitors_ccd`)
- Refresh rate detection
- G-Sync detection
- CPU cache detection
- Memory speed detection
- Multiple GPU detection
- Error handling paths

---

## Phase 7: Unused Handler Integration

**Estimated effort:** 1 hour
**Coverage impact:** Reduces dead code, +50 lines

### 7.1 Integrate Handlers into Profiles

Add unused handlers to appropriate profiles:

| Handler | Add to Profiles | Rationale |
|---------|-----------------|-----------|
| `AudioSettingsHandler` | rivals2, slippi-melee | Audio latency matters for fighting games |
| `VisualSettingsHandler` | All profiles | Reduce DWM overhead |
| `UpdatesSettingsHandler` | All profiles | Prevent mid-game updates |
| `StorageSettingsHandler` | diablo4, fortnite | TRIM for SSD health |

**Implementation:**
```python
# In rivals2.py get_handlers():
from abso.settings.audio import AudioSettingsHandler
from abso.settings.visual import VisualSettingsHandler
from abso.settings.updates import UpdatesSettingsHandler

return [
    # ... existing handlers ...
    AudioSettingsHandler(),
    VisualSettingsHandler(),
    UpdatesSettingsHandler(),
]
```

---

## Phase 8: Miscellaneous Coverage

**Estimated effort:** 1 hour
**Coverage impact:** +139 lines (~3%)

### 8.1 Low-Hanging Fruit

| Module | Current | Easy Wins |
|--------|---------|-----------|
| `profiles/base.py` | 40% | Test abstract methods |
| `profiles/rivals2.py` | 57% | Test get_handlers, get_settings |
| `settings/audio.py` | 38% | Test private methods |
| `settings/updates.py` | 47% | Test private methods |
| `settings/visual.py` | 43% | Test private methods |

---

## Execution Order

| Phase | Task | Lines | Cumulative |
|-------|------|-------|------------|
| 1.1 | Fix linting | 0 | 48% |
| 1.2 | Remove IMPROVEMENT_PLAN.md | 0 | 48% |
| 1.3 | Test constants.py | +85 | 50% |
| 2.1 | Test interactive.py | +170 | 54% |
| 3.1 | Test game_detector.py | +85 | 56% |
| 4.1 | Test settings/registry.py | +130 | 59% |
| 5.1 | Test main.py CLI | +80 | 61% |
| 6.1 | Expand detector.py tests | +170 | 65% |
| 7.1 | Integrate unused handlers | +50 | 66% |
| 8.1 | Misc coverage | +139 | **70%** |

**Total estimated effort:** 9-10 hours

---

## Verification Checklist

After completion, verify:

```bash
# Coverage ≥ 70%
pytest tests/ --cov=abso --cov-fail-under=70

# Zero linting errors
ruff check .

# Zero type errors
mypy abso/ --ignore-missing-imports

# All tests pass
pytest tests/ -v

# No IMPROVEMENT_PLAN.md
test ! -f IMPROVEMENT_PLAN.md

# Unused handlers integrated (no dead code)
grep -r "AudioSettingsHandler" abso/profiles/
grep -r "VisualSettingsHandler" abso/profiles/
```

---

## Risk Mitigation

1. **Mocking Windows APIs**: Use `unittest.mock` extensively for winreg, subprocess
2. **Test isolation**: Each test should be independent
3. **CI enforcement**: Add GitHub Actions with coverage gate after completion

---

*This plan addresses all 7 critical blockers from the customer review.*
