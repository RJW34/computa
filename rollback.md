# Competitive Latency Legacy Note
## Rivals of Aether 2 (ONLINE) & Slippi / SSBM (Slippi Dolphin)

> **Status 2026-05-26:** legacy design note. This file preserves useful
> rollback-coupling rationale, but it is no longer the repo-wide authoritative
> source of truth for shipped profile behavior.
>
> Current agents should read `AGENTS.md`, `docs/CURRENT_AGENT_BRIEFING.md`, and
> `docs/AGENT_PROTOCOL.md` first. For live profile behavior, inspect the
> shipped catalog with `python -m abso profiles --json`, the profile modules
> under `abso/profiles/`, and the snapshot tests. For the current Rivals 2
> 300 Hz user-facing guide, use
> `rivals2-300hz-lowest-latency-guide.md`.

**Purpose:** Preserve latency/rollback design rationale that should be checked
against the live catalog before implementation work.
**Audience:** Windows optimizer / per-game profile system
**Scope:** historical profile refactor + enforcement logic

---

## Core Principle (Do Not Violate)

> **Optimization strategy MUST be chosen based on rollback coupling to the render pipeline.**

| Game | Rollback Coupling | Optimization Priority |
|----|----|----|
| Rivals of Aether 2 (Online) | Tightly coupled | Frame pacing stability > absolute latency |
| SSBM (Slippi Dolphin) | Decoupled | Absolute end-to-end latency |

This document encodes that distinction explicitly.

---

# PROFILE 1: Rivals of Aether 2 — ONLINE (Ranked / Matchmaking)

**Profile ID:** `rivals2-nosync` (2026-07 merge; the retired `rivals2-online` / `rivals2-offline` IDs alias to it)  
**Goal:** Lowest possible latency that does NOT cause hitches or rollback instability  
**Optimization Class:** Rollback-Safe Low Latency  
**DO NOT reuse offline settings**

---

## Display Pipeline (Hard Requirements)

| Setting | Value |
|----|----|
| Display Mode | Exclusive Fullscreen |
| VSync (anywhere) | OFF |
| G-SYNC / VRR | OFF |
| Windows Variable Refresh Rate | OFF |
| Fast Sync / Adaptive Sync | OFF |

**Rationale:**
Rollback netcode in Rivals 2 is sensitive to timing. The no-sync lane keeps
the scanout path simple and deterministic; the Online GSYNC lane exists for
players who want tear-free VRR online.
High-refresh tearing is visually negligible and latency-optimal.

---

## Frame Rate Control

| Setting | Value |
|----|----|
| In-Game FPS Cap | Largest multiple of 60 at/below refresh (ABSO auto-writes; 300 @ 300 Hz) |
| NVCP Frame Rate Limit | OFF |
| External Limiters (RTSS) | DISABLED |

**Note:** Online no-sync uses one authoritative engine limiter and no
external limiter. Do not add RTSS/NVCP caps to this profile. Rivals 2 ticks
at a fixed 60 Hz: 60-multiple caps hold an even frames-per-tick cadence, and
the bounded render load preserves CPU headroom for rollback resimulation
bursts (this is "frame pacing stability > raw latency" made concrete).

---

## NVIDIA Driver (Per-App)

| Setting | Value | Notes |
|----|----|----|
| Vertical Sync | OFF | No sync latency |
| Low Latency Mode | **ON** | Reduces queue safely |
| Low Latency Mode = Ultra | **AVOID** | Can cause frame pacing issues in non-GPU-bound scenarios |
| Max Frame Rate | OFF | Avoid limiter jitter; in-game limiter owns pacing |
| Threaded Optimization | ON | Rivals 2 is CPU-bound UE5/DX11; worker threads improve frame times. SnapNet's sim is server-authoritative, so driver threading cannot desync rollback |
| Power Management | Prefer Maximum Performance | Clock stability |
| Triple Buffering | OFF | Irrelevant without VSync |
| G-SYNC (per-app) | OFF | No VRR |

---

## Windows Settings

| Setting | Value |
|----|----|
| Game Mode | ON |
| Fullscreen Optimizations | OFF (per-exe) |
| Game Bar | OFF |
| Game DVR | OFF |
| HDR / Auto HDR | OFF |
| VRR Optimize | OFF |
| **HAGS** | **ON** |

**HAGS Rule:**  
- Baseline = ON (DX12, no overlays)  
- First rollback if hitches detected = test OFF

---

## Power & Scheduling

| Setting | Value |
|----|----|
| Power Plan | **Ultimate Performance** |
| CPU Priority | Normal / Above Normal |
| High / Realtime Priority | FORBIDDEN |

**Reason:**  
Standardized on Ultimate Performance; rollback stability is preserved by
sync/VRR constraints and conservative latency settings elsewhere.

---

## Overlays & Injection

**DISABLE ALL:**
- Steam overlay
- Discord overlay
- NVIDIA overlay / GeForce Experience
- RTSS
- Any frame pacing or capture hook

