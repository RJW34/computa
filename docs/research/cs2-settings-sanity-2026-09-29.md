# Counter-Strike 2 settings sanity review — 2026-09-29

This review covers all six shipped CS2 lanes on the reported i9-14900F,
RTX 4070, 2560×1440 300 Hz VRR primary and mixed-refresh secondary setup.
The intended result is smooth motion with low latency, with Windows HDR when
requested. No gameplay, frame-time or latency measurement was performed.
These are defensible defaults and explicit tradeoffs, not a measured optimum.

## Corrections

1. **All four G-SYNC lanes now recommend native VSync Enabled.** The strict
   fullscreen variants previously recommended Disabled while the capture
   variants recommended Enabled. Valve's CS2-specific guidance recommends
   G-SYNC, VSync and Reflex together. Its video-settings update also added an
   in-game G-Sync status indicator; that is a useful manual check, distinct
   from ABSO's driver readback. The status may be hidden with Vulkan or a
   non-NVIDIA GPU. Native settings remain manual. [Valve release notes,
   25 June 2024](https://store.steampowered.com/news/posts/?appids=730&enddate=1719438877&feed=steam_community_announcements)
2. **Reflex Enabled is the starting recommendation; Boost is optional.**
   NVIDIA's CS2 instructions select Enabled. Boost can further reduce latency
   but uses more power and can lower FPS. It should be compared on the actual
   workload, not represented as automatically superior. [NVIDIA CS2 guide,
   27 September 2023](https://www.nvidia.com/en-us/geforce/news/counter-strike-2-released-featuring-nvidia-reflex/)
3. **Retain the managed driver refresh-minus-three ceiling for G-SYNC.**
   At 300 Hz this is 297; native `fps_max 0` remains manual guidance. CS2 has
   no native writer or verification handler, so removing the driver ceiling
   as was done for OW2 would remove CS2's only managed static ceiling. Reflex
   can pace below it. The fallback is not proof of better performance, VRR
   engagement, or a need for duplicate limiters. NVIDIA documents automatic
   below-refresh pacing with G-SYNC/VSync/Reflex and specifically requires
   native VSync for its windowed path. [NVIDIA latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)
4. **Preserve captured power, scheduler/MMCSS, NIC and MSI policy.** All six
   lanes opt into `preserve_baseline_system_policy`. They no longer impose
   Ultimate Performance, CPU minimum100, forced unparking, USB/PCIe power
   changes, scheduling quantum/MMCSS Games overrides, NIC tuning or GPU MSI.
   NVIDIA describes such advanced system changes as situational and capable
   of worsening latency. This is removal of an unsupported default, not a
   claim that the opposite settings are faster. [NVIDIA latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)
5. **Allow Fullscreen Optimizations in every CS2 lane.** Explicitly clear the
   old per-executable and global FSO-disable requests. Fullscreen in a menu
   does not prove exclusive presentation or a compositor cost. Microsoft's
   FSO design permits optimized presentation with fast switching and overlays;
   disabling it is a troubleshooting choice requiring evidence, not a universal
   FPS fix. Native Fullscreen and fullscreen-only G-SYNC remain the strict
   lane's intended modes. [Microsoft FSO explanation](https://devblogs.microsoft.com/directx/demystifying-full-screen-optimizations/)
6. **Remove unsupported graphics and HDR claims.** Split Shader Detail and
   Particle Detail into actual menu options. Describe Low and anti-aliasing
   choices as starting points. Boost Player Contrast improves visibility but
   has a possible graphics cost, contrary to the former negligible-cost claim.
   HDR lanes enable Windows HDR; they do not verify CS2's output color space.
   CS2's High Dynamic Range Quality/Performance option is a rendering-quality
   choice and its label alone does not prove HDR display output. Digital
   vibrance45 is a desaturation preference, not an sRGB clamp. A200-nit SDR
   white setting is a preference, not calibration.

## Direct current-build evidence

Read-only inspection of installed Steam app730 reported build **25588766**.
Valve's `resource/csgo_english.txt`, read from the installed `pak01_dir.vpk`
archive and its data archive, contains:

- `LowLatencyVSyncRecommendation_Nvidia`: recommends the three-way
  G-SYNC/VSync/Reflex combination.
- `SFUI_Settings_Reflex_Info`: describes Boost's power/FPS tradeoff.
- `SFUI_Settings_PlayerContrast_Info`: describes visibility improvement and
  possible graphics-performance degradation.
- Separate Shader Detail and Particle Detail labels/tooltips; both higher
  settings have visual-quality and rendering-cost tradeoffs.
- `SFUI_Settings_HDR_Info`: describes HDR rendering quality and GPU-memory
  use. It does not identify the live swap-chain output color space.

Only relevant labels/tooltips were inspected; no game binaries were executed
and no settings were written. The web research used Valve/NVIDIA/Microsoft
sources. The old Valve FAQ endpoint linked by its release notes returned no
usable article text through the research tools; conclusions above use the
accessible official release notes and installed Valve resources instead.

Two Steam account-local video files had the same relevant saved values:
2560×1440, `fullscreen=0`, `coop_fullscreen=1`, `nowindowborder=1`,
`mat_vsync=1`, `r_low_latency=2`, MSAA4, HDR-detail−1, FSR-detail0. Both
account-local machine convar files stored `fps_max=400`. File timestamps
were3August and27September2026 UTC. These were point-in-time reads while
CS2 was running; they do not prove consumed runtime settings, the active
account, native HDR output, or synchronization engagement. No numeric HDR/
FSR enum meaning was inferred from the saved values alone. They were not
rewritten to match recommendations. Source `abso.yaml` had no CS2 override.

## Effective setting inventory after this review

The following covers inherited defaults as well as CS2 declarations. It is
the source configuration, before optional user overrides, capability gates,
device support and baseline restoration. Readback is not a performance test.

| Area | Effective intent | Evidence / remaining limitation |
| --- | --- | --- |
| Native game configuration | No CS2 handler; display mode, VSync, Reflex, FPS and graphics recommendations are manual | `system_only`; applying ABSO cannot establish native compliance |
| Windows game policy | Game ModeOn; Game BarOff; Game DVROff; HAGSOn; maximum refresh requested | Existing compatibility choices; no current CS2 comparison establishes HAGS as fastest |
| Windows presentation | Strict/no-sync windowed-optimizationsOff and VRR-optimizationOff; capture bothOn | Preserve existing DX11 lane contract; different from FSO, which is now allowed everywhere |
| FSO | Global disableFalse and `cs2.exe` per-app disableFalse | Explicitly clears stale disable targets; actual present mode remains unverified |
| Power | Empty handler targets | Retains backup/restore handler; no selected power plan, CPU floor/ceiling, parking, USB or PCIe override |
| Registry scheduler/MMCSS | No Win32PrioritySeparation or Games task override | FSO map remains; opt-in legacy settings are still available to deliberate custom profiles |
| NIC driver / GPU MSI | `nic_tuning=False`, `enable_msi=False` | Handler no-op flags, not inverse writes; focused tests block device probes and confirm unchanged success |
| Network | `disable_nagle=False`, presetdefault; network_scope none | No automatic TCP gaming tuning; no measured ping benefit claimed |
| Native graphics API | DeclaredDX11 | Windows default path assumption, not runtime detection; Vulkan launch choice can invalidate status/driver assumptions |
| Process priority | Strict/no-sync CPUHigh3 and IOHigh3; captureNormal2/2 | Retained existing policy; no evidence that High improves this machine's CS2 frame times |
| CPU placement | Native affinity strategyNone; inherited partition policyfull | Does not hard-pin through the affinity handler. User governor/CPU Sets are separate and remain enabled according to user policy; unrestricted scheduling is not promised |
| NVIDIA identity | Counter-Strike2 stable profile, `cs2.exe`, historical CS:GO aliases | Four G-SYNC lanes require exact binding; profile name alone is not binding proof |
| NVIDIA common preset | LLMOff, prefer-maximum-performance, shader-cacheOn, threaded-optimizationOn, triple-bufferingOff | Retained preset choices. Native Reflex is manual. Not every driver knob is relevant to every graphics API or publicly readable; unknown private controls remain manual |
| NVIDIA no-sync | VSyncOff, Max Frame RateOff, per-app VRRforce_off, globalVRRoff, tear-controldisable | Explicit tearing policy; not the default recommendation for someone seeking tear-free smoothness |
| NVIDIA G-SYNC | VSyncOn, per-app VRRallow, tear-controldisable, VRR/VSync coordinationenable, automatic refresh−3 driver cap | Managed fallback ceiling. Native VSync/Reflex still require user action; lower runtime FPS is not necessarily cap drift |
| Global G-SYNC mode | Strictfullscreen_only; capturefullscreen_and_windowed | Desktop-wide selection; per-app binding and runtime engagement still matter |
| Windows HDR | SDRlanesOff; HDRlanesOn + advanced-colorOn; AutoHDROff throughout | Windows policy, not game-native HDR proof |
| HDR color policy |200-nit SDR white; ACMdisabled; native ICC; vibrance50 | Existing preferences retained; exact monitor calibration and live game color-space output are unverified |
| SDR color policy | sRGB ICC; vibrance45; OSD guidancecompetitive_fps | An ICC association or vibrance adjustment cannot establish a calibrated sRGB clamp |
| Display range | Full | Appropriate only with matching display signal interpretation; no image-quality or speed measurement here |
| Mouse | AccelerationOff, linear curve requested, Windows sensitivity10 | Desktop pointer policy; no in-game sensitivity, raw-input or latency result established |
| Audio | Enhancement-disable requested | Existing APO policy retained; potential functional/audio tradeoffs are not a measured CS2 performance gain |
| Game DVR | hard_disableTrue in all lanes | Capture-safe preserves designated OBS/Medal/overlay processes; it does not enable Xbox Game Bar recording |
| Process sweep | Strict/no-sync retains inherited broad killset; capture filters designated capture/peripheral images | User protections win. Capture does not preserve every background app or guarantee recorder headroom |
| Xbox / AI | inheritedoff/off | Launch/background policy retained, separate from video settings |
| AMD fallback | Derived ULPS-disable, Anti-LagOn, EnhancedSyncOff, ChillOff, BoostOff | Not applicable to the reported RTX4070; not researched or claimed correct for AMD CS2 in this pass |
| Legacy memory/MMCSS | Disabled by default | No automatic LargeSystemCache, DisablePagingExecutive, SystemResponsiveness or NetworkThrottlingIndex target |
| Classification | `requires_reflex=True`, `low_latency_high_fps`, `is_online_profile=False` | Historical online/rollback classification conflates concepts; not a claim CS2 is offline. No new TCP tuning or rollback policy was introduced |

Strict G-SYNC variants retain the overlay-free gate and their matching capture
fallback. Existing mixed-refresh fallback can select the no-sync sibling;
that changes the user's tear-free goal and must be surfaced by the caller.
Capture lanes have neither fallback pointer and preserve their capture mode.
This pass did not change fallback routing, shared governor policy or janitor
scope.

## Why the retired system defaults were not replaced with guessed defaults

Microsoft describes power management as platform- and workload-sensitive,
with silicon-vendor tuning. Its OEM Game Mode example containing a100% CPU
floor is not a universal desktop-CS2 prescription. [Processor power
management](https://learn.microsoft.com/en-us/windows-hardware/customize/power-settings/configure-processor-power-management-options)
NIC interrupt moderation exchanges CPU work against latency; a low-latency
server example does not establish an FPS benefit in CS2. [Microsoft network
adapter tuning](https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics)
MSI support belongs to device/driver installation and capability; a registry
switch is not a gaming benchmark. [Microsoft MSI documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/kernel/enabling-message-signaled-interrupts-in-the-registry)
MMCSS Games priority6 under High is treated as2, and its GPU-priority entry
is not used; there is no basis here for a universal scheduler gain.
[Microsoft MMCSS](https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service)

An ordinary profile transaction restores captured system baseline before
new targets. Removing a target alone does not undo a prior write already
present in that baseline. No cross-game migration, driver write, power change,
network restart, config edit, game launch or deployment occurred in this
subtask. Unknown original settings must not be replaced by guessed defaults.

## Validation and remaining work

`tests/test_cs2_sanity.py`: **36 passed**. It checks all six lanes for baseline
preservation, MSI/NIC no-op behavior, explicit stale FSO-clear requests,
native/driver sync consistency, retained G-SYNC ceilings and no-sync driver
limiterOff, manual Reflex choice, capture/display/HDR separation, truthful
graphics guidance and absence of a native writer. Focused Ruff passes.
The root integration owns the shared FSO expectation, complete catalog and
snapshot update, full-suite results and any deployment.

To establish a better local configuration requires user gameplay evidence:
confirm the actual display/API/G-SYNC status, record representative frame-time
distributions and latency with reproducible workloads, then compare one
variable at a time. Priorities are Reflex Enabled versus Boost, the fallback
driver ceiling with Reflex pacing, graphics quality versus GPU time, HAGS,
process priority/CPU partitioning, and capture contention. HDR output color
space needs an actual presentation check. FPS near297 alone cannot answer
whether VRR engaged or whether motion is smooth.
