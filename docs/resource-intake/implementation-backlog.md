# External Resource Incorporation Backlog

This is the concrete handoff for a stronger model or future agent.

## Completed (2026-09-03)

- **WinUtil parity audit — DONE (absorbed).** All 67 tweaks payload-mapped;
  8 reversible deltas imported into `debloat_tweaks.yaml` with tests; full
  disposition table at `parity/winutil-parity-table.md`; decision note at
  `decisions/winutil-parity-audit.md`.
- **CPU core-partitioning family — DONE (absorbed, deployed).** Backfilled from
  the 2026-08-31 work; decision note at
  `decisions/core-partitioning-absorption.md`.

## Immediate next pass

1. **ShutUp10 privacy-toggle mapping** (`oo-shutup10-privacy-toggle-mapping`):
   no public machine-readable catalog, so map at category level against the
   now-expanded tier-1/tier-2 rows; expect heavy documented-noop overlap after
   the WinUtil import.
2. **Winaero registry audit** (`winaero-tweaker-registry-audit`): bucket into
   performance-relevant / UX-only / reject before any code proposal.
3. **AtlasOS delta extraction** stays watchlist per
   `decisions/atlasos-wholesale-import.md`.
4. **NVCleanstall scope note** stays watchlist: write the boundary doc keeping
   driver-package installation out of computa scope.
5. Watchlist item worth a real feature slice: `SvcHostSplitThresholdInKB`
   (RAM-aware computed value, reboot-gated, with verify) — see the WinUtil
   parity table.

## Good first implementation slices

- user-facing docs that explain already-present external influences honestly
- missing troubleshooting/verification docs for current integrations
- safe optional integrations with clear rollback and detection paths
- benchmark harnesses that test whether a third-party idea is real or placebo

## Things to reject unless strong evidence appears

- one-click blind debloat packs
- irreversible registry bundles with no restore story
- latency/network placebo tweaks with no measurement path
- anti-cheat-risky process tampering in online profiles
- Windows service removal framed as a universal gaming win

## Handoff standard

A follow-on implementation pass should leave behind:

- updated candidate statuses
- explicit decision notes
- code/docs/tests if something was absorbed
- a short summary of what still remains unreviewed
