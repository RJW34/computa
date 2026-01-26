# Competitive Latency Canonical Profiles
## Rivals of Aether 2 (ONLINE) & Slippi / SSBM (Slippi Dolphin)

**Status:** FINAL – Deterministic  
**Purpose:** Enforce lowest-latency configurations that do NOT introduce hitches, rollback instability, or frame pacing variance  
**Audience:** Windows optimizer / per-game profile system  
**Scope:** Profile refactor + enforcement logic

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

**Profile ID:** `rivals2-online`  
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
Rollback netcode in Rivals 2 is sensitive to timing variance, not tearing.  
High-refresh tearing is visually negligible and latency-optimal.

---

## Frame Rate Control

| Setting | Value |
|----|----|
| In-Game FPS Cap | Unlimited / Engine Max |
| NVCP Frame Rate Limit | 240 FPS |
| External Limiters (RTSS) | DISABLED |

**Note:** 240 FPS cap via NVCP provides stable frame pacing for online play.  

---

## NVIDIA Driver (Per-App)

| Setting | Value | Notes |
|----|----|----|
| Vertical Sync | OFF | No sync latency |
| Low Latency Mode | **ON** | Reduces queue safely |
| Low Latency Mode = Ultra | **FORBIDDEN** | Causes rollback contention |
| Max Frame Rate | OFF | Avoid limiter jitter |
| Threaded Optimization | OFF | UE5 driver contention |
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
| Power Plan | **High Performance** |
| Ultimate Performance | FORBIDDEN |
| CPU Priority | Normal / Above Normal |
| High / Realtime Priority | FORBIDDEN |

**Reason:**  
Rollback requires scheduling headroom. Over-aggression causes hitches.

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

The optimizer MUST block these when `rivals2-online` is active:

- LLM = Ultra  
- Fast Sync  
- G-SYNC / VRR  
- External FPS caps  
- Refresh-minus-X logic  
- Ultimate Performance plan  
- Injection tools (SK / RTSS)  

---

### Canonical One-Line Definition (Rivals 2 Online)

> **Exclusive fullscreen + no sync + 240 FPS cap + NV LLM ON (not Ultra) + HAGS ON + High Performance plan + no overlays**

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
| Low Latency Mode | **ULTRA** | Just-in-time submission |
| Vertical Sync | OFF | Remove sync delay |
| G-SYNC | OFF | Fixed 60fps |
| Threaded Optimization | OFF | Emulator stability |
| Power Management | Prefer Maximum Performance | |

LLM Ultra is **SAFE and CORRECT** here.

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
| Backend | Direct3D 12 |
| VSync | OFF |
| Backend Multithreading | OFF |
| Internal Resolution | 1×–2× |
| Exclusive Fullscreen | ON |

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

## 2. Online vs Offline Profiles Are Mandatory (Rivals 2)
Offline aggression MUST NOT leak into online play.

## 3. Injection Detection
If SK / RTSS / overlays are detected:
- Block `rivals2-online`
- Allow `slippi-melee`

## 4. Power Plan Guardrails
- `rivals2-online` → High Performance only
- `slippi-melee` → Ultimate Performance allowed

---

## Final Truth Table

| Setting | Rivals 2 Online | Slippi / SSBM |
|----|----|----|
| VSync | OFF | OFF |
| VRR | OFF | OFF |
| LLM | ON | ULTRA |
| HAGS | ON | ON |
| FPS Cap | 240 | NONE |
| Priority Aggression | LOW | HIGH |
| Frame Pacing Priority | HIGH | LOW |
| Raw Latency Priority | MEDIUM | MAX |

---

## End of Document

This file is the **authoritative reference** for competitive latency behavior.
Any optimizer behavior that contradicts this is a bug.
