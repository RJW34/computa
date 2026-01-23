# NVAPI Integration Plan

## Problem Statement

ABSO currently cannot read NVIDIA 3D profile settings before modifying them. This means:
1. We cannot detect current settings to audit them
2. We cannot merge changes - we can only replace entire profiles
3. Users' carefully tuned global settings can be accidentally reset

## Current Architecture

```
User → ProfileApplier → NvidiaSettingsHandler → NPIManager → NPI.exe
                                                      ↓
                                              .nip XML file
```

**Limitations:**
- `nvidia-smi`: Only queries hardware metrics (power, temp, clocks), not 3D settings
- `pynvml`: Same as nvidia-smi - hardware only
- Registry: 3D settings stored in binary driver database, not readable registry keys
- NPI: Requires GUI for export, only supports `-silent` for import

## Solution: Direct NVAPI Integration

NVAPI is NVIDIA's C API that NPI uses internally. We can call it directly via ctypes.

### Phase 1: Read-Only Detection (Priority: HIGH)

**Goal:** Detect current 3D settings without modifying anything.

**Key NVAPI Functions:**
```c
// Initialize
NvAPI_Initialize()

// Get session handle
NvAPI_DRS_CreateSession(NvDRSSessionHandle *phSession)

// Load settings from driver
NvAPI_DRS_LoadSettings(NvDRSSessionHandle hSession)

// Get base profile (global settings)
NvAPI_DRS_GetBaseProfile(NvDRSSessionHandle hSession, NvDRSProfileHandle *phProfile)

// Read a setting value
NvAPI_DRS_GetSetting(NvDRSSessionHandle hSession, NvDRSProfileHandle hProfile,
                     NvU32 settingId, NVDRS_SETTING *pSetting)

// Cleanup
NvAPI_DRS_DestroySession(NvDRSSessionHandle hSession)
```

**Implementation Steps:**

1. **Create `abso/settings/nvidia/nvapi.py`**
   - Load `nvapi64.dll` via ctypes
   - Define necessary structures (NVDRS_SETTING, etc.)
   - Implement `NvapiReader` class with `detect()` method

2. **Setting IDs to Read:**
   ```python
   SETTINGS_TO_DETECT = {
       0x10834BB: "low_latency_mode",      # Low Latency Mode
       0x10834E4: "power_management",       # Power Management Mode
       0x10834F8: "vsync",                  # Vertical Sync
       0x10835F7: "max_frame_rate",         # Max Frame Rate
       0x10835FE: "shader_cache",           # Shader Cache Size
       0x10835E8: "threaded_optimization",  # Threaded Optimization
       0x10834FC: "triple_buffering",       # Triple Buffering
       0x10A879CF: "vrr_app_override",      # G-Sync per-app control
       # Additional settings for comprehensive detection:
       0x1085B0E: "texture_filtering_quality",
       0x1085BA9: "anisotropic_filtering",
       0x10E41DF: "antialiasing_mode",
   }
   ```

3. **Update `NvidiaSettingsHandler.detect()`**
   ```python
   def detect(self) -> dict[str, Any]:
       result = self._detect_gpu_info()  # nvidia-smi

       # NEW: Read 3D settings via NVAPI
       nvapi = NvapiReader()
       if nvapi.is_available():
           result["3d_settings"] = nvapi.read_base_profile_settings()

       return result
   ```

### Phase 2: Smart Merge/Apply (Priority: MEDIUM)

**Goal:** Only change settings that differ from desired state.

**Approach A: Read-Modify-Write via NVAPI**
```python
def apply_with_merge(self, desired_settings: dict) -> dict:
    # 1. Read current settings
    current = self.nvapi.read_base_profile_settings()

    # 2. Compute delta
    changes_needed = {}
    for key, desired_value in desired_settings.items():
        if current.get(key) != desired_value:
            changes_needed[key] = desired_value

    # 3. Apply only changes via NVAPI (no NPI needed)
    for setting_id, value in changes_needed.items():
        self.nvapi.set_setting(setting_id, value)

    # 4. Save changes
    self.nvapi.save_settings()
```

**NVAPI Write Functions:**
```c
NvAPI_DRS_SetSetting(NvDRSSessionHandle hSession, NvDRSProfileHandle hProfile,
                     NVDRS_SETTING *pSetting)
NvAPI_DRS_SaveSettings(NvDRSSessionHandle hSession)
```

**Approach B: Keep NPI for writes, use NVAPI only for reads**
- Simpler, less risk of breaking things
- Still generates full .nip files but at least we can detect first

