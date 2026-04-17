# A.B.S.O. Architecture Refactoring Plan

## Status Tracker

- [x] **Snapshot test** — Golden file captures all 28 profiles (commit `212792e`)
- [x] **P4: Config known_keys** — Auto-derived from dataclass fields (commit `212792e`)
- [ ] **P6: NVIDIA codepath docs** — Mark NPI deprecated, add architecture comments
- [ ] **P1: Base class collapse** — Four bases → one `TieredBaseProfile`
- [ ] **P3: CLI split** — `main.py` (1,865 lines) → `abso/cli/` (16 modules)
- [ ] **P5: ctypes centralization** — 11 files → shared `utils/win32.py`
- [ ] **P2: Profiles to YAML** — 14 Python profiles → `profiles/builtin/*.yaml`
- [ ] **P7: State management** — 17 JSON files → centralized `StateManager`

---

## Execution Order

```
P6 (NVIDIA docs)     — 30 min, zero risk, documentation only
P1 (base collapse)   — 2-4 hr, medium risk, VERIFY SNAPSHOT AFTER
P3 (CLI split)       — 2-3 hr, low risk, mechanical extraction
P5 (ctypes central)  — 2-3 hr, medium risk, one file at a time
P2 (profiles→YAML)   — 4-8 hr, high risk, DEPENDS ON P1, verify after each profile
P7 (state manager)   — 1-2 hr, medium risk, path centralization only
```

P1 must complete before P2. All others are independent.

---

## P6: NVIDIA Codepath Documentation

**Files to modify (3):**

### `abso/settings/nvidia/npi.py`
Add at top of file (after existing docstring):
```python
# DEPRECATED — NPI imports are permanently disabled (NPI_IMPORTS_DISABLED = True).
# This module is retained for NPI export PARSING only (reading .nip files).
# The active apply path is nvapi_drs.py which talks directly to the NVIDIA
# driver via the NVAPI DRS API.
```

### `abso/settings/nvidia/presets.py`
Add section headers:
- Before `class NvidiaSettingValues`: `# === NPI-FORMAT VALUES (used for .nip parsing only) ===`
- Before `NVIDIA_PRESETS`: `# === PRESET CONFIGURATIONS (consumed by both NPI and DRS paths) ===`
- The existing docstring on `NvidiaSettingValues` already has the SDK vs NPI warning (we added it earlier)

### `abso/settings/nvidia/__init__.py`
Add architecture comment at module level (after imports):
```python
# Architecture: Two codepaths exist for NVIDIA profile management.
#
# 1. DRS (primary): nvapi_drs.py talks directly to the NVIDIA driver via
#    NVAPI DRS API (ctypes). This is the active apply path. Uses correct
#    NVAPI SDK setting IDs and hex values.
#
# 2. NPI (legacy): profiles.py generates .nip XML files for Nvidia Profile
#    Inspector. NPI imports are permanently disabled (NPI_IMPORTS_DISABLED=True
#    in npi.py). The NPI path is retained only for parsing exported .nip files.
#
# When apply() is called, it uses DRSProfileManager from nvapi_drs.py.
# The NvidiaSettingValues class in presets.py uses NPI's internal integer
# values (not NVAPI SDK hex values) — used only for .nip parsing.
```

**Verification:** Syntax check all 3 files. No behavioral change.

---

## P1: Base Class Collapse

**Goal:** `profile_bases.py` from 679 lines → ~250 lines. Four bases → one `TieredBaseProfile`.

### The Tier System

```python
from enum import Enum

class SettingsTier(Enum):
    AGGRESSIVE = "aggressive"  # fighting, shooters, emulators
    MODERATE = "moderate"      # browser, casual

# The ONLY settings that differ between tiers:
TIER_CONFIGS = {
    SettingsTier.AGGRESSIVE: {
        "win32_priority_separation": 0x2A,
        "game_priority": {"gpu_priority": 8, "priority": 6, "scheduling_category": "High"},
        "network_preset": "gaming",
        "disable_nagle": True,
        "cpu_priority": 3,
        "io_priority": 3,
        "disable_global_fso": True,
        "include_mouse": True,
        "include_cpu_affinity": True,
        "disable_pcie_power_saving": True,
    },
    SettingsTier.MODERATE: {
        "win32_priority_separation": 0x26,
        "game_priority": {"gpu_priority": 8, "priority": 4, "scheduling_category": "Medium"},
        "network_preset": "default",
        "disable_nagle": False,
        "cpu_priority": 2,
        "io_priority": 2,
        "disable_global_fso": False,
        "include_mouse": False,
        "include_cpu_affinity": False,
        "disable_pcie_power_saving": False,
    },
}
```

### TieredBaseProfile

Single class with `settings_tier` and `color_game_type` as the only varying inputs:

