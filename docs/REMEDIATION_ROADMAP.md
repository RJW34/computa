# A.B.S.O. Remediation Roadmap

This roadmap is the execution plan for raising A.B.S.O. from its March 26, 2026 baseline (`C+` overall) to `A` grades across the board.

The emphasis is not "more features." The emphasis is:

- stronger truth guarantees
- stronger rollback guarantees
- stronger post-apply verification
- profile evidence and release discipline

## Operating Model

Use these ownership buckets even if one person is wearing all of them:

| Role | Scope |
| --- | --- |
| `Core Systems` | transaction flow, compliance, contracts, rollback semantics |
| `Handlers` | individual settings handlers, backup/restore/verify parity |
| `Profiles & Evidence` | profile contracts, evidence classes, benchmark policy |
| `UX & Tray` | GUI, Tauri shell, PowerShell tray, wording and status truthfulness |
| `QA & Release` | CI gates, snapshots, regression coverage, release checklist |

## Sequencing Rules

1. Truthfulness work comes before more optimization work.
2. Rollback and verification work comes before new profiles.
3. Benchmarking comes after contracts and verification, not before.
4. No UI improvements may add claims the backend cannot prove.

## Machine Role Policy

The remediation program assumes different machines may be used for implementation and validation.

Current expected split:

- `MAGNETON`: implementation host
- primary gaming/dev machine: validation host
- release signoff: validation host unless a broader matrix is approved

What may be done on the implementation host:

- code changes
- tests
- refactors
- tray/GUI work
- handler contract work
- CI/release gate work

What may not be signed off from the implementation host alone:

- VRR / G-SYNC behavior claims
- HDR correctness claims
- NVIDIA driver-path claims
- refresh-rate path claims
- benchmark-backed "optimal" claims

Rule:

- HERMES may improve structure and truthfulness on `MAGNETON`, but it must not upgrade profile evidence to `measured` or claim a path is `optimal` without validation-host artifacts.

## Phase 1: Truth Freeze

Objective:

- eliminate overstated claims and hardcoded profile summaries

Expected grade lift:

- UI And Tray Truthfulness: `C-` -> `B`

### PR-01: Remove optimistic wording and placeholders

Owner: `UX & Tray`

Files:

- [abso/tray/ABSO-Tray.ps1](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/tray/ABSO-Tray.ps1)
- [gui/src/components/StatusBar.tsx](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/gui/src/components/StatusBar.tsx)
- [gui/src/pages/AuditDetails.tsx](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/gui/src/pages/AuditDetails.tsx)

Tasks:

- Replace `system optimized` language with scope-qualified wording.
- Replace hardcoded `NPI: Available` badge with backend-derived or unknown state.
- Audit tray/GUI strings for forbidden trust phrases.

Acceptance:

- No placeholder capability badges remain.
- No string claims optimization beyond backend audit scope.
- Snapshot tests added for trust-sensitive UI strings.

### PR-02: Generate profile review/success views from backend data

Owner: `UX & Tray`

Files:

- [gui/src/pages/ProfileWizard.tsx](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/gui/src/pages/ProfileWizard.tsx)
- [gui/src/lib/api.ts](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/gui/src/lib/api.ts)
- [gui/src/lib/types.ts](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/gui/src/lib/types.ts)
- [abso/main.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/main.py)

Tasks:

- Add a backend summary endpoint or enrich existing profile/report output.
- Remove hardcoded review bullets and hardcoded success report content.
- Drive wizard success state from actual apply result plus generated report content.

Acceptance:

- Wizard review reflects selected profile data.
- Wizard success view reflects actual apply output and actual report content.
- No hardcoded backend-specific settings remain in the frontend.

## Phase 2: Handler Capability Contracts

Objective:

- make handler guarantees explicit and machine-readable

Expected grade lift:

- Mechanical Correctness: `B-` -> `B+`
- Safety And Rollback: `C` -> `B-`

### PR-03: Introduce handler capability metadata

Owner: `Core Systems`

Files:

- [abso/settings/base.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/base.py)
- [abso/core/applier.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/core/applier.py)
- [abso/core/backup.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/core/backup.py)
- [abso/core/transaction.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/core/transaction.py)

Tasks:

- Add explicit capability fields for apply/backup/restore/verify support.
- Replace implicit backup truth inference with contract-based behavior.
- Surface capability data in transaction output where relevant.

Acceptance:

- Every handler declares capability metadata.
- Backup and transaction code consume capability metadata, not payload guesswork.
- Tests enforce handler metadata presence.

