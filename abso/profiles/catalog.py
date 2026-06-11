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
from abso.profiles.deadlock import (
    DeadlockGSyncHDRProfile,
    DeadlockGSyncProfile,
    DeadlockHDRProfile,
    DeadlockProfile,
)
from abso.profiles.diablo4 import Diablo4Profile, Diablo4SDRProfile
from abso.profiles.fortnite import FortniteHDRProfile, FortniteProfile
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
    Rivals2GSyncHDRProfile,
    Rivals2GSyncProfile,
    Rivals2OnlineGSyncHDRProfile,
    Rivals2OnlineGSyncProfile,
)
from abso.profiles.rivals2_offline import Rivals2OfflineHDRProfile, Rivals2OfflineProfile
from abso.profiles.rivals2_online import Rivals2OnlineHDRProfile, Rivals2OnlineProfile
from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile
from abso.profiles.slippi_melee import (
    SlippiMeleeConsoleParityHDRProfile,
    SlippiMeleeConsoleParityProfile,
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
    "productivity": TrayProfileUi(
        "productivity", "Desktop / Productivity", "SDR", 10
    ),
    "productivity-hdr": TrayProfileUi(
        "productivity", "Desktop / Productivity", "HDR", 20
    ),
    "rivals2-online": TrayProfileUi(
        "rivals2", "Rivals 2", "Online No Sync (SDR)", 100
    ),
    "rivals2-online-hdr": TrayProfileUi(
        "rivals2", "Rivals 2", "Online No Sync (HDR)", 110
    ),
    "rivals2-online-gsync": TrayProfileUi(
        "rivals2", "Rivals 2", "Online G-SYNC (SDR)", 120
    ),
    "rivals2-online-gsync-hdr": TrayProfileUi(
        "rivals2", "Rivals 2", "Online G-SYNC (HDR)", 130
    ),
    "rivals2-offline": TrayProfileUi(
        "rivals2", "Rivals 2", "Offline No Sync (SDR)", 140
    ),
    "rivals2-offline-hdr": TrayProfileUi(
        "rivals2", "Rivals 2", "Offline No Sync (HDR)", 150
    ),
    "rivals2-gsync": TrayProfileUi(
        "rivals2", "Rivals 2", "Offline G-SYNC (SDR)", 160
    ),
    "rivals2-gsync-hdr": TrayProfileUi(
        "rivals2", "Rivals 2", "Offline G-SYNC (HDR)", 170
    ),
    "slippi-melee": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Competitive No Sync (SDR)", 200
    ),
    "slippi-melee-hdr": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Competitive No Sync (HDR)", 210
    ),
    "slippi-melee-console-parity": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Console-Parity 60 Hz (SDR)", 220
    ),
    "slippi-melee-console-parity-hdr": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Console-Parity 60 Hz (HDR)", 230
    ),
    "slippi-melee-universal": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Universal No Sync (SDR)", 240
    ),
    "slippi-melee-universal-hdr": TrayProfileUi(
        "slippi-melee", "Super Smash Bros. Melee (Slippi)", "Universal No Sync (HDR)", 250
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
    "marvel-rivals-sdr": TrayProfileUi(
        "marvel-rivals", "Marvel Rivals", "G-SYNC (SDR)", 300
    ),
    "marvel-rivals-hdr": TrayProfileUi(
        "marvel-rivals", "Marvel Rivals", "G-SYNC (HDR)", 310
    ),
    "overwatch2": TrayProfileUi("overwatch2", "Overwatch 2", "No Sync (SDR)", 400),
    "overwatch2-hdr": TrayProfileUi("overwatch2", "Overwatch 2", "No Sync (HDR)", 410),
    "overwatch2-gsync": TrayProfileUi("overwatch2", "Overwatch 2", "G-SYNC (SDR)", 420),
    "overwatch2-gsync-hdr": TrayProfileUi("overwatch2", "Overwatch 2", "G-SYNC (HDR)", 430),
    "overwatch2-gsync-capture": TrayProfileUi(
        "overwatch2", "Overwatch 2", "Capture-Safe G-SYNC (SDR)", 440
    ),
    "overwatch2-gsync-hdr-capture": TrayProfileUi(
        "overwatch2", "Overwatch 2", "Capture-Safe G-SYNC (HDR)", 450
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
        "rivals2-offline": ProfileCatalogEntry(
            profile_class=Rivals2OfflineProfile,
            tray_category="Fighting",
            tray_subtitle="No Sync SDR | LLM ON | Uncapped | Offline Only",
            tray_description=(
                "Offline/training Rivals 2 no-sync SDR profile. VSync and VRR off, "
                "uncapped engine path, exclusive fullscreen."
            ),
            sync_mode="off",
        ),
        "rivals2-offline-hdr": ProfileCatalogEntry(
            profile_class=Rivals2OfflineHDRProfile,
            tray_category="Fighting",
            tray_subtitle="No Sync HDR | LLM ON | Uncapped | Offline Only",
            tray_description=(
                "Offline/training Rivals 2 no-sync profile with Windows HDR composition. "
                "Rivals 2 currently advertises no native HDR support, so the game stays SDR "
                "inside the HDR desktop."
            ),
            sync_mode="off",
        ),
        "rivals2-online": ProfileCatalogEntry(
            profile_class=Rivals2OnlineProfile,
            tray_category="Fighting",
            tray_subtitle="No Sync SDR | LLM ON | Rollback-Safe",
            tray_description=(
                "Rollback-safe Rivals 2 online SDR profile. VSync and VRR off, LLM On "
                "(not Ultra), external frame caps disabled."
            ),
            sync_mode="off",
        ),
        "rivals2-online-hdr": ProfileCatalogEntry(
            profile_class=Rivals2OnlineHDRProfile,
            tray_category="Fighting",
            tray_subtitle="No Sync HDR | LLM ON | Rollback-Safe",
            tray_description=(
                "Rollback-safe Rivals 2 online profile with Windows HDR composition. "
                "Same no-sync timing contract as SDR; native game HDR remains off."
            ),
            sync_mode="off",
        ),
        "rivals2-gsync": ProfileCatalogEntry(
            profile_class=Rivals2GSyncProfile,
            tray_category="Fighting",
            tray_subtitle="Strict SDR G-SYNC | LLM ON | VSync Safety Net | Offline Only",
            tray_description=(
                "Offline/training Rivals 2 strict fullscreen-only G-SYNC SDR profile. "
                "Uses refresh - 3 FPS caps and disables UE5 driver threaded optimization."
            ),
            sync_mode="on",
        ),
        "rivals2-gsync-hdr": ProfileCatalogEntry(
            profile_class=Rivals2GSyncHDRProfile,
            tray_category="Fighting",
            tray_subtitle="Strict HDR G-SYNC | LLM ON | VSync Safety Net | Offline Only",
            tray_description=(
                "Offline/training Rivals 2 strict G-SYNC profile with Windows HDR composition. "
                "Rivals 2 currently advertises no native HDR support, so it stays SDR inside "
                "the HDR desktop."
            ),
            sync_mode="on",
        ),
        "rivals2-online-gsync": ProfileCatalogEntry(
            profile_class=Rivals2OnlineGSyncProfile,
            tray_category="Fighting",
            tray_subtitle="Strict SDR G-SYNC | LLM ON | Rollback-Safe",
            tray_description=(
                "Rollback-safe Rivals 2 online strict fullscreen-only G-SYNC SDR profile. "
                "Threaded optimization off for UE5 rollback stability."
            ),
            sync_mode="on",
        ),
        "rivals2-online-gsync-hdr": ProfileCatalogEntry(
            profile_class=Rivals2OnlineGSyncHDRProfile,
            tray_category="Fighting",
            tray_subtitle="Strict HDR G-SYNC | LLM ON | Rollback-Safe",
            tray_description=(
                "Rollback-safe Rivals 2 online strict G-SYNC profile with Windows HDR composition. "
                "Same VRR stability contract as SDR; Rivals 2 currently advertises no native "
                "HDR support, so native game HDR remains off."
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
        "overwatch2": ProfileCatalogEntry(
            profile_class=Overwatch2Profile,
            tray_category="Shooters",
            tray_subtitle="No Sync SDR | Reflex OFF | VSync OFF | G-SYNC OFF",
            sync_mode="off",
        ),
        "overwatch2-hdr": ProfileCatalogEntry(
            profile_class=Overwatch2NoSyncHDRProfile,
            tray_category="Shooters",
            tray_subtitle="No Sync HDR | Reflex OFF | VSync OFF | G-SYNC OFF",
            tray_description=(
                "Minimum-latency no-sync Overwatch 2 with native HDR for "
                "OLED / Mini-LED. Same sync/VRR contract as the SDR variant."
            ),
            sync_mode="off",
        ),
        "overwatch2-gsync": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncProfile,
            tray_category="Shooters",
            tray_subtitle="Overlay-Free SDR Borderless | Reflex (set in-game) | G-SYNC ON",
            tray_description=(
                "Low-latency Overwatch 2 G-SYNC on the same optimized borderless VRR "
                "path as capture-safe, while stopping capture and overlay processes."
            ),
            sync_mode="on",
        ),
        "overwatch2-gsync-hdr": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncHDRProfile,
            tray_category="Shooters",
            tray_subtitle="Overlay-Free HDR Borderless | Reflex (set in-game) | G-SYNC ON",
            tray_description=(
                "Low-latency native-HDR Overwatch 2 G-SYNC on the optimized borderless "
                "VRR path, while stopping capture and overlay processes."
            ),
            sync_mode="on",
        ),
        "overwatch2-gsync-capture": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncCaptureProfile,
            tray_category="Shooters",
            tray_subtitle="SDR Capture-Safe | Borderless VRR | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Same borderless G-SYNC path as the overlay-free lane, but keeps "
                "OBS, Medal, RTSS, and overlay apps running at launch instead of "
                "stopping them."
            ),
            sync_mode="on",
        ),
        "overwatch2-gsync-hdr-capture": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncHDRCaptureProfile,
            tray_category="Shooters",
            tray_subtitle="HDR Capture-Safe | Borderless VRR | Keeps OBS/Medal/Overlays",
            tray_description=(
                "Same borderless HDR G-SYNC path as the overlay-free lane, but keeps "
                "OBS, Medal, RTSS, and overlay apps running at launch instead of "
                "stopping them."
            ),
            sync_mode="on",
        ),
        "pokemon-auto-chess": ProfileCatalogEntry(
            profile_class=PokemonAutoChessProfile,
            tray_category="Other",
            tray_subtitle="LLM ON | Browser WebGL",
            sync_mode="agnostic",
        ),
        "pacdeluxe": ProfileCatalogEntry(
            profile_class=PACDeluxeProfile,
            tray_category="Other",
            tray_subtitle="LLM ON | Tauri + WebView2 | Adaptive VSync",
            sync_mode="agnostic",
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
    # Retired generic/no-value Rivals variants map to the evidence-backed
    # offline no-sync lane instead of lingering as separate menu clutter.
    "rivals2": "rivals2-offline",
    "rivals2-300hz-max": "rivals2-offline",
    "rivals2-tournament-sim-144hz": "rivals2-offline",
    # Streaming variants consolidated into their base profiles.
    "fortnite-streaming": "fortnite",
    "fortnite-streaming-hdr": "fortnite-hdr",
    "overwatch2-gsync-streaming": "overwatch2-gsync",
    "overwatch2-gsync-hdr-streaming": "overwatch2-gsync-hdr",
    "pacdeluxe-streaming": "pacdeluxe",
    "ryujinx-ssbu-streaming": "ryujinx-ssbu",
    "rivals2-streaming": "rivals2-online",
    "rivals2-streaming-hdr": "rivals2-online-hdr",
    "slippi-melee-streaming": "slippi-melee",
    # Experimental/duplicate Slippi variants.
    "slippi-melee-vrr-lab": "slippi-melee",
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
        tray_group = (
            entry.tray_group
            or (built_in_ui.group if built_in_ui else None)
            or profile_id
        )
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
                "launch_process_killset": profile.launch_process_killset().to_dict(),
                "requires_overlay_free_path": bool(
                    profile.display_path_requirements.require_overlay_free_path
                ),
                "keep_awake_while_gaming": bool(profile.keep_awake_while_gaming),
                "is_online_profile": bool(profile.is_online_profile),
            }
        )
    return manifest


def get_profile_aliases() -> dict[str, str]:
    """Return retired-id -> canonical-id aliases for tray/GUI normalization."""
    return dict(PROFILE_ALIASES)
