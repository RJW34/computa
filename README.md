# computa

**Per-game Windows optimization, with a backup of everything it touches.**

computa is a CLI-first Windows 11 gaming tuning tool: it detects your
hardware, audits your system configuration, and applies game-specific
optimization profiles — Windows, power, input, GPU driver, and display state
together — with automatic backups and one-command rollback.

## What it does

- **Hardware detection** — GPU (NVIDIA/AMD/Intel), CPU topology, monitors,
  refresh rates, G-SYNC/FreeSync/VRR capability, HDR support
- **Configuration audit** — scans 15+ system areas and explains what's
  suboptimal for gaming and why
- **Game profiles** — per-game optimization lanes (no-sync minimum latency,
  G-SYNC/VRR, HDR, capture-safe variants) that tune Windows, power, input,
  GPU driver, and display state together
- **First-run calibration** — `computa setup` walks hardware detection, audit,
  and profile selection, and adapts what it offers to *your* machine
- **Safe by default** — timestamped backup of every setting before any change,
  one-command restore, and a baseline captured at setup so you can always get
  back to where you started
- **System tray app** — one-click profile switching, game detection, and
  status, with selectable icon/sound themes
- **Live verification** — `state --json --verify` and `health --json` prove
  whether the active profile is actually in effect instead of assuming it

## Requirements

- Windows 10/11 (64-bit); Windows 11 has the deepest coverage
- Administrator privileges (system settings require elevation)
- **GPU:** any. NVIDIA gets the deepest driver tuning (per-app driver
  profiles, Low Latency Mode, VRR overrides); AMD Radeon gets vendor-specific
  registry tuning (Anti-Lag, Enhanced Sync, ULPS); other GPUs still get all
  OS/power/input/display optimizations
- Python 3.11+ **only for source installs** — the released `computa.exe` is
  self-contained

### Optional: NVIDIA Profile Inspector

For the deepest NVIDIA driver control, computa can use NVIDIA Profile Inspector:

