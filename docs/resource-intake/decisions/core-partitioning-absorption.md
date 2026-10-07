# Resource decision: CPU core-partitioning tools (charlie754 Game-Optimizer, CPUSetSetter)

- `resource_id`: `cpu-core-partitioning-family`
- `reviewed_on`: `2026-09-03` (work performed 2026-08-31; recorded here when the
  intake scaffold landed)
- `reviewed_by`: `Claude (session 018J2A7fsXxxWdreMD4fS4k2)`
- `source_url`: `https://github.com/charlie754/Game-Optimizer-CPUs-Threads-Optimizer`
  (also reviewed: `https://github.com/SimonvBez/CPUSetSetter`,
  `https://github.com/LordBlacksun/x3d-ccd-optimizer`,
  `https://github.com/saturnsky/saturn_affinity_python`)
- `outcome`: absorbed

## Claimed value

Two-sided CPU core partitioning while a game runs: game → fast cores (P-cores
on Intel hybrid, V-Cache CCD on AMD X3D), background apps (OBS, browsers,
Discord) → remaining cores, with heavy-app auto-detection. Headline claim
(~190→300 fps OW2) is the AMD dual-CCD cross-CCD case; on Intel hybrid the
honest expectation is frame-time/1%-low consistency under multitasking.

## Overlap with current computa

computa already had the same API substrate (CPU Sets soft steering, June 2026
Process Lasso wave). The absorption added the missing halves: LLC-based AMD
X3D classification, game-descendant coverage, full-clock background steering
(distinct from EcoQoS throttling), sustained-CPU auto-steer, per-profile
policies, tray automation and status surfacing.

## Risks / caveats

- Anti-cheat: soft `SetProcessDefaultCpuSets` only, minimal handle rights, no
  injection, hard affinity untouched (their approach, kept).
- X3D pitfall (from CPUSetSetter docs): Windows Game Mode's own CCD parking
  can fight manual steering — encoded as a runtime warning + `x3d_partition`
  config veto.
- Symmetric multi-CCD and single-domain topologies must no-op — encoded in the
  classifier and locked by tests.

## Decision

Absorbed and deployed. `x3d-ccd-optimizer` and `saturn_affinity_python` were
reviewed as corroborating prior art; no unique mechanisms to import —
watchlist for future ideas only.

## Follow-on implementation

- [x] code — `abso/core/cpu_sets.py` (CorePartition classifier, L3 domains),
  `abso/core/partition_steer.py` (steerer + journal), `abso/core/cpu_balancer.py`
  (hosting, auto-steer, `--no-restraint`), profile policies, tray wiring
- [x] tests — full hermetic suite 2,665 passed (partition classifier, steerer,
  auto-steer, resolver, profile invariants, tray contracts)
- [x] docs — `docs/PROCESS_LASSO_FEATURES.md`, `docs/TROUBLESHOOTING.md`, README
- [x] verification evidence — deployed 2026-08-31 (backend 18,205,442 bytes,
  tray PID 3792, `health --json` 8 ok / 2 standing warnings, PYZ contains
  `partition_steer`)

## Evidence links

- `abso/core/partition_steer.py`
- `abso/core/cpu_sets.py`
- `abso/core/cpu_balancer.py`
- `docs/PROCESS_LASSO_FEATURES.md`
- `docs/CURRENT_AGENT_BRIEFING.md` (2026-08-31 entry)