### PR-04: Enforce contract-aware transaction semantics

Owner: `Core Systems`

Files:

- [abso/core/transaction.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/core/transaction.py)
- [abso/core/compliance.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/core/compliance.py)
- [abso/main.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/main.py)

Tasks:

- Distinguish `fully restorable`, `partially restorable`, and `non-restorable` apply paths.
- Fail closed by default when a transaction cannot honestly promise clean rollback.
- Add degraded-mode semantics only if intentionally supported.

Acceptance:

- Transaction output explicitly reports rollback confidence.
- Incomplete baseline restore no longer silently proceeds in normal mode.
- Restore-related tests cover complete, partial, and impossible rollback scenarios.

## Phase 3: Restore Parity And Baseline Integrity

Objective:

- close the remaining mismatch between backup promises and actual restore behavior

Expected grade lift:

- Safety And Rollback: `B-` -> `B+`

### PR-05: Fix network backup/restore symmetry

Owner: `Handlers`

Files:

- [abso/settings/network.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/network.py)
- [tests/test_handlers/test_network.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/tests/test_handlers/test_network.py)

Tasks:

- Restore TCP-global settings as well as per-interface values.
- Add round-trip tests covering gaming preset, default preset, and mixed state.

Acceptance:

- Network backup/restore is symmetric.
- Round-trip tests prove parity.

### PR-06: Audit and fix restore symmetry for remaining high-impact handlers

Owner: `Handlers`

Files:

- [abso/settings/process_priority.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/process_priority.py)
- [abso/settings/power.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/power.py)
- [abso/settings/graphics.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/graphics.py)
- [abso/settings/timer.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/timer.py)
- matching tests

Tasks:

- Confirm each backed-up field is restorable.
- Remove rollback claims for fields that cannot be restored safely.
- Add round-trip tests.

Acceptance:

- No handler participates in rollback promises without parity.
- Restore coverage exists for all high-impact handlers.

### PR-07: Resolve NVIDIA rollback stance

Owner: `Core Systems` + `Handlers`

Files:

- [abso/settings/nvidia/__init__.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/nvidia/__init__.py)
- [docs/NVAPI_INTEGRATION_PLAN.md](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/docs/NVAPI_INTEGRATION_PLAN.md)

Decision:

- either implement narrow, safe restore scope
- or permanently exclude NVIDIA from rollback guarantees and expose that clearly everywhere

Acceptance:

- The code, docs, and UI all say the same thing about NVIDIA rollback.
- No ambiguity remains.

## Phase 4: Deep Verification Coverage

Objective:

- prove final machine state rather than inferring it from successful writes

Expected grade lift:

- Mechanical Correctness: `B+` -> `A-`

### PR-08: Add verification to high-impact handlers

Owner: `Handlers`

Files:

- [abso/settings/nvidia/__init__.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/nvidia/__init__.py)
- [abso/settings/network.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/network.py)
- [abso/settings/power.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/power.py)
- [abso/settings/process_priority.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/process_priority.py)
- [abso/settings/color.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/settings/color.py)

Tasks:

- Implement `verify_active` where missing.
- Distinguish `verified active`, `pending reboot`, `unverified`, and `mismatch`.

Acceptance:

- High-impact handlers support post-apply verification.
- Verification tests cover true success, mismatch, and detection failure.

### PR-09: Expand compliance severity model

Owner: `Core Systems`

Files:

- [abso/core/compliance.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/core/compliance.py)
- [abso/core/transaction.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/core/transaction.py)

Tasks:

- Make criticality data-driven instead of hardcoded to a narrow handler list.
- Treat VRR/HDR/NVIDIA mismatches as critical for profiles that depend on them.
- Distinguish `unverified` from `verified mismatch`.

Acceptance:

- Compliance output is specific enough to drive honest UX.
- Critical profile paths fail on unresolved verification gaps.

## Phase 5: Profile Contracts And Evidence

Objective:

- make profiles defensible and reviewable

Expected grade lift:

- Optimization Capability: `B` -> `A-`

### PR-10: Introduce profile contract schema

Owner: `Profiles & Evidence`

Files:

- `abso/manifests/profile_contracts/`
- [abso/profiles/catalog.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/profiles/catalog.py)
- `tests/test_profile_contracts.py`

Each profile contract must declare:

- optimization thesis
- prerequisites
- display path model
- sync model
- HDR model
- launch assumptions
- benchmark expectation
- evidence class per nontrivial setting

Acceptance:

- Every shipping profile has a contract file.
- Catalog validation fails if contract is missing or incomplete.

