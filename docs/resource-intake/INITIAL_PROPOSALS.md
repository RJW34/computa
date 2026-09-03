# Initial External Resource Proposals

These are the first concrete proposal slices seeded into the scaffold so a
stronger model does not start from an empty intake queue.

They are **not** claims that the work is already implemented.
They are the highest-leverage next slices based on current computa repo truth.

## 1. WinUtil parity audit into computa debloat tiers

**Resource:** Chris Titus Tech WinUtil

**Why this is first:** computa already has a real debloat/settings substrate
(`abso/settings/debloat.py` + `abso/data/debloat_tweaks.yaml`). That means a
follow-on agent can compare WinUtil against an existing target surface instead
of inventing a new subsystem.

**Proposed output:**
- parity table: WinUtil tweak -> covered / missing / rejected / watchlist
- smallest safe delta import into `debloat_tweaks.yaml`
- rationale doc for anything intentionally excluded

**Acceptance test:**
- the parity table exists,
- imported deltas are reversible,
- and docs explain why high-risk WinUtil actions stayed out.

## 2. ShutUp10 privacy-toggle mapping

**Resource:** O&O ShutUp10++

**Why this is second:** the repo already proves privacy/telemetry work, but it
is not yet explicit which common privacy-toggle expectations are already covered
and which are intentionally omitted.

**Proposed output:**
- a privacy toggle mapping doc against computa's tier-1 / tier-2 debloat catalog
- optional import of missing reversible privacy toggles
- explicit reject notes for feature-breaking or placebo rows

**Acceptance test:**
- every reviewed toggle gets a disposition,
- missing safe toggles become normal computa entries,
- and no ambiguous "maybe" rows remain.

## 3. AtlasOS reversible-delta extraction

**Resource:** AtlasOS

**Why this is third:** AtlasOS is likely useful as a source of ideas, but it is
far too broad to import wholesale without violating computa's restore and
verification model.

**Proposed output:**
- shortlist of reversible per-setting deltas only
- explicit out-of-scope list for image/install-time modifications
- benchmark plan for any kept changes on target games/display paths

**Acceptance test:**
- no whole-image or non-reversible Atlas import is proposed,
- every kept delta maps to a real computa surface,
- and every proposed change has a rollback story.

## 4. NVIDIA install-path boundary note

**Resource:** NVCleanstall

**Why this matters:** computa already has NVIDIA profile control surfaces
(NPI now, NVAPI planned), but driver-install mediation is a different risk class.
The next agent should not blur those together.

**Proposed output:**
- a scope decision note keeping driver installation out unless a narrow optional
  lane is explicitly justified
- if kept in scope, a docs-only preparation path before any automation

**Acceptance test:**
- the scope boundary is explicit,
- no hidden installer creep lands,
- and NPI/NVAPI work stays distinct from driver-package management.

## Strong recommendation for the next model

Start with **WinUtil parity audit**.

It is the cleanest path because:
- the target surface already exists,
- the changes can stay reversible,
- and the result can produce real computa code/docs deltas without expanding
  the product into a full Windows toolbox.
