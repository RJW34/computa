# Fortnite G-SYNC Streaming audit and corrections

## Observations and limits

The reported in-match FPS fluctuated between **60 and 70**, rather than staying
at exactly 60. The audited session ran DX12 at native 1440p with Nanite,
Lumen High illumination/reflections, TSR, and DLSS disabled. The driver cap
was 297 on a 300 Hz primary display. This makes rendering load a plausible
cause; no representative frame-time recording established the bottleneck.

Direct readback showed the same saved NVIDIA synchronization settings for
Fortnite and CS2: G-SYNC allowed, fullscreen/windowed VRR, driver VSync On,
Fast Sync disabled, driver Low Latency Mode Off, and cap 297. The actual
Fortnite renderer executable belonged to NVIDIA's predefined Fortnite profile.
No persistent 60 FPS cap was found. OW2's specialized limiter/latency policy
is a separate contract and was not copied into Fortnite.

Windows HDR was enabled, but Fortnite's runtime log explicitly reported native
HDR output disabled. Borderless Fortnite had in-game VSync Off in the audited
session. An ordinary INI verification could not establish either actual HDR
output or G-SYNC engagement during play.

## Settings configured through the game UI

The subsequent Computer Use pass applied and verified these video settings:

| Setting | Saved configuration |
| --- | --- |
| Display | 2560×1440, Windowed Fullscreen on the primary monitor |
| Renderer / upscaling | DX12 / DLSS Quality |
| Synchronization | In-game VSync On, Reflex On + Boost |
| FPS limit | Unlimited in-game; existing NVIDIA ceiling 297 retained |
| Nanite, shadows, global illumination, reflections, ray tracing | Off |
| Textures / view distance | Medium / Medium |
| Effects / post processing | Low / Low |
| Motion blur, dynamic resolution, frame generation | Off |

One game restart activated DX12. The final quality Apply produced no additional
restart prompt, and saved-file readback confirmed the settings. No gameplay
benchmark or before/after tearing result was collected. Native HDR remained
disabled; the game exposed no native-HDR toggle in the inspected video menu.

The resolution and Medium quality choices are a starting point for the audited
RTX 4070 setup, not universal automatic profile values. Graphics, renderer,
resolution, and Reflex remain user-controlled; sync-only profile application
preserves their serialized keys.

## Product corrections

- Both Fortnite Streaming profiles now request borderless, in-game VSync On,
  engine Unlimited, and the NVIDIA `refresh - 3` ceiling. The strict fullscreen
  profiles retain their separate synchronization policy.
- HDR Streaming retains Windows HDR configuration and stops repeatedly writing
  native-game HDR and brightness keys. Guidance and catalog descriptions make
  the output-verification limit explicit; Auto HDR and RTX HDR are not implied.
- All four `NVDRS_APPLICATION` structures now match the NVIDIA SDK. Correct
  field sizes and packed flags restore actual application-ownership queries.
  V4 is 20492 bytes, version token `0x0004500C`; the old 20496-byte structure
  yielded false missing-ownership results. Corrected read-only queries confirmed
  actual Fortnite, CS2, and OW2 ownership on the audited machine.
- NVIDIA verification rejects unavailable setting reads and unresolved required
  executable ownership. A missing explicitly named profile no longer falls back
  to Base Profile, and a safe-to-create binding proposal is not existing-binding
  evidence.
- UE config verification no longer reports success for missing requested values,
  a missing config, or an unresolved automatic FPS-cap target. UE audit compares
  display mode and VSync against the active profile instead of prescribing
  exclusive fullscreen and VSync Off for every game.
- A subsequent switch to the CS2 profile exposed another persistence defect:
  baseline restore rewrote the entire old Fortnite INI, undoing the manually
  verified graphics and Reflex settings. UE restore now restores only the
  handler's managed INI keys and fullscreen mirrors, preserving newer user
  graphics, controls, renderer settings, and unrelated sections. Managed sync
  keys still return to baseline when switching away, then use the corrected
  contract when Fortnite Streaming is applied again.

Regression coverage includes profile contracts, preservation/idempotency/restore
of user-owned game settings, fixed ABI sizes and fallback-version calls,
unavailable driver/config evidence, and profile-aware presentation advice.
Raw settings backups, runtime logs, and machine diagnostic JSON remain in the
local ignored `reports/audits/2026-09-06-fortnite-gsync-hdr-streaming/` directory
under the repository's [local-only policy](../LOCAL_ONLY_FILES.md).

Final validation: **2725 tests passed, 13 integration tests deselected**, and
`ruff check .` passed. The frozen CLI built successfully and independently
confirmed Fortnite's driver settings and executable binding. Hardware detection,
BIOS readback, and backup creation completed. The full live `audit` command
required elevation unavailable in the shell; targeted read-only verification
was used instead. No profile apply, display reset, or HDR cycle was needed.

The tested build was deployed through `build.py deploy-existing`. A running
session governor initially held the executable open; its supported stop-file
signal allowed graceful cleanup, deployment, and automatic tray restart on the
same still-running CS2 process. The active CS2 profile was retained. The
Fortnite video values were recovered from the session's UI-verified snapshot
while Fortnite was closed, changing only the selected video keys and preserving
other current settings. Installed readback confirmed the saved Fortnite sync
contract and actual NVIDIA binding. No additional Windows reboot or Fortnite
renderer change was required by this recovery.

## Remaining runtime validation

Use a repeatable gameplay scene to measure FPS plus GPU/CPU frame times, check
the G-SYNC indicator, and compare tearing. Establish the intended HDR/capture
output separately. The older HDR-capability detector disagreement and the
secondary display's lower refresh rate are recorded observations, not proven
causes of this incident. Neither calls for a profile reapply or display reset
as part of this correction.

## References

- [NVIDIA system latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/): windowed G-SYNC/Reflex VSync guidance.
- [NVIDIA SDK header](https://github.com/NVIDIA/nvapi/blob/main/nvapi.h): application structure ABI.
- [Epic competitive settings guide](https://store.epicgames.com/news/fortnite-on-pc-best-settings-for-competitive-play-in-2026): rendering-cost tradeoffs.
- [NVIDIA G-SYNC indicator](https://www.nvidia.com/content/Control-Panel-Help/vLatest/en-gb/mergedProjects/nvdspENG/To_know_if_VRR_is_turned_on_in_your_game.htm): checking runtime engagement.
