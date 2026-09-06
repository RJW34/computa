# Installed Profile Optimization Audit — 2026-08-12

## Scope and standard

This audit covers the exact catalog used by the installed computa tray on the
reference PC: 35 visible profiles in 12 families (38 built-ins total; three
Rivals variants are hidden by tray preferences). The installed catalog and the
repository catalog were byte-for-byte aligned when inspected.

“Optimal” is not treated as a synonym for “plausible.” A setting is accepted
as a default only when it has a vendor/platform contract, direct live evidence,
or a recorded benchmark artifact. Hardware-dependent choices remain explicit
A/B decisions. No game or live display path was launched or reset during this
audit.

Reference hardware: GeForce RTX 4070, Core i9-14900F, 32 GB RAM, 2560×1440
300 Hz VRR primary plus 59.95 Hz secondary.

## Family results

| Family | Renderer/API evidence | Result |
| --- | --- | --- |
| Slippi / Melee | Installed netplay build is Ishiiruka-derived v3.6.4. It stores `GFXBackend` in `Dolphin.ini`; its Windows backend order starts with D3D11. | Preserve the user's renderer. D3D11 is the compatibility baseline; Vulkan/D3D12 are benchmark candidates, not universal upgrades. Fixed the detector and stale-baseline reset. |
| Rivals 2 | Fresh local game log loads `D3D12RHI` with no API launch override. Steam's DirectX 11 line is a minimum requirement, not proof of the active renderer. | Corrected metadata to D3D12. Fixed the capture-safe lane's inherited exclusive-FSO conflict. The 60 Hz simulation-grid cap remains an explicit project policy. |
| Diablo IV | Local runtime log reports a D3D12 device and a fullscreen-windowed HDR surface. Retail setting value `DisplayModeWindowMode=1` is not legacy exclusive fullscreen. | Kept D3D12/Reflex/native limiter; corrected the profile to windowed G-SYNC, FSO enabled, and truthful display labels. |
| Fortnite | Current native config and local log select DX12. Epic has removed DX11 from the current renderer menu. | DX12 is a supported default. Performance Mode versus full DX12 is GPU/workload dependent; ABSO does not force that choice. |
| Marvel Rivals | No current executable/runtime log remained on this machine; profile uses the modern DX12 + native Reflex contract. | Retained as a plausible vendor-supported default, not locally benchmarked. Native-config values remain enforceable when installed. |
| Deadlock | Local config is borderless; Source 2 has no legacy exclusive presentation path. Renderer choice is not locally proven. | Removed contradictory exclusive/DWM-bypass claims and FSO disables. Keep DX11 metadata as a heuristic pending a DX11/Vulkan capture. |
| Counter-Strike 2 | Recent local config is borderless. Steam's Windows requirement is DirectX 11 and there is no local Vulkan launch override, but no renderer log was available. | Retained DX11 metadata. Removed contradictory exclusive/DWM-bypass claims and FSO disables. Native VSync/Reflex remain manual because the family is honestly `system_only`. |
| Overwatch 2 | Fresh local log selects DX11; active native config is borderless HDR, matching the capture-safe G-SYNC lane. Blizzard still identifies DX11 as its lead API and warns that DX12 beta can regress or stutter on some systems. | Retained DX11. Fixed stale no-sync descriptions and retired the unmeasured ULL-Ultra local override so the built-in Reflex On + Boost contract is authoritative again. The machine-specific G-SYNC/ULL cap policy still requires a new benchmark before generalization. |
| Ryujinx / Ryubing | No working install/config was found; renderer guidance assumes Vulkan. | Marked effectively unverified on this PC. Removed the false claim that NVIDIA's OpenGL Threaded Optimization control accelerates Vulkan shader compilation. |
| Pokémon Auto Chess | Browser/WebGL system-only path. | Windowed VRR policy is coherent; broad browser executable binding and experimental ANGLE guidance remain manual/heuristic. |
| PACDeluxe | Native Tauri/WebView2 system-only path. | Windowed VRR policy is coherent; no native game renderer is owned by ABSO. |
| Productivity SDR/HDR | Mixed desktop applications on a windowed flip path. | Fixed global VRR inheritance: these profiles now explicitly restore fullscreen+windowed G-SYNC and use the VSync safety net they promise. |

## Cross-profile corrections

1. Native game restores now own only keys the corresponding handler can write.
   A profile switch no longer restores an entire stale config file for every
   unrelated game. User renderer, audio, controls, quality settings, unknown
   future keys, and other unmanaged values survive.
2. Slippi backend detection now reads the real `Dolphin.ini` location, so HAGS
   and NVIDIA LLM follow DX11/DX12/Vulkan/OpenGL instead of silently using the
   unknown-backend fallback.
3. Stateful peripheral daemons (G HUB agent, iCUE/Corsair service, LCore) are
   no longer considered safe launch-kill targets. Stopping them can change DPI,
   button mappings, macros, RGB, or cooling state.
4. NIC advanced-property tuning is again genuinely opt-in. It is vendor-
   specific and can reset the active link, so an unmeasured default profile no
   longer mutates it during online play.
5. Slippi competitive/universal lanes are marked rollback-sensitive; the
   console-parity lane remains explicitly offline.

## Deliberately not called “optimal” yet

The following need controlled PresentMon/CapFrameX captures on the same game,
map/scene, driver, display path, and warm shader cache before changing defaults:

- Slippi D3D11 versus Vulkan versus D3D12, and HAGS per backend.
- Overwatch G-SYNC native Reflex versus the current ULL/driver-cap policy.
- Fortnite and Marvel Rivals single native limiter versus same-value driver
  fallback.
- Deadlock DX11 versus Vulkan.
- Ryujinx fork/backend/HAGS/shader-cache behavior.
- High process/MMCSS priority, pinned CPU floor/core parking, and unlimited
  shader-cache policies that currently lack artifacts under `reports/benchmarks/`.

## Primary sources

- [Slippi Ishiiruka v3.6.4 backend order](https://github.com/project-slippi/Ishiiruka/blob/v3.6.4/Source/Core/VideoCommon/VideoBackendBase.cpp#L70-L116)
- [Slippi `GFXBackend` persistence](https://github.com/project-slippi/Ishiiruka/blob/v3.6.4/Source/Core/Core/ConfigManager.cpp#L690-L696)
- [Dolphin graphics settings guide](https://dolphin-emu.org/docs/guides/settings/)
- [Blizzard: Overwatch 2 DX12 beta; DX11 remains lead API](https://news.blizzard.com/en-us/article/24173128/get-ready-for-the-directx-12-beta-on-overwatch-2)
- [Epic: Fortnite DX11 renderer option removed](https://www.epicgames.com/help/c-202300000001636/c-202300000001721/has-the-directx-11-option-been-permanently-removed-from-rendering-mode-in-fortnite-a202300000083887)
- [Rivals 2 Windows requirements](https://store.steampowered.com/app/2217000/Rivals_of_Aether_2/)
- [Counter-Strike 2 Windows requirements](https://store.steampowered.com/app/730/CounterStrike_2/)
- [NVIDIA windowed G-SYNC configuration](https://www.nvidia.com/content/Control-Panel-Help/vLatest/en-us/mergedProjects/Display/To_use_variable_refresh_rates.htm)
- [NVIDIA NVAPI driver-setting definitions](https://docs.nvidia.com/nvapi/NvApiDriverSettings_8h.html)
- [Microsoft process-priority guidance](https://learn.microsoft.com/en-us/windows/win32/procthread/scheduling-priorities)
- [Microsoft Multimedia Class Scheduler](https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service)