---

## Network (Minimal, Stable)

| Setting | Value |
|----|----|
| Connection | Wired Ethernet |
| VPN / Proxy | OFF |
| Aggressive TCP Tweaks | Avoid beyond proven-safe Nagle disable |

---

## Rivals 2 Online – Explicitly Forbidden Optimizations

The optimizer MUST block these when any merged Rivals 2 lane is active:

- LLM = Ultra  
- Fast Sync  
- G-SYNC / VRR  
- External FPS caps  
- Refresh-minus-X logic  
- Injection tools (SK / RTSS)  

---

### Canonical One-Line Definition (Rivals 2 Online)

> **Exclusive fullscreen + no sync + in-game 60-multiple cap (300 @ 300 Hz) + NV LLM ON (not Ultra - can cause frame pacing issues) + HAGS ON + Ultimate Performance plan + no overlays**

---

# PROFILE 2: Super Smash Bros. Melee — Slippi Dolphin (Online & Offline)

**Profile ID:** `slippi-melee`  
**Goal:** Absolute minimum end-to-end latency  
**Optimization Class:** Deterministic Emulator (Latency-First)

---

## Why This Profile Is Different

- Game logic is fixed 60Hz and deterministic
- Rollback occurs inside the emulator
- Rendering timing does NOT affect gameplay correctness
- GPU pacing variance is irrelevant

Therefore: **chase absolute latency**

---

## Display Pipeline

| Setting | Value |
|----|----|
| Display Mode | Exclusive Fullscreen |
| VSync | OFF |
| G-SYNC / VRR | OFF |
| FPS Caps | NONE |
| Refresh Rate | MAX (240 / 300 Hz+) |

Higher refresh = faster scanout = lower display latency.

---

## NVIDIA Driver (Per-App)

| Setting | Value | Notes |
|----|----|----|
| Low Latency Mode | **On (Ultra optional, test both)** | Reduces queue safely |
| Vertical Sync | OFF | Remove sync delay |
| G-SYNC | OFF | Fixed 60fps |
| Threaded Optimization | OFF | Emulator stability |
| Power Management | Prefer Maximum Performance | |

LLM On is recommended. Ultra may work but test for your specific system.

---

## Windows Settings

| Setting | Value |
|----|----|
| Game Mode | ON |
| Fullscreen Optimizations | OFF |
| Game Bar / DVR | OFF |
| VRR Optimize | OFF |
| **HAGS** | **ON** (DX12 Dolphin) |

---

## Dolphin Configuration (Critical)

| Setting | Value |
|----|----|
| Backend | Experiment (Vulkan often best on NVIDIA/AMD) |
| VSync | OFF |
| Backend Multithreading | OFF |
| Internal Resolution | 1×–2× |
| Exclusive Fullscreen | ON |
| Rush Frame Presentation | Optional (test for 8-14ms reduction) |
| Immediately Present XFB | Enabled (default for Melee) |

---

## Slippi Profile Enforcement

- No VRR
- No frame pacing tools
- No sync of any kind
- Latency-first, tear-tolerant

---

# Global Refactor Rules for Optimizer

## 1. Profiles MUST be Netcode-Aware
Do not classify by genre alone.  
Classify by **rollback coupling**.

## 2. Online vs Offline Profiles Are Mandatory (Rivals 2) — SUPERSEDED 2026-07
The 2026-07 consolidation merged the split: every Rivals lane now carries the
online-safe tuning, so there is no offline aggression left to leak.

## 3. Injection Detection
If SK / RTSS / overlays are detected:
- Block the Rivals 2 lanes
- Allow `slippi-melee`

## 4. Power Plan Guardrails
- `rivals2-nosync` → Ultimate Performance standard
- `slippi-melee` → Ultimate Performance standard

---

## Final Truth Table

| Setting | Rivals 2 Online | Slippi / SSBM |
|----|----|----|
| VSync | OFF | OFF |
| VRR | OFF | OFF |
| LLM | ON | ULTRA |
| HAGS | ON | ON |
| FPS Cap | 60-multiple at refresh (300 @ 300 Hz) | NONE |
| Priority Aggression | LOW | HIGH |
| Frame Pacing Priority | HIGH | LOW |
| Raw Latency Priority | MEDIUM | MAX |

---

## Sources

- [Blur Busters G-SYNC 101](https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/) - LLM and VRR research
- [Dolphin Progress Report December 2025](https://dolphin-emu.org/blog/2025/12/) - Rush Frame Presentation
- [Dolphin Performance Guide](https://wiki.dolphin-emu.org/index.php?title=Performance_Guide) - Backend recommendations
- [melee.tv](https://melee.tv/) - Competitive Melee optimization

---

## End of Document

This file is historical guidance. If it contradicts the live profile catalog,
tests, or current docs, update or archive this note rather than assuming the
optimizer behavior is wrong.
