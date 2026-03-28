# HERMES Handoff

This is the start-here document for a long-running remediation effort on A.B.S.O.

If you are HERMES, read this file first, then follow the reading order below.

## Mission

Raise A.B.S.O. from its current baseline to `A` grades across the board by executing the remediation program without drifting into:

- optimistic UX
- unverifiable optimization claims
- rollback promises the code cannot keep
- new profile work before trust-critical work is finished

## Read In This Order

1. [README.md](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/README.md)
2. [docs/QUALITY_RUBRIC.md](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/docs/QUALITY_RUBRIC.md)
3. [docs/REMEDIATION_ROADMAP.md](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/docs/REMEDIATION_ROADMAP.md)
4. [docs/NVAPI_INTEGRATION_PLAN.md](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/docs/NVAPI_INTEGRATION_PLAN.md)

Optional historical context:

- [CLAUDE_AGENT_HANDOFF.md](/c:/Users/mtoli/Documents/Code/windowsoptimizerabso/CLAUDE_AGENT_HANDOFF.md)

## Current Project Reality

The project is no longer a toy and no longer obvious snake oil. It does real work and has meaningful safety scaffolding.

It is also not yet at the bar required for a state-of-the-art Windows optimization product.

Main deficits still open:

- incomplete rollback parity for some handlers
- incomplete post-apply verification coverage
- optimistic GUI/tray wording and hardcoded summaries
- insufficient evidence discipline for "optimal" claims
- missing machine-role guardrails for validation and signoff

## Machine Roles

Do not assume the machine you are running on is the same as the primary gaming/dev machine.

Current expected split:

- `MAGNETON`: implementation host
- primary gaming/dev machine: validation host
- release signoff host: validation host unless broader matrix exists

Implications:

- You may implement structural fixes on `MAGNETON`.
- You may not upgrade evidence from `heuristic` to `measured` without validation-host artifacts.
- You may not sign off VRR, HDR, NVIDIA, refresh, or "optimal" claims from implementation-host testing alone.

## Execution Rules

1. Work one roadmap PR slice at a time.
2. Follow roadmap phase order unless a hard dependency forces deviation.
3. Do not add new profiles while trust/rollback/verification work is still open.
4. Prefer fail-closed behavior over permissive behavior.
5. Remove misleading behavior instead of preserving it for compatibility.
6. Update tests with every behavioral change.
7. If scope expands, document the expansion before continuing.

## Required Output Per Slice

For every roadmap slice, report:

1. What changed
2. Why it was necessary
3. Files changed
4. Tests added or updated
5. Commands run
6. Remaining risk
7. Which rubric category improved
8. Recommended next slice

## Things You Must Not Do

- Do not call a profile `optimal` without benchmark evidence.
- Do not ship placeholder capability text as fact.
- Do not leave a hardcoded per-profile summary in the GUI.
- Do not let incomplete baseline restore commit silently.
- Do not broaden rollback claims beyond actual handler capability.

## First Recommended Slices

Start here unless blocked:

1. `PR-01: Remove optimistic wording and placeholders`
2. `PR-02: Generate profile review/success views from backend data`
3. `PR-03: Introduce handler capability metadata`
4. `PR-04: Enforce contract-aware transaction semantics`

Reason:

- These slices improve truthfulness and control-plane safety before deeper optimization work.

## Definition Of Success

The remediation program is complete only when:

- all rubric categories are `A-` or better
- weighted score is `A` or better
- default profiles are contract-backed and benchmark-backed
- rollback is fail-closed by default
- high-impact handlers are verified post-apply
- GUI, tray, CLI, and reports are backend-truthful
- CI blocks regressions automatically