```python
class TieredBaseProfile(BaseProfile):
    """Parameterized base for all gaming profiles."""

    @property
    def settings_tier(self) -> SettingsTier:
        return SettingsTier.AGGRESSIVE  # default; subclasses override

    @property
    def color_game_type(self) -> str:
        return "competitive_fps"  # subclasses override

    @property
    def nvidia_preset(self) -> str | None:
        return None  # reflex_shooter subclasses override to "reflex_game"

    @property
    def include_max_refresh_rate(self) -> bool:
        return False  # reflex_shooter subclasses override to True

    def get_handlers(self) -> list[SettingsHandler]:
        # Build handler list from tier config + property flags
        tier = TIER_CONFIGS[self.settings_tier]
        handlers = [WindowsSettingsHandler(), PowerSettingsHandler(), RegistrySettingsHandler(), NvidiaSettingsHandler()]
        handlers.append(NetworkSettingsHandler())
        if tier["include_mouse"]:
            handlers.append(MouseSettingsHandler())
        handlers.append(GraphicsSettingsHandler())
        handlers.append(ServicesSettingsHandler())
        if self.include_legacy_tweaks:
            handlers.append(MemorySettingsHandler())
        handlers.append(ProcessPriorityHandler(self.executable_hints))
        if tier["include_cpu_affinity"]:
            handlers.append(CpuAffinityHandler(self.executable_hints))
        handlers.extend(self._additional_handlers())
        handlers.append(CNMSettingsHandler())
        handlers.append(ColorProfileSettingsHandler())
        return handlers

    def _additional_handlers(self) -> list[SettingsHandler]:
        return []  # subclasses add game-specific handlers

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        tier = TIER_CONFIGS[self.settings_tier]
        settings = {
            "WindowsSettingsHandler": {
                "game_mode": True, "game_bar": False, "game_dvr": False,
                "hags": True, "hdr": False, "auto_hdr": False,
                "windowed_optimizations": False, "vrr_optimize": False,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "processor_max_performance": True,
            },
            "RegistrySettingsHandler": {
                "win32_priority_separation": tier["win32_priority_separation"],
                "game_priority": tier["game_priority"].copy(),
            },
            # ... etc, reading from tier config
        }
        if tier["disable_pcie_power_saving"]:
            settings["PowerSettingsHandler"]["disable_pcie_power_saving"] = True
        if self.include_max_refresh_rate:
            settings["WindowsSettingsHandler"]["max_refresh_rate"] = True
        if self.nvidia_preset:
            settings["NvidiaSettingsHandler"] = {"preset": self.nvidia_preset}
        if self.include_legacy_tweaks:
            # ... add legacy settings
        return settings
```

### Compatibility Aliases (keep old names working during transition)

```python
# Old names → new parameterized instances
class Rivals2BaseProfile(TieredBaseProfile):
    """Alias: aggressive tier, competitive_fps color."""
    settings_tier = SettingsTier.AGGRESSIVE
    color_game_type = "competitive_fps"
    # Keep rivals2-specific hooks
    include_nvidia_notifications = False
    include_rivals2_config = False

class EmulatorLatencyBaseProfile(TieredBaseProfile):
    """Alias: aggressive tier, emulator color."""
    settings_tier = SettingsTier.AGGRESSIVE
    color_game_type = "emulator"
    is_emulator_profile = True
    allows_aggressive_settings = True

class WebGLBaseProfile(TieredBaseProfile):
    """Alias: moderate tier, casual color."""
    settings_tier = SettingsTier.MODERATE
    color_game_type = "casual"

class ReflexShooterBaseProfile(TieredBaseProfile):
    """Alias: aggressive tier, reflex preset, max refresh."""
    settings_tier = SettingsTier.AGGRESSIVE
    color_game_type = "competitive_fps"
    nvidia_preset = "reflex_game"
    include_max_refresh_rate = True
    requires_reflex = True
    graphics_api = "dx12"
```

### Files Modified

- `abso/profiles/profile_bases.py` — Full rewrite (~250 lines vs 679)
- No changes to any profile `.py` files (they import the alias names)

### Verification

1. `python -c "from abso.profiles.catalog import get_profile_manifest; print(len(get_profile_manifest()))"` → 28
2. Run snapshot comparison → all settings identical
3. Syntax check `profile_bases.py`

---

## P3: CLI Split

**Goal:** `main.py` (1,865 lines) → thin shim + `abso/cli/` modules

### File Map

