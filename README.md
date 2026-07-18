# A.B.S.O.

**Adaptive Battle Station Optimizer** — a CLI-first Windows 11 gaming tuning
tool that detects your hardware, audits your system configuration, and applies
game-specific optimization profiles, with automatic backups and rollback for
everything it touches.

## What it does

- **Hardware detection** — GPU (NVIDIA/AMD/Intel), CPU topology, monitors,
  refresh rates, G-SYNC/FreeSync/VRR capability, HDR support
- **Configuration audit** — scans 15+ system areas and explains what's
  suboptimal for gaming and why
- **Game profiles** — per-game optimization lanes (no-sync minimum latency,
  G-SYNC/VRR, HDR, capture-safe variants) that tune Windows, power, input,
  GPU driver, and display state together
- **First-run calibration** — `abso setup` walks hardware detection, audit,
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
- Python 3.11+ **only for source installs** — the released `abso.exe` is
  self-contained

### Optional: NVIDIA Profile Inspector

For the deepest NVIDIA driver control, ABSO can use NVIDIA Profile Inspector:

1. Download the latest release from
   [Orbmu2k/nvidiaProfileInspector](https://github.com/Orbmu2k/nvidiaProfileInspector/releases)
2. Extract to one of these auto-detected locations:
   - `tools/npi/nvidiaProfileInspector.exe` (project directory)
   - `%USERPROFILE%\nvidiaProfileInspector\nvidiaProfileInspector.exe`
   - anywhere in your `PATH`

Without NPI, NVIDIA tuning still works through the driver's NVAPI interface.

## Installation

### From a release (recommended)

Download `abso.exe` from the latest GitHub release, then from an elevated
PowerShell:

```powershell
.\install.ps1            # installs to %LOCALAPPDATA%, runs first-time setup
```

or manually: put `abso.exe` anywhere and run `abso setup`.

### From source (developers)

```powershell
git clone <this repo>
cd windowsoptimizerabso
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
abso setup
```

It detects your hardware, checks for known-problematic Windows updates,
audits current settings, captures a **baseline backup** of your system, and
offers the game profiles that match what your machine supports (HDR lanes on
HDR displays, G-SYNC/VRR lanes on VRR displays, and so on). Nothing is applied
without confirmation.

## Everyday use

```powershell
abso profiles                  # list available profiles for this machine
abso apply overwatch2-gsync    # apply a profile (backup happens automatically)
abso audit --verbose           # what would ABSO change, and why
abso state --json --verify     # is the active profile actually in effect?
abso health --json             # overall install/runtime health
abso restore latest            # roll back the last apply
abso uninstall                 # restore baseline + remove ABSO from the system
abso tray --install-startup    # start the tray app with Windows
```

The tray app (`abso tray`) gives you one-click switching, shows the active
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
with a manifest of every component touched. `abso restore latest` (or a
specific timestamp) rolls back. `abso setup` additionally captures a baseline
snapshot, and `abso uninstall` returns the system to that baseline and removes
ABSO's startup registration.

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
