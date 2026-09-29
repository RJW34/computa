# OW2 reapply repair, 2026-09-21

The user explicitly requested leaving the existing OW2 profile reapplied after
the failed OW2-to-Slippi switch. The verified selection was
`overwatch2-gsync-hdr-capture`, with seven mismatched handlers and no pending
reboot. The persisted NVIDIA/native frame ceiling was already 297 FPS and HDR
was already enabled.

## Defects blocking or undermining repair

- Graphics verification emitted `GraphicsSettingsHandler.disable_global_fso`
  as a pending repair, but pending remediation accepted only MPO. Both apply
  and reapply rejected the FSO request before a full transaction could run.
  Narrow remediation now accepts the verifier's boolean FSO target, combines
  supported FSO/MPO requests without unrelated writes, and retains changed
  settings/reboot metadata if a later write fails. Success requires the
  requested pending keys to disappear on readback. A targeted repair preserves
  the recorded full-profile apply and any existing reboot requirement; a
  separate timestamp prevents an older system boot clearing a new reboot gate.
- The NVIDIA shader cache preset confused the cache enable setting with its
  separate size setting. The official NVIDIA header defines cache enable as
  0/1; unlimited size belongs to a different setting. Driver enumeration on
  this machine confirmed the distinction. Built-in profiles now request cache
  enabled (1). Unsupported size values fail explicitly rather than writing an
  invalid enable value or silently changing a global budget. NIP parsing and
  export distinguish the two IDs. The global size policy is preserved.
- OW2 baseline restore could replace the current manual Reflex choice with an
  older snapshot despite the apply handler deliberately never authoring that
  setting. Restore now preserves the live Reflex value or its absence.

NVIDIA reference: [NvApiDriverSettings.h](https://github.com/NVIDIA/nvapi/blob/main/NvApiDriverSettings.h).

## Live operation evidence

Machine-local raw evidence is in
`reports/repairs/2026-09-21-ow2-reapply/`, including before-state, hardware
detection, driver probes, test results, deployment log, the scoped operation
script, backup snapshot, apply results, and verification readbacks.

Code commit `153df96` passed 2,871 tests (13 integration tests deselected), Ruff,
and diff checks. The existing pytest asyncio configuration warning remains.
`build.py deploy` installed backend SHA256
`2bf0237771a4e28c3d1f74275dac86cb0a557f5bd0b3a081295050e92b82cfa1`
(18,393,679 bytes). GUI, tray assets, and configuration were already current;
tray PID8436 remained running with matching assets. Frozen profile discovery
and the FSO dry run passed.

The elevated repair captured manual backup `2026-09-21_004340`, cleared the
global FSO disable with `apply-pending`, then applied the same OW2 profile with
fallback disabled. The same-profile path skipped baseline restore. It committed
at `2026-09-21T00:44:18.773649`; no handler failed. Independent verify and state
readbacks report `all_active: true`, no mismatched handlers, no pending apply,
and no pending reboot. Raw NVAPI readback confirms Overwatch 2 shader cache
enabled=1; the global cache-size setting is unchanged.

Windows windowed optimizations/VRR policy, CPU minimum state, mouse sensitivity,
CPU/I/O process priority, NIC flow control/interrupt moderation, and global FSO
now match the selected profile. Native and NVIDIA ceilings remain 297 FPS;
HDR remains enabled on the 300 Hz primary display. No display reset fired;
the post-apply process sweep stopped no processes.

Health reports 8 OK, 2 warnings, 0 errors. Remaining warnings concern the
existing mixed 300/59.95 Hz display topology and earlier power/boot events;
the profile-mismatch warning is gone.

## Authorized in-game settings follow-up

The user launched OW2 and explicitly requested Computer Use to align its
settings with the profile, with all gameplay testing reserved for the user.
Through the game's options UI, the agent changed:

- NVIDIA Reflex: Disabled to Enabled + Boost.
- Shadow Detail: Off to Low, matching the profile's visual guidance. This is
  not evidence that Low is faster than Off.
- Local Reflections: On to Off.
- Damage FX: Default to Low.

Apply was clicked. The game subsequently restarted outside the agent's input
sequence. Its new window was rediscovered at the home screen; General, Graphics
Quality, and HDR were rechecked. All four changes persisted and the restart
notice was gone. OW2 was returned to its home screen without entering a match,
practice range, or other gameplay.

Confirmed settings include DirectX 11, borderless windowed mode, native 100%
rendering, dynamic resolution Off, custom 297 FPS ceiling, in-game VSync and
triple buffering Off, Reduce Buffering On, low detail settings, anti-aliasing
Off, ambient occlusion and dynamic reflections Off, and HDR On. Existing
controls, sensitivity, field of view, audio, and HDR calibration were preserved.
The user confirmed that high precision mouse input was removed in a recent
patch; no hidden setting was created or changed.

The above is a historical observation, not current setup guidance. The native
VSync policy was corrected on September 28, and Reduce Buffering was changed
to Off for the Reflex profiles on September 29; see
[the follow-up correction](ow2-reflex-buffering-fix-2026-09-29.md).

Installed verify and state readbacks after UI work both succeeded. They report
all active, no pending apply or reboot, and the manual Reflex step satisfied
with `ReflexMode=2` (Enabled + Boost). Evidence includes `verify-after-ui.json`,
`state-after-ui.json`, and `Settings_v0-after-ui.ini` in the evidence folder.
The calibration remains 388.0 maximum / 0.16 minimum tonemap luminance.

Profile conformance does not establish best possible game performance without
frame-time and latency measurements on this machine. No gameplay benchmark
was performed.
