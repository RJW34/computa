# Opus 4.7 xhigh Handoff

> **ARCHIVED 2026-05-13.** This handoff is frozen to the April 21, 2026
> gaming-performance audit. Most of its findings have since been
> remediated; references to `PRD.md` and `GAME_CONFIGURATIONS.md` point
> to docs that no longer exist. Read
> **[`docs/AGENT_PROTOCOL.md`](../AGENT_PROTOCOL.md)** for the current
> forward-looking protocol.

This is the start-here handoff for continuing the April 21, 2026 gaming-performance profile audit.

Target agent: Opus 4.7 xhigh, or the nearest available high-reasoning implementation agent.

## Mission

Turn the cross-referenced audit into a concrete remediation pass for A.B.S.O. profiles and documentation.

The user asked:

> For every single possible settings tweak / assertion made about PC Performance when it comes to the profiles this program applies, how are any of them coded incorrectly or following incorrect documentation? Cross reference findings against internet resources as of Today's current date, 4/21/2026 on how to best optimize a Windows PC for gaming performance (one of the main points of this app) and what this app is neglecting to do that would further boost performance during gaming after applying a profile.

Codex completed the research/audit portion and did not implement behavior changes. This handoff packages the result so the next agent can decide and patch deliberately.

## Current Repo State

- Workspace: `C:\Users\mtoli\Documents\Code\windowsoptimizerabso`
- Shell: PowerShell
- Pre-existing dirty files before this handoff:
  - `.codex_audit/latest.json`
  - `abso/tray/profile-catalog-cache.json`
- Do not revert those dirty files unless the user explicitly asks.
- `.codex_audit/latest.json` reflects an unrelated infrastructure audit (tray notifications, restore path, JSON parsing, `Save-TrayConfig`) dated 2026-04-21 with verdict `APPROVED_WITH_NOTES` and all findings already addressed in commits `23a08ff` and `2305195`. It does NOT contain the gaming-performance findings in this document. The findings below are the authoritative record for this audit.
- Codex-added handoff files:
  - `docs/OPUS_4_7_XHIGH_HANDOFF.md`
  - `docs/INDEX.md` link update

## Read In This Order

1. `docs/OPUS_4_7_XHIGH_HANDOFF.md`
2. `docs/HERMES_HANDOFF.md`
3. `README.md`
4. `PRD.md`
5. `GAME_CONFIGURATIONS.md`
6. `abso/profiles/base.py`
7. `abso/profiles/profile_bases.py`
8. Profile files under `abso/profiles/`
9. Settings handlers under `abso/settings/`
10. `docs/QUALITY_RUBRIC.md`
11. `docs/REMEDIATION_ROADMAP.md`
12. `docs/NEXT_IMPLEMENTATION_PHASE.md`

## External Sources Used

These were checked during the audit on April 21, 2026. Refresh before using them to justify new product claims.

- Microsoft Support, Optimizations for windowed games:
  `https://support.microsoft.com/en-us/windows/optimizations-for-windowed-games-in-windows-11-3f006843-2c7e-4ed0-9a5e-f9389e535952`
- Microsoft Windows Learning Center, gaming PC setup, Game Mode and DirectStorage:
  `https://www.microsoft.com/en-us/windows/learning-center/optimize-your-gaming-pc-setup`
- Microsoft DirectX Developer Blog, Hardware Accelerated GPU Scheduling:
  `https://devblogs.microsoft.com/directx/hardware-accelerated-gpu-scheduling/`
- Microsoft Learn, timeBeginPeriod:
  `https://learn.microsoft.com/en-us/windows/win32/api/timeapi/nf-timeapi-timebeginperiod`
- Microsoft Learn, Network Adapter Performance Tuning / TCP autotuning:
  `https://learn.microsoft.com/en-au/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics`
- Microsoft Learn, Memory integrity and VBS:
  `https://learn.microsoft.com/en-us/windows-hardware/drivers/bringup/device-guard-and-credential-guard`
- NVIDIA Reflex latency guide:
  `https://www.nvidia.com/en-us/geforce/guides/gfecnt/202010/system-latency-optimization-guide/`
