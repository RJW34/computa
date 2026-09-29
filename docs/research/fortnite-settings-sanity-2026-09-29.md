# Fortnite settings sanity review — 2026-09-29

Fortnite's five profiles now have a consistent separation between settings the
program writes and choices the player makes in-game. This review does not
establish an FPS or latency improvement. No game was launched, no live profile
was applied, and no installed settings were changed. CS2 was running during
the source work and was left alone.

## Findings and corrections

The strict G-SYNC HDR profile previously wrote both a native `refresh - 3`
limit and a matching driver limit. All Fortnite G-SYNC lanes now use native
Unlimited and one explicit driver ceiling, `refresh - 3` (297 at 300Hz).
Fortnite's menu offers discrete limits; the ability to write a custom INI
number does not establish that the game retains or offers that value. The
existing capture policy already used this arrangement. No-sync lanes remain
uncapped with driver VSync and VRR override disabled. This is a product policy,
not a measurement that this ceiling is optimal on every machine.

NVIDIA recommends native Reflex, describes its G-SYNC/VSync pacing below
refresh, and directs windowed users to in-game VSync. Capture profiles retain
borderless plus native VSync On; the strict profile retains its fullscreen
selection and driver VSync policy. Saved settings do not prove runtime G-SYNC
engagement. [NVIDIA latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)

