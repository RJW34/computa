# Rivals of Aether II settings sanity review — 2026-09-29

This pass covers the six shipped Rivals lanes and two import-compatible legacy
aliases. It corrects unsupported claims, conflicting limiter/presentation policy,
and native-file safety defects. It does **not** establish the fastest settings for
this PC. No game was launched, gameplay recorded, native configuration changed,
or live system/driver setting applied by this review.

## Evidence and its limits

| Question | Primary evidence checked | Conclusion and limit |
| --- | --- | --- |
| Must rendering follow a 60-FPS multiple? | [SnapNet simulation versus presentation](https://www.snapnet.dev/docs/core-concepts/simulation-vs-presentation/) explicitly describes interpolation between fixed simulation ticks, including rendering at 144 Hz with a 60-Hz simulation. [Aether animation documentation](https://rivals2.com/workshop/knowledge-base/miscellaneous/animation-states/) describes animation authoring. | Fixed simulation/animation timing does not prove that 240 is required instead of 297 on a 300-Hz display. SDK capability alone does not prove every aspect of the current game's runtime implementation. |
| Is Reflex established? | [NVIDIA's supported-products list](https://www.nvidia.com/en-us/geforce/technologies/reflex/supported-products/) was checked on September 29; it lists Marvel Rivals, not Rivals of Aether II. | No supported native Reflex integration was established. Absence from a list is not proof of permanent absence. Do not copy OW2's Reflex policy into this game or label driver queue controls as Reflex. |
| What graphics API is published? | [Aether's Steam product page](https://store.steampowered.com/app/2217000/Rivals_of_Aether_II/) lists DirectX 11 in both minimum and recommended requirements. | DX11 remains the published policy basis. This is not a live renderer probe and does not rule out undocumented launch paths. |
| What do the native keys mean? | [Epic UGameUserSettings API](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/UGameUserSettings) documents VSync, fullscreen modes and zero as the disabled FPS-limit value. The checked documentation defaults to UE5.8, not a proven match to this game's engine build. | `999` remains a finite numeric readback, not an invented uncapped synonym. `bUseRawInput` is not documented there; no Aether source establishing that key's use was found. Its presence in a previously managed file is not proof the game consumes it. |
| Why one below-refresh cap? | [Blur Busters' original G-SYNC testing and recommendations](https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/14/), initially published June 20, 2017, describe a native cap at least three below refresh and alternative external limiters. | Refresh-minus-three is a starting policy, not a Rivals-specific result. The original test setup used a hardware G-SYNC display; implementation, modern driver and mixed-monitor differences limit transfer to this PC. |
| Does driver VSync cover capture/borderless? | [NVIDIA's latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/), October 1, 2020, distinguishes fullscreen driver VSync from native VSync for windowed presentation. | Capture lanes now request native VSync On and windowed/fullscreen G-SYNC. This does not prove active VRR or tear-free runtime output. |
| Is Ultra always harmful, or system tuning always beneficial? | The same NVIDIA guide recommends Ultra when Reflex is unavailable and describes advanced scheduling/interrupt/power changes as situational. | Remove blanket Ultra-harm and automatic improvement claims. Retained LLM On is a starting choice to compare, not proven best. Preserve baseline power/scheduler policy. |
| Is exclusive fullscreen universally faster? | [Microsoft's DXGI flip-model guidance](https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/for-best-performance--use-dxgi-flip-model) describes efficient windowed presentation paths. | An INI fullscreen flag or FSO registry value does not prove legacy exclusive presentation or a latency win. Keep the existing distinct lanes without promising an advantage. |
| Does forced Threaded Optimization improve this DX11 game? | The repo maps `threaded_optimization` to `0x20C1221E` (`OGL_THREAD_CONTROL_ID`). [Profile Inspector's primary mapping](https://raw.githubusercontent.com/Orbmu2k/nvidiaProfileInspector/master/nvidiaProfileInspector/CustomSettingNames.xml) defines Auto=0, On=1, Off=2. | Request Auto to clear former forced On. No measured or documented DX11 worker-thread gain is claimed. Inspector mapping is implementation evidence, not a benchmark. |

The publisher's [Steam announcement API](https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=2217000&count=30&maxlength=0&feeds=steam_community_announcements)
was read through HTTPS on September 29. It returned `1.7.2.1 Single Change
Hotfix` dated September 28, 2026, 19:13 UTC (floorhug input-buffer correction),
`Hotfix 1.7.1.1` dated September 22 (lobby-search repair following EOS maintenance),
and `Patch 1.7.1 - Mecha Madness GX` dated September 1. The returned feed was
checked for Reflex, FPS, VSync, HDR, rendering and performance changes; no new
setting policy was established from those entries. This is not an exhaustive
patch archive or proof of the installed game version; a distinct 1.7.2 main
announcement was not in the returned feed. Input-buffer patch notes do not
describe a GPU render queue.

## Corrected lane policy

| Lane | Requested presentation | Native VSync | Driver VSync / VRR | Native cap at 300 Hz | HDR |
| --- | --- | --- | --- | --- | --- |
| No Sync | Fullscreen; FSO disabled | Off | Off / Off | 300 | Windows Off, game Off |
| No Sync HDR | Same | Off | Off / Off | 300 | Windows On, game Off |
| G-SYNC | Fullscreen; FSO disabled | Off | On / fullscreen | 297 | Windows Off, game Off |
| G-SYNC HDR | Same | Off | On / fullscreen | 297 | Windows On, game Off |
| G-SYNC Capture | Borderless; FSO allowed | On | On / windowed and fullscreen | 297 | Windows Off, game Off |
| G-SYNC HDR Capture | Same | On | On / windowed and fullscreen | 297 | Windows On, game Off |

All lanes explicitly request driver Max Frame Rate Off. G-SYNC no longer asks
two limiters for the old 240 target or declares dual limiting intentional.
Capture guidance now agrees with native VSync and global G-SYNC targets.
`fighting_60hz_vrr` remains an explicit legacy custom policy (240 at 300 Hz).
No-sync retains its existing bounded multiple-of-60 policy (300 at 300 Hz,
120 at 144 Hz) for compatibility; there is no claim that this cadence is required
by simulation or prevents rollback. The legacy `rivals2-300hz-max` alias follows
detected refresh and does not force an unsupported 300-Hz mode.

The NVIDIA family remains `Rivals 2`, bound to
`Rivals2-Win64-Shipping.exe`, retaining existing aliases. The explicit per-game
map retains LLM On, Prefer maximum performance, shader cache On and triple
buffering Off; Threaded Optimization is now Auto. No global shader-cache budget
is changed and no native Reflex control is invented. GPU power mode remains a
policy choice with possible power/thermal cost, not a measured improvement.
Existing unsupported-private-control manual confirmation remains applicable.

## Remaining effective settings and boundaries

| Area | Effective family policy after this pass | Evidence boundary |
| --- | --- | --- |
| CPU power, parking, USB and PCIe | Empty power-handler request; existing baseline policy preserved | Does not silently revert historical values to guessed Windows defaults. |
| Scheduler / MMCSS | No Win32PrioritySeparation or game-priority request | No scheduler improvement is claimed from SnapNet's existence. |
| Network / NIC / MSI | Network default with Nagle tweak disabled; no NIC or MSI request | No network-adapter restart or interrupt rewrite; settings do not guarantee online stability. |
| Process priority / affinity | Normal CPU and I/O; no profile affinity pinning | Shared user governor preferences are separate and were not changed. |
| Windows | Game Mode On, Game Bar/DVR Off, HAGS On, maximum detected refresh | Retained policies, not a measured best combination. Windowed optimizations and VRR optimization are On only for capture lanes. |
| Input | Existing Windows mouse acceleration/curve/sensitivity policy retained | No controller benefit claimed. In-game controls, account tags, bindings and raw-input values remain user-owned. |
| Color | SDR sRGB/vibrance45/full-range policy; HDR variants retain neutral HDR color policy, Windows HDR/WCG On, Auto HDR Off and SDR white200 nits | These are appearance/brightness starting points, not display calibration or FPS improvements. |
| Native HDR | Off in every lane; no built-in write to HDR nits | HDR-labeled variants intentionally use SDR content within Windows HDR. Native game HDR support is unestablished. |
| Capture / background processes | Capture lanes keep OBS/Medal/RTSS/overlays available; strict lanes use existing cleanup rules | Running capture software can still affect performance. Shell/AI-agent preferences and notification policy remain existing behavior. |
| Graphics quality / renderer | No resolution scale, AA, texture/effects, dynamic resolution or renderer writes | Preserve user choices until game-specific measurements support a change. |

Read-only local evidence from
`%LOCALAPPDATA%\Rivals2\Saved\Config\Windows\GameUserSettings.ini` showed
fullscreen0, last-confirmed0, preferred1, VSyncFalse, cap999, dynamic-resolution
False, gameHDROff, HDRnits1000 and raw-inputTrue. Those values were not changed.
They prove saved text only; this review did not observe in-game menus, monitor
VRR engagement, runtime cap consumption, presentation mode or input latency.

## Native-handler defects corrected

`abso/settings/rivals2_config.py` now:

- Rejects missing target sections in sectioned files instead of reading or
  modifying equal-looking keys in another section. Sectionless legacy files
  remain supported; BOM-prefixed target headers are readable.
- Fails before any write when automatic refresh/cap resolution fails or a
  requested nonempty config has not been created. Explicit cap policies remain
  supported; the global policy helper was not changed.
- Rejects unsupported keys, including deprecated explicit `raw_input`, in apply
  and verification. Framework `_` metadata remains ignored. Custom overrides
  using `raw_input` must remove it; the unsupported request cannot verify as active.
- Validates finite, nonnegative integer cap requests and fullscreen0/1/2. Invalid
  saved numeric values cannot falsely match through truncation. Finite999 is not
  equivalent to zero. Fractional caps are rejected rather than silently rounded.
- Uses atomic writes and skips unchanged files.
- Restores only managed native keys and the last-confirmed fullscreen mirror in
  the intended section, reusing the shared UE restore implementation. Newer
  unrelated graphics, controls and raw-input text survive; managed keys absent
  from the baseline are removed. Full-file recovery remains available when the
  current file is missing. Legacy detected-field backups remain readable, but
  their raw-input field is deliberately not reapplied.
- Leaves profile-target comparisons to `verify_active`; generic audit no longer
  calls deliberate borderless or native-VSync-On configurations defects.

Restore still owns the handler's supported HDR-nits key for explicit custom
requests and historical snapshots. Built-in profiles do not set that value.
Saved-file checks do not prove a running game has consumed settings; closing the
game before later authorized changes remains the normal workflow.

## Validation and next evidence

Focused command: `python -m pytest tests/test_rivals2_sanity.py
tests/test_handlers/test_rivals2_config.py tests/test_core/test_native_config_switch.py -q`.
**91 passed**, with one existing pytest unknown-option warning. Whole-repository
Ruff and `git diff --check` passed. Tests cover all six shipped lanes and both
legacy aliases, cap/presentation consistency, no competing driver cap, raw-input
preservation, unsupported requests, malformed sections/numbers, unresolved cap
failure, idempotence and native-config switching. Independent review cleared
the managed-restore and false-success issues. Release-wide tests/build/deploy
are owned by the coordinating task and are not claimed here.

No local before/after performance artifacts exist for these policy changes.
The useful remaining comparison is a controlled, user-authorized run of native
297 versus the retained legacy240 cap, LLM On versus Ultra, and fullscreen versus
capture/borderless, holding graphics and workload constant. Record frame-time
distribution, actual display mode, tearing, GPU utilization and input latency
where measurable. Average FPS alone cannot establish responsiveness or online
netcode behavior. Do not call any current lane the absolute optimum without that
evidence.
