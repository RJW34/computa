# Resource decision: Chris Titus Tech WinUtil parity audit

- `resource_id`: `chris-titus-winutil-parity-audit`
- `reviewed_on`: `2026-09-03`
- `reviewed_by`: `Claude (session 018J2A7fsXxxWdreMD4fS4k2)`
- `source_url`: `https://github.com/ChrisTitusTech/winutil`
- `outcome`: absorbed

## Claimed value

Broad Windows utility whose tweak catalog could surface safe missing deltas
for computa's debloat/privacy tiers.

## Overlap with current computa

High. All 67 entries of `config/tweaks.json` were payload-extracted and mapped
(see `../parity/winutil-parity-table.md`). Outcome distribution:

- **8 absorbed** — reversible registry/service deltas computa lacked
  (InputPersonalization privacy family, PublishUserActivities, device-metadata
  policy, WPBT execution block, MapsBroker service).
- **13 documented-noop** — already covered, in several cases more carefully
  (telemetry floor honest for Home/Pro, MPO reboot-gated, mouse curves,
  Delivery Optimization via `updates.py`, Ultimate Performance via `power.py`).
- **~40 rejected** — UX customization, third-party app surgery, destructive
  uninstalls, online-risky network tweaks (Teredo/IPv6), breakage-prone
  service changes, and one-shot maintenance actions.
- **3 watchlist** — `SvcHostSplitThresholdInKB` (needs RAM-aware handler
  logic), the WindowsAI policy set (computa is deliberately detect-only on the
  25H2 AI surface), and the ShutUp10 launcher button (superseded by the
  dedicated ShutUp10 candidate).

## Risks / caveats

- Imported rows are plain tiered registry/service writes with recorded
  defaults — DebloatHandler's existing backup/restore and the blocked-HKLM-path
  guard cover them; no new mechanism was added.
- WPBT disable takes effect next boot (documented in the row description).
- Rejects are recorded so the same rows are not re-litigated on every future
  WinUtil release; re-audit only on major catalog changes.

## Decision

Absorbed via the smallest reversible delta set. WinUtil's remaining value to
computa is as a periodic diff source, not a dependency.

## Follow-on implementation

- [x] code — `abso/data/debloat_tweaks.yaml` (+5 tier-1 registry, +2 tier-2
  registry, +1 tier-2 service)
- [x] tests — `tests/test_handlers/test_debloat.py::TestBundledCatalogIntegrity`
  (catalog shape, blocked-path invariant, explicit parity-row lock)
- [x] docs — `../parity/winutil-parity-table.md`
- [x] verification evidence — debloat suite 11 passed; full-suite run pending
  in the main working tree alongside the session's other changes

## Evidence links

- `docs/resource-intake/parity/winutil-parity-table.md`
- `abso/data/debloat_tweaks.yaml`
- `abso/settings/debloat.py`
- `abso/settings/updates.py`
- `tests/test_handlers/test_debloat.py`