The strict HDR profiles still claimed native HDR and wrote the UE output flag
and 1000-nit value, although the earlier local game log explicitly reported
native HDR disabled. All Fortnite profiles now preserve those native HDR and
calibration keys. HDR lanes describe **Windows HDR**, with native game output
unverified; Auto HDR and RTX HDR are not enabled by these profiles. Epic's
HDR glossary defines HDR but does not establish this installed PC build's
output support. [Epic HDR glossary](https://dev.epicgames.com/documentation/fortnite/hdr)

Reflex is a manual choice, with either On or On + Boost accepted. The handler
only reads `LatencyTweak2`; it never writes Reflex. Values 0/1/2 produce saved
Off/On/On + Boost observations, and absent or unrecognized values produce an
unknown manual check. This is a locally observed serialization contract, not
a guarantee from Epic that the key will remain stable. The existing September
6 UI evidence correlated On + Boost with value2. Legacy boolean keys are not
substituted for this three-state value. NVIDIA describes Boost as keeping GPU
clocks higher with a power tradeoff, so Boost is not presented as a measured
best choice here. [NVIDIA Reflex explanation](https://www.nvidia.com/en-gb/geforce/news/reflex-low-latency-platform/)

The old claim that disabling Fullscreen Optimizations prevents it from
stealing FPS was unsupported. All Fortnite lanes now allow global/per-exe
FSO. A fullscreen selector does not prove exclusive presentation. Microsoft
describes the optimized presentation path and recommends disabling FSO as a
troubleshooting comparison when a specific problem is observed.
[Microsoft FSO explanation](https://devblogs.microsoft.com/directx/demystifying-full-screen-optimizations/)

The inherited Ultimate Performance, minimum CPU state100, parking, USB/PCIe,
scheduler, GPU MSI, and NIC tweaks were not supported by Fortnite-specific
measurements. Fortnite now uses the shared policy that preserves captured
system defaults for those controls. NVIDIA explicitly characterizes advanced
scheduler/interrupt/idle tuning as situational and potentially harmful.
[NVIDIA latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)
Epic does recommend HAGS, Game Mode, Game Bar off, and High performance/Best
performance as troubleshooting options. HAGS and Game Mode remain requested;
High performance is a manual comparison option, not justification for forcing
Ultimate Performance plus every associated subsetting.
[Epic low-FPS support](https://www.epicgames.com/help/c-34254770/c-38015632/pcfortnite-a25544495)

## Effective profile inventory

The table records the source policy after this review. User overrides can
change these targets; no Fortnite override was identified in the reviewed
machine configuration. Runtime consumption still needs game testing.

| Area | Current policy and limit of the claim |
| --- | --- |
| Native presentation | No-sync and strict G-SYNC: selector0; capture: selector1/borderless. Updates `PreferredFullscreenMode` and `LastConfirmedFullscreenMode`, never invents `FullscreenMode`. |
| Native sync/cap | No-sync and strict: VSync Off; capture: On. All native limits Unlimited0. G-SYNC lanes retain one driver ceiling. |
| Reflex | Manual saved check, On or On + Boost; manual-only mismatch never changes `all_active` or triggers reapply. |
| Native HDR/calibration | Preserved, excluded from apply and existing-file restore ownership. Explicit legacy HDR-write requests fail before any config write. |
| Renderer/graphics | Preserved. Performance (DX12) and standard DX12 are manual comparison options; standard DX12/DLSS Quality and reduced effects remain a capture starting point. Resolution, Nanite, Lumen, ray tracing, DLSS, frame generation, and controls are not silently changed. |
| Windows | Game Mode/HAGS/max refresh requested; Game Bar/DVR/Auto HDR disabled. Capture requests windowed optimization/VRR optimization; strict lanes retain existing False values. |
| HDR Windows/color | HDR variants request Windows HDR/WCG, SDR brightness200, native ICC, vibrance50, ACM off. SDR variants request Windows HDR off, sRGB ICC, vibrance45. Full RGB requested. These are preferences, not monitor calibration proof. |
| NVIDIA | Native Reflex path requests driver LLM Off. No-sync preset forces VRR/VSync off; G-SYNC preset allows VRR and driver VSync On. Existing prefer-maximum-performance, shader-cache On, OpenGL threading On, triple-buffering Off, and tear-control defaults remain. OpenGL options are not claimed to improve Fortnite DX12. |
| Driver binding | NVIDIA profile `Fortnite`, actual renderer `FortniteClient-Win64-Shipping.exe`; anti-cheat executable hints are process-detection aliases, not renderer-binding proof. Capture retains exact-binding verification. |
| Power/scheduler | Power target map empty; Win32PrioritySeparation and Games MMCSS targets removed. A normal transaction restores the captured baseline, which may already contain older tuning. Removing ownership does not prove stock defaults or undo settings immediately. |
| NIC/GPU interrupt | `nic_tuning=False`, `enable_msi=False` are no-op ownership policies, not instructions to disable networking features or revert MSI. No NIC restart or GPU interrupt change is performed by this review. |
| Network | Default preset; Nagle-disable False. Existing profile online classification is False; no new transport optimization or anti-cheat claim is made. |
| Priority/affinity | Capture CPU/I/O Normal2; strict lanes retain High3. Hard affinity strategyNone. Runtime partition policy remains full and depends on tray flags; it is not a demonstrated Fortnite performance gain. |
| Other inherited settings | DVR hard-disable and audio-enhancement disable remain; mouse acceleration off/linear curve/sensitivity10 remain. These affect user preferences and have not been measured as Fortnite FPS gains. No timer-resolution or standby-memory handler is added. |
| AMD path | Existing ULPS-disable/Anti-Lag on, Enhanced Sync/Chill/Boost off; not exercised on this NVIDIA machine. |

Epic's current competitive guide recommends Performance mode using DX12,
lower rendering cost, and manual Reflex. It does not establish that every
RTX4070 user should replace standard DX12 or use a particular DLSS preset.
The checklist presents renderer changes as a manual comparison and preserves
the current file. Epic's graphics troubleshooting also offers a Performance
mode fallback and warns that renderer problems can be configuration-specific.
[Epic competitive guide](https://store.epicgames.com/news/fortnite-on-pc-best-settings-for-competitive-play-in-2026),
[Epic graphics troubleshooting](https://www.epicgames.com/help/c-202300000001636/c-202300000001719/a202300000013484)

## Local read-only observations

`%LOCALAPPDATA%\FortniteGame\Saved\Config\WindowsClient\GameUserSettings.ini`
contained borderless1, Unlimited0, native VSyncFalse, native HDRFalse, saved
Reflex2, 2560×1440, standard DX12/SM6, DLSSQuality3, NaniteFalse,
ray-tracingFalse and frame-generationFalse. Motion blur and dynamic resolution
were off; most expensive lighting/effects scalability values were0, with
textures/view distance1. The inspected UI evidence from September6 associates
DLSSQuality3 with Quality. These are file observations, not runtime metrics.
The selected system profile was OW2, so Fortnite VSyncFalse is not evidence
that an active Fortnite profile failed verification.

The earlier report remains historical context:
[Fortnite streaming audit](fortnite-streaming-audit-2026-09-06.md). Its raw
`ui-settings-result.json` and `session-evidence.json` live under the local-only
`reports/audits/2026-09-06-fortnite-gsync-hdr-streaming/` folder. The old report's
statement that native managed keys revert on a cross-game switch predates the
later transaction fix that preserves unrelated games' native configs.

## Validation and remaining checks

Focused tests cover all five lane contracts, inherited-policy removal,
single-limiter behavior, idempotent apply, unsupported HDR/Reflex-write
rejection, manual Reflex satisfied/disabled/unknown/missing cases, invalid
fullscreen enums, invalid/non-finite caps, fractional readbacks that must not
round into a false match, section isolation, and restoration from an older backup
without undoing later HDR/calibration/Reflex/renderer choices. Missing-file
restore still performs full backup recovery because there is no newer file to
preserve; explicit restore of managed sync keys remains supported.

Validation: **59 focused tests passed** in `test_fortnite_config.py` and
`test_fortnite_sanity.py`; Ruff and whitespace checks passed for the changed
files. The existing pytest configuration warning is unchanged. The parent
integration pass owns the full suite, catalog/golden refresh, and deployment.

The game must supply the remaining evidence: repeatable frame times, GPU and
CPU load, runtime G-SYNC indication, tearing, native HDR/output/capture color,
and On versus Boost under the intended scene and capture workload. Do not
restart a running game, apply another full profile, or clear shader caches
merely because saved settings cannot establish these outcomes.
