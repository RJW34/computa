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
Validation and deployment results are appended after completion. No game
performance claim follows from this correctness repair.
