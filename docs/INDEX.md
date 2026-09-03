# Docs Index

This index points to the documents that are current and load-bearing.
Anything not listed here is either in `docs/archive/` (frozen historical
context) or is a focused-scope note that you can ignore unless you're
actively working on that area.

## Start Here

- **[New Machine Setup](./NEW_MACHINE_SETUP.md)** - **read first on a fresh
  clone / new PC.** What ABSO is, dev-environment setup, how to establish this
  machine's real state, and why the live-state docs may describe a different box.
- **[`../AGENTS.md`](../AGENTS.md)** - root-level zero-context agent entrypoint
  with the current safe command set and documentation reading order.
- **[Current Agent Briefing](./CURRENT_AGENT_BRIEFING.md)** - latest
  machine state, verified fixes, and monitor-flicker precautions. Machine-
  specific; re-verify on a fresh clone before trusting its live-state claims.
- **[Agent Protocol](./AGENT_PROTOCOL.md)** — durable workflow and
  architecture guide for any agent picking up work. Reading order, machine
  roles, live-PC test policy, current patterns, open backlog.
- **[`../CLAUDE.md`](../CLAUDE.md)** - root-level Claude Code orientation.
  It is intentionally short and points back to the briefing and protocol.

## Standards & Plan

- [Quality Rubric](./QUALITY_RUBRIC.md) — shipping bar, forbidden claims,
  handler capability contract, release gates.
- [Remediation Roadmap](./REMEDIATION_ROADMAP.md) — long-running grade-
  lift plan. Completed PRs are marked inline; see Agent Protocol §6 for
  the current open backlog.
- [External Resource Incorporation](./EXTERNAL_RESOURCE_INCORPORATION.md) —
  staging contract for turning outside repos, tweets, tools, and tuning guides
  into explicit absorb / reject / watchlist decisions.

## Reference

- [API Reference](./API.md)
- [Process Lasso-Class Features](./PROCESS_LASSO_FEATURES.md) — ProBalance
  governor, core-parking power plan, Keep-Awake, CPU Sets, EcoQoS, CPU Limiter,
  and the declarative watchdog: feature catalog, every config/tray-config flag,
  online-safety model, and the one-step enablement.
- [Troubleshooting](./TROUBLESHOOTING.md)
- [NVAPI Integration Plan](./NVAPI_INTEGRATION_PLAN.md)

## Research Notes

- [VRR Latency Research Notes](./research/vrr-latency-research-notes.md)
- [Dolphin Latency Research Notes](./research/dolphin-latency-research-notes.md)

## Focused-Scope Notes

- [Multimon Gaming Idea](./MULTIMON_GAMING_IDEA.md)
- [OW2 Keybinds Format](./ow2-keybinds-format.md)

## Archive

Frozen handoffs and superseded plans live in `docs/archive/`. They are
preserved for history but should not be used as a current-state
reference. `CURRENT_AGENT_BRIEFING.md` wins for this PC's live state;
`AGENT_PROTOCOL.md` wins for general process and repo policy.