### Phase 3: Full Audit Capability (Priority: MEDIUM)

**Goal:** Compare current settings against optimal and report issues.

```python
def audit(self) -> list[Issue]:
    current = self.detect()["3d_settings"]
    optimal = OPTIMAL_GAMING_SETTINGS

    issues = []
    for setting, optimal_value in optimal.items():
        current_value = current.get(setting)
        if current_value != optimal_value:
            issues.append(Issue(
                title=f"{setting} not optimal",
                current_value=current_value,
                optimal_value=optimal_value,
                # ...
            ))
    return issues
```

## Technical Details

### NVAPI DLL Location
```
C:\Windows\System32\nvapi64.dll  (64-bit)
C:\Windows\SysWOW64\nvapi.dll    (32-bit)
```

### Ctypes Structure Definitions

```python
import ctypes
from ctypes import wintypes

# NVAPI uses its own types
NvU32 = ctypes.c_uint32
NvAPI_Status = ctypes.c_int
NvDRSSessionHandle = ctypes.c_void_p
NvDRSProfileHandle = ctypes.c_void_p

NVAPI_UNICODE_STRING_MAX = 2048
NVAPI_SETTING_MAX_VALUES = 100

class NVDRS_SETTING(ctypes.Structure):
    _fields_ = [
        ("version", NvU32),
        ("settingName", ctypes.c_wchar * NVAPI_UNICODE_STRING_MAX),
        ("settingId", NvU32),
        ("settingType", NvU32),
        ("settingLocation", NvU32),
        ("isCurrentPredefined", NvU32),
        ("isPredefinedValid", NvU32),
        # Union for value - simplified
        ("u32CurrentValue", NvU32),
        ("u32PredefinedValue", NvU32),
    ]
```

### Error Handling

```python
NVAPI_OK = 0
NVAPI_ERROR = -1
NVAPI_LIBRARY_NOT_FOUND = -2
# ... etc

def check_status(status: int, operation: str):
    if status != NVAPI_OK:
        raise NvapiError(f"{operation} failed with status {status}")
```

## File Structure

```
abso/settings/nvidia/
├── __init__.py          # NvidiaSettingsHandler (existing)
├── npi.py               # NPIManager (existing)
├── nvapi.py             # NEW: Direct NVAPI integration
├── nvapi_types.py       # NEW: Ctypes structures
├── parsing.py           # NIP file parsing (existing)
├── presets.py           # Preset definitions (existing)
└── profiles.py          # Profile generation (existing)
```

## Testing Strategy

1. **Unit Tests** (`tests/test_handlers/test_nvapi.py`)
   - Mock NVAPI DLL for CI environments
   - Test structure packing/unpacking
   - Test setting value conversions

2. **Integration Tests** (local only, requires NVIDIA GPU)
   - Read current settings
   - Verify against NPI export
   - Round-trip: read → change → read back

3. **Safety Tests**
   - Ensure read-only operations don't modify settings
   - Verify backup before any write operation

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| NVAPI version changes | Struct layouts may change | Version check, graceful fallback to NPI |
| DLL not found | Non-NVIDIA systems | Check availability, skip gracefully |
| Permission issues | Need admin for writes | Already require admin elevation |
| Driver-specific quirks | Some settings may behave differently | Test across driver versions |

## Timeline Estimate

- **Phase 1 (Read-Only):** 4-6 hours
  - Ctypes setup: 2h
  - Read implementation: 2h
  - Testing: 2h

- **Phase 2 (Merge/Apply):** 4-6 hours
  - Write implementation: 2h
  - Merge logic: 2h
  - Testing: 2h

- **Phase 3 (Full Audit):** 2-3 hours
  - Audit logic: 1h
  - Optimal settings research: 1h
  - Testing: 1h

## References

- [NVAPI Reference](https://docs.nvidia.com/gameworks/content/gameworkslibrary/coresdk/nvapi/group__drsapi.html)
- [NPI Source (for reference)](https://github.com/Orbmu2k/nvidiaProfileInspector)
- [Python ctypes docs](https://docs.python.org/3/library/ctypes.html)

## Immediate Fix (Completed)

While NVAPI integration is developed, we've reverted to per-game profiles:

1. NVIDIA settings are applied as **per-game profiles** targeting specific executables
2. The user's **global Base Profile is never modified**
3. Users can still tune global settings in NVCP without ABSO overwriting them

This is a safe interim solution that prevents the "config nuke" bug.