| Source lines | Target file | Commands |
|---|---|---|
| 1-110 | `cli/__init__.py` | cli group, helpers (output_json, json_error, console, paths, STATE_FILE) |
| 49-99 | `cli/state.py` | get_current_profile, set_current_profile, clear_reboot_pending |
| 150-170 | `cli/interactive.py` | interactive, setup |
| 172-400 | `cli/detect.py` | detect |
| 401-456 | `cli/audit.py` | audit |
| 458-538 | `cli/profiles.py` | profiles, games |
| 540-732 | `cli/apply.py` | apply (with --benchmark), reapply, verify |
| 734-845 | `cli/launch.py` | launch |
| 847-991 | `cli/restore.py` | restore, backups, prune |
| 993-1140 | `cli/tools.py` | timer, memory-clear, debloat, cpu-balance |
| 1141-1200 | `cli/report.py` | report |
| 1202-1264 | `cli/tray.py` | tray |
| 1265-1324 | `cli/config_cmd.py` | config |
| 1326-1504 | `cli/benchmark.py` | benchmark, benchmark-compare |
| 1506-1700 | `cli/bios.py` | bios |
| 1700-1712 | `cli/profile_create.py` | profile-create |

### `abso/main.py` becomes:
```python
"""CLI entry point for ABSO."""
from abso.cli import cli

def main() -> None:
    cli()

if __name__ == "__main__":
    main()
```

### `abso/cli/__init__.py` structure:
```python
import click
from rich.console import Console

console = Console()

@click.group(invoke_without_command=True)
@click.version_option(...)
@click.pass_context
def cli(ctx): ...

# Shared helpers
def output_json(data, ...): ...
def json_error(message, ...): ...

# Register all commands
from abso.cli.detect import detect
from abso.cli.apply import apply, reapply, verify
# ... etc
```

### Verification

```bash
python -m abso --help        # All 21+ commands listed
python -m abso detect --help # Each command's help works
python -m abso profiles      # Functional test
```

---

## P5: ctypes Centralization

**Goal:** New `abso/utils/win32.py` with shared structures + DLL handles

### Structures to centralize (currently duplicated)

| Structure | Currently in | Used by |
|---|---|---|
| `_LUID` | windows.py:31, detector.py, color.py | HDR, display config |
| `DISPLAYCONFIG_DEVICE_INFO_HEADER` | windows.py:35 | HDR toggle |
| `DISPLAYCONFIG_*` (6 structs) | windows.py:35-92, detector.py | Display enumeration |
| `FILETIME` | cpu_balancer.py:72 | CPU time measurement |
| `MEMORYSTATUSEX` | standby_list.py | Memory stats |
| `PROCESSENTRY32W` | cpu_balancer.py:50 | Process enumeration |
| `PHYSICAL_MONITOR` | monitor_adaptive_sync.py:46 | DDC/CI |
| `DEVMODE` | detector.py | Refresh rate |

### DLL handle singletons

```python
# abso/utils/win32.py
import ctypes, functools

@functools.lru_cache(maxsize=1)
def get_user32(): return ctypes.WinDLL("user32")

@functools.lru_cache(maxsize=1)
def get_kernel32(): return ctypes.WinDLL("kernel32")

@functools.lru_cache(maxsize=1)
def get_ntdll(): return ctypes.WinDLL("ntdll")

@functools.lru_cache(maxsize=1)
def get_dxva2(): return ctypes.WinDLL("dxva2")
```

### Shared privilege escalation

```python
def enable_privilege(privilege_id: int) -> bool:
    """Enable a process privilege via ntdll.RtlAdjustPrivilege."""
    # Currently duplicated in standby_list.py and timer.py
```

### Migration order (one file at a time, verify after each)

1. Create `utils/win32.py` with all structures + DLL getters
2. Migrate `cpu_balancer.py` (FILETIME, PROCESSENTRY32W)
3. Migrate `standby_list.py` (MEMORYSTATUSEX, enable_privilege)
4. Migrate `timer.py` (get_ntdll, enable_privilege)
5. Migrate `windows.py` (DISPLAYCONFIG structures, get_user32)
6. Migrate `detector.py` (DEVMODE, DISPLAY_DEVICE, DISPLAYCONFIG)
7. Migrate remaining files

---

## P2: Profiles to YAML

**DEPENDS ON P1 (base class collapse)**

### Profiles to convert (13)

| Profile ID | Current file | Base → YAML `base:` |
|---|---|---|
| rivals2 | rivals2.py | competitive_fps |
| rivals2-offline | rivals2_offline.py | competitive_fps |
| rivals2-online | rivals2_online.py | competitive_fps |
| rivals2-300hz-max | rivals2_300hz_max.py | competitive_fps |
| rivals2-gsync | rivals2_gsync.py | competitive_fps |
| rivals2-online-gsync | rivals2_gsync.py | competitive_fps |
| rivals2-tournament-sim-144hz | rivals2_tournament_sim.py | competitive_fps |
| fortnite | fortnite.py | reflex_shooter |
| marvel-rivals-sdr | marvel_rivals.py | reflex_shooter |
| marvel-rivals-hdr | marvel_rivals.py | reflex_shooter |
| pokemon-auto-chess | pokemon_auto_chess.py | browser |
| pacdeluxe | pacdeluxe.py | browser |
| ryujinx-ssbu | ryujinx_ssbu.py | emulator |

