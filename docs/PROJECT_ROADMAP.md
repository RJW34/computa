# Project Roadmap

Audit date: 2026-06-24
Project: RJW34/computa
Family: Windows gaming performance and private ops
Current publication stance: DO_NOT_PUBLISH_YET

## Current Intent

Project-specific product candidate; complete public shape requires docs, tests, provenance, and boundary decisions.

## Documentation Audit

- Remote default-branch docs counted: 39
- Local/remediation docs counted: 40
- Key docs present: AGENT_PROJECT_STATUS, AGENTS, GitHub/CI docs, LICENSE, README, release checklist, SECURITY
- Inspection note: Remote default branch inventory plus local/remediation shallow docs where available.

## Existing Documentation Sample

- .github/workflows/ci.yml
- .github\workflows\ci.yml
- AGENTS.md
- CHANGELOG.md
- CONTRIBUTING.md
- docs/AGENT_PROTOCOL.md
- docs/API.md
- docs/archive/2.0_OVERHAUL_GUIDE.md
- docs/archive/abso_claude_agent_improvement_specification.md
- docs/archive/CLAUDE_AGENT_HANDOFF_2026-02-11.md
- docs/archive/CLAUDE_AGENT_HANDOFF_2026-02-18.md
- docs/archive/CLAUDE_AGENT_HANDOFF.md

## Documentation Scaffold To Add

- private/public boundary
- credential/history remediation plan
- fresh-extract plan
- owner decision record

## Completion Roadmap

- Keep diagnostic public before optimizer mutations.
- Prove rollback/restore for every mutating optimizer path.
- Separate private cockpit/topology from public diagnostics.
- Add live disposable-machine verification before release.

## Feature And Hardening Backlog

- Keep all machine-changing flows behind dry-run, backup, and rollback paths.
- Document hardware/driver assumptions and report formats.
- Add smoke tests for diagnostics that must not mutate host state.

## Blockers And Constraints

- not public-ready without fresh extraction or owner decision

## Next Allowed Local Action

Write boundary/status docs and decide keep-private versus fresh extract.

## Acceptance Criteria For This Roadmap

- The README describes the actual current workflow and does not overstate completion.
- Setup, test, security, and release notes are present or intentionally marked not applicable.
- Public/private boundaries, credentials, generated artifacts, and provenance are documented before publication or promotion.