- NVIDIA Reflex SDK / platform article:
  `https://www.nvidia.com/en-my/geforce/news/reflex-low-latency-platform/`
- NVIDIA Game Ready Driver 551.23, DX12 Ultra Low Latency Mode support:
  `https://www.nvidia.com/Download/driverResults.aspx/%20218113/en-us/`
- Blur Busters G-SYNC 101 optimal settings:
  `https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/14/`
- Tom's Hardware VBS/HVCI benchmarks:
  `https://www.tomshardware.com/news/windows-11-gaming-benchmarks-performance-vbs-hvci-security`
- Microsoft DirectStorage 1.1:
  `https://devblogs.microsoft.com/directx/directstorage-1-1-now-available/`

## Primary Findings To Carry Forward

1. README claims are stale.
   - README says profiles disable FSO/MPO, Nagle, telemetry services, and large system cache.
   - Current profiles do not disable Nagle, services, updates, timer, or VBS.
   - No built-in profile sets `disable_mpo: true`.
   - The code is more conservative than the docs, and the docs should be corrected first.

2. Diablo 4 preset notes and profile implementation disagree on which limiter to use.
   - `abso/settings/nvidia/presets.py` `vrr_diablo4` notes advertise an in-game-first strategy: "Set in-game Max Foreground FPS to refresh_rate - 3 (e.g., 297 for 300Hz). In-game limiter has lower latency than NVCP/RTSS limiters."
   - `abso/profiles/diablo4.py` implements the opposite strategy: NVIDIA `auto_vrr_fps_cap: True` (driver caps), `Diablo4ConfigHandler.limit_foreground_fps: False`, `foreground_fps_limit: 0` (game limiter off). The in-game guidance text at `diablo4.py:160-165` tells the user "Foreground FPS Limit: Unlimited" to match the implementation.
   - The profile is internally consistent — one limiter, owned by the driver — but the preset's advertised strategy (Blur Busters-preferred in-game limiter) is not what the profile wires up.
   - Blur Busters guidance is clear: in-game/config limiter first, external/NVCP limiter only as fallback.
   - Fix path: pick one strategy and align the preset notes, the profile's `auto_vrr_fps_cap` / `limit_foreground_fps` / `foreground_fps_limit` values, and the in-game guidance text so they all tell the same story.

3. VRR profiles need a single-limiter policy.
   - Several profiles combine driver auto cap with game config caps.
   - This may work when values match, but it creates ambiguous behavior and harder troubleshooting.
   - Preferred policy: native Reflex limiter or in-game cap first; NVIDIA Max Frame Rate only when native config is unavailable.

4. Fortnite and Overwatch 2 Reflex claims are not enforced.
   - Fortnite profile text says Reflex On+Boost.
   - `FortniteConfigHandler` only mutates fullscreen, VSync, frame limit, and HDR.
   - Overwatch 2 profile text discusses Reflex, but `OW2ConfigHandler` has no Reflex setting.
   - Keep driver Low Latency Mode off for Reflex games, but stop claiming Reflex is applied unless the app can actually enforce or verify it.

5. HAGS should not be advertised as a universal boost.
   - Most base profiles force `hags: True`.
   - Microsoft positions HAGS as an opt-in scheduler modernization, not a guaranteed gaming win.
   - It can be a valid profile choice, but should be described as hardware/driver dependent and reboot-relevant.

6. Windowed Optimizations, VRR Optimize, and FSO are too broad.
   - Microsoft says Optimizations for windowed games reduce latency for DX10/DX11 borderless/windowed games and enable modern features such as Auto HDR and VRR.
   - Current strict esports profiles may be right to disable/avoid them, but global language implying they should generally be off is not current Windows 11 guidance.
   - Prefer per-game and per-presentation-mode contracts.

7. Game Bar/Game DVR disable is incomplete.
   - Code toggles `UseNexusForGameBarEnabled` and `AppCaptureEnabled`.
   - It does not fully cover background capture policy or all capture-related settings.
   - Either broaden implementation or narrow claims to exactly what is changed.

8. VBS/HVCI/VMP is omitted but real.
   - No built-in profile includes a VBS setting.
   - Current setter only flips HVCI `Enabled`; it does not disable Virtual Machine Platform or hypervisor launch state.
   - This should be opt-in only: less security, potential performance gain, reboot required, and never hidden inside a normal profile.

