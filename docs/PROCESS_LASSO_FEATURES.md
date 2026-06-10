# Process Lasso-Class Features (CPU / process / power session tuning)

ABSO ships an in-house equivalent of the useful parts of
[Process Lasso](https://bitsum.com/) — background-process restraint, P-core
steering, per-process power throttling, a reversible CPU limiter, and a
declarative watchdog — plus a "Highest Performance" core-parking power plan.
Everything here targets **frame-time consistency (1% lows), not average FPS**,
and **nothing runs until you opt in** (see [Enablement](#enablement)).

> Do not confuse these with GPU tuning. Higher graphics quality at a fixed FPS
> cap is a GPU-headroom problem (DLSS / Frame Gen). These features reduce
> CPU-side stutter so a capped game *feels* locked.

## Feature catalog

| Feature | What it does | Where it lives |
|---|---|---|
| **ProBalance governor** | Demotes background CPU spikers to BelowNormal during a game session and auto-restores them. Never touches the game, foreground, anti-cheat, launchers, audio, Discord, editors, or your `process_overrides.protect` images. | `abso/core/cpu_balancer.py` (daemon), spawned by the tray |
| **"Highest Performance" power plan** | Disables CPU core parking (`CPMINCORES`=100) and holds the processor min-state at 100% during gaming profiles; the desktop profile relaxes the floor to 5 so the CPU still idles cool. | `abso/settings/power.py` (apply pipeline) |
| **Keep-Awake** | Inhibits system/display sleep while a gamepad-driven game runs (emulators) — `SetThreadExecutionState`. Cleared on game exit. | tray (`ABSO-Tray.ps1`) + profile flag |
| **CPU Sets (soft P-core steering)** | `SetProcessDefaultCpuSets` biases the game toward P-cores while leaving hard affinity intact (threads still spill to E-cores). Anti-cheat-safe, hybrid-correct. | `abso/core/cpu_sets.py`, hosted in the daemon |
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

cpu_sets:                   # soft P-core steering
  enabled: false

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
| `cpuBalancer` | `false` | Spawn the daemon (ProBalance) for a game session. **Master gate** — the Tier B flags below require it. |
| `cpuSets` | `false` | Pass `--cpu-sets` (P-core steering). |
| `ecoMode` | `false` | Pass `--eco` (EcoQoS herding; set `efficiency_mode.background_images`). |
| `watchdog` | `false` | Pass `--watchdog` (rule engine; `--online` is added automatically for online profiles). |
| `keepAwakeWhileGaming` | `true` | Allow Keep-Awake. The per-profile catalog flag decides which profiles assert it (emulators only). |

### Profile catalog flags (set in profile classes, surfaced in the cache)

- `keep_awake_while_gaming` — `True` only on `EmulatorLatencyBaseProfile`.
- `is_online_profile` — drives the watchdog `--online` demote-only restriction.

## Online-safety model

- **ProBalance / EcoQoS / CPU Sets** are online-positive: they only demote/steer
  *background* work or apply a soft hint, never mutating the game's timing. They
  run on online profiles with the hardened exclusion set.
- **Watchdog** is restricted to **demote-only** on `is_online_profile` profiles
  (the tray passes `--online`). Throttle (affinity mutation) and trim are
  offline-only — mid-match affinity changes are exactly the nondeterminism
  RollbackGuard exists to prevent.
- **Terminate is never expressible** as a watchdog action; any disallow-list
  kill still routes through `ProcessJanitor` (NEVER_KILL + protect list).

## Enablement

Nothing is active out of the box (except Keep-Awake for emulator profiles,
which only inhibits the idle timer). To turn the rest on **for this machine**,
edit `%APPDATA%\ABSO\tray-config.json`:

```json
{ "cpuBalancer": true, "cpuSets": true, "ecoMode": false, "watchdog": false }
```

then restart the tray and launch a game. For EcoQoS, also set
`efficiency_mode.background_images` in `abso.yaml`; for the watchdog, add
`watchdog.rules`. Watch your in-game **1% lows / frame-time graph** — that's the
metric these move, and anti-cheat behavior is yours to confirm in your titles.

## Verification status

All mechanisms are covered by hermetic tests (Win32 calls are dependency-injected)
**and** were live-verified on the i9-14900F: CPU Sets topology (16 logical
P-core threads identified), CPU limiter affinity round-trip, EcoQoS apply/reset,
proc_actions priority/trim/working-set, the watchdog demote+restore on a real
process, and the fully-integrated daemon (`--cpu-sets --eco --watchdog`) with a
graceful sentinel stop. A live run also caught and fixed a real bug — hidden
power settings (core parking) require `powercfg /qh`, not `/query`.
