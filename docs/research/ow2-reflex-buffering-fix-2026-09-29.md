# OW2 native sync and Reflex buffering correction — 2026-09-29

This records the initial buffering repair. The subsequent
[evidence-based defaults review](ow2-evidence-based-defaults-2026-09-29.md)
supersedes its Boost-only guidance and duplicate-cap policy.

Applying the installed OW2 HDR Streaming profile restored an old native config
before launch: transaction backups show `VerticalSyncEnabled` changing from 1
to 0 and `CpuForceSyncEnabled` from 0 to 1. The old verifier checked the unrelated
`LimitToRefresh` key, so application success did not establish native VSync.
The previously committed VSync/restore fixes had not yet been deployed.

The remaining source defect was a blanket Reduce Buffering On target. All six
OW2 profiles now request Reduce Buffering Off alongside their existing manual
Reflex On + Boost setup. Guidance describes this as the chosen Reflex policy,
without claiming a measured FPS or latency improvement. The generic native
audit no longer labels Reduce Buffering Off a problem; profile verification
still checks the actual saved value against the selected profile's target.

The four borderless G-SYNC lanes retain native VSync On, a static refresh-minus-
three ceiling (297 at 300 Hz), and the saved manual Reflex choice. No-sync lanes
retain VSync Off. Profile application does not write ReflexMode. HDR calibration,
controls, audio and other unrequested native settings remain user-owned.

Regression checks cover all six profiles' target/guidance agreement, audit
behavior with Reflex enabled/disabled/unknown, surgical native changes and an
idempotent second apply, and stale-baseline restoration followed by correct
same-game application. Cross-game switches preserve the other game's file.

[NVIDIA's latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)
recommends in-game VSync for windowed G-SYNC + Reflex.
[Earlier instrumented Overwatch tests](https://github.com/klasbo/GamePerfTesting/blob/master/text/02-reflex.md)
found no latency difference between Reduce Buffering On and Off with Reflex in
their tested configurations. Those results do not establish current behavior on
this PC; this change does not claim that enabling both necessarily causes harm.

Machine-specific before/after snapshots, build/test results and deployment
verification are recorded in `reports/repairs/2026-09-29-ow2-sync/` and the
gitignored `docs/CURRENT_AGENT_BRIEFING.md`. Local deployment uses the official
helper, preserves the selected profile, then narrowly repairs the two saved
native options while Overwatch is closed. No full profile apply, display reset,
HDR cycle or gameplay test is part of this correction.

Validation: 3,081 tests passed, 13 integration tests excluded, with one existing
pytest configuration warning. Ruff and diff checks passed. All 44 catalog
entries still match the generated manifest; the snapshot delta is confined to
the six OW2 Reduce Buffering targets and their guidance.
