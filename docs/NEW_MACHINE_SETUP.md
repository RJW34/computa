# New Machine Setup & Fresh-Clone Onboarding

**Read this FIRST if the repo was just cloned onto a new PC, or if you are a
fresh Claude / Codex session with no prior context on _this_ machine.** Once you
have established this machine's state and read the project docs, hand off to
`docs/AGENT_PROTOCOL.md` for the durable workflow.

---

## Why this file exists

The other agent docs were written against **one specific live machine**: an
RTX 4070 Windows 11 box (hostname `MIRAIDON`) that was mid-way through debugging
Overwatch 2 secondary-monitor black flashes. On a freshly cloned machine, those
"live state" claims are **history, not truth**:

- No ABSO build is deployed to `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\`
  yet — the installed `abso.exe`, tray runtime, and state file do not exist here.
- **No profile is applied. Nothing is reboot-pending.** The system is unmodified.
- The active profile, PIDs, build hashes, and deploy timestamps in
  `docs/CURRENT_AGENT_BRIEFING.md` and the "Current Live-PC Constraint" section
  of `AGENTS.md` describe the **old machine**, not this one.

Do **not** act on those live-state claims until you have re-established this
machine's actual state with the read-only commands in step 2.

---

## What ABSO is (30-second version)

**A.B.S.O.** (Adaptive Battle Station Optimizer) is a CLI-first Windows 11
gaming-optimization tool. It auto-detects hardware (GPU/CPU/RAM/monitors),
audits system configuration, and applies game-specific optimization profiles
(NVIDIA driver settings, power plan, Windows toggles, mouse/input, per-exe
fullscreen/MPO presentation) with timestamped backup + rollback for every change.
It ships a PowerShell system-tray app for one-click profile switching.

It is single-user, enthusiast-grade, latency-focused, and **safe by default**
(always backs up before applying). For the full product surface, profile
catalog, and exactly what each profile touches, read `README.md`.

---

## 1. Set up the dev environment

Requirements: Windows 10/11 (64-bit), Python 3.11+, admin privileges for any
system change, NVIDIA GPU optional (for GPU-specific tuning).

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

The repo's own tooling (`build.py`, `CLAUDE.md` examples) assumes the venv lives
at `.\.venv\`. Use `.\.venv\Scripts\python.exe` for build/deploy commands.

Optional, for full NVIDIA tuning: install NVIDIA Profile Inspector — see the
"Optional: NVIDIA Profile Inspector" section of `README.md`.

## 2. Establish THIS machine's state (read-only, safe)

These commands only **read** system/hardware state. None of them modify the
system, deploy a build, or apply a profile:

```powershell
python -m abso detect          # hardware: GPU, CPU, monitors, VRR/G-Sync
python -m abso audit           # configuration audit (no changes)
python -m abso health --json   # current health; "no active profile" on a fresh box
python -m abso profiles        # available profile catalog
python -m abso state --json --verify
```

On a fresh clone, expect **no active profile**, **no installed runtime**, and
the audit to report a stock, unoptimized system. That is the correct baseline.

## 3. Safety: the live-PC mutation exception does NOT transfer

`docs/AGENT_PROTOCOL.md` §3 says the user granted **read-only _and_
state-mutating** access "to this machine" — but that was the old box
(`MIRAIDON`). The user's standing global rule is **never run tests or
system-mutating commands on the live PC without permission.**

On this new machine, **default to read-only.** Do not run `apply`, `restore`,
`apply-pending`, `launch`, `build.py deploy`, registry writes, display resets,
or the tray installer until the user **explicitly authorizes mutating _this_
machine.** Re-confirm scope here; the old machine's grant does not carry over.

## 4. Reading order to understand the project

1. **`README.md`** — what ABSO is, the profile catalog, and exactly what each
   profile changes (Windows / power / graphics / input / NVIDIA / VBS). This is
   the most accurate single source for "what does it actually do."
2. **`docs/AGENT_PROTOCOL.md`** — durable workflow, architecture patterns,
   handler/profile conventions, validation pipeline, evidence/claim rules, and
   the open backlog. **Treat §2 (machine roles, `MIRAIDON`) and §3 (live-PC
   mutation exception) as machine-specific history — they do not describe this
   PC.**
3. **`CLAUDE.md`** — repo-rooted conventions and critical constraints
   (always-backup, admin elevation, idempotency, online-safety, hermetic tests).
4. **`docs/INDEX.md`** — full map of current vs. archived docs.
5. **`docs/CURRENT_AGENT_BRIEFING.md`** — the **last** machine's live state.
   Useful as a record of what the previous session was working on (OW2 flicker,
   MPO/VRR mixed-refresh, tray startup-state fixes), **not** as this machine's
   truth until you re-verify with step 2.

Architecture at a glance: CLI entry `abso/main.py` → `abso/core/applier.py`
orchestrates a validation pipeline (linter → multimon detector → rollback guard
→ stability gate → network scope) → per-domain `abso/settings/*` handlers, each
implementing detect/audit/apply/backup/restore. Profiles live in
`abso/profiles/`. Every state-mutating handler is registered once in
`abso/core/handler_registry.py` (auditor + backup pick it up automatically).
See `README.md` "Project Structure" and `CLAUDE.md` "Architecture" for the map.

## 5. Run the tests (after the dev environment is set up)

The test suite is hermetic — it does not touch real system state — so it is safe
to run on any machine:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
.\.venv\Scripts\python.exe -m ruff check .
```

## 6. Optional: build & deploy the installed runtime (MUTATING — authorize first)

Only after the user authorizes mutating this machine (step 3):

```powershell
.\.venv\Scripts\python.exe build.py deploy           # build CLI, deploy to LocalAppData
.\.venv\Scripts\python.exe build.py deploy-existing  # deploy current dist\abso.exe
```

This installs the runtime to `%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\`
and is the point at which `CURRENT_AGENT_BRIEFING.md`-style live-state tracking
begins to apply to this machine. Once you are operating on a configured machine,
keep `docs/CURRENT_AGENT_BRIEFING.md` updated as the live-state handoff for the
next session.
