# Profile switch blocked by a removed audio endpoint

## Incident and evidence

The installed tray received `apply slippi-melee-universal-hdr --json --no-fallback`
at 2026-09-20 23:59:13. It returned a structured failure at 23:59:24:
`Baseline restore incomplete for restorable handlers: AudioEngineHandler
(Handler returned False)`. Stderr recorded WinError 5 (access denied).
The tray remained running and displayed the error; this was a failed backend
transaction, not a demonstrated tray crash.

The transaction captured pre-switch snapshot `2026-09-20_235914`, then restored
baseline `2026-09-18_004811` before attempting Slippi settings. That baseline
contains render endpoint `{088caa61-c9b6-4e30-a079-2f2dff2bbc21}`, flag 1.
Read-only registry probes confirm the endpoint no longer exists. The current
snapshot instead names `{18b15eea-dba3-4879-a4de-46fccb9b27fe}` and its flag
already reads 1. The restore helper called `CreateKeyEx` on the missing old
endpoint's full path, attempting to recreate a Windows-managed audio endpoint.
This produced the permission failure. Changing registry permissions or taking
ownership is unnecessary and would not fix the incorrect restore semantics.

A second defect amplified the failure: baseline restore had already changed
other handlers, but its failure returned before the transaction's rollback
path. The payload recorded `rollback_performed: false` despite a valid
pre-switch snapshot. OW2 remained the saved profile with its prior timestamp.
Readbacks confirmed changes relative to the pre-switch snapshot, including
processor minimum 100 to 5, mouse sensitivity 10 to 11, and NIC flow control
and interrupt moderation. Other readback problems, such as unavailable NVIDIA
shader-cache evidence, must not automatically be attributed to this incident.

## Repair

- Audio restore checks that the original endpoint still exists and skips a
  removed endpoint with an explicit log. It does not recreate endpoint parents.
- Existing endpoint values are compared before writes/deletes; already-correct
  values need no write permission. Unreadable state and genuine write failures
  remain failures, rather than being confused with an absent value.
- Transactions recover the pre-switch snapshot if baseline restoration fails
  or a later phase fails after baseline mutation. Recovery results distinguish
  an attempt, complete restoration, and partial/unavailable restoration.
- Failed tray operations discard old verification and request fresh read-only
  evidence for the saved profile while preserving the failed-switch feedback.

Raw logs, the two incident snapshots, readbacks and validation/deployment
results are preserved locally under `reports/incidents/2026-09-21-tray-switch/`.
No game performance claim follows from this correctness repair.

## Validation and installed result

- 2,814 Python tests passed; 13 integration tests deselected. Repository Ruff
  and diff checks passed. The existing pytest asyncio configuration warning
  remains. Focused coverage includes 50 audio tests, 155 transaction/applier/CLI
  tests, and 178 tray tests.
- A read-only reproduction used the exact incident snapshots. With all registry
  mutation functions blocked, the fixed handler accepted the removed endpoint
  and the already-correct current endpoint with zero writes. The old handler
  attempted creation of the removed endpoint path and failed when that write
  was rejected. Full live profile apply was not used as a test.
- Frozen CLI build and 44-profile catalog smoke check passed. Code commit:
  `2f843aa` on `codex/fix-profile-switch-audio-restore`.
- Installed through `build.py deploy-existing`; backend 18,390,136 bytes,
  SHA256 `3444400a2eb27700e193b464f53f46d0fd7b9c1aedf5863c45be92c3d1dea545`.
  Previous backend: `deploy-backups/computa.exe.bak-20260921-001102`.
- Tray restarted from verified PID 17000 to PID 8436 through its startup task;
  startup result 0, all loaded module hashes match. Script SHA256
  `e786ac99a0c094a90fa39e6996950b2162bdc94d486de72e00626baeed936f71`.
- GUI, backend config, and saved state are byte-identical to their pre-deploy
  copies. Tray preferences are preserved except startup bookkeeping. Slippi
  process 20136 remained running with its original start time; it was not
  stopped or retuned. No profile apply, registry permission change, display
  reset, HDR cycle or reboot was performed.

The installed runtime is repaired; the already-partial profile state has not
been reapplied. OW2 capture remains recorded with applied_at
`2026-09-18T00:48:31.365853`, but verification still reports mismatches and
`pending_apply`; no reboot is pending. Health reports 7 OK / 3 warnings /
0 errors: profile verification, prior display/power events, and mixed-refresh
topology. These warnings must not be presented as full profile success.
Retry the intended Slippi Universal HDR selection to complete the switch,
then verify the resulting profile. The repaired failure path reports recovery
limitations explicitly if any other setting fails.
