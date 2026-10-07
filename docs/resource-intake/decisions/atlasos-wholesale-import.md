# Resource decision: AtlasOS wholesale import

- `resource_id`: `atlasos-reversible-delta-extraction`
- `reviewed_on`: `2026-09-03`
- `reviewed_by`: `DEKU`
- `source_url`: `https://github.com/Atlas-OS/Atlas`
- `outcome`: watchlist

## Claimed value

AtlasOS promises performance, privacy, and usability gains through a broad set
of Windows changes.

## Overlap with current computa

computa already has targeted game profiles, power tuning, debloat/privacy
controls, rollback-aware apply paths, and verification discipline. That means
some AtlasOS ideas may overlap, but computa does not currently have an image- or
preset-style whole-OS mutation lane.

## Risks / caveats

- Wholesale adoption conflicts with computa's reversible transaction model.
- Image/install-time modifications are not equivalent to normal profile apply.
- Category-wide claims in this space are often anecdotal until measured on the
  target hardware and game mix.

## Decision

Do **not** treat AtlasOS as a one-shot import target.
Treat it only as a source of candidate reversible deltas for later review.
Non-reversible, image-only, or whole-OS assumptions stay out of scope unless
product scope changes explicitly.

## Follow-on implementation

- [ ] code
- [ ] tests
- [ ] docs
- [ ] verification evidence

## Evidence links

- `abso/settings/debloat.py`
- `abso/settings/power.py`
- `docs/REMEDIATION_ROADMAP.md`
- `docs/MULTIMON_GAMING_IDEA.md`