1. Download the latest release from
   [Orbmu2k/nvidiaProfileInspector](https://github.com/Orbmu2k/nvidiaProfileInspector/releases)
2. Extract to one of these auto-detected locations:
   - `tools/npi/nvidiaProfileInspector.exe` (project directory)
   - `%USERPROFILE%\nvidiaProfileInspector\nvidiaProfileInspector.exe`
   - anywhere in your `PATH`

Without NPI, NVIDIA tuning still works through the driver's NVAPI interface.

## Installation

### From a release (recommended)

Download **`computa-setup.exe`** from the latest GitHub release and
double-click it — a standard Windows installer (per-user, no admin prompt
for the install itself). It registers computa in Apps & Features, adds
Start Menu shortcuts, and optionally puts `computa` on your PATH.

The finish page offers to run **first-time setup**: a small window that
shows what was found on your PC, lets you toggle what setup may do (safety
snapshot, tray on startup), and asks a short survey — which games you play
(installed ones are pre-checked) and whether you use HDR, VRR, or
streaming — so the tray menu only shows profiles you'd actually use.
Neither installing nor setup changes your Windows or game settings — you
pick a game profile later, from the tray.

Portable/power-user path: download `computa.exe` + `install.ps1` and run
`powershell -ExecutionPolicy Bypass -File .\install.ps1` (console), or put
`computa.exe` anywhere and run `computa setup` from an elevated terminal.

`computa update-check` reports when a newer release is available; updating is a
manual re-download (no auto-update). Maintainers: see
[`docs/RELEASING.md`](docs/RELEASING.md).

### From source (developers)

```powershell
git clone <this repo>
cd computa
python -m venv .venv          # tooling assumes the venv is named .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m abso setup
```

Dev/build tooling (pytest, ruff, PyInstaller) lives in
`requirements-dev.txt`.

## First run

Run the calibration wizard from an elevated terminal:

```powershell
computa setup
```

It detects your hardware, checks for known-problematic Windows updates,
audits current settings, captures a **baseline backup** of your system, and
offers the game profiles that match what your machine supports (HDR lanes on
HDR displays, G-SYNC/VRR lanes on VRR displays, and so on). Nothing is applied
without confirmation.

## Everyday use

```powershell
computa profiles                  # list available profiles for this machine
computa apply overwatch2-gsync    # apply a profile (backup happens automatically)
computa audit --verbose           # what would computa change, and why
computa state --json --verify     # is the active profile actually in effect?
computa health --json             # overall install/runtime health
computa restore latest            # roll back the last apply
computa uninstall                 # restore baseline + remove computa from the system
computa tray --install-startup    # start the tray app with Windows
```

The tray app (`computa tray`) gives you one-click switching, shows the active
profile, watches for game launches, and supports icon/sound theme packs — see
`abso/tray/themes/README.md`.

## What profiles change

Exact settings vary per profile; this is what built-in profiles touch today.

### Windows
- Game Mode on; Game Bar / Game DVR capture off (per-user registry)
- Hardware-Accelerated GPU Scheduling (HAGS) on most gaming profiles
  (hardware/driver-dependent; first change needs a reboot)
- Per-executable Fullscreen Optimizations (FSO) matched to each profile's
  presentation path (exclusive fullscreen vs composited borderless)
- Multi-Plane Overlay (MPO) is **not** disabled by default — disabling it can
  break the Windows 11 VRR/compositor path

### Power
- Ultimate Performance plan; USB selective suspend and PCIe link-state power
  saving off; processor max state 100%

### Input
- Mouse acceleration off, linear response curves, enhanced pointer precision
  off

### GPU driver
- **NVIDIA:** per-application driver profile (NPI / NVAPI DRS) with Low
  Latency Mode, VSync, Power Management, Max Frame Rate, and VRR overrides per
  profile. Native Reflex is preferred over driver LLM whenever the game
  supports it; the Reflex toggle itself must still be enabled in-game
- **AMD:** vendor registry tuning (Anti-Lag, Enhanced Sync, ULPS) mapped from
  the same profile intents
- VRR safety caps scale to *your* panel (default `refresh − 3`), not to any
  hardcoded refresh rate

### Deliberately conservative
- Network: built-in profiles keep Windows TCP defaults (most game traffic is
  UDP; Nagle/autotuning tweaks don't help gameplay latency). TCP tuning exists
  only as an opt-in preset
- Services: no telemetry/search/Xbox service disabling — brittle, no measured
  win on modern Windows 11
- VBS / Memory Integrity: never silently disabled; explicit opt-in flow only
- Legacy registry tweaks (`SystemResponsiveness`, `LargeSystemCache`, network
  throttling index) sit behind an opt-in legacy flag

## Safety

Every apply first writes a timestamped backup (`backups/YYYY-MM-DD_HHMMSS/`)
with a manifest of every component touched. `computa restore latest` (or a
specific timestamp) rolls back. `computa setup` additionally captures a baseline
snapshot, and `computa uninstall` returns the system to that baseline and removes
computa's startup registration.

Some settings need one reboot the **first** time they change (HAGS, MPO,
opt-in VBS/memory settings); profile switches after that are instant. `state
--json --verify` distinguishes "not applied" from "applied, reboot pending".

## Troubleshooting

- **"Admin privileges required"** — run the terminal as administrator; the
  interactive mode prompts for elevation itself
- **Changes not taking effect** — check `state --json --verify`; a
  reboot-gated setting shows as written-but-pending rather than missing
- **NVIDIA settings not applied** — confirm an NVIDIA GPU is present; some
  settings need NPI (see above) or a driver restart
- **Restore issues** — every backup folder contains `manifest.json` plus
  per-component files that can be inspected and restored manually

## Project structure

```
abso/
├── main.py                 # CLI entry point (Click)
├── core/                   # detection, audit, apply, backup, verification
│   ├── handler_registry.py # one HandlerEntry per settings handler
│   ├── gpu_vendor.py       # GPU vendor resolution (NVIDIA/AMD/other)
│   └── ...
├── data/                   # hardware/monitor lookup tables
├── profiles/               # game profiles (data + logic)
├── settings/               # ~25 settings handlers (windows, power, nvidia/, amd, ...)
├── tray/                   # PowerShell tray app + theme packs
└── utils/                  # admin elevation, registry, atomic IO
```

For development workflow, agent protocol, and quality standards see
[`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md),
[`docs/QUALITY_RUBRIC.md`](docs/QUALITY_RUBRIC.md), and
[`docs/NEW_MACHINE_SETUP.md`](docs/NEW_MACHINE_SETUP.md). Files that
intentionally exist only on a maintainer's machine are listed in
[`docs/LOCAL_ONLY_FILES.md`](docs/LOCAL_ONLY_FILES.md).

## License

MIT — see [`LICENSE`](LICENSE).

## Disclaimer

This tool modifies Windows system settings. It backs up everything it changes
and can restore those backups, but you should still keep your own restore
points for anything you can't afford to lose. The authors are not responsible
for issues arising from use of this tool.
