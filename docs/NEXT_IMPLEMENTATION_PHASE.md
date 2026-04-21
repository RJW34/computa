# Next Implementation Phase

This document turns the April 8, 2026 whole-product audit into the next concrete execution phase.

Current verified repo state for this phase:

- commit baseline when this phase opened: `c90f5cf`
- live catalog size: `39` profiles
- full verification on implementation host after current code work: `1217 passed, 3 skipped`
- profiles with an explicit game/emulator config handler in the live manifest: `29`
- profiles without an explicit game/emulator config handler in the live manifest: `10`

The important interpretation is:

- A.B.S.O. is now a real multi-layer profile engine.
- It is not yet end-to-end for every shipped gaming family.
- The highest-value remaining product gap is not tray/UI truth anymore.
- The highest-value remaining gap is profile completeness plus post-apply proof.

## Verified Gap Summary

These facts were re-verified from the current working repo and current local machine state on April 8, 2026.

### Families already using explicit game/emulator config handlers

- Overwatch 2 via [OW2ConfigHandler](../abso/profiles/overwatch2.py)
- Rivals 2 via [Rivals2ConfigHandler](../abso/profiles/profile_bases.py)
- Slippi via [DolphinConfigHandler](../abso/profiles/slippi_melee.py)
- Fortnite via [FortniteConfigHandler](../abso/profiles/fortnite.py)
- Marvel Rivals via [MarvelRivalsConfigHandler](../abso/profiles/marvel_rivals.py)

### Shipped families still missing explicit game/emulator config enforcement

- Diablo 4:
  - current profile stack in [diablo4.py](../abso/profiles/diablo4.py)
  - current local game prefs expose native HDR, refresh, VSync, and Reflex in `%USERPROFILE%\Documents\Diablo IV\LocalPrefs.txt`
- Ryujinx SSBU / HewDraw Remix:
  - current profile stack in [ryujinx_ssbu.py](../abso/profiles/ryujinx_ssbu.py)
  - still inherits the generic emulator base without emulator config enforcement in [profile_bases.py](../abso/profiles/profile_bases.py)

### Post-apply proof is still narrower than the product goal

