# Implementation Prompt — OW2 Per-Hero Keybind Handler

**Paste this entire file into Claude Code running in the `windowsoptimizerabso` repo. It is self-contained — it briefs the agent on the existing code, the source data, the hardware, and the hard constraints.**

---

## Goal

Extend ABSO's Overwatch 2 profile family so that applying a profile can also apply per-hero keybind rebinds sourced from an external JSON file, **without touching any other part of `Settings_v0.ini`** (no sensitivity, no crosshair, no render, no audio, no video, no communication binds).

Output: a new `OW2KeybindsHandler` following the existing `SettingsHandler` pattern, new `overwatch2-keybinds*` profile variants, tests, and format documentation.

---

## Hardware context — Logitech G602 HERO

The user's mouse is a Logitech G602 HERO (11 programmable buttons). Relevant facts:

- Front thumb buttons **G4 and G5** transmit standard HID `Mouse 4` / `Mouse 5`. Overwatch sees these natively — no Logitech software needed.
- Back thumb buttons **G6–G9** do **not** transmit standard mouse HID codes. They only produce output when Logitech Gaming Software (LGS / `lcore.exe`) is running with a profile mapping them to keyboard keys.
- The source `recommendations.json` only uses `MOUSE 4`, `MOUSE 5`, scroll wheel, and standard keyboard keys — all G602-native — so the baseline preset requires **zero LGS configuration**.
- **Do not** auto-configure LGS. Out of scope. Only surface a `preflight()` warning if a future preset requests a key the G602 can't produce natively and LGS isn't detected.

---

## Files you MUST read before writing any code

In `windowsoptimizerabso/`:
- `CLAUDE.md` — architecture overview and constraints
- `abso/settings/base.py` — `SettingsHandler` ABC (detect/audit/apply/backup/restore + optional `preflight`, `verify_active`, `restore_guarantee`)
- `abso/settings/ow2_config.py` — existing OW2 INI handler. **Read in full.** It already implements the snapshot-and-verify pattern for protected keys, idempotent upsert, drift detection, and full-file backup/restore. You will mirror this structure.
- `abso/profiles/overwatch2.py` — profile definitions, `get_handlers()`, `_base_overrides()`, `_variant_overrides()` flow
- `abso/profiles/profile_bases.py` — the `ReflexShooterBaseProfile` superclass
- `abso/profiles/catalog.py` — where new profile variants get registered
- `abso/core/config_safety.py` — shared INI safety helpers (`validate_allowed_keys`, maybe `apply_ini_key_patch`)
- `abso/core/models.py` — `Issue` dataclass

In the user's knowledge base:
- `C:\Users\mtoli\Documents\Code\theknower\overwatch\keybinds\recommendations.json` — **source of truth.** 50 heroes, OWControls-compatible keycode vocabulary.
- `C:\Users\mtoli\Documents\Code\theknower\overwatch\keybinds\schema.json` — JSON Schema. Use `jsonschema` (already in tree? confirm — else gate the validation behind an optional import).
- `C:\Users\mtoli\Documents\Code\theknower\overwatch\keybinds\config-format.md` — three integration paths (UI automation, share code, direct INI patch) with tradeoffs.
- `C:\Users\mtoli\Documents\Code\theknower\overwatch\keybinds\key-reference.md` — the full OWControls keycode list (`LSHIFT`, `MOUSE 4`, `MOUSE WHEEL UP`, OEM_*, etc).

---

## Hard requirements

Read twice. These aren't guidelines.

### 1. Surgical writes — no collateral mutation

The handler may ONLY mutate INI sections that carry per-hero keybind data. It must NOT touch:

- `[Render.X]` sections (owned by `OW2ConfigHandler`)
- Any line containing `MouseSensitivity`, `MouseSensitivityY`, `MouseSensitivityHero`, `CrosshairSettings`, `CrosshairSettingsV2`, or any other key currently listed in `OW2ConfigHandler.PROTECTED_INI_KEYS` that is not a keybind
- Audio / communication / video / accessibility sections
- Global-scope ("All Heroes") bindings unless explicitly opted in via a separate setting — default off

### 2. Snapshot-and-verify pattern

Mirror `OW2ConfigHandler._snapshot_protected()` + post-apply verification + drift detection. Specifically:

1. Read the file into memory once.
2. Compute a hash/snapshot of every line that is NOT inside a per-hero binding section (i.e. "everything we claim not to touch").
3. Apply rebind mutations to the in-memory line list.
4. Re-compute the snapshot over the mutated in-memory file.
5. If the snapshot changed outside the keybind scope, **abort** — do not write. Return `{"success": False, "error": "non-keybind mutation detected: <list>"}`.
6. Only write the file if the snapshot is identical AND at least one keybind section changed.
7. Re-read the written file and run drift detection (mirror `_detect_post_apply_drift`). If Overwatch clobbered the file between write and re-read, surface a clear notice.

