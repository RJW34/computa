# Resource Intake Directory

This directory is the handoff surface for external-resource work.

## Files

- `current-external-surfaces.json`
  - grounded examples the repo already proves today
- `incoming-candidates.json`
  - queue of outside resources that still need review
- `resource-template.json`
  - copy/paste schema for a new candidate entry
- `decision-template.md`
  - short decision write-up template after review
- `implementation-backlog.md`
  - concrete follow-on build steps for a stronger model or future agent

## Status meanings

- `unreviewed` — captured, not yet compared against repo truth
- `reviewing` — overlap and risk analysis in progress
- `documented-noop` — resource is already represented in current computa behavior
- `absorbed` — code/docs/tests landed from this resource
- `rejected` — intentionally not adopted
- `watchlist` — plausible, but blocked on evidence/scope/hardware/time

## Rules

1. Do not delete historical candidate rows; update status instead.
2. Prefer one resource per row even if several came from one tweet.
3. Keep claimed value and next action concrete.
4. If a resource influences user-facing behavior, make sure the follow-on pass
   updates `README.md` and any affected docs.