9. Scheduler and process-priority claims need downgrade.
   - `Win32PrioritySeparation` and IFEO high CPU priority are treated as verified gaming wins.
   - These are old global/process tweaks with real downside risk for audio, OBS, anti-cheat, launchers, and online stability.
   - Consider experimental status, opt-in, or per-profile measured evidence only.

10. Network handler copy is wrong; profile behavior is mostly right.
    - Handler says disabling ECN/autotuning is safe and latency-reducing.
    - Microsoft documentation says TCP receive window autotuning default `normal` improves TCP throughput.
    - Most gameplay latency is UDP, so Nagle/TCP tweaks should not be sold as general gaming latency fixes.
    - Keeping built-in profiles at `disable_nagle: False` is correct.

11. Timer resolution is not applied by profiles.
    - Handler correctly says timer requests are ephemeral/per-process.
    - No built-in profile includes `TimerSettingsHandler`.
    - If exposed, use a session guard for legacy games/emulators only; do not market it as a static latency tweak.

## High-Impact Code Touchpoints

- `README.md`
  - Remove or qualify stale claims around MPO, Nagle, TCP autotuning, services, and memory/cache tweaks.
  - Verified stale as of 2026-04-21: `README.md:146` ("Multi-Plane Overlay (MPO) disabled") and `README.md:155` ("Nagle's algorithm disabled") under the generic Graphics/Network sections, plus "Telemetry services disabled" under Background Services — none of these are implemented by any current built-in profile.
- `PRD.md` and `GAME_CONFIGURATIONS.md`
  - Same truth-pass scope as README. Scan for MPO, Nagle, telemetry, services, LargeSystemCache, and universal-HAGS claims.
- `abso/profiles/profile_bases.py`
  - Base Windows, graphics, registry, network, process priority defaults.
  - Important defaults include `hags: True`, `windowed_optimizations: False`, `vrr_optimize: False`, `disable_global_fso: True`, `disable_nagle: False`.
- `abso/profiles/diablo4.py`
  - Fix limiter contradiction.
  - Reconcile `auto_vrr_fps_cap`, `limit_foreground_fps`, and `foreground_fps_limit`.
- `abso/settings/nvidia/presets.py`
  - Align notes and behavior for `vrr_diablo4`, `vrr_fighting_game`, `reflex_gsync`, and `reflex_game`.
- `abso/profiles/fortnite.py`
  - Reflex On+Boost claim currently not enforced by config handler.
- `abso/settings/fortnite_config.py`
  - Confirm whether Fortnite exposes a stable Reflex config key before adding support.
- `abso/profiles/overwatch2.py`
  - Reflex guidance is profile text only unless handler support exists.
- `abso/settings/ow2_config.py`
  - Confirm whether Reflex can be safely read/written. If not, convert to manual requirement/verification note.
- `abso/settings/windows.py`
  - Game Bar/Game DVR partial implementation.
  - HAGS toggle.
  - HVCI-only VBS setter.
  - Windowed Optimizations and VRR Optimize registry flags.
- `abso/settings/graphics.py`
  - MPO handling is updated for Windows 11 24H2+ and mostly sensible.
  - Audit text saying MPO is "required" for VRR/G-SYNC is too absolute.
- `abso/settings/network.py`
  - Rewrite claims around ECN/autotuning.
- `abso/settings/registry.py`
  - Downgrade `Win32PrioritySeparation` certainty.
- `abso/settings/process_priority.py`
  - Treat high priority as experimental/risk-managed.
- `abso/settings/timer.py`
  - Good cautionary docs; consider explicit non-default/session-only UX.

## Recommended Implementation Order

1. Documentation truth pass.
   - Update `README.md`, `PRD.md`, `GAME_CONFIGURATIONS.md`, and any profile copy so claims match actual applied settings.
   - Confirm `docs/NEXT_IMPLEMENTATION_PHASE.md` reflects current scope; update or retire if stale.
   - Also reconcile the `vrr_diablo4` preset notes with whichever limiter strategy finding #2 converges on, so docs-vs-code does not re-drift on the next profile edit.
   - This is low-risk and stops the app from promising unsupported tweaks.

