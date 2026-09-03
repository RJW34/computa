# Process Lasso-Class Features (CPU / process / power session tuning)

ABSO ships an in-house equivalent of the useful parts of
[Process Lasso](https://bitsum.com/) and the CPU-partitioning tools
(CPUSetSetter, Game-Optimizer) — automatic two-sided core partitioning,
background-process restraint, per-process power throttling, a reversible CPU
limiter, and a declarative watchdog — plus a "Highest Performance"
core-parking power plan. Everything here targets **frame-time consistency
(1% lows), not average FPS** — except core partitioning under heavy
multitasking (streaming with OBS, browser + Discord open), where reclaiming
fast-core time for the game can move average FPS too.

**Core partitioning is automatic**: every gaming profile declares
`cpu_partition_policy = "full"` in the catalog, so applying a profile and
launching its game is enough — the tray starts the session governor, the game
is steered to the fast cores, and the profile's background apps (plus
auto-detected heavy processes) are steered to the remaining cores. The
priority-mutating features (ProBalance restraint, EcoQoS, watchdog) remain
explicit opt-ins (see [Enablement](#enablement)).

> Do not confuse these with GPU tuning. Higher graphics quality at a fixed FPS
> cap is a GPU-headroom problem (DLSS / Frame Gen). These features reduce
> CPU-side stutter so a capped game *feels* locked.

## Feature catalog

| Feature | What it does | Where it lives |
|---|---|---|
| **ProBalance governor** | Demotes background CPU spikers to BelowNormal during a game session and auto-restores them. Never touches the game, foreground, anti-cheat, launchers, audio, Discord, editors, or your `process_overrides.protect` images. | `abso/core/cpu_balancer.py` (daemon), spawned by the tray |
| **"Highest Performance" power plan** | Disables CPU core parking (`CPMINCORES`=100) and holds the processor min-state at 100% during gaming profiles; the desktop profile relaxes the floor to 5 so the CPU still idles cool. | `abso/settings/power.py` (apply pipeline) |
| **Keep-Awake** | Inhibits system/display sleep while a gamepad-driven game runs (emulators) — `SetThreadExecutionState`. Cleared on game exit. | tray (`ABSO-Tray.ps1`) + profile flag |
| **Core partitioning (automatic)** | Classifies the CPU into a game/background split — P-cores vs E-cores on Intel hybrid, V-Cache CCD vs frequency CCD on AMD X3D (larger-L3 domain wins), honest no-op on symmetric multi-CCD and single-domain parts. The game **and its descendants** are soft-steered (`SetProcessDefaultCpuSets`) to the fast side; the profile's background images (OBS on capture lanes, browsers/Discord/Spotify everywhere) and any process sustaining >4% CPU for 5 s go to the other side at **full clock speed**. Hard affinity is never touched; CPU Sets are re-swept every poll (they are not inherited by children) and cleared on game exit, with a crash-recovery journal. | `abso/core/cpu_sets.py` (topology + classification), `abso/core/partition_steer.py` (steerer), hosted in the daemon |
| **EcoQoS herding** | Throttles busy *background* images onto E-cores via `ProcessPowerThrottling`, freeing P-cores for the game. Releases on exit. Never throttles the game/anti-cheat/capture/Discord. | `abso/core/efficiency_mode.py`, hosted in the daemon |
| **CPU Limiter** | Reversible hard-affinity shrink — the "throttle" watchdog action. Restores the original mask on stop. | `abso/core/cpu_limiter.py` |
| **Watchdog** | Declarative rules (`match`/`metric`/`threshold`/`sustain`/`action`) with reversible demote/throttle/trim actions. Online profiles are auto-restricted to demote-only. | `abso/core/watchdog.py` (policy) + `watchdog_engine.py` (runtime), hosted in the daemon |

The four runtime features (ProBalance, CPU Sets, EcoQoS, watchdog) are all
hosted inside the one `cpu-balance` daemon the tray spawns on game launch — not
separate processes. The daemon stops via a stop-file **sentinel** (not a kill),
so its cleanup always restores demoted priorities / affinity / EcoQoS / CPU Sets.

## Configuration reference

### `abso.yaml` (backend config)

```yaml
cpu_balancer:
  enabled: false            # (informational; the tray flag is the real gate)
  system_cpu_threshold: 55  # aggregate-CPU % that arms background scanning (tuned for 24C/32T)
  process_cpu_threshold: 8  # per-process % (of total capacity) to restrain
  trigger_delay_ms: 2800
  restraint_duration_ms: 6000
  poll_interval_ms: 1000
  # excluded_processes is unioned with the NEVER_KILL safety net + process_overrides.protect

efficiency_mode:            # EcoQoS herding
  enabled: false
  background_images: []     # e.g. ["SomeUpdater.exe", "BackgroundTool.exe"] — what to herd to E-cores

cpu_sets:                   # core partitioning (profile-driven; these tune/override it)
  enabled: false            # force game->fast-core steering on EVERY profile
  background_steer: true    # allow the background half when the profile policy is "full"
  background_images: []     # EXTRA images to steer to background cores (unioned with the profile's list)
  auto_steer: true          # auto-detect heavy background processes and steer them
  auto_steer_process_threshold: 4   # per-process CPU % (of total capacity), ~1.3 cores on 32T
  auto_steer_sustain_ms: 5000       # must stay above threshold this long
  smt_avoid: false          # experimental: game side = one thread per physical core
  x3d_partition: true       # allow the AMD X3D cache-CCD split (disable Game Mode if it regresses)

cpu_limiter:                # the watchdog "throttle" action
  enabled: false
  keep_cores: 4             # cores left to a throttled process

watchdog:
  enabled: false
  rules:
    - match: discord.exe    # process image (case-insensitive)
      metric: priority      # cpu | ram | priority
      threshold: 3.0        # cpu=%, ram=MB, priority=rank (0 idle .. 5 realtime)
      sustain_s: 5.0        # must breach for this long before acting
      action: demote        # demote | throttle | trim  (reversible only; never terminate)
```

A behavior runs if its `abso.yaml` flag is enabled **or** its tray-config flag
passes the `--<flag>` CLI option to the daemon (the tray gate). `process_overrides.protect`
augments the never-touch set for ALL of these, not just the killer.

### Tray config (`%APPDATA%\ABSO\tray-config.json`)

| Key | Default | Effect |
|---|---|---|
| `cpuBalancer` | `false` | Enable ProBalance **restraint** in the session governor. Without it, a governor started for partition steering runs `--no-restraint` (steer-only). |
| `cpuSets` | `false` | Pass `--cpu-sets` (force game-side steering on every profile; redundant on gaming lanes, which declare it). |
| `ecoMode` | `false` | Pass `--eco` (EcoQoS herding; set `efficiency_mode.background_images`). |
| `watchdog` | `false` | Pass `--watchdog` (rule engine; `--online` is added automatically for online profiles). |
| `keepAwakeWhileGaming` | `true` | Allow Keep-Awake. The per-profile catalog flag decides which profiles assert it (emulators only). |

The governor daemon starts when **any** of these is enabled **or** the active
profile's `cpu_partition_policy` is not `off` (all gaming lanes). Each flag —
and the profile policy — independently justifies the daemon; `cpuBalancer` is
no longer a master gate.

### Profile catalog flags (set in profile classes, surfaced in the cache)

- `keep_awake_while_gaming` — `True` only on `EmulatorLatencyBaseProfile`.
- `is_online_profile` — drives the watchdog `--online` demote-only restriction.
- `cpu_partition_policy` — `full` on every gaming lane (game + background
  steering + auto-steer), `off` on productivity. The tray passes
  `--profile <id>` and the daemon resolves the policy from the catalog.
- `background_steer_images` — the profile's background steer list: browsers /
  Discord / Spotify / Wallpaper Engine everywhere; capture lanes add
  OBS + Medal (their encoders run at full speed on background cores). Never
  includes the profile's own executables (browser-game lanes) or overlay /
  input tools (RTSS, G HUB).

## Online-safety model

- **ProBalance / EcoQoS / core partitioning** are online-positive: they only
  demote/steer *background* work or apply a soft scheduler hint, never mutating
  the game's timing or hard affinity. They run on online profiles with the
  hardened exclusion set. Partition steering opens processes with only
  `PROCESS_SET_LIMITED_INFORMATION`, never injects, and never reads memory.
  Auto-steer additionally honors the NEVER_KILL + `process_overrides.protect`
  exclusion union, the game subtree, and the foreground app.
- **Watchdog** is restricted to **demote-only** on `is_online_profile` profiles
  (the tray passes `--online`). Throttle (affinity mutation) and trim are
  offline-only — mid-match affinity changes are exactly the nondeterminism
  RollbackGuard exists to prevent.
- **Terminate is never expressible** as a watchdog action; any disallow-list
  kill still routes through `ProcessJanitor` (NEVER_KILL + protect list).

## Enablement

**Core partitioning is on by default** for every gaming profile: apply a
profile, launch the game, and the tray starts the session governor
automatically (steer-only unless `cpuBalancer` is on). Disable or tune it via
the `cpu_sets` section of `abso.yaml` (`background_steer: false` keeps only
the game-side steering; per-profile `cpu_partition_policy` overrides belong in
a profile subclass). On single-domain CPUs and symmetric dual-CCD parts it
no-ops safely. On AMD X3D parts, disable Windows Game Mode if performance
regresses — its own CCD parking can fight manual steering.

The priority-mutating tiers stay opt-in. To turn them on **for this machine**,
edit `%APPDATA%\ABSO\tray-config.json`:

```json
{ "cpuBalancer": true, "ecoMode": false, "watchdog": false }
```

then restart the tray and launch a game. For EcoQoS, also set
`efficiency_mode.background_images` in `abso.yaml` (images already on the
partition steer list are steered, not eco-throttled); for the watchdog, add
`watchdog.rules`. Watch your in-game **1% lows / frame-time graph** — that's the
metric these move (partitioning under streaming/multitasking load can also lift
average FPS), and anti-cheat behavior is yours to confirm in your titles.

## Verification status

All mechanisms are covered by hermetic tests (Win32 calls are dependency-injected)
**and** were live-verified on the i9-14900F: CPU Sets topology (16 logical
P-core threads identified), CPU limiter affinity round-trip, EcoQoS apply/reset,
proc_actions priority/trim/working-set, the watchdog demote+restore on a real
process, and the fully-integrated daemon (`--cpu-sets --eco --watchdog`) with a
graceful sentinel stop. A live run also caught and fixed a real bug — hidden
power settings (core parking) require `powercfg /qh`, not `/query`.
