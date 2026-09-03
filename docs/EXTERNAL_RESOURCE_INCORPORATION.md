# External Resource Incorporation

This document is the staging contract for folding outside resources into
**computa** without cargo-culting them.

Use it when the maintainer drops:

- a tweet or thread
- a GitHub repo
- a vendor tool
- a benchmark article
- a tuning guide
- a research note about Windows / gaming optimization

The goal is not "collect links." The goal is to turn an outside resource into
one of four explicit outcomes:

1. **absorbed** — the idea lands in code/docs/tests
2. **documented-noop** — already present in computa, with proof
3. **rejected** — not compatible with computa's safety/evidence bar
4. **watchlist** — interesting, but blocked on hardware, evidence, or scope

## Non-goals

- Blindly mirroring third-party tweak packs
- Treating anecdotal FPS claims as proof
- Expanding scope without mapping the idea to a real computa surface
- Marking a resource as "done" just because it was mentioned in chat

## Branding / naming note

User-facing product name is **computa**.
Internal package/module names may still use **ABSO** (`abso/`, `abso.manifest`,
`python -m abso ...`).

When writing new user-facing docs, prefer **computa** unless the text is about
an internal module or historical artifact.

## Directory contract

The machine-readable intake artifacts live under:

- `docs/resource-intake/current-external-surfaces.json`
- `docs/resource-intake/incoming-candidates.json`
- `docs/resource-intake/resource-template.json`
- `docs/resource-intake/decision-template.md`
- `docs/resource-intake/implementation-backlog.md`

## Required per-resource fields

Every candidate resource should eventually have these fields captured in
`incoming-candidates.json`.

- `resource_id` — stable slug
- `title` — human-readable name
- `source_type` — tweet, repo, vendor-tool, article, benchmark, guide, other
- `url` — canonical link
- `status` — unreviewed, reviewing, absorbed, documented-noop, rejected, watchlist
- `claimed_value` — what the resource allegedly helps with
- `candidate_surfaces` — exact computa areas it could affect
- `current_overlap` — what computa already appears to do in that area
- `evidence_needed` — what proof would justify absorbing it
- `risk_notes` — safety, rollback, trust, maintainability, anti-cheat, or scope risks
- `next_action` — one concrete next step

## Review workflow

### 1. Intake

Add or update a row in `incoming-candidates.json`.
Do not decide anything yet.

### 2. Surface mapping

Map the resource to one or more real computa surfaces:

- handler (`abso/settings/...`)
- profile (`abso/profiles/...`)
- tray / GUI
- docs / troubleshooting
- detection / verification / rollback
- benchmark / evidence collection

If it does not map cleanly, that is evidence **against** absorbing it.

### 3. Overlap check

Compare against `current-external-surfaces.json` and the current repo.
Possible results:

- already present
- partially present
- absent
- conflicts with existing design

### 4. Decision

Use `decision-template.md` to write a short durable decision note.
A resource is not considered incorporated until the decision is written and one
of the four outcomes is explicit.

### 5. Implementation handoff

If the outcome is `absorbed`, the follow-on implementation pass should produce:

- code changes or docs changes
- tests where behavior changed
- updated user-facing documentation when the product surface changed
- proof that the feature is safe, reversible, and honestly described

## Evidence rules

A higher-level LLM or future agent should keep these rules:

- A popular tweak is not evidence.
- A tweet screenshot is not evidence.
- A benchmark claim must identify the hardware, workload, and measurement path.
- Safety-sensitive changes need rollback semantics before recommendation.
- If computa deliberately rejected a category before (for example brittle
  service disabling or network placebo tweaks), new absorption must explain why
  the old rejection no longer applies.

## Current seeded truth

The scaffold ships with two grounded seed examples in
`current-external-surfaces.json`:

1. **Process Lasso** — documented as a Process Lasso-class analogue, not a
   bundled dependency.
2. **NVIDIA Profile Inspector** — explicit optional integration surface.

These are included because the current repo already proves them. They are not a
claim that every other prior user-shared resource has already been reviewed.

## Definition of done

A resource only counts as "incorporated" when:

- its intake entry exists,
- its overlap was checked against current repo truth,
- its decision outcome is explicit,
- and the resulting code/docs/tests (or rejection note) actually landed.
