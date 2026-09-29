# OW2 defaults after the evidence review

The September 2026 review found a well-supported synchronization configuration
alongside unmeasured system tweaks. The revised six OW2 profiles preserve their
SDR/HDR and capture policies while reducing the settings they impose.

- G-SYNC profiles keep native VSync On and the game's refresh-minus-three
  ceiling (297 at 300 Hz). NVIDIA Max Frame Rate is explicitly Off so an old
  driver limiter cannot remain alongside the native limiter. No-sync profiles
  retain native VSync Off and the game's 600 FPS ceiling.
- Reflex Enabled and Enabled + Boost both satisfy the manual verification
  step. The saved choice is never rewritten. Boost is optional, with power and
  possible FPS tradeoffs; it is not a verified improvement on every machine.
- Reduce Buffering Off remains the baseline with Reflex enabled. The profile
  does not claim that On necessarily conflicts with Reflex or causes stutter.
- OW2 no longer chooses Ultimate Performance, forces minimum CPU state or
  core parking, changes USB/PCIe power policy, overrides scheduler/MMCSS
  values, tunes NIC driver properties, or forces GPU MSI mode. These settings
  remain available elsewhere but are not justified as automatic OW2 defaults.
- Native resolution, image-quality options, windowed VRR, HDR and capture
  choices remain as before. Global user CPU-governor preferences are separate
  from these profile changes and are not silently rewritten.

This is a conservative configuration policy, not a benchmark result. A single
native limiter is simpler; it does not establish that duplicate limiters caused
the reported stutter. Refusing to force experimental tweaks likewise does not
prove that their opposite values are faster.

## Evidence and limitations

[NVIDIA's latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)
documents G-SYNC/VSync/Reflex below-refresh pacing and directs windowed users
to native VSync. [Original limiter experiments](https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/11/)
compare native and external limiters; they do not establish a benefit from
stacking both on this PC.

[NVIDIA's Boost explanation](https://www.nvidia.com/en-us/geforce/news/reflex-low-latency-platform/)
and [its FPS tradeoff discussion](https://www.nvidia.com/en-gb/geforce/news/ces-2022-nvidia-community-qa/)
support treating Boost as a choice requiring measurement.
[Original Overwatch Reflex experiments](https://github.com/klasbo/GamePerfTesting/blob/master/text/02-reflex.md)
found no meaningful Reduce Buffering difference with Reflex after repeated
sampling. Those results are from an older game version and hardware, not a
current OW2 benchmark on this machine.

[Microsoft processor power management](https://learn.microsoft.com/en-us/windows-hardware/customize/power-settings/configure-processor-power-management-options)
and [interrupt moderation documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/interrupt-moderation)
describe tradeoffs rather than universal gaming gains. Local comparisons of
frame-time distributions and latency are still required.

## Correct capability reporting

AMD FreeSync version-3 EDID blocks can store a maximum above 255 Hz in extended
fields. Reading only the legacy maximum mislabeled the reviewed primary as
48–240 Hz when its active EDID advertises 48–300 Hz. The decoder now handles
the versioned fields and checks block boundaries. The reference is the
[original edid-decode implementation](https://github.com/gjasny/v4l-utils/blob/master/utils/edid-decode/parse-cta-block.cpp).

HDR capability is queried from active Windows display targets and matched by
display identity. Unsupported is false; failed, missing or ambiguous readback
is unknown. Neither advertised VRR support nor desktop HDR activity proves
that a game's live presentation path is using VRR.

## Existing installations

Removing a profile target does not itself undo an earlier write. Ordinary
profile transactions restore the captured baseline before applying new
targets. A targeted migration must restore only known retired values from a
verified backup, preserve unrelated settings, and report missing baseline
coverage honestly. Do not invent factory defaults, reset displays, or restart
network adapters to make verification appear complete.

Local research evidence is in
`reports/research/2026-09-29-ow2-settings/`; deployment and machine state belong
in the machine-local briefing. Software tests validate setting resolution,
readback, and preservation; they do not establish a gaming-performance win.