### Profiles staying as Python (14 — have runtime logic or MRO)

| Profile ID | Why |
|---|---|
| slippi-melee (4 variants) | `_detect_dolphin_backend()` runtime logic |
| overwatch2 (3 variants) | Multi-layer `_base_overrides` + `_variant_overrides` |
| diablo4 | Custom handler list + VSync preset override |
| productivity | Custom handler list (no PowerSettingsHandler) |
| *-streaming (5 variants) | OBSStreamingMixin MRO |

### YAML location: `abso/profiles/builtin/`

### Changes to `yaml_loader.py`

Add `load_builtin_directory()`:
```python
def load_builtin_directory(self) -> dict[str, ProfileCatalogEntry]:
    builtin_dir = Path(__file__).parent / "builtin"
    if not builtin_dir.is_dir():
        return {}
    return self.load_directory(builtin_dir)
```

### Changes to `catalog.py`

```python
def _get_full_catalog() -> dict[str, ProfileCatalogEntry]:
    merged = OrderedDict()
    # 1. Built-in YAML profiles
    merged.update(_load_builtin_yaml_profiles())
    # 2. Built-in Python profiles (Slippi, OW2, Diablo, streaming)
    merged.update(PYTHON_PROFILES)
    # 3. User YAML profiles (~/.abso/profiles/)
    merged.update(_load_user_profiles())
    return merged
```

### Conversion process (per profile)

1. Read the Python profile, trace through `_base_settings()` + `_settings_overrides()` to get final resolved settings
2. Write equivalent YAML
3. Verify snapshot test passes with the YAML version
4. Delete the Python file
5. Remove the import from `catalog.py`

### Verification: snapshot test must pass after EACH profile conversion

---

## P7: State Management

**Goal:** Centralize 17 scattered JSON file paths + add atomic write

### `abso/core/state.py`

```python
class StateManager:
    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir or get_data_dir()

    # Centralized path definitions (files stay in current locations)
    @property
    def profile_state(self) -> Path:
        return self._data_dir / ".abso_state.json"

    @property
    def power_switcher_state(self) -> Path:
        return self._data_dir / ".power_switcher_state.json"

    @property
    def fallback_state(self) -> Path:
        return Path.home() / ".abso" / "fallback_state.json"

    @property
    def crash_history(self) -> Path:
        return Path(os.environ.get("LOCALAPPDATA", "")) / "ABSO" / "crash_history.json"

    @property
    def timer_guard(self) -> Path:
        return Path(os.environ.get("TEMP", "")) / "abso_timer_guard.json"

    @property
    def osd_acknowledged(self) -> Path:
        return Path.home() / ".abso" / "color" / "osd_acknowledged.json"

    # Atomic, BOM-safe read/write
    def read_json(self, path: Path) -> dict | None:
        """Read JSON file, handling BOM and errors gracefully."""
        if not path.exists():
            return None
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]  # strip UTF-8 BOM
        return json.loads(raw)

    def write_json(self, path: Path, data: dict) -> None:
        """Atomic write: write to .tmp then rename (no BOM)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
```

### Migration (gradual)

Replace hardcoded paths in each module with `StateManager` imports. Files stay in their current locations — only the path definitions are centralized.

---

## How to Execute Each Phase

### Starting a phase:
```bash
# 1. Verify clean state
python -c "from abso.profiles.catalog import get_profile_manifest; print(len(get_profile_manifest()), 'profiles')"

# 2. Run snapshot baseline
python -c "
import sys; sys.path.insert(0, '.')
from tests.test_snapshot import _build_snapshot, GOLDEN_FILE
import json
current = _build_snapshot()
golden = json.loads(GOLDEN_FILE.read_text(encoding='utf-8'))
diffs = []
for pid in sorted(set(current) | set(golden)):
    if pid not in current or pid not in golden:
        diffs.append(f'MISSING: {pid}')
        continue
    for h in set(current[pid]['settings']) | set(golden.get(pid, {}).get('settings', {})):
        cs = current[pid]['settings'].get(h, {})
        gs = golden.get(pid, {}).get('settings', {}).get(h, {})
        if cs != gs:
            for k in set(cs) | set(gs):
                if cs.get(k) != gs.get(k):
                    diffs.append(f'{pid}.{h}.{k}')
print(f'Diffs: {len(diffs)}' if diffs else 'SNAPSHOT CLEAN')
"
```

### After each phase:
1. Run the snapshot comparison above — must show `SNAPSHOT CLEAN`
2. `python -m abso --help` — all commands present
3. Syntax check modified files
4. Commit and push