### PR-11: Tag all profile settings with evidence class

Owner: `Profiles & Evidence`

Files:

- profile definitions under [abso/profiles](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/profiles)
- profile contract files

Tasks:

- Mark each nontrivial setting as `documented`, `measured`, `heuristic`, `compatibility`, or `legacy_off_by_default`.
- Remove or downgrade unsupported "optimal" language where evidence is not yet sufficient.

Acceptance:

- No shipping profile contains uncategorized nontrivial settings.
- `heuristic` settings are explicitly visible in contract output.

## Phase 6: Benchmark Harness And Performance Evidence

Objective:

- earn the right to call profiles optimal

Expected grade lift:

- Optimization Capability: `A-` -> `A`

### PR-12: Add benchmark artifact format and storage

Owner: `Profiles & Evidence` + `QA & Release`

Files:

- `docs/PROFILE_ACCEPTANCE.md`
- `reports/benchmarks/`
- benchmark helpers under [abso/core](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/core)

Metrics:

- average FPS
- 1% low
- 0.1% low
- frame-time variance
- stutter/event notes
- latency proxy where available

Acceptance:

- Benchmarks have a standard format.
- Touched optimal profiles must attach benchmark artifacts.
- Benchmark artifacts record which machine acted as implementation host, validation host, and signoff host.

### PR-13: Benchmark top-tier shipping profiles

Owner: `Profiles & Evidence`

Priority profiles:

- `overwatch2`
- `overwatch2-gsync`
- `overwatch2-gsync-hdr`
- `marvel-rivals-sdr`
- `marvel-rivals-hdr`
- `rivals2`
- `rivals2-gsync`
- `slippi-melee`

Acceptance:

- Each priority profile has at least one benchmark artifact on a representative machine.
- Regressions are documented before release.
- Validation-host identity is recorded for every benchmark artifact.

## Phase 7: Shared Backend Truth For GUI, Tray, And CLI

Objective:

- make every surface a generated view of backend truth

Expected grade lift:

- UI And Tray Truthfulness: `B` -> `A`

### PR-14: Introduce shared status payloads

Owner: `Core Systems` + `UX & Tray`

Files:

- [abso/main.py](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/main.py)
- [gui/src/lib/api.ts](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/gui/src/lib/api.ts)
- [gui/src/lib/types.ts](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/gui/src/lib/types.ts)
- [gui/src-tauri/src/main.rs](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/gui/src-tauri/src/main.rs)
- [abso/tray/ABSO-Tray.ps1](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/abso/tray/ABSO-Tray.ps1)

Tasks:

- Standardize apply, restore, audit, and profile summary payloads.
- Eliminate per-surface JSON shape assumptions.
- Ensure tray and GUI read the same truth model.

Acceptance:

- Tray and GUI show the same state for the same backend event.
- No surface needs hardcoded fallback interpretation for core actions.

## Phase 8: CI And Release Discipline

Objective:

- make quality gates enforceable and repeatable

Expected grade lift:

- Release Rigor: `B-` -> `A`

### PR-15: Add blocking CI quality gates

Owner: `QA & Release`

Checks:

1. `python -m pytest -q`
2. `npm run lint`
3. `npm run build`
4. `cargo check`
5. handler contract validation
6. profile contract validation
7. snapshot validation
8. forbidden-claims scan

Acceptance:

- CI blocks merge on any failed gate.
- New profiles cannot merge without contracts.

### PR-16: Add release checklist and benchmark gate

Owner: `QA & Release`

Files:

- `docs/RELEASE_CHECKLIST.md`
- CI workflow files under `.github/workflows/`

Release checklist must require:

- benchmark artifacts for touched optimal profiles
- explicit note when a profile remains heuristic
- explicit rollback/verification statement in release notes
- explicit validation-host signoff for touched VRR/HDR/NVIDIA profile paths

Acceptance:

- Release process no longer depends on maintainer memory.

## Stop Conditions

Pause new profile work if any of these are true:

- incomplete baseline restore can still commit normally
- high-impact handler lacks verification
- GUI or tray still contains forbidden claims
- a default profile lacks a contract

## Definition Of Done For "A Across The Board"

The roadmap is complete only when all of the following are true:

1. All rubric categories are `A-` or better.
2. Weighted score is `A` or better.
3. Default profiles are contract-backed and benchmark-backed.
4. Transaction flow is fail-closed by default.
5. High-impact handlers are verified post-apply.
6. GUI, tray, and CLI expose only backend-derived truth.
7. CI blocks regressions automatically.