### 3. Idempotent

Applying the same keybind preset twice produces zero mutations on the second call. Verify via a new `verify_active()` that re-parses bindings and reports target vs current.

### 4. Backup and restore

`backup()` returns the full `Settings_v0.ini` content exactly like `OW2ConfigHandler.backup()` already does. `restore()` writes it back verbatim. `restore_guarantee` is `"full"`. ABSO's backup manager handles timestamped folders — you just need to return/accept the content.

### 5. Ownership boundary with `OW2ConfigHandler`

`OW2ConfigHandler.PROTECTED_INI_KEYS` currently includes `KeyBinds` and `KeyBindsV2`. The new handler needs to write to keybind-bearing regions. Resolve the ownership conflict by introducing shared constants:

```python
# abso/core/config_safety.py (or a new abso/core/ow2_scopes.py)

OW2_RENDER_OWNED_SECTIONS = frozenset({"Render"})      # [Render.X] — owned by OW2ConfigHandler
OW2_KEYBIND_OWNED_SECTION_PREFIXES = frozenset({        # owned by OW2KeybindsHandler
    # fill in from Step 1 below — e.g. "CustomGame.BindingsHeroScope",
    # "Gamepad.0.BindingsHeroScope", whatever the actual layout uses
})

OW2_SENSITIVITY_KEYS = frozenset({
    "MouseSensitivity", "MouseSensitivityY", "MouseSensitivityHero",
})
OW2_CROSSHAIR_KEYS = frozenset({
    "CrosshairSettings", "CrosshairSettingsV2",
})
# Sensitivity + crosshair keys are protected from BOTH handlers.
```

Then have both handlers enforce their respective scopes and assert the shared never-touch set. Update `OW2ConfigHandler.PROTECTED_INI_KEYS` to import the shared constants. Assert in tests that neither handler can modify keys owned by the other.

### 6. Opt-in — do not apply by default

Existing `overwatch2*` profiles must continue to work exactly as they do today. Add opt-in variants:

- `overwatch2-keybinds` (no-sync + keybinds)
- `overwatch2-gsync-keybinds`
- `overwatch2-gsync-hdr-keybinds`
- `overwatch2-gsync-capture-keybinds`
- `overwatch2-gsync-hdr-capture-keybinds`

Use a mixin pattern to avoid combinatorial copy-paste:

```python
class _KeybindsMixin:
    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        base = super()._variant_overrides()
        base.setdefault("OW2KeybindsHandler", {}).update({
            "apply_keybinds": True,
            "min_confidence": "high",
        })
        return base

class Overwatch2KeybindsProfile(_KeybindsMixin, Overwatch2Profile):
    @property
    def profile_id(self) -> str: return "overwatch2-keybinds"
    @property
    def display_name(self) -> str: return "Overwatch 2 - No-Sync + Keybinds"
```

### 7. Live-game safety

If `Overwatch.exe` is running when `apply()` is called, refuse: OW2 rewrites `Settings_v0.ini` on exit and will overwrite anything you just wrote. `preflight()` checks `tasklist` / `psutil`, returns `{"success": False, "error": "close Overwatch before applying keybinds"}`.

---

## Step-by-step

### Step 1 — Reverse-engineer the OW2 per-hero binding INI layout

**Do this first. Nothing else proceeds without it.**

