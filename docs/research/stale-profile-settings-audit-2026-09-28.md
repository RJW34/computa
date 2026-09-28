# Stale profile settings audit — 2026-09-28

The live installation still contained the September 21 `153df96` backend and
September 6 GUI. Commit `5535b70` and the subsequent investigation changes had
not reached the running application. The saved active lane was initially
`overwatch2-gsync-hdr-capture`; the user switched to CS2 HDR Streaming during
this audit. The user required deployment to preserve that selection and wait
for CS2 to close.

## Confirmed defects

- OW2's `vsync` writer/verifier referenced `LimitToRefresh`, while its actual
  native toggle is `VerticalSyncEnabled`. The live native value was 0 despite
  the old verifier reporting all settings active. The corrected verifier
  detected exactly this OW2 mismatch. Missing files/keys no longer pass.
- The four borderless OW2 G-SYNC lanes incorrectly requested native VSync Off.
  They now request On, keeping driver VSync On, the static refresh-minus-three
  ceiling and manual Reflex On + Boost contract. No-sync lanes remain Off.
- CS2's two streaming G-SYNC lanes guided borderless mode but disabled native
  VSync. Their manual guidance now requests On. ABSO does not automatically
  edit CS2's native settings.
- Diablo IV's G-SYNC lane requested fullscreen-only VRR, disabled native VSync,
  and disabled per-application fullscreen optimizations despite its borderless
  presentation path. Its display contract now uses fullscreen-and-windowed VRR,
  native VSync On, and preserves the optimized Windows presentation path.
- Diablo IV and Rivals 2 verification treated missing native config files as
  success and dropped automatic cap requests when refresh detection failed.
  Both now surface missing evidence. Diablo verification also excludes internal
  transaction metadata from native-setting comparisons.
- Tray background catalog refresh updated disk without replacing loaded
  metadata/aliases. Manual refresh announced success before fresh data arrived.
  The new asynchronous completion path adopts validated metadata, defers during
  mutations, invalidates changed verification, and refreshes existing controls.
  Structural menu changes request a restart. Refresh never applies a profile.
- A GUI build could package an existing obsolete backend sidecar. It now
  synchronizes all sidecars from `dist/computa.exe`, builds that backend if
  missing, and aborts on failed synchronization.
- Read-only NVIDIA DRS sessions unnecessarily saved the profile database on
  exit. Only sessions with successful mutations now save; failure/cleanup paths
  have regression coverage.
- NVIDIA Low Latency Mode was mapped to maximum pre-rendered frames, making
  `ultra` request two queued frames. The corrected model separates queue depth,
  native ULL scheduling state, and the control-panel mode mirror. Unsupported
  private controls produce explicit manual confirmation steps; an absent value
  is never treated as proof of Off. The misleading `nvidia_reflex` DRS alias is
  rejected because native Reflex must be configured inside the game.
- NVIDIA Fast Sync and Adaptive Sync encodings were reversed. Compound mode
  writes and readback now use the reference encodings. NIP export uses native
  DWORDs and the same mode combinations; unsafe NPI import remains disabled.
- The primary display exposed 624 modes, with its native-resolution modes at
  indices 615–623. Refresh enumeration stopped at 500, causing the Windows
  verifier to accept an undetectable maximum. The Windows probe and both display
  detector paths now enumerate up to 4,096 modes; read-only local verification
  confirms current 300 Hz and maximum 300 Hz.
- Baseline cleanup on a profile switch restored every native game-config
  handler, including games absent from the target profile. This reproduced the
  stale OW2 reset during a CS2 switch. Baseline selection now preserves native
  handlers outside the target profile while retaining full explicit restore
  and pre-switch rollback behavior.
- Two local Start-menu shortcuts referenced a temporary installer sandbox.
  Both were backed up and repointed to the installed runtime's launchers. The
  scheduled startup task already referenced the correct installed directory.

## Guidance and scope

[NVIDIA's latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)
directs windowed G-SYNC + VSync + Reflex users to in-game VSync and states that
Reflex overrides driver Ultra Low Latency when both are enabled. This is
configuration guidance, not a measurement of this PC's gameplay frame pacing.
Native NVIDIA setting encodings were compared with the
[NVIDIA SDK header](https://github.com/NVIDIA/nvapi/blob/main/NvApiDriverSettings.h)
and [Profile Inspector's setting definitions](https://github.com/Orbmu2k/nvidiaProfileInspector/blob/master/nvidiaProfileInspector/CustomSettingNames.xml).
Removed generic OW2 HDR calibration targets and unmeasured claims about
borderless speed, buffering, and capture performance. Existing personal HDR
calibration is preserved. VRR capability warnings no longer assert that VRR
is currently engaged.

The persisted OW2 cap remains 297 at 300 Hz. Reflex's observed lower runtime
pacing is separate from that saved ceiling. No maximum-performance or
tear-free-gameplay claim can be established from configuration readback alone.

## Local evidence

Raw machine-specific backups, readbacks, diffs, and build/test logs are in the
gitignored `reports/repairs/2026-09-28-stale-settings/` directory. A targeted
out-of-game edit changed only `VerticalSyncEnabled` from 0 to 1; the old backend's
subsequent CS2 profile switch restored it to 0 through the baseline path. Final
live readback must therefore follow deployment, not rely on that earlier edit.
No gameplay was entered or tested by the agent.

## Validation

- Final full suite: **3,070 passed**, 13 integration tests excluded. The existing
  pytest `asyncio_default_fixture_loop_scope` configuration warning remains.
- Repository-wide Ruff and `git diff --check` passed.
- GUI profile-state tests: 8 passed; GUI lint passed.
- Fresh `build.py all` completed the CLI, GUI, MSI, and NSIS builds.
- Frozen CLI emitted all 44 profiles and exactly matched the bundled tray
  catalog. GUI sidecar bytes matched the fresh backend.
- Independent review covered cross-game restoration, sidecar synchronization,
  tray adoption, and native NVIDIA mode combinations. The full run caught an
  overly broad linter rule requiring a legacy Windows VRR switch for DX12;
  regression coverage now permits DX12's native path while still requiring
  windowed G-SYNC for borderless guidance.

Machine-specific installation, process restart, and final saved-setting evidence
belong in `docs/CURRENT_AGENT_BRIEFING.md` and the local repair directory. A
successful build alone is not evidence that the running tray was upgraded.
