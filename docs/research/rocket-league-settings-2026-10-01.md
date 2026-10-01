# Rocket League profile policy - 2026-10-01

Rocket League has six system/driver profiles: no-sync, fullscreen G-SYNC,
and borderless G-SYNC Streaming, each with SDR and Windows HDR variants.
These are starting policies, not measured performance optima. Creating or
deploying the profiles does not select one or change the game's settings.

## Native configuration boundary

The PC game requires DirectX 11 according to [Epic's support article](https://www.epicgames.com/help/c-37599050/a24988335?lang=en-US).
The installed Epic build uses `RocketLeague.exe`; its generic `Launcher.exe`
must not be used as the NVIDIA binding or session process identity. Steam
app 252950 and Epic Rocket League installations share the game family.
Apply the desired profile, then start the game from Epic or Steam. The
`launch` command refuses this family before applying settings because its
direct-executable launcher cannot yet track platform authentication, the EAC
bootstrapper and the game process as one session. Supplying `--launch-path`
does not bypass that limitation. Detection, profile selection and normal tray
session watching still use the actual game executable.

The inspected `TAGame/Config/TASystemSettings.ini` exposes `UseVsync`,
`Fullscreen`, `Borderless`, resolution, `CustomFPS` and `UncappedFramerate`.
`CustomFPS=0` appears alongside `UncappedFramerate=False`; the value must not
be assumed to mean an active uncapped mode. Shipped defaults establish these
key names, but not whether CustomFPS selects a limit or only adds a dropdown
option. The live game was running
during inspection. No native config writer or readback claim is shipped:
each profile is `system_only`, and native video options remain manual.
This also preserves controller mappings, camera, dead zones, graphics,
input buffering, and the game's cloud/saved settings.

[Epic documents the Frames Per Second dropdown under Settings > Video](https://www.epicgames.com/help/c-37599050/c-32343914/a10445751).
Its general recommendation is to match the display refresh. The G-SYNC
profiles deliberately use the app's existing refresh-minus-three driver
ceiling instead, with native FPS Unlimited to avoid a second lower limiter.
At 300 Hz the requested ceiling is 297; at 144 Hz it is 141. This is a
heuristic margin, not a gameplay FPS guarantee or a physics/network tick rate.

## Sync, latency and display choices

| Lane | Driver policy | Manual native video setup |
| --- | --- | --- |
| No Sync | VSync Off, VRR disabled, driver limiter Off | Fullscreen, VSync Off; choose a sustainable FPS limit or compare Unlimited |
| G-SYNC | VSync On, fullscreen VRR, refresh-minus-three driver cap | Fullscreen, VSync Off, FPS Unlimited |
| G-SYNC Streaming | VSync On, fullscreen/windowed VRR, same cap | Borderless, VSync On, FPS Unlimited |

[NVIDIA's latency guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)
describes native Reflex as preferred where supported and driver Ultra Low
Latency as an alternative elsewhere. Its windowed G-SYNC guidance calls for
native VSync. Rocket League was absent from the inspected
[Reflex compatibility list](https://www.nvidia.com/en-us/geforce/technologies/reflex/supported-products/);
absence is not proof about every future build, but no native Reflex setting
is claimed or requested here.

These profiles use driver Low Latency Mode **On** as a conservative heuristic.
The application's existing online/stability rules would downgrade Ultra;
the profile must describe the effective request honestly. Ultra can be a
separate measured comparison, not a proven universal improvement. Unavailable
private driver readback remains an explicit manual verification step. Public
queue-depth readback alone must not be promoted to proof of Ultra's state.

Fullscreen Optimizations remain available. Normal CPU/I/O priorities avoid
imposing High priority. Power, HAGS, MPO, scheduler/MMCSS, NIC, GPU interrupt,
audio enhancement and input policies are not newly tuned by this family.
No monitor calibration, ICC association or digital-vibrance preference is
imposed. Existing shared session-governor preferences remain applicable.
Leaving a setting out does not erase changes already present in a captured
baseline.

## HDR and capture scope

[Epic's HDR support documentation](https://www.epicgames.com/help/c-37599050/c-42869540/a19619804)
describes console HDR; it does not establish native PC HDR. The HDR variants
enable **Windows HDR**, disable Auto HDR, and leave game content and display
calibration alone. They do not configure or verify RTX HDR, native HDR,
expanded highlight detail, or capture tone mapping.

Streaming variants preserve capture/overlay processes through the shared
capture-safe policy and enable the windowed presentation path. They do not
rewrite OBS configuration. Use SDR Streaming for an ordinary SDR destination;
HDR Streaming requires a deliberately configured output/tone-mapping path.
The ordinary lanes retain the app's capture-closing process policy.

## Verification limits

Tests cover the six-way policy, executable binding, native-config boundary,
guard compatibility, fallback routing, discovery, aliases and tray catalog.
Existing profile snapshots must remain unchanged. Live read-only checks can
confirm discovery and saved driver requests; they do not prove VRR engagement,
frame pacing or latency. No game launch or gameplay test is part of this work.