- `verify_profile()` only checks handlers that implement `verify_active` in [applier.py](../abso/core/applier.py#L707).
- Compliance only treats a narrow subset of verify mismatches as critical in [compliance.py](../abso/core/compliance.py#L81).
- NVIDIA is still intentionally non-restorable in [abso/settings/nvidia/__init__.py](../abso/settings/nvidia/__init__.py#L89).

## Phase Goal

Bring the remaining major gaming families to the same architectural standard as Overwatch, Rivals 2, Fortnite, Marvel Rivals, and Slippi:

- explicit game/emulator config enforcement where the title exposes tunable state
- explicit SDR/HDR correctness where native HDR exists
- explicit sync/display-path modeling
- post-apply verification for the new handler paths
- tray/catalog parity after every matrix change

This phase is complete when:

1. Diablo 4 is end-to-end.
2. Ryujinx SSBU is end-to-end or explicitly contract-limited.
3. Verification coverage is expanded enough that those families are no longer "mostly OS-level" profiles.

## Progress Update

Implemented locally in the current working tree:

- `PR-17` completed:
  - added `Diablo4ConfigHandler`
  - wired Diablo 4 HDR/SDR profiles into native `LocalPrefs.txt` enforcement
  - added backup/restore and verification coverage
- `PR-20` materially advanced:
  - added `verify_active` support for `PowerSettingsHandler`
  - added `verify_active` support for `NetworkSettingsHandler`
  - added `verify_active` support for `RegistrySettingsHandler`
  - added `verify_active` support for `MouseSettingsHandler`
  - added `verify_active` support for `ProcessPriorityHandler`
  - expanded compliance criticality for these verified handlers
- `PR-18` and `PR-19` moved from optimistic to honest:
  - Ryujinx now surfaces `system_only` application scope instead of implying end-to-end native config enforcement
  - tray/catalog descriptions now state that the emulator still relies on manual tuning

Still open after this implementation pass:

- a true Ryujinx config handler or a fork-safe explicit config contract
- additional verification coverage for lower-priority handlers such as OBS, color, affinity, and CNM where worth enforcing

## Scope Rules

- Do not add brand-new game families in this phase.
- Do not broaden "optimal" claims in this phase.
- Do not create HDR variants for games that do not expose meaningful native HDR.
- If a title lacks stable config ownership or safe write semantics, fail closed and document the contract limit.

## PR Slices

### PR-17: Diablo 4 Native Config Handler

Owner: `Handlers` + `Profiles & Evidence`

Objective:

- add a Diablo 4 config handler so the shipped SDR/HDR profiles control native game state, not just Windows/NVIDIA state

Expected grade lift:

- Optimization Capability: `B-` -> `B`
- Mechanical Correctness: `B-` -> `B`

Files:

- `abso/settings/diablo4_config.py`
- [abso/profiles/diablo4.py](../abso/profiles/diablo4.py)
- [abso/profiles/catalog.py](../abso/profiles/catalog.py)
- [abso/tray/ABSO-Tray.ps1](../abso/tray/ABSO-Tray.ps1)
- `tests/test_handlers/test_diablo4_config.py`
- [tests/test_profiles.py](../tests/test_profiles.py)

Local evidence already verified:

- `%USERPROFILE%\Documents\Diablo IV\LocalPrefs.txt` currently exposes:
  - `DisplayModeWindowMode`
  - `DisplayModeRefreshRate`
  - `DisplayModeColorSpace`
  - `HDRBlackPoint`
  - `HDRWhitePoint`
  - `HDRBrightness`
  - `Vsync`
  - `Reflex`

Tasks:

- parse and mutate Diablo IV native prefs safely
- enforce SDR/HDR lane correctness in native prefs, not only in Windows
- enforce window mode / sync alignment with the shipped VRR lane
- back up and restore the file losslessly
- implement `verify_active`

Acceptance:

- Diablo 4 profiles append a Diablo-specific config handler
- HDR and SDR variants both control native Diablo IV config
- handler has round-trip backup/restore tests
- handler has verify tests

### PR-19: Ryujinx Config Enforcement Or Explicit Contract Limit

Owner: `Handlers` + `Profiles & Evidence`

Objective:

- stop treating Ryujinx as fully optimized if ABSO is not actually controlling emulator config

Expected grade lift:

- UI/Truthfulness and Optimization Capability both improve modestly

Files:

- [abso/profiles/ryujinx_ssbu.py](../abso/profiles/ryujinx_ssbu.py)
- candidate handler file under `abso/settings/`
- [abso/profiles/catalog.py](../abso/profiles/catalog.py)
- tests

Tasks:

- detect current Ryujinx or Ryubing config ownership on the validation host
- decide whether the emulator config is stable enough for enforcement
- if stable: implement handler plus verification
- if unstable or missing on target hosts: keep the profile but explicitly classify it as system-level plus guidance-only

Acceptance:

- Ryujinx is either truly end-to-end or honestly bounded
- no silent “guidance-only but presented as fully applied” state remains

### PR-20: Verification Expansion For Remaining High-Impact System Handlers

Owner: `Handlers` + `Core Systems`

Objective:

- improve closed-loop proof for profiles that still lean heavily on shared OS/system handlers

Expected grade lift:

- Mechanical Correctness: `B` -> `B+`
- Post-apply proof: `C+` -> `B`

Priority handlers:

- [PowerSettingsHandler](../abso/settings/power.py)
- [NetworkSettingsHandler](../abso/settings/network.py)
- [ProcessPriorityHandler](../abso/settings/process_priority.py)
- [RegistrySettingsHandler](../abso/settings/registry.py)
- [MouseSettingsHandler](../abso/settings/mouse.py)
- [ColorProfileSettingsHandler](../abso/settings/color.py)

Tasks:

- add `verify_active` to the handlers that are still apply-only
- update [compliance.py](../abso/core/compliance.py) to classify new criticality correctly
- make family-specific criticality data-driven, not just handler-name-driven

Acceptance:

- the profiles touched in PR-17/18/19 have materially deeper post-apply proof
- compliance output distinguishes:
  - verified active
  - verified mismatch
  - pending reboot
  - unverified

## Recommended Execution Order

1. PR-17 Diablo 4
2. PR-20 verification expansion groundwork
3. PR-19 Ryujinx

Reason:

- Diablo has verified local native config evidence already.
- Verification groundwork helps the later family slices land on a stronger foundation.
- Ryujinx needs more discovery and may require a contract-bound outcome instead of an immediate full handler.

## Commands To Run For Every Slice

At minimum:

1. `py -m pytest -q`
2. `npm run lint`
3. `npm run build`
4. `cargo check`
5. PowerShell parse for [ABSO-Tray.ps1](../abso/tray/ABSO-Tray.ps1) if tray/catalog metadata changed

For handler slices:

1. focused handler tests
2. [tests/test_profiles.py](../tests/test_profiles.py)
3. [tests/test_profiles_catalog.py](../tests/test_profiles_catalog.py)
4. [tests/test_tray_profile_catalog_cache.py](../tests/test_tray_profile_catalog_cache.py)
5. [tests/test_snapshot.py](../tests/test_snapshot.py)

## Validation Host Rules

- Native HDR, VRR, refresh, and game-config claims still require validation-host confirmation.
- `MAGNETON` may implement these slices, but may not upgrade evidence to `measured`.
- If a title’s config format differs between hosts, the validation-host shape wins.

## Definition Of Done For This Phase

This phase is done only when:

1. Diablo 4 is no longer OS-level-only.
2. CoD is either native-config enforced or explicitly contract-limited.
3. Ryujinx is either native-config enforced or explicitly contract-limited.
4. Verification depth is expanded enough that these families no longer depend mainly on optimistic post-apply assumptions.
5. Tray, GUI, and manifest outputs stay congruent after the matrix changes.
