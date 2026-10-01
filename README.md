# computa

**Per-game Windows tuning, with backups and explicit verification.**

computa is a CLI-first Windows 11 gaming tuning tool: it detects your
hardware, audits your system configuration, and applies game-specific
optimization profiles — Windows, power, input, GPU driver, and display state
together — with automatic backups and one-command rollback.

## What it does

- **Hardware detection** — GPU (NVIDIA/AMD/Intel), CPU topology, monitors,
  refresh rates, G-SYNC/FreeSync/VRR capability, HDR support
- **Configuration audit** — scans 15+ system areas and explains differences from its configured targets and why
- **Game profiles** — per-game optimization lanes (no-sync minimum latency,
  G-SYNC/VRR, HDR, capture-safe variants) that tune Windows, power, input,
  GPU driver, and display state together
- **First-run calibration** — `computa setup` walks hardware detection, audit,
  and profile selection, and adapts what it offers to *your* machine
- **Recovery support** — timestamped backups before profile transactions and
  a baseline captured at setup. Restore coverage depends on each handler;
  runtime process effects and partially restorable settings have limits
- **Automatic CPU core partitioning** — while a game runs, CPU Sets select
  the fast-core group for the game and its children, and the remaining group
  for configured or sustained-heavy background apps. Placement, compatibility,
  and performance depend on the CPU topology and workload; cleanup is attempted
  on game exit. See [docs/PROCESS_LASSO_FEATURES.md](docs/PROCESS_LASSO_FEATURES.md)
- **System tray app** — one-click profile switching, game detection, and
  status, with selectable icon/sound themes
- **Live verification** — `state --json --verify` and `health --json` check
  supported setting readbacks. They do not measure FPS, input latency, or
  prove that every game/driver has consumed a saved setting

## Requirements

- Windows 10/11 (64-bit); Windows 11 has the deepest coverage
- Administrator privileges (system settings require elevation)
- **GPU:** any. NVIDIA gets the deepest driver tuning (per-app driver
  profiles, Low Latency Mode, VRR overrides); AMD Radeon has experimental
  registry mappings; other GPUs use applicable OS/power/input/display settings
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
OW2 profiles use the game's FPS limiter, accept either enabled Reflex mode,
and preserve baseline power, scheduler, NIC and GPU interrupt policies. These
profiles do not impose the broader experimental tweaks listed below.

### Streaming and OBS lanes

Profiles labeled **Streaming** are the lanes to use while OBS, Medal, RTSS,
or another capture/overlay tool is running. They deliberately keep the
capture stack alive during the apply-time display-path check and the recurring
launch janitor sweep. Where the game supports it, they use a capture-compatible
borderless/windowed VRR path so capture hooks can coexist with G-SYNC. They
also leave the game's persistent CPU and I/O priority at Windows Normal rather
than forcing High, preserving scheduler room for the recorder and encoder.

Streaming lanes are available for Slippi Melee, Rivals 2, Counter-Strike 2,
Fortnite, Overwatch 2, and Rocket League in SDR/HDR variants where the game family supports
both. For these families, `*-streaming` command names are
aliases to the matching capture-safe lane; they never resolve to an
overlay-free profile that stops OBS. Use the read-only command below to
inspect the exact process policy:

```powershell
computa launch-killset fortnite-streaming-hdr --json
```

These lanes do not rewrite OBS encoder, bitrate, service, canvas, or recording
settings. Those choices depend on the streaming service, scene complexity,
encoder, and desired output, so computa preserves the user's OBS configuration
instead of imposing a generic preset. Use an SDR Streaming lane for a normal
SDR stream destination. Choose an HDR Streaming lane only when OBS and the
destination color path are already configured for HDR output or tone mapping.

Rocket League includes No Sync, G-SYNC, and G-SYNC Streaming pairs. Its
profiles manage system/driver settings and provide manual native video setup;
they preserve game files, controls and camera settings. G-SYNC lanes use a
driver `refresh - 3` ceiling (297 at 300 Hz), with native FPS Unlimited set
manually. The HDR variants enable Windows HDR without claiming native game
HDR. See the [Rocket League policy and setup](docs/research/rocket-league-settings-2026-10-01.md).

### Windows
- Game Mode on; Game Bar / Game DVR capture off (per-user registry)
- Hardware-Accelerated GPU Scheduling (HAGS) on most gaming profiles
  (hardware/driver-dependent; first change needs a reboot)
- Per-executable Fullscreen Optimizations (FSO) matched to each profile's
  presentation path (exclusive fullscreen vs composited borderless)
- Multi-Plane Overlay (MPO) is **not** disabled by default — disabling it can
  break the Windows 11 VRR/compositor path

### Power
- Many profiles select Ultimate Performance, disable USB selective suspend and
  PCIe link-state power saving, and request processor max state 100%. These
  policies are not measured improvements on every machine; OW2 leaves the
  captured baseline power policy unchanged.

### Input
- Mouse acceleration off, linear response curves, enhanced pointer precision
  off

### GPU driver
- **NVIDIA:** per-application driver profile (NPI / NVAPI DRS) with Low
  Latency Mode, VSync, Power Management, Max Frame Rate, and VRR overrides per
  profile. Native Reflex is preferred over driver LLM whenever the game
  supports it; the Reflex toggle itself must still be enabled in-game
- **AMD:** experimental registry mappings for profile intents; registry
  readback does not establish per-game driver behavior or performance
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

Some settings need a reboot whenever their effective target changes (HAGS,
MPO, opt-in VBS/memory settings); profile switches can require another reboot. `state
--json --verify` distinguishes "not applied" from "applied, reboot pending".

Profiles are starting points for measurement. No built-in profile is proven
to deliver the best possible performance on every supported setup. Use
repeatable per-game frame captures before accepting an optimization claim.

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

This tool modifies Windows system settings. It backs up supported handler state
and reports restore limitations; you should still keep your own restore
points for anything you can't afford to lose. The authors are not responsible
for issues arising from use of this tool.
