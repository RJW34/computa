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
detection, focused test results, and the scoped operation script. Deployment,
backup, apply, and verification results will be recorded here after execution.

Reflex was read as Off. It remains a manual in-game setting; neither a profile
apply nor this report establishes that it is enabled. Profile conformance also
does not establish best possible game performance without frame-time and
latency measurements on this machine.
