# ABSO Claude Code CLI Agent — Comprehensive Improvement Specification

**Version:** Draft 1.0  
**Target:** Claude Code CLI Agent responsible for auditing, validating, and applying ABSO game optimization profiles  
**Scope:** Implements all recommended improvements identified in the external technical audit (January 2026)

---

## 1. Purpose and Design Goals

This document defines **mandatory architectural and behavioral upgrades** for the Claude Code CLI Agent that interfaces with the ABSO codebase.

### Primary Goals
- Increase **robustness** without sacrificing latency-first philosophy
- Replace static assumptions with **runtime validation**
- Detect and mitigate edge cases automatically
- Preserve ABSO’s safety-first backup/rollback guarantees
- Maintain per-game determinism, especially for rollback netcode titles

### Non-Goals
- Mass-market compatibility
- User-friendly abstraction
- Visual/UI features

This agent is designed for **expert, single-user, enthusiast environments**.

---

## 2. High-Level Architectural Enhancements

### 2.1 New Agent Responsibilities

The Claude Agent SHALL:
- Act as a **profile linting engine** prior to apply
- Perform **runtime validation hooks** (post-launch monitoring)
- Dynamically **gate aggressive optimizations** based on live telemetry
- Enforce **hard prohibitions** for unsafe combinations
- Provide deterministic fallback paths

### 2.2 New Internal Subsystems

| Subsystem | Purpose |
|---------|---------|
| ProfileLinter | Static validation before apply |
| RuntimeValidator | Live telemetry + heuristics |
| StabilityGate | Enables/disables risky tweaks |
| RollbackGuard | Protects online rollback titles |
| MultiMonitorDetector | Detects compositor edge cases |
| NetworkScopeManager | Per-game network tuning |
| FallbackController | Automatic reversion logic |

---

## 3. Profile Linting System (Pre-Apply)

### 3.1 Mandatory Lint Checks

Before ANY profile is applied, the agent MUST run a lint pass.

#### 3.1.1 NVIDIA Pipeline Conflicts

Hard errors (abort apply):
- NVIDIA Reflex ON + Driver Low Latency Mode != Off
- LLM Ultra + Explicit FPS cap present
- Fast Sync + Rollback-enabled online profile
- VRR + Fixed-framerate emulator profile

Warnings (allow with explicit override flag):
- LLM Ultra on DX12 titles
- Threaded Optimization OFF on non-fighting UE5 titles

---

#### 3.1.2 Windows Graphics Stack Conflicts

Hard errors:
- HDR enabled for SDR-only profiles
- VRR Optimize ON for latency-critical gaming profiles

Warnings:
- HAGS enabled on DX11-only titles
- MPO enabled with known overlay injectors (RTSS, SK)

---

#### 3.1.3 Power & Scheduler Sanity

Checks:
- Disable Paging Executive only if RAM >= 32GB
- Ultimate Performance is the standard for performance profiles

---

## 4. Runtime Validation System (Post-Launch)

### 4.1 Telemetry Sources

The agent SHALL consume:
- PresentMon (or equivalent) frame timing data
- CPU package utilization
- GPU render queue depth (if available)
- Rollback indicators (game-specific heuristics)

---

### 4.2 Frame Time Variance Detection

#### Rule: HAGS Stability Gate

If:
- HAGS = ON
- AND 99th percentile frame time variance > threshold
- AND sustained for N seconds

Then:
1. Flag profile as unstable
2. Revert HAGS
3. Persist fallback decision to profile cache

---

#### Rule: LLM Ultra Degradation Detection

If:
- LLM = Ultra
- AND average frametime OK
- BUT input-to-present jitter exceeds threshold

Then:
- Downgrade to LLM = On
- Log downgrade reason

---

## 5. Stability Gate System

### 5.1 Aggressive Setting Classes

The following are classified as **gated**:
- Low Latency Mode = Ultra
- HAGS = On
- Win32PrioritySeparation = 0x2A
- Disable Paging Executive

These MUST NOT be applied blindly.

---

### 5.2 Gating Criteria

A gated setting may be applied ONLY IF:
- Profile type allows it
- Linter passes
- RuntimeValidator has no prior failure record

Otherwise, fallback value is applied.

---

## 6. RollbackGuard (Online Netcode Protection)

### 6.1 Rollback-Aware Profiles

Profiles marked as:
- Online
- Ranked
- Matchmaking

MUST enable RollbackGuard.

---

### 6.2 Hard Prohibitions (Enforced)

For rollback profiles, the agent SHALL forcibly block:
- LLM Ultra
- Fast Sync
- External FPS limiters (RTSS)
- Refresh-3 FPS logic
- Forced zero-buffer pipelines

Attempts to apply these MUST fail loudly.

---

### 6.3 Runtime Rollback Failure Detection

If rollback-related frame drops are detected:
- Automatically downgrade to conservative preset
- Persist downgrade for that executable

---

## 7. NetworkScopeManager

### 7.1 Per-Game Network Tuning

Global Nagle disable is prohibited.

The agent SHALL:
- Apply Nagle disable ONLY to profiles explicitly tagged:
  - Rollback
  - Twitch shooter

All other profiles retain OS defaults.

---

### 7.2 Verification

After apply, the agent MUST:
- Confirm registry keys are scoped correctly
- Log per-profile network state

---

## 8. Multi-Monitor & Compositor Detection

### 8.1 Detection Logic

The agent SHALL detect:
- Multiple active monitors
- Mixed refresh rates
- Borderless-forced engines
- Active overlays (DWM, GFE, Xbox, etc.)

---

### 8.2 Conditional Behavior

If exclusive fullscreen cannot be guaranteed:
- Allow VRR Optimize opt-in
- Prevent exclusive-only assumptions
- Warn about added compositor latency

---

## 9. FallbackController

### 9.1 Fallback Triggers

Fallback MUST trigger on:
- Repeated runtime validation failures
- Game crash during apply window
- Severe frametime instability

---

### 9.2 Persistence

Fallback decisions SHALL:
- Be stored per executable
- Survive reboots
- Be overrideable only with explicit force flag

---

## 10. Logging & Observability

### 10.1 Required Logs

The agent SHALL log:
- Lint results
- Gating decisions
- Runtime downgrades
- RollbackGuard interventions
- Fallback applications

Logs must be timestamped and profile-scoped.

---

## 11. Safety & Rollback Guarantees

All new systems MUST:
- Integrate with existing ABSO backup manifests
- Never mutate state without a restore point
- Allow full system restore via `abso restore`

---

## 12. Implementation Priority

| Priority | Feature |
|---------|--------|
| P0 | Profile Linter |
| P0 | RollbackGuard |
| P1 | Runtime Validation |
| P1 | Stability Gate |
| P2 | Multi-monitor detection |
| P2 | Network scoping |
| P3 | Telemetry refinement |

---

## 13. Success Criteria

This upgrade is considered successful if:
- Aggressive profiles self-correct instead of failing
- Online rollback stability improves under load
- No silent conflicts occur between driver, OS, and game
- ABSO remains deterministic and reversible

---

**End of Specification**
