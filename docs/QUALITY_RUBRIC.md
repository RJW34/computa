# A.B.S.O. Quality Rubric

This document defines the shipping bar for A.B.S.O. It exists to prevent drift from "interesting tweak collection" toward "state-of-the-art Windows gaming optimization product."

The standard is simple:

- No feature ships unless it is truthful.
- No optimization ships unless it is mechanically verifiable.
- No rollback promise ships unless it is restorable in practice.
- No profile is called "optimal" unless the project has evidence for that claim.

## Current Baseline

Baseline assessment as of March 26, 2026:

| Category | Grade | Notes |
| --- | --- | --- |
| Optimization Capability | B | Real profiles, real settings, incomplete evidence loop |
| Mechanical Correctness | B- | Stronger than average, still not fully closed-loop |
| Safety And Rollback | C | Some handlers remain partially restorable |
| UI And Tray Truthfulness | C- | Still contains optimistic and hardcoded claims |
| Release Rigor | B- | Good local checks, incomplete quality gates |
| Overall | C+ | Promising, not yet state-of-the-art |

## Weighted Score

The overall release grade is weighted as follows:

| Category | Weight |
| --- | --- |
| Optimization Capability | 30% |
| Mechanical Correctness | 20% |
| Safety And Rollback | 25% |
| UI And Tray Truthfulness | 15% |
| Release Rigor | 10% |

Shipping target:

- Every category must be `A-` or better.
- Weighted overall score must be `A` or better.

## Grade Definitions

### 1. Optimization Capability

`A`

- Every shipping profile has an explicit optimization thesis.
- Every nontrivial setting is tagged with an evidence class.
- Every "optimal performance" profile has benchmark artifacts on at least one representative hardware/display path.
- Every profile declares prerequisites and known tradeoffs.

`B`

- Profiles are coherent and mostly evidence-backed.
- Some settings remain heuristic or only loosely justified.
- Benchmarking is partial or inconsistent.

`C`

- Profiles are plausible but weakly validated.
- "Optimal" language outruns measured evidence.

### 2. Mechanical Correctness

`A`

- Apply is deterministic and idempotent.
- High-impact handlers are verified post-apply.
- Partial failure is always surfaced as failure.
- Handler contracts are explicit and enforced.

`B`

- Apply is usually correct.
- Some handlers lack deep verification or edge-case coverage.

`C`

- Success can be reported without proving final machine state.

### 3. Safety And Rollback

`A`

- Every claimed change is either fully restorable or explicitly excluded from rollback promises.
- Baseline restore fails closed by default.
- Round-trip tests exist for every restorable handler.

`B`

- Most handlers restore cleanly.
- Some restore paths remain best-effort or incomplete.

`C`

- Transactional switching can continue after incomplete restore.
- Restore claims are broader than actual capability.

### 4. UI And Tray Truthfulness

`A`

- Every success state is derived from backend facts.
- Every audit/result string reflects actual scope.
- No hardcoded per-profile summary can drift from backend behavior.

`B`

- Most surfaces are truthful.
- A few optimistic strings or static summaries remain.

`C`

- UI can imply certainty the backend has not established.

### 5. Release Rigor

`A`

- CI enforces full test/build/lint/quality gates.
- Profile contract validation is mandatory.
- Benchmark regressions block release for touched profiles.

`B`

- Strong checks exist but are not yet complete or fully blocking.

`C`

- Quality depends too heavily on manual review.

## Non-Negotiable Rules

These rules are release-blocking.

1. No UI, tray, CLI, or report may say `optimized`, `active`, `applied successfully`, or equivalent unless backend state supports the claim.
2. No transaction may proceed after incomplete baseline restore unless the user has explicitly entered degraded mode.
3. No handler may participate in backup/restore promises without declaring restore support and having matching test coverage.
4. No profile may claim `optimal` without benchmark evidence and prerequisite documentation.
5. No frontend may hardcode per-profile setting summaries or success details that can drift from backend truth.
6. No placeholder capability badge may be shown as fact.

## Evidence Classes

Every nontrivial profile setting must declare one of these evidence classes:

| Class | Meaning |
| --- | --- |
| `documented` | Backed by vendor or OS documentation |
| `measured` | Backed by repeatable local measurement |
| `heuristic` | Reasonable best guess, not yet strongly proven |
| `compatibility` | Set to avoid known breakage or conflicts |
| `legacy_off_by_default` | Common tweak with weak modern evidence; disabled by default |

Rules:

- `heuristic` settings are allowed only when clearly labeled.
- `legacy_off_by_default` settings cannot be enabled in default competitive profiles.
- Profiles using `heuristic` settings cannot earn `A` until those settings are measured or removed.

## Handler Capability Contract

Every settings handler must declare:

- `supports_apply`
- `supports_backup`
- `supports_restore`
- `supports_verify`
- `restore_guarantee`: `full`, `partial`, `none`
- `verification_scope`: `full`, `reboot_only`, `none`

Rules:

- `supports_restore=False` means the handler cannot be counted in rollback promises.
- `restore_guarantee=partial` forces degraded transaction semantics unless explicitly excluded.
- High-impact handlers must expose `supports_verify=True` before their profile path can be graded `A`.

## Evidence & Validation Discipline

A.B.S.O. is developed and validated on a single machine — whatever PC the repo
is checked out on (see `docs/AGENT_PROTOCOL.md` §2). There is no multi-host role
split; the same box does coding, validation, and signoff. What matters is the
evidence standard, not which machine produced it:

- A profile cannot be upgraded to `measured` evidence without an actual
  benchmark artifact in `reports/benchmarks/`, captured on hardware that
  actually exposes the relevant path.
- VRR, HDR, refresh-rate, and NVIDIA claims are only valid on a machine that
  actually exposes those capabilities — confirm with `python -m abso detect`.
- "Optimal" claims require recorded before/after frame data, not just passing
  tests.

## Forbidden Claims

These phrases are forbidden unless backed by a matching backend proof path:

- `system optimized`
- `fully optimized`
- `applied successfully`
- `optimal settings applied`
- `NPI available`
- `restored successfully`
- `no issues found` without qualifying audit scope

Allowed replacements:

- `No issues detected by the current audit scope`
- `Profile apply completed with verified handlers: ...`
- `Restore completed for fully restorable handlers`
- `NPI status unknown`

## Release Gates

Every release candidate must pass all of the following:

1. `python -m pytest -q`
2. `npm run lint`
3. `npm run build`
4. `cargo check`
5. Handler contract validation
6. Profile contract validation
7. Snapshot validation
8. Quality-string scan for forbidden claims
9. Benchmark artifact review for every touched "optimal" profile
10. Validation-host confirmation for touched VRR/HDR/NVIDIA/"optimal" profile paths

## PR Checklist

Every PR touching handler, profile, tray, or GUI behavior must answer:

1. What truth claims does this PR add or modify?
2. What backend fact proves each claim?
3. Is rollback affected?
4. Is verification affected?
5. What tests prove success, failure, and partial failure behavior?
6. Does this increase, reduce, or preserve evidence quality?

## Graduation Criteria To A

The project earns an `A` only when:

- All release gates are enforced.
- All default profiles are contract-backed.
- All default profiles are truthful in GUI, tray, CLI, and reports.
- Transactional rollback semantics are fail-closed by default.
- High-impact handlers are verified post-apply.
- Every "optimal performance" profile has benchmark evidence.
