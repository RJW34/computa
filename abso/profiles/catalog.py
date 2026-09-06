"""Central profile catalog and metadata.

This module is the single source of truth for profile registration and
cross-surface metadata (CLI, tray, GUI integrations).
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal, get_args

from abso.profiles.base import BaseProfile
from abso.profiles.counter_strike_2 import (
    CounterStrike2GSyncCaptureProfile,
    CounterStrike2GSyncHDRCaptureProfile,
    CounterStrike2GSyncHDRProfile,
    CounterStrike2GSyncProfile,
    CounterStrike2HDRProfile,
    CounterStrike2Profile,
)
from abso.profiles.deadlock import (
    DeadlockGSyncHDRProfile,
    DeadlockGSyncProfile,
    DeadlockHDRProfile,
    DeadlockProfile,
)
from abso.profiles.diablo4 import Diablo4Profile, Diablo4SDRProfile
from abso.profiles.fortnite import (
    FortniteGSyncCaptureProfile,
    FortniteGSyncHDRCaptureProfile,
    FortniteGSyncHDRProfile,
    FortniteHDRProfile,
    FortniteProfile,
)
from abso.profiles.marvel_rivals import MarvelRivalsHDRProfile, MarvelRivalsSDRProfile
from abso.profiles.overwatch2 import (
    Overwatch2GSyncCaptureProfile,
    Overwatch2GSyncHDRCaptureProfile,
    Overwatch2GSyncHDRProfile,
    Overwatch2GSyncProfile,
    Overwatch2NoSyncHDRProfile,
    Overwatch2Profile,
)
from abso.profiles.pacdeluxe import PACDeluxeProfile
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile
from abso.profiles.productivity_oled import ProductivityHDRProfile, ProductivityProfile
from abso.profiles.rivals2_gsync import (
    Rivals2GSyncCaptureProfile,
    Rivals2GSyncHDRCaptureProfile,
    Rivals2GSyncHDRProfile,
    Rivals2GSyncProfile,
)
from abso.profiles.rivals2_nosync import Rivals2NoSyncHDRProfile, Rivals2NoSyncProfile
from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile
from abso.profiles.slippi_melee import (
    SlippiMeleeCaptureProfile,
    SlippiMeleeConsoleParityHDRProfile,
    SlippiMeleeConsoleParityProfile,
    SlippiMeleeHDRCaptureProfile,
    SlippiMeleeHDRProfile,
    SlippiMeleeProfile,
    SlippiMeleeUniversalHDRProfile,
    SlippiMeleeUniversalProfile,
)

TrayCategory = Literal[
    "Desktop",
    "Fighting",
    "Shooters",
    "RPGs",
    "Other",
    # Legacy/user-profile aliases accepted on input and normalized in the manifest.
    "Productivity",
    "Shooter",
    "ARPG",
    "Streaming",
]
SyncMode = Literal["on", "off", "agnostic"]

PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VALID_TRAY_CATEGORIES: frozenset[str] = frozenset(get_args(TrayCategory))
VALID_SYNC_MODES: frozenset[str] = frozenset(get_args(SyncMode))


def is_valid_profile_id(profile_id: str) -> bool:
    """Return True when a profile id is safe for CLI/tray routing."""
    return bool(PROFILE_ID_PATTERN.fullmatch(profile_id))


def is_valid_tray_category(category: str) -> bool:
    """Return True when a tray category is known to catalog/tray clients."""
    return category in VALID_TRAY_CATEGORIES


def is_valid_sync_mode(sync_mode: str) -> bool:
    """Return True when a sync badge mode is known to catalog/tray clients."""
    return sync_mode in VALID_SYNC_MODES


def tray_category_choices() -> tuple[str, ...]:
    """Return valid tray categories in a stable display order."""
    return tuple(get_args(TrayCategory))


def sync_mode_choices() -> tuple[str, ...]:
    """Return valid sync modes in a stable display order."""
    return tuple(get_args(SyncMode))


@dataclass(frozen=True)
class ProfileCatalogEntry:
    """Profile class and UI metadata consumed by tray/GUI surfaces."""

    profile_class: type[BaseProfile]
    tray_category: TrayCategory
    tray_subtitle: str
    tray_description: str | None = None
    sync_mode: SyncMode = "agnostic"
    tray_group: str | None = None
    tray_group_name: str | None = None
    tray_variant: str | None = None
    tray_rank: int = 100
    tray_visible: bool = True


@dataclass(frozen=True)
class TrayProfileUi:
    """Tray grouping metadata for built-in profiles.

    ``group`` is the stable icon/group key. ``group_name`` is the user-facing
    submenu label. ``variant`` is the concise label shown inside that submenu.
    """

    group: str
    group_name: str
    variant: str
    rank: int


TRAY_CATEGORY_ALIASES: dict[str, str] = {
    "Productivity": "Desktop",
    "Shooter": "Shooters",
    "ARPG": "RPGs",
    "Streaming": "Other",
}


def normalize_tray_category(category: str) -> str:
    """Return the current user-facing tray category for a catalog category."""
    return TRAY_CATEGORY_ALIASES.get(category, category)


BUILTIN_TRAY_UI: dict[str, TrayProfileUi] = {
    "productivity": TrayProfileUi("productivity", "Desktop / Productivity", "SDR", 10),
    "productivity-hdr": TrayProfileUi("productivity", "Desktop / Productivity", "HDR", 20),
    "rivals2-gsync-hdr": TrayProfileUi("rivals2", "Rivals 2", "G-SYNC (HDR)", 100),
    "rivals2-gsync-hdr-capture": TrayProfileUi(
        "rivals2", "Rivals 2", "Streaming G-SYNC (HDR)", 110
    ),
    "rivals2-gsync": TrayProfileUi("rivals2", "Rivals 2", "G-SYNC (SDR)", 120),
    "rivals2-gsync-capture": TrayProfileUi("rivals2", "Rivals 2", "Streaming G-SYNC (SDR)", 130),
    "rivals2-nosync-hdr": TrayProfileUi("rivals2", "Rivals 2", "No Sync (HDR)", 140),
    "rivals2-nosync": TrayProfileUi("rivals2", "Rivals 2", "No Sync (SDR)", 150),
    "slippi-melee": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Competitive No Sync (SDR)", 200
    ),
    "slippi-melee-hdr": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Competitive No Sync (HDR)", 210
    ),
    "slippi-melee-capture": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Streaming No Sync (SDR)", 220
    ),
    "slippi-melee-hdr-capture": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Streaming No Sync (HDR)", 230
    ),
    "slippi-melee-console-parity": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Console-Parity 60 Hz (SDR)", 240
    ),
    "slippi-melee-console-parity-hdr": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Console-Parity 60 Hz (HDR)", 250
    ),
    "slippi-melee-universal": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Universal No Sync (SDR)", 260
    ),
    "slippi-melee-universal-hdr": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Universal No Sync (HDR)", 270
    ),
    "ryujinx-ssbu": TrayProfileUi(
        "ryujinx-ssbu", "SSBU / HewDraw Remix (Ryujinx)", "Low-Latency Emulator", 300
    ),
    "deadlock": TrayProfileUi("deadlock", "Deadlock", "No Sync (SDR)", 100),
    "deadlock-hdr": TrayProfileUi("deadlock", "Deadlock", "No Sync (HDR)", 110),
    "deadlock-gsync": TrayProfileUi("deadlock", "Deadlock", "G-SYNC (SDR)", 120),
    "deadlock-gsync-hdr": TrayProfileUi("deadlock", "Deadlock", "G-SYNC (HDR)", 130),
    "fortnite": TrayProfileUi("fortnite", "Fortnite", "No Sync (SDR)", 200),
    "fortnite-hdr": TrayProfileUi("fortnite", "Fortnite", "No Sync (HDR)", 210),
    "fortnite-gsync-capture": TrayProfileUi("fortnite", "Fortnite", "Streaming G-SYNC (SDR)", 220),
    "fortnite-gsync-hdr": TrayProfileUi("fortnite", "Fortnite", "G-SYNC (HDR)", 230),
    "fortnite-gsync-hdr-capture": TrayProfileUi(
        "fortnite", "Fortnite", "Streaming G-SYNC (HDR)", 240
    ),
    "marvel-rivals-sdr": TrayProfileUi("marvel-rivals", "Marvel Rivals", "G-SYNC (SDR)", 300),
    "marvel-rivals-hdr": TrayProfileUi("marvel-rivals", "Marvel Rivals", "G-SYNC (HDR)", 310),
    "overwatch2": TrayProfileUi("overwatch2", "Overwatch 2", "No Sync (SDR)", 400),
    "overwatch2-hdr": TrayProfileUi("overwatch2", "Overwatch 2", "No Sync (HDR)", 410),
    "overwatch2-gsync": TrayProfileUi("overwatch2", "Overwatch 2", "G-SYNC (SDR)", 420),
    "overwatch2-gsync-hdr": TrayProfileUi("overwatch2", "Overwatch 2", "G-SYNC (HDR)", 430),
    "overwatch2-gsync-capture": TrayProfileUi(
        "overwatch2", "Overwatch 2", "Streaming G-SYNC (SDR)", 440
    ),
    "overwatch2-gsync-hdr-capture": TrayProfileUi(
        "overwatch2", "Overwatch 2", "Streaming G-SYNC (HDR)", 450
    ),
    "counter-strike-2": TrayProfileUi("counter-strike-2", "Counter-Strike 2", "No Sync (SDR)", 500),
    "counter-strike-2-hdr": TrayProfileUi(
        "counter-strike-2", "Counter-Strike 2", "No Sync (HDR)", 510
    ),
    "counter-strike-2-gsync": TrayProfileUi(
        "counter-strike-2", "Counter-Strike 2", "G-SYNC (SDR)", 520
    ),
    "counter-strike-2-gsync-hdr": TrayProfileUi(
        "counter-strike-2", "Counter-Strike 2", "G-SYNC (HDR)", 540
    ),
    "counter-strike-2-gsync-capture": TrayProfileUi(
        "counter-strike-2", "Counter-Strike 2", "Streaming G-SYNC (SDR)", 530
    ),
    "counter-strike-2-gsync-hdr-capture": TrayProfileUi(
        "counter-strike-2", "Counter-Strike 2", "Streaming G-SYNC (HDR)", 550
    ),
    "diablo4": TrayProfileUi("diablo4", "Diablo 4", "HDR", 100),
    "diablo4-sdr": TrayProfileUi("diablo4", "Diablo 4", "SDR", 110),
    "pokemon-auto-chess": TrayProfileUi(
        "pokemon-auto-chess", "Pokemon Auto Chess", "Browser WebGL", 100
    ),
    "pacdeluxe": TrayProfileUi(
        "pacdeluxe", "PACDeluxe (Pokemon Auto Chess)", "Native Tauri / WebView2", 110
    ),
}


PROFILE_CATALOG: OrderedDict[str, ProfileCatalogEntry] = OrderedDict(
    {
        "slippi-melee": ProfileCatalogEntry(
            profile_class=SlippiMeleeProfile,
            tray_category="Fighting",
            tray_subtitle="Competitive | No Sync | Backend-Aware",
            sync_mode="off",
        ),
        "slippi-melee-hdr": ProfileCatalogEntry(
            profile_class=SlippiMeleeHDRProfile,
            tray_category="Fighting",
            tray_subtitle="Competitive HDR | No Sync | Eye-Strain Relief",
            tray_description=(
                "Competitive Slippi profile with Windows HDR on. Dolphin renders SDR through "
                "the HDR composition path; small latency cost in exchange for the lower-strain "
                "HDR desktop look."
            ),
            sync_mode="off",
        ),
        "slippi-melee-capture": ProfileCatalogEntry(
            profile_class=SlippiMeleeCaptureProfile,
            tray_category="Fighting",
            tray_subtitle="SDR Streaming | Borderless | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Competitive Slippi SDR on Dolphin's borderless path. OBS, Medal, "
                "RTSS, and overlays remain available; game CPU/I/O priority stays "
                "Normal and OBS encoder/output settings are left untouched."
            ),
            sync_mode="off",
        ),
        "slippi-melee-hdr-capture": ProfileCatalogEntry(
            profile_class=SlippiMeleeHDRCaptureProfile,
            tray_category="Fighting",
            tray_subtitle="HDR Streaming | Borderless | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Competitive Slippi SDR-in-HDR on Dolphin's borderless path. OBS, "
                "Medal, RTSS, and overlays remain available; game CPU/I/O priority "
                "stays Normal and OBS encoder/output settings are left untouched."
            ),
            sync_mode="off",
        ),
        "slippi-melee-console-parity": ProfileCatalogEntry(
            profile_class=SlippiMeleeConsoleParityProfile,
            tray_category="Fighting",
            tray_subtitle="Console-Parity | 60Hz + VSync | LLM OFF",
            sync_mode="on",
        ),
        "slippi-melee-console-parity-hdr": ProfileCatalogEntry(
            profile_class=SlippiMeleeConsoleParityHDRProfile,
            tray_category="Fighting",
            tray_subtitle="Console-Parity HDR | 60Hz + VSync | Eye-Strain Relief",
            tray_description=(
                "Console-parity Slippi profile with Windows HDR on. 60 Hz + VSync cadence "
                "preserved; Dolphin renders SDR through the HDR composition path."
            ),
            sync_mode="on",
        ),
        "slippi-melee-universal": ProfileCatalogEntry(
            profile_class=SlippiMeleeUniversalProfile,
            tray_category="Fighting",
            tray_subtitle="No Sync | HAGS ON | Reapply-Friendly",
            tray_description=(
                "No-sync Slippi profile with HAGS kept on so re-applying does not require "
                "a reboot. VSync OFF, G-SYNC/VRR OFF."
            ),
            sync_mode="off",
        ),
        "slippi-melee-universal-hdr": ProfileCatalogEntry(
            profile_class=SlippiMeleeUniversalHDRProfile,
            tray_category="Fighting",
            tray_subtitle="Universal HDR | HAGS ON | No Sync | Eye-Strain Relief",
            tray_description=(
                "Universal HDR Slippi profile. Fixed HAGS on (no reboot on re-apply), no-sync "
                "latency contract, Windows HDR for daily eye-strain relief."
            ),
            sync_mode="off",
        ),
        # 2026-07 consolidation: the offline/online lane split collapsed into
        # single rollback-safe lanes (SnapNet is server-authoritative, so the
        # aggressive offline-only tuning bought nothing measurable). Retired
        # IDs redirect via PROFILE_ALIASES below.
        "rivals2-nosync": ProfileCatalogEntry(
            profile_class=Rivals2NoSyncProfile,
            tray_category="Fighting",
            tray_subtitle="No Sync SDR | LLM ON | Rollback-Safe",
            tray_description=(
                "Rollback-safe Rivals 2 no-sync SDR lane for online play and "
                "training. VSync and VRR off, in-game cap on the 60 Hz sim grid "
                "(300 @ 300 Hz), exclusive fullscreen."
            ),
            sync_mode="off",
        ),
        "rivals2-nosync-hdr": ProfileCatalogEntry(
            profile_class=Rivals2NoSyncHDRProfile,
            tray_category="Fighting",
            tray_subtitle="No Sync HDR | LLM ON | Rollback-Safe",
            tray_description=(
                "Rollback-safe Rivals 2 no-sync lane with Windows HDR composition. "
                "Same no-sync timing contract as SDR; Rivals 2 currently advertises "
                "no native HDR support, so the game stays SDR inside the HDR desktop."
            ),
            sync_mode="off",
        ),
        "rivals2-gsync": ProfileCatalogEntry(
            profile_class=Rivals2GSyncProfile,
            tray_category="Fighting",
            tray_subtitle="Strict SDR G-SYNC | LLM ON | VSync Safety Net | Rollback-Safe",
            tray_description=(
                "Rollback-safe Rivals 2 strict fullscreen-only G-SYNC SDR lane for "
                "online play and training. Caps on the 60 Hz sim grid (largest "
                "multiple of 60 below refresh, e.g. 240 @ 300 Hz)."
            ),
            sync_mode="on",
        ),
        "rivals2-gsync-capture": ProfileCatalogEntry(
            profile_class=Rivals2GSyncCaptureProfile,
            tray_category="Fighting",
            tray_subtitle="SDR Streaming | Borderless VRR | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Rollback-safe SDR G-SYNC on the borderless windowed VRR path. "
                "OBS, Medal, RTSS, and overlays remain available; game CPU/I/O "
                "priority stays Normal and OBS settings are left untouched."
            ),
            sync_mode="on",
        ),
        "rivals2-gsync-hdr": ProfileCatalogEntry(
            profile_class=Rivals2GSyncHDRProfile,
            tray_category="Fighting",
            tray_subtitle="Strict HDR G-SYNC | LLM ON | VSync Safety Net | Rollback-Safe",
            tray_description=(
                "Rollback-safe Rivals 2 strict G-SYNC lane with Windows HDR "
                "composition. Rivals 2 currently advertises no native HDR support, "
                "so it stays SDR inside the HDR desktop."
            ),
            sync_mode="on",
        ),
        "rivals2-gsync-hdr-capture": ProfileCatalogEntry(
            profile_class=Rivals2GSyncHDRCaptureProfile,
            tray_category="Fighting",
            tray_subtitle="HDR Streaming | Borderless VRR | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Rollback-safe G-SYNC lane with Windows HDR composition on the "
                "borderless windowed VRR path. OBS, Medal, RTSS, and overlays remain "
                "available; game CPU/I/O priority stays Normal and OBS settings are "
                "left untouched. Rivals 2 native HDR remains off."
            ),
            sync_mode="on",
        ),
        "diablo4": ProfileCatalogEntry(
            profile_class=Diablo4Profile,
            tray_category="RPGs",
            tray_subtitle="HDR ON | Reflex ON | G-SYNC ON | LLM OFF",
            sync_mode="on",
        ),
        "diablo4-sdr": ProfileCatalogEntry(
            profile_class=Diablo4SDRProfile,
            tray_category="RPGs",
            tray_subtitle="SDR | Reflex ON | VRR",
            sync_mode="on",
        ),
        "fortnite": ProfileCatalogEntry(
            profile_class=FortniteProfile,
            tray_category="Shooters",
            tray_subtitle="SDR | Reflex (set in-game) | No Sync",
            sync_mode="off",
        ),
        "fortnite-hdr": ProfileCatalogEntry(
            profile_class=FortniteHDRProfile,
            tray_category="Shooters",
            tray_subtitle="HDR ON | Reflex (set in-game) | No Sync",
            sync_mode="off",
        ),
        "fortnite-gsync-hdr": ProfileCatalogEntry(
            profile_class=FortniteGSyncHDRProfile,
            tray_category="Shooters",
            tray_subtitle="HDR ON | Reflex (set in-game) | G-SYNC ON",
            tray_description=(
                "Tear-free low-latency VRR Fortnite with native HDR for "
                "OLED / Mini-LED. G-SYNC ON + NVCP VSync safety net at a "
                "refresh - 3 cap; enable Reflex On + Boost in-game."
            ),
            sync_mode="on",
        ),
        "fortnite-gsync-capture": ProfileCatalogEntry(
            profile_class=FortniteGSyncCaptureProfile,
            tray_category="Shooters",
            tray_subtitle="SDR Streaming | Borderless VRR | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Capped SDR G-SYNC on Fortnite's borderless path. OBS, Medal, RTSS, "
                "and overlays remain available; game CPU/I/O priority stays Normal "
                "and OBS encoder/output settings are left untouched."
            ),
            sync_mode="on",
        ),
        "fortnite-gsync-hdr-capture": ProfileCatalogEntry(
            profile_class=FortniteGSyncHDRCaptureProfile,
            tray_category="Shooters",
            tray_subtitle="HDR Streaming | Borderless VRR | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Capped Windows-HDR G-SYNC on Fortnite's borderless path. OBS, Medal, "
                "RTSS, and overlays remain available; game CPU/I/O priority stays "
                "Normal and OBS encoder/output settings are left untouched."
            ),
            sync_mode="on",
        ),
        "marvel-rivals-sdr": ProfileCatalogEntry(
            profile_class=MarvelRivalsSDRProfile,
            tray_category="Shooters",
            tray_subtitle="SDR | Reflex ON+Boost | G-SYNC ON",
            tray_description=(
                "Performance-first SDR Marvel Rivals profile. Uses Reflex + VRR and keeps "
                "engine-specific options in the native config handler."
            ),
            sync_mode="on",
        ),
        "marvel-rivals-hdr": ProfileCatalogEntry(
            profile_class=MarvelRivalsHDRProfile,
            tray_category="Shooters",
            tray_subtitle="HDR ON | Reflex ON+Boost | G-SYNC ON",
            tray_description=(
                "Performance-first HDR Marvel Rivals profile. Uses Reflex + VRR and keeps "
                "engine-specific options in the native config handler."
            ),
            sync_mode="on",
        ),
        "deadlock": ProfileCatalogEntry(
            profile_class=DeadlockProfile,
            tray_category="Shooters",
            tray_subtitle="No Sync SDR | Reflex (set in-game) | VSync OFF | G-SYNC OFF",
            tray_description=(
                "Minimum-latency no-sync Deadlock profile. ABSO tunes the OS/driver path; "
                "enable Reflex On + Boost manually in Deadlock's video settings."
            ),
            sync_mode="off",
        ),
        "deadlock-hdr": ProfileCatalogEntry(
            profile_class=DeadlockHDRProfile,
            tray_category="Shooters",
            tray_subtitle="No Sync HDR | Reflex (set in-game) | VSync OFF | G-SYNC OFF",
            tray_description=(
                "Minimum-latency no-sync Deadlock with Windows HDR on for OLED / Mini-LED. "
                "Deadlock currently renders SDR through the HDR composition path."
            ),
            sync_mode="off",
        ),
        "deadlock-gsync": ProfileCatalogEntry(
            profile_class=DeadlockGSyncProfile,
            tray_category="Shooters",
            tray_subtitle="Strict SDR Exclusive | Reflex (set in-game) | G-SYNC ON",
            tray_description=(
                "Tear-free low-latency VRR Deadlock profile on the strict fullscreen-only "
                "G-SYNC path. Enable Reflex On + Boost manually in-game."
            ),
            sync_mode="on",
        ),
        "deadlock-gsync-hdr": ProfileCatalogEntry(
            profile_class=DeadlockGSyncHDRProfile,
            tray_category="Shooters",
            tray_subtitle="Strict HDR Exclusive | Reflex (set in-game) | G-SYNC ON",
            tray_description=(
                "Tear-free low-latency VRR Deadlock with Windows HDR on for OLED / Mini-LED. "
                "Deadlock currently renders SDR through the HDR composition path."
            ),
            sync_mode="on",
        ),
        "counter-strike-2": ProfileCatalogEntry(
            profile_class=CounterStrike2Profile,
            tray_category="Shooters",
            tray_subtitle="No Sync SDR | Reflex (set in-game) | VSync OFF | G-SYNC OFF",
            tray_description=(
                "Minimum-latency no-sync Counter-Strike 2 profile. ABSO tunes the "
                "OS/driver path; enable Reflex Enabled + Boost manually in CS2's "
                "video settings."
            ),
            sync_mode="off",
        ),
        "counter-strike-2-hdr": ProfileCatalogEntry(
            profile_class=CounterStrike2HDRProfile,
            tray_category="Shooters",
            tray_subtitle="No Sync HDR | Reflex (set in-game) | VSync OFF | G-SYNC OFF",
            tray_description=(
                "Minimum-latency no-sync Counter-Strike 2 with Windows HDR on for "
                "OLED / Mini-LED. CS2 currently renders SDR through the HDR "
                "composition path."
            ),
            sync_mode="off",
        ),
        "counter-strike-2-gsync": ProfileCatalogEntry(
            profile_class=CounterStrike2GSyncProfile,
            tray_category="Shooters",
            tray_subtitle="Strict SDR Exclusive | Reflex (set in-game) | G-SYNC ON",
            tray_description=(
                "Tear-free low-latency VRR Counter-Strike 2 profile on the strict "
                "fullscreen-only G-SYNC path. Enable Reflex Enabled + Boost "
                "manually in-game."
            ),
            sync_mode="on",
        ),
        "counter-strike-2-gsync-capture": ProfileCatalogEntry(
            profile_class=CounterStrike2GSyncCaptureProfile,
            tray_category="Shooters",
            tray_subtitle="SDR Streaming | Borderless VRR | Keeps Medal/OBS/Overlays",
            tray_description=(
                "SDR G-SYNC on the borderless windowed path. OBS, Medal, RTSS, and "
                "overlays remain available; game CPU/I/O priority stays Normal and "
                "OBS encoder/output settings are left untouched."
            ),
            sync_mode="on",
        ),
        "counter-strike-2-gsync-hdr": ProfileCatalogEntry(
            profile_class=CounterStrike2GSyncHDRProfile,
            tray_category="Shooters",
            tray_subtitle="Strict HDR Exclusive | Reflex (set in-game) | G-SYNC ON",
            tray_description=(
                "Tear-free low-latency VRR Counter-Strike 2 with Windows HDR on "
                "for OLED / Mini-LED. CS2 currently renders SDR through the HDR "
                "composition path."
            ),
            sync_mode="on",
        ),
        "counter-strike-2-gsync-hdr-capture": ProfileCatalogEntry(
            profile_class=CounterStrike2GSyncHDRCaptureProfile,
            tray_category="Shooters",
            tray_subtitle="HDR Streaming | Borderless VRR | Keeps Medal/OBS/Overlays",
            tray_description=(
                "Windows HDR G-SYNC on the borderless windowed path. OBS, Medal, "
                "RTSS, and overlays remain available; game CPU/I/O priority stays "
                "Normal and OBS encoder/output settings are left untouched."
            ),
            sync_mode="on",
        ),
        "overwatch2": ProfileCatalogEntry(
            profile_class=Overwatch2Profile,
            tray_category="Shooters",
            tray_subtitle="No Sync SDR | Reflex ON+Boost (set in-game) | VSync OFF | G-SYNC OFF",
            sync_mode="off",
        ),
        "overwatch2-hdr": ProfileCatalogEntry(
            profile_class=Overwatch2NoSyncHDRProfile,
            tray_category="Shooters",
            tray_subtitle="No Sync HDR | Reflex ON+Boost (set in-game) | VSync OFF | G-SYNC OFF",
            tray_description=(
                "Minimum-latency no-sync Overwatch 2 with native HDR for "
                "OLED / Mini-LED. Same sync/VRR contract as the SDR variant."
            ),
            sync_mode="off",
        ),
        "overwatch2-gsync": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncProfile,
            tray_category="Shooters",
            tray_subtitle="Overlay-Free SDR Borderless | Reflex OFF + ULL Ultra | G-SYNC ON",
            tray_description=(
                "Low-latency Overwatch 2 G-SYNC on the same borderless VRR "
                "path as the Streaming sibling, while stopping capture and overlay processes."
            ),
            sync_mode="on",
        ),
        "overwatch2-gsync-hdr": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncHDRProfile,
            tray_category="Shooters",
            tray_subtitle="Overlay-Free HDR Borderless | Reflex OFF + ULL Ultra | G-SYNC ON",
            tray_description=(
                "Low-latency native-HDR Overwatch 2 G-SYNC on the optimized borderless "
                "VRR path, while stopping capture and overlay processes."
            ),
            sync_mode="on",
        ),
        "overwatch2-gsync-capture": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncCaptureProfile,
            tray_category="Shooters",
            tray_subtitle="SDR Streaming | Borderless VRR | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Borderless SDR G-SYNC streaming path. OBS, Medal, RTSS, and "
                "overlays remain available; game CPU/I/O priority stays Normal and "
                "OBS encoder/output settings are left untouched."
            ),
            sync_mode="on",
        ),
        "overwatch2-gsync-hdr-capture": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncHDRCaptureProfile,
            tray_category="Shooters",
            tray_subtitle="HDR Streaming | Borderless VRR | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Borderless native-HDR G-SYNC streaming path. OBS, Medal, RTSS, "
                "and overlays remain available; game CPU/I/O priority stays Normal "
                "and OBS encoder/output settings are left untouched."
            ),
            sync_mode="on",
        ),
        "pokemon-auto-chess": ProfileCatalogEntry(
            profile_class=PokemonAutoChessProfile,
            tray_category="Other",
            tray_subtitle="LLM ON | Browser WebGL | G-SYNC + VSync On",
            sync_mode="on",
        ),
        "pacdeluxe": ProfileCatalogEntry(
            profile_class=PACDeluxeProfile,
            tray_category="Other",
            tray_subtitle="LLM ON | Tauri + WebView2 | G-SYNC + VSync On",
            sync_mode="on",
        ),
        "productivity": ProfileCatalogEntry(
            profile_class=ProductivityProfile,
            tray_category="Desktop",
            tray_subtitle="SDR | HDR OFF | Adaptive VSync | VRR",
            sync_mode="agnostic",
        ),
        "productivity-hdr": ProfileCatalogEntry(
            profile_class=ProductivityHDRProfile,
            tray_category="Desktop",
            tray_subtitle="HDR ON | WCG ON | Adaptive VSync | VRR | OLED/Mini-LED",
            sync_mode="agnostic",
        ),
        "ryujinx-ssbu": ProfileCatalogEntry(
            profile_class=RyujinxSSBUProfile,
            tray_category="Fighting",
            tray_subtitle="Vulkan | Fixed 60fps | HAGS ON | LLM OFF",
            tray_description=(
                "Low-latency Ryujinx system path for SSBU/HewDraw Remix. ABSO handles the OS/driver side, "
                "but emulator settings still need to be configured manually."
            ),
            sync_mode="off",
        ),
    }
)

PROFILE_ALIASES: dict[str, str] = {
    # Retired generic/no-value Rivals variants map to the merged no-sync
    # lane instead of lingering as separate menu clutter.
    "rivals2": "rivals2-nosync",
    "rivals2-300hz-max": "rivals2-nosync",
    "rivals2-tournament-sim-144hz": "rivals2-nosync",
    # 2026-07 offline/online consolidation: the split lanes collapsed into
    # single rollback-safe lanes; every retired ID redirects to its merged
    # successor so old tray configs, state files, and history normalize.
    "rivals2-offline": "rivals2-nosync",
    "rivals2-offline-hdr": "rivals2-nosync-hdr",
    "rivals2-online": "rivals2-nosync",
    "rivals2-online-hdr": "rivals2-nosync-hdr",
    "rivals2-online-gsync": "rivals2-gsync",
    "rivals2-online-gsync-hdr": "rivals2-gsync-hdr",
    "rivals2-online-gsync-hdr-capture": "rivals2-gsync-hdr-capture",
    # Requested OBS Streaming aliases resolve directly to capture-safe canonical lanes.
    "fortnite-streaming": "fortnite-gsync-capture",
    "fortnite-streaming-hdr": "fortnite-gsync-hdr-capture",
    "fortnite-gsync-streaming": "fortnite-gsync-capture",
    "fortnite-gsync-streaming-hdr": "fortnite-gsync-hdr-capture",
    "fortnite-gsync-hdr-streaming": "fortnite-gsync-hdr-capture",
    "fortnite-gsync-sdr-capture": "fortnite-gsync-capture",
    "overwatch2-streaming": "overwatch2-gsync-capture",
    "overwatch2-streaming-hdr": "overwatch2-gsync-hdr-capture",
    "overwatch2-gsync-streaming": "overwatch2-gsync-capture",
    "overwatch2-gsync-streaming-hdr": "overwatch2-gsync-hdr-capture",
    "overwatch2-gsync-hdr-streaming": "overwatch2-gsync-hdr-capture",
    "overwatch2-gsync-sdr-capture": "overwatch2-gsync-capture",
    "pacdeluxe-streaming": "pacdeluxe",
    "ryujinx-ssbu-streaming": "ryujinx-ssbu",
    "rivals2-streaming": "rivals2-gsync-capture",
    "rivals2-streaming-hdr": "rivals2-gsync-hdr-capture",
    "rivals2-gsync-streaming": "rivals2-gsync-capture",
    "rivals2-gsync-streaming-hdr": "rivals2-gsync-hdr-capture",
    "rivals2-gsync-hdr-streaming": "rivals2-gsync-hdr-capture",
    "rivals2-gsync-sdr-capture": "rivals2-gsync-capture",
    "roa2-streaming": "rivals2-gsync-capture",
    "roa2-streaming-hdr": "rivals2-gsync-hdr-capture",
    "roa2-gsync-capture": "rivals2-gsync-capture",
    "roa2-gsync-hdr-capture": "rivals2-gsync-hdr-capture",
    "slippi-melee-streaming": "slippi-melee-capture",
    "slippi-melee-streaming-hdr": "slippi-melee-hdr-capture",
    "slippi-melee-hdr-streaming": "slippi-melee-hdr-capture",
    "slippi-capture": "slippi-melee-capture",
    "slippi-hdr-capture": "slippi-melee-hdr-capture",
    "ssbm-streaming": "slippi-melee-capture",
    "ssbm-streaming-hdr": "slippi-melee-hdr-capture",
    # Experimental/duplicate Slippi variants.
    "slippi-melee-vrr-lab": "slippi-melee",
    # Short-form Counter-Strike 2 convenience ids (cs2 == counter-strike-2).
    "cs2": "counter-strike-2",
    "cs2-hdr": "counter-strike-2-hdr",
    "cs2-gsync": "counter-strike-2-gsync",
    "cs2-gsync-hdr": "counter-strike-2-gsync-hdr",
    "cs2-streaming": "counter-strike-2-gsync-capture",
    "cs2-streaming-hdr": "counter-strike-2-gsync-hdr-capture",
    "counter-strike-2-streaming": "counter-strike-2-gsync-capture",
    "counter-strike-2-streaming-hdr": "counter-strike-2-gsync-hdr-capture",
    "cs2-gsync-capture": "counter-strike-2-gsync-capture",
    "cs2-gsync-hdr-capture": "counter-strike-2-gsync-hdr-capture",
    "counter-strike-2-gsync-sdr-capture": "counter-strike-2-gsync-capture",
}


def profile_id_conflict_kind(profile_id: str) -> str | None:
    """Return the reserved-ID conflict kind for a user profile id."""
    if profile_id in PROFILE_CATALOG:
        return "built-in profile"
    if profile_id in PROFILE_ALIASES:
        return "profile alias"
    return None


def is_reserved_profile_id(profile_id: str) -> bool:
    """Return True when a profile id is already owned by ABSO."""
    return profile_id_conflict_kind(profile_id) is not None


def _load_user_profiles() -> dict[str, ProfileCatalogEntry]:
    """Load user-defined YAML profiles from ~/.abso/profiles/.

    User profiles cannot override built-in profile IDs.
    """
    try:
        from abso.profiles.yaml_loader import YAMLProfileLoader

        loader = YAMLProfileLoader()
        user_profiles = loader.load_directory()
        # Filter out conflicts with built-in profiles and retired aliases.
        # Alias conflicts are especially confusing: the manifest would expose
        # the user profile ID, while apply/launch resolution would silently
        # route the same ID to the built-in canonical target.
        safe = {}
        for pid, entry in user_profiles.items():
            conflict_kind = profile_id_conflict_kind(pid)
            if conflict_kind is not None:
                import logging

                logging.getLogger(__name__).warning(
                    "User profile '%s' conflicts with %s, skipping",
                    pid,
                    conflict_kind,
                )
            else:
                safe[pid] = entry
        return safe
    except Exception as e:
        import logging

        logging.getLogger(__name__).debug(f"User profile loading skipped: {e}")
        return {}


def _get_full_catalog() -> dict[str, ProfileCatalogEntry]:
    """Get built-in + user profiles merged."""
    merged = dict(PROFILE_CATALOG)
    merged.update(_load_user_profiles())
    return merged


def get_profile_classes() -> dict[str, type[BaseProfile]]:
    """Get profile registry mapping profile ID to profile class."""
    return {pid: entry.profile_class for pid, entry in _get_full_catalog().items()}


def resolve_profile_id(profile_id: str | None) -> str | None:
    """Resolve a potentially legacy profile id to its canonical id."""
    if profile_id is None:
        return None
    return PROFILE_ALIASES.get(profile_id, profile_id)


def get_profile_sync_mode(profile_id: str | None) -> str | None:
    """Return the catalog-declared sync mode for a profile, or None.

    Used by the apply path to thread profile sync intent through to handlers
    that need it (e.g. ColorProfileSettingsHandler filtering monitor OSD
    recommendations that contradict the active profile's sync mode).
    """
    canonical = resolve_profile_id(profile_id)
    if not canonical:
        return None
    entry = _get_full_catalog().get(canonical)
    if entry is None:
        return None
    return entry.sync_mode


def get_profile_instances() -> dict[str, BaseProfile]:
    """Get all profile instances keyed by profile ID."""
    return {pid: entry.profile_class() for pid, entry in _get_full_catalog().items()}


def get_profile_manifest() -> list[dict[str, Any]]:
    """Get profile metadata for GUI/tray clients."""
    manifest: list[dict[str, Any]] = []
    for profile_id, entry in _get_full_catalog().items():
        profile = entry.profile_class()
        handlers = [handler.__class__.__name__ for handler in profile.get_handlers()]
        built_in_ui = BUILTIN_TRAY_UI.get(profile_id)
        tray_group = entry.tray_group or (built_in_ui.group if built_in_ui else None) or profile_id
        tray_group_name = (
            entry.tray_group_name
            or (built_in_ui.group_name if built_in_ui else None)
            or profile.display_name
        )
        tray_variant = (
            entry.tray_variant
            or (built_in_ui.variant if built_in_ui else None)
            or profile.display_name
        )
        tray_rank = built_in_ui.rank if built_in_ui else entry.tray_rank
        manifest.append(
            {
                "id": profile_id,
                "display_name": profile.display_name,
                "description": profile.description,
                "optimization_target": profile.optimization_target,
                "application_scope": profile.application_scope,
                "executables": profile.executable_hints,
                "handlers": handlers,
                "has_in_game_settings": profile.has_in_game_settings(),
                "tray_category": normalize_tray_category(entry.tray_category),
                "tray_subtitle": entry.tray_subtitle,
                "tray_description": entry.tray_description or profile.description,
                "tray_group": tray_group,
                "tray_group_name": tray_group_name,
                "tray_variant": tray_variant,
                "tray_rank": tray_rank,
                "tray_visible": entry.tray_visible,
                "sync_mode": entry.sync_mode,
                # Machine-independent capability requirement: True for lanes
                # that turn Windows HDR composition on. Clients (tray, setup
                # wizard) filter these on displays without HDR support.
                "requires_hdr_display": bool(
                    profile.get_settings("WindowsSettingsHandler").get("hdr") is True
                ),
                "launch_process_killset": profile.launch_process_killset().to_dict(),
                "requires_overlay_free_path": bool(
                    profile.display_path_requirements.require_overlay_free_path
                ),
                "keep_awake_while_gaming": bool(profile.keep_awake_while_gaming),
                "is_online_profile": bool(profile.is_online_profile),
                "cpu_partition_policy": str(profile.cpu_partition_policy),
                "background_steer_images": list(profile.background_steer_images),
            }
        )
    return manifest


def get_profile_partition(profile_id: str | None) -> tuple[str, tuple[str, ...]]:
    """Resolve a profile's session core-partitioning declaration.

    Returns ``(cpu_partition_policy, background_steer_images)``; unknown or
    missing profile ids resolve to ``("off", ())`` so callers no-op safely.
    Used by the cpu-balance governor to decide game-side steering and the
    background steer list for the session.
    """
    canonical = resolve_profile_id(profile_id)
    if not canonical:
        return "off", ()
    entry = _get_full_catalog().get(canonical)
    if entry is None:
        return "off", ()
    profile = entry.profile_class()
    return str(profile.cpu_partition_policy), tuple(profile.background_steer_images)


def get_profile_aliases() -> dict[str, str]:
    """Return retired-id -> canonical-id aliases for tray/GUI normalization."""
    return dict(PROFILE_ALIASES)
