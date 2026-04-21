# Overwatch 2 Keybind Storage — Observed Format

Investigation output for Step 1 of the OW2 per-hero keybind handler prompt
(`docs/OW2_KEYBINDS_IMPLEMENTATION_PROMPT.md`). Branch decision: **not plaintext,
not recoverable via direct INI patching on this machine.** Reasons and evidence
below.

## What was checked

- `%USERPROFILE%\Documents\Overwatch\Settings\Settings_v0.ini` — the file the
  existing `OW2ConfigHandler` already patches.
- `%USERPROFILE%\Documents\Overwatch\Settings\` siblings.
- `%LOCALAPPDATA%\Blizzard Entertainment\Overwatch\` subtree.
- `%APPDATA%\Blizzard Entertainment\` (does not exist on this install).
- Recursive AppData search for `*overwatch*` and `*keybind*` artifacts.

## What was found

### Settings_v0.ini — no keybind data present

File is 2,158 bytes / 100 lines, written today by a recent OW2 session. Full
set of section headers:

```
[Cinematics.1]
[environment.1]
[GPU.6]
[Input.1]
[MovieExport.1]
[Render.13]
[Sound.3]
[TankMenuItems.1]
```

`[Input.1]` contains exactly one line:

```
HighTickInput = "1"
```

No `KeyBinds`, `KeyBindsV2`, `Gamepad.*`, `BindingsHeroScope`, or any other
per-hero-binding region is present anywhere in the file. `grep -i
"keybind|binding|gamepad|hero" Settings_v0.ini` returns zero matches.

The keys that `OW2ConfigHandler.PROTECTED_INI_KEYS` currently guards
(`KeyBinds`, `KeyBindsV2`, `MouseSensitivity*`, `CrosshairSettings*`) are
**not present** in this file either. The protection list is forward-defensive,
not a reflection of current-state contents.

### AppData

```
%LOCALAPPDATA%\Blizzard Entertainment\Overwatch\<buildN>\Hotfix\
```

Nothing but per-build hotfix cache directories — no settings / binding data.
No Roaming\Blizzard folder exists on this machine.

### External config-format.md (pre-existing analysis)

The sister repo `theknower/overwatch/keybinds/config-format.md` (which seeded
the original implementation prompt) already states, plainly:

> The file uses INI-style sections but the binding data inside them is a
> packed/encoded blob, not plain `key = value` pairs. Directly editing the
> bindings section in the .ini is **not** straightforward — the blob is
> versioned and changes break when game patches alter the binding schema.
>
> ...
>
> ### 3. Direct .ini patching (fragile, don't)

That community-sourced characterization matches what we observe: no plaintext
per-hero section lives in the INI that ABSO could target.

## Interpretation

Two compatible explanations for the empty state on this machine:

1. **User has never customized keybinds in-game.** OW2 only materializes the
   `KeyBinds`/`KeyBindsV2` keys once the user has deviated from defaults, and
   even then it writes a packed blob rather than plaintext actions.
2. **OW2 stores binds server-side** under the Battle.net account. The local
   INI keeps only per-machine / render-pipeline state; control bindings sync
   from the cloud on launch. This is consistent with the fact that signing in
   on another PC carries binds across, and with the INI having zero
   keybind-adjacent bytes even after active play.

Either way, **the precondition for the prompt's preferred Step 2A (direct INI
patching of plaintext per-hero sections) is not met on this system.** Writing
to `Settings_v0.ini` for keybinds is either a no-op (keys not present) or — if
the user later customizes a bind and OW2 materializes them — a write into a
packed, versioned blob that is known to break across patches.

## Branch decision

Per the implementation prompt:

> **Plaintext** → Step 2A (direct INI patching, preferred)
> **Packed blob** → Step 2B (share-code fallback). If blob, **stop and
> report back** before writing code — the design branches significantly.

**We are in the "blob" / "not present" branch.** Stopping here per the prompt's
instructions.

## Viable paths forward (not yet chosen)

Each has costs that conflict with one or more hard requirements in the prompt.
User decision needed.

### Path A — Share-code "surface only" handler

`apply()` does not write any system state. It:

1. Derives (or reads a pre-generated) OW2 import-settings share code per
   preset variant.
2. Prints the code to the CLI / tray UI and walks the user through
   Options → Controls → Import Settings manually.
3. `verify_active()` parses whatever OW2 ends up writing and confirms the
   rebinds landed.

- **Pros:** zero risk of collateral mutation, satisfies Requirement 1
  trivially (we write nothing), no LGS / pyautogui dependency.
- **Cons:** not "apply" in the usual ABSO sense. A share code also carries
  sensitivity, crosshair, and other non-keybind settings — so any code we
  ship has to be hand-crafted to contain *only* rebind deltas, which means
  generating it from a pristine account. That's a one-time human step per
  preset variant.

### Path B — OWControls-style UI automation

`apply()` drives Options → Controls via `pywinauto` / `pyautogui`, hero by
hero, action by action, matching on the action-name strings from
`recommendations.json`.

- **Pros:** granular (per-hero, per-action); survives patches as long as
  menu labels are stable; doesn't touch the INI at all.
- **Cons:** requires `Overwatch.exe` to be running and focused — directly
  contradicts Requirement 7 ("refuse apply if Overwatch running"). Slow
  (~1 minute per full preset). Brittle against menu localization and DPI
  scaling. Adds pyautogui / pywinauto as runtime deps (prompt says gate as
  optional extras). Not something to run unattended.

### Path C — Guidance-only handler

`apply()` is a no-op writer. It renders the full preset as a human-readable
"Controls cheat sheet" (per hero, per action, recommended + secondary) into
the audit/apply output and the tray notification. The user applies binds
manually or via OWControls.

- **Pros:** dead simple, no OW2 interaction at all, no platform risk, fits
  naturally into `get_in_game_settings()` which already exists for display
  mode / HDR / FPS cap guidance.
- **Cons:** marketing-wise it's not really "applying keybinds." It is honest
  about what ABSO can safely do with the blob format, though.

### Path D — Skip it

Acknowledge that ABSO is a system-optimization tool and OW2 keybind
management is better served by OWControls directly. Close the prompt without
implementation. Surface the recommendations JSON as a linked reference from
the existing OW2 profile docs.

## Recommended path

**Path C** for the first cut — it's the only option that honors all of:

- Requirement 1 (surgical writes; here, zero writes)
- Requirement 4 (`restore_guarantee = "full"`; here, vacuously "full" since
  we never mutated anything)
- Requirement 7 (refuse apply if OW2 running; here, irrelevant because we
  don't touch OW2 files)
- "Do not add runtime deps beyond `jsonschema`" (Path B would add
  pywinauto/pyautogui)
- The existing `get_in_game_settings()` pattern already in
  `overwatch2.py`, which is the right home for per-action guidance

Path C still lets us ship the `overwatch2-keybinds*` profile variants, the
mixin, the schema-validated recommendations loader, and the full audit
integration. The only thing it declines to do is automate the in-game binding
UI — and that declination is earned by the observed file format, not a
cop-out.

If the user wants actual automated rebinds later, Path B (OWControls-style
automation) can be added behind the `pywinauto` optional extra, with
Requirement 7 explicitly amended for that handler alone ("requires OW2
running, launches and drives Options → Controls, then exits menu").

## Open questions for the user

1. Do you want to proceed with **Path C** (guidance-only handler that renders
   the preset into tray/CLI output), or a different path from the list above?
2. If Path C: should the handler's `apply()` return `success=True, skipped=...`
   with the guidance payload in `notices`, or should it fail-closed until we
   have a way to verify binds landed?
3. If later Path B is wanted, is pywinauto an acceptable optional extra, or
   would you rather ABSO shell out to an external OWControls binary?

## Verification data (reproducibility)

```
$ ls "C:\Users\mtoli\Documents\Overwatch\Settings\"
Settings_v0.ini

$ wc -l "Settings_v0.ini"
100

$ grep -niE "keybind|binding|gamepad|hero" Settings_v0.ini
(no matches)

$ head -3 "[Input.1]" section:
[Input.1]
HighTickInput = "1"
(blank line)
```

File mtime at investigation time: 2026-04-18 23:35 local, consistent with a
recent OW2 session exit (OW2 rewrites Settings_v0.ini on exit).

Anything that assumes plaintext per-hero sections will be a no-op against this
file. That has to be the starting assumption for whatever path is chosen next.