1. Call `_get_ow2_settings_path()` (reuse the helper in `abso/settings/ow2_config.py`).
2. Run `grep -nE '^\[' Settings_v0.ini | head -200` — enumerate every section header.
3. Find the section(s) carrying per-hero bindings. Candidates from community reverse-engineering: `[CustomGame.BindingsHeroScope.N]`, `[Gamepad.0.BindingsHeroScope.N]`, `[Input.0.BindingsHeroScope.N]`. The hero is identified somehow — either by index with a lookup table, or by a `CustomGameName = "Ana"` key inside the section.
4. Identify whether values are plaintext `Action = "Key"` pairs (like `[Render.X]`) or a packed/base64 blob.
5. Change one bind in-game (e.g. Ana's Sleep Dart → Mouse 4), save, quit, diff the INI. Document the diff.

**Write what you found to `docs/ow2-keybinds-format.md`** with example diff snippets. Do not proceed to Step 2 before writing that doc — future agents will need it, and if you skip it you'll end up redoing this investigation.

**Branch decision:**
- **Plaintext** → Step 2A (direct INI patching, preferred — mirrors `OW2ConfigHandler`)
- **Packed blob** → Step 2B (share-code fallback). If blob, **stop and report back** before writing code — the design branches significantly.

### Step 2A — Direct INI patching (preferred)

Create `abso/settings/ow2_keybinds.py` with `OW2KeybindsHandler(SettingsHandler)`. Reuse the patterns from `ow2_config.py`:

- `_find_hero_binding_sections(lines) -> dict[str, tuple[int, int]]` — returns `{hero_id: (start, end)}`
- `_parse_hero_bindings(lines, start, end) -> dict[str, str]` — action → key for one hero
- `_upsert_binding(lines, start, end, action, key) -> tuple[lines, changed, appended]`
- `_apply_to_hero_sections(lines, replacements) -> tuple[lines, changed_keys, appended_keys]`
- Build a translation table `OWCONTROLS_TO_OW_INI` for keycodes — derive empirically from Step 1's diffs (e.g. `MOUSE 4 → BUTTON_4` or whatever the INI uses)

Supported settings for the handler:

| Key | Type | Default | Meaning |
|---|---|---|---|
| `apply_keybinds` | bool | `False` | Master switch. Unless True, `apply()` is a no-op. |
| `min_confidence` | `"high"|"medium"|"low"` | `"high"` | Filter rebinds below this threshold. "high" gives the pro-only preset. |
| `heroes` | `list[str] \| None` | `None` | If set, restrict to these hero IDs; else all heroes in the JSON. |
| `skip_fictional` | bool | `True` | Skip any hero with `fictional: true` in the JSON. |
| `recommendations_path` | `str \| None` | `None` | Override source JSON path for tests. Defaults to the theknower location. |
| `apply_secondary` | bool | `True` | Whether to also write the optional `secondary` bind. |

### Step 2B — Share-code fallback (only if Step 1 finds a blob)

1. Create `data/ow2-keybind-presets/` with one `.txt` file per preset variant containing the OW2 "Import Settings" share code. Generate these manually one time from a rig with the recommendations already applied in-game.
2. `apply()` uses `pyautogui` + `pywinauto` to navigate Options → Controls → Import Settings and paste the code.
3. Requires `Overwatch.exe` running — contradicts Requirement 7. Resolve by either: (a) launching OW specifically for the import then closing it, or (b) documenting the share-code path as a manual step and the handler just prints the code for the user to paste.
4. Add `pyautogui` as an **optional** extra in `pyproject.toml` — gate its import behind a try/except with a clear error if missing and Step 2B is taken.
5. Don't go down this path without reporting back. Slower, more fragile, more moving parts.

### Step 3 — Wire into profiles

In `abso/profiles/overwatch2.py`:

1. `_Overwatch2BaseProfile.get_handlers()` appends `OW2KeybindsHandler()` alongside `OW2ConfigHandler()`.
2. Add `"OW2KeybindsHandler": {"apply_keybinds": False}` to `_base_overrides()` — existing profiles unchanged.
3. Implement `_KeybindsMixin` as shown in Requirement 6.
4. Define the five `*-keybinds` concrete variants using the mixin.
5. Register all five in `abso/profiles/catalog.py`.
6. Extend `get_in_game_settings()` output with a "Controls" section summarizing rebinds when keybinds are enabled (read from the JSON and list them).
7. Update the profile lists in `CLAUDE.md` ("Available Profiles") and `README.md` to include the new variants.

### Step 4 — Tests

Create `tests/test_ow2_keybinds.py`. **All tests must operate on a synthetic `Settings_v0.ini` fixture in `tmp_path`** — never touch the user's real config.

Required tests:

1. `test_apply_keybinds_false_is_noop` — default settings → file bytes unchanged
2. `test_non_keybind_sections_untouched` — apply with `apply_keybinds=True`, diff the file, assert every section that isn't a per-hero binding section is byte-identical pre vs post. Include synthetic `[Render.13]`, `MouseSensitivity`, `CrosshairSettings` lines in the fixture.
3. `test_protected_ini_keys_untouched` — explicitly pre-seed `MouseSensitivity = "3.14"` and a crosshair blob; assert they are unchanged
4. `test_idempotent` — apply twice, second call reports zero changes
5. `test_min_confidence_filter` — `"high"` applies strictly fewer rebinds than `"low"` (use a mocked JSON with a mix)
6. `test_fictional_heroes_skipped` — hero with `fictional: true` gets no mutations (currently no heroes are flagged, but schema still supports it)
7. `test_missing_recommendations_file` — returns `{"success": True, "skipped": "..."}` with clear message; never crashes
8. `test_missing_settings_v0_ini` — matches existing `OW2ConfigHandler` behavior (skip silently if OW2 not installed)
9. `test_backup_restore_roundtrip` — apply, capture backup, mutate file further, restore — file is byte-identical to post-apply state
10. `test_overwatch_running_refuses_apply` — mock psutil to report `Overwatch.exe` running; `preflight()` returns failure
11. `test_ownership_boundary_ow2_config_cannot_write_keybinds` — call `OW2ConfigHandler.apply({"keybind_something": ...})` somehow; assert the protected-keys check still trips
12. `test_schema_validation` — the shipped `recommendations.json` validates against the schema (use `jsonschema`)
13. `test_keycode_translation_roundtrip` — for every key in the recommendations file, the OWControls → INI translation is non-null and reversible

### Step 5 — Audit integration

`OW2KeybindsHandler.audit()` returns informational `Issue` objects:

- `severity="info"` — rebinds configured but `apply_keybinds=False` (user might have forgotten to enable)
- `severity="info"` — current in-game bind differs from recommended for a given hero (don't flag as `warning` — may be intentional)
- `severity="warning"` — Overwatch currently running
- `severity="warning"` — recommendations file is older than 90 days (patch may have changed defaults)

### Step 6 — G602 preflight polish

In `preflight()`:

- Parse the full set of `recommended` + `secondary` keys that the current settings will apply.
- For each, check if it's in the "G602-native" set: `{MOUSE LEFT CLICK, MOUSE RIGHT CLICK, MOUSE MIDDLE CLICK, MOUSE 4, MOUSE 5, MOUSE WHEEL UP, MOUSE WHEEL DOWN}` + any keyboard key.
- If any key falls outside that set, check for `lcore.exe` in running processes (G602 uses LGS, not G HUB).
- If LGS not running, add a **warning** (not a block) saying the user may need to configure LGS to translate that button to a keyboard key.
- The current `recommendations.json` uses only G602-native keys — this check is future-proofing.

---

## Definition of done

- `python -m abso apply overwatch2-keybinds` completes without error on a system with OW2 installed and closed
- `diff` of `Settings_v0.ini` pre vs post shows changes **only** inside per-hero binding sections
- `python -m abso restore latest` produces a byte-identical `Settings_v0.ini` to the pre-apply state
- `pytest tests/test_ow2_keybinds.py` passes
- Existing `pytest tests/` passes — no regressions in `overwatch2`, `overwatch2-gsync`, or any other profile
- `docs/ow2-keybinds-format.md` documents the INI layout you discovered in Step 1
- `CLAUDE.md` and `README.md` list the new variants
- Running `python -m abso audit` on the user's machine produces sensible output — no false positives, no crashes

---

## Things to NOT do

- **Do not** narrow or delete `OW2ConfigHandler.PROTECTED_INI_KEYS` without implementing the shared-ownership refactor (Requirement 5). Both handlers must enforce the boundary.
- **Do not** mutate any section outside per-hero binding scope even if you "know" it's sub-optimal. That's the user's call.
- **Do not** ship changes to unrelated profiles (fortnite, marvel-rivals, rivals2, etc). Keep the diff surgical.
- **Do not** auto-configure Logitech Gaming Software. The G602's extra thumb buttons are out of scope.
- **Do not** launch `Overwatch.exe`. Ever. (Exception: Step 2B share-code fallback, if blob forces it — and only after reporting back.)
- **Do not** add runtime dependencies beyond `wmi`, `pywin32`, `click`, `rich`, `pyyaml`, `jsonschema`. Gate `pyautogui` / `pywinauto` as optional extras.
- **Do not** mark the task "done" if any test is xfailed or skipped without a written justification in the test docstring.

---

## First actions, in order

1. Read the files under "Files you MUST read before writing any code"
2. Execute Step 1's INI investigation on the user's actual `Settings_v0.ini`
3. Write `docs/ow2-keybinds-format.md` with the layout findings + example diffs
4. **Report back with the layout (plaintext vs blob) and the identifier format you observed.** Do not write `ow2_keybinds.py` until that's confirmed — the whole design branches here.
5. After confirmation, proceed Step 2A or 2B as appropriate.

---

## Source-of-truth paths (copy these exactly)

```
recommendations JSON:  C:\Users\mtoli\Documents\Code\theknower\overwatch\keybinds\recommendations.json
JSON schema:           C:\Users\mtoli\Documents\Code\theknower\overwatch\keybinds\schema.json
config format notes:   C:\Users\mtoli\Documents\Code\theknower\overwatch\keybinds\config-format.md
key vocabulary:        C:\Users\mtoli\Documents\Code\theknower\overwatch\keybinds\key-reference.md
OW2 settings file:     %USERPROFILE%\Documents\Overwatch\Settings\Settings_v0.ini
```