2. Diablo 4 limiter fix.
   - Prefer in-game `MaxForegroundFPS = refresh - 3` when refresh is known.
   - Disable NVIDIA driver cap for Diablo 4 unless config write is unavailable.
   - Preserve rollback and post-apply verification.

3. Shared VRR limiter policy.
   - Add a helper or profile convention: one limiter source per profile.
   - Update tests to assert no duplicate limiter unless explicitly justified.

4. Reflex enforcement/contract cleanup.
   - Fortnite and OW2: either implement config support with tests or downgrade copy to "set manually".
   - Keep NVIDIA LLM off where Reflex is expected.

5. Claim downgrade for HAGS, FSO/windowed optimizations, scheduler, process priority, and network.
   - Prefer "profile-specific tradeoff" language over universal "boost" language.

6. Opt-in max-performance module.
   - Design a separate explicit flow for VBS/HVCI/VMP with warning, restore path, and reboot requirements.
   - Do not silently add this to default gaming profiles.

7. Missing performance checks.
   - Add diagnostic checks for Windows per-app high-performance GPU preference, background capture/overlays, update/download activity, driver/chipset freshness, XMP/EXPO/Resizable BAR, DirectStorage/NVMe support, and mixed-refresh/multi-monitor risk.

## Suggested Tests

- README/profile copy tests if this repo has doc snapshot checks; otherwise add focused unit tests for profile settings.
- Profile invariant test: no built-in profile should set both NVIDIA `auto_vrr_fps_cap` and a native in-game cap unless an explicit `allow_dual_limiter` marker exists.
- Diablo 4 config tests:
  - refresh known -> foreground cap set to refresh minus three
  - config unavailable -> NVIDIA cap fallback allowed
  - rollback restores prior `LimitForegroundFPS` and `MaxForegroundFPS`
- Fortnite/OW2 tests:
  - if Reflex config support is added, fail closed on unknown keys
  - if not added, profile metadata must not say Reflex is applied by ABSO
- Network handler audit test:
  - default profiles keep `disable_nagle: False`
  - handler copy does not claim ECN/autotuning disable is universally safe
- Windows handler tests:
  - Game DVR claim matches exact registry values changed
  - VBS setting warns/blocks if VMP/hypervisor state cannot be managed

## Source-Supported Statements To Preserve

- Microsoft: windowed-game optimizations reduce latency for compatible DX10/DX11 windowed/borderless games and enable Auto HDR/VRR.
- NVIDIA: native Reflex is preferred over driver Ultra Low Latency Mode when the game supports Reflex.
- NVIDIA: DX12 support for Ultra Low Latency Mode was added in driver 551.23; Vulkan support is still not general in the same way.
- Blur Busters: G-SYNC best practice is G-SYNC on, NVCP VSync on, in-game VSync off, and cap at least three FPS below max refresh; use in-game/config limiter first when available.
- Microsoft: timer resolution is per-process on Windows 10 2004+ and higher resolution can increase scheduler activity/power use.
- Microsoft: TCP receive window autotuning default `normal` can improve TCP throughput; do not disable it as a blanket gaming tweak.
- Microsoft/Tom's Hardware: VBS/HVCI can cost measurable performance in some gaming configurations, but disabling it is a security tradeoff.

## Things Not To Do

- Do not silently add VBS/VMP disabling to normal profiles.
- Do not call any profile "optimal" unless backed by validation-host benchmark artifacts.
- Do not downgrade security features without a reversible, explicit user flow.
- Do not disable services, updates, Defender, or telemetry broadly to chase benchmark numbers.
- Do not add undocumented NVIDIA/Windows registry values just because forum tweak guides mention them.
- Do not assume README claims are true; the code currently disagrees with several of them.

## Expected Deliverable For Next Agent

Produce one or more small PR-sized changes with:

1. Files changed
2. Exact behavioral change
3. External source justification, refreshed as of the work date
4. Tests run
5. Remaining risk
6. Whether the change is docs-only, behavior-changing, or UX-changing

Recommended first PR: documentation truth pass plus tests or checks that prevent stale "profile applies X" claims from drifting again.
