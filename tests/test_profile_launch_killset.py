"""Profile-level launch killset resolution tests.

These cover the BaseProfile.launch_process_killset() derivation across the
catalog so the launch sanitizer behaves predictably for every profile family
without requiring per-profile override boilerplate.
"""

from __future__ import annotations

import pytest

from abso.core.process_janitor import (
    ALWAYS_SAFE_LAUNCH_KILLSET,
    OPT_IN_LAUNCH_KILLSET,
    LaunchKillset,
)
from abso.profiles.catalog import get_profile_instances


@pytest.fixture(scope="module")
def profiles_by_id() -> dict[str, object]:
    return get_profile_instances()


def test_every_profile_returns_a_launch_killset(profiles_by_id) -> None:
    assert len(profiles_by_id) > 0
    for profile_id, profile in profiles_by_id.items():
        killset = profile.launch_process_killset()
        assert isinstance(killset, LaunchKillset), profile_id


def test_productivity_profile_has_empty_killset(profiles_by_id) -> None:
    """The user is working in those apps - don't kill their overlays."""
    productivity = profiles_by_id.get("productivity")
    assert productivity is not None

    killset = productivity.launch_process_killset()
    assert killset.always_safe == ()
    assert killset.opt_in == ()
    assert killset.resolve() == []
    assert killset.resolve(include_opt_in=True) == []


@pytest.mark.parametrize(
    "profile_id",
    [
        # Overwatch 2 strict G-SYNC lanes
        "overwatch2-gsync",
        "overwatch2-gsync-hdr",
        # Deadlock strict G-SYNC lanes
        "deadlock-gsync",
        "deadlock-gsync-hdr",
        # Rivals 2 G-SYNC lanes (offline + online, both fullscreen-only VRR)
        "rivals2-gsync",
        "rivals2-online-gsync",
        # Diablo 4 (Reflex + fullscreen-only G-SYNC by default)
        "diablo4",
        "diablo4-sdr",
        # Marvel Rivals (Reflex + fullscreen-only G-SYNC)
        "marvel-rivals-sdr",
        "marvel-rivals-hdr",
    ],
)
def test_strict_overlay_free_profiles_get_full_killset(profile_id, profiles_by_id) -> None:
    """Strict fullscreen-only VRR profiles get always-safe + opt-in tiers.

    This is auto-derived from ``uses_fullscreen_only_vrr_path``, so adding a
    new strict fullscreen G-SYNC profile to the catalog will pick this
    contract up automatically.
    """
    profile = profiles_by_id[profile_id]
    killset = profile.launch_process_killset()

    assert killset.always_safe == tuple(ALWAYS_SAFE_LAUNCH_KILLSET)
    assert killset.opt_in == tuple(OPT_IN_LAUNCH_KILLSET)


@pytest.mark.parametrize(
    "profile_id",
    [
        # No-sync / minimum-latency lanes (no fullscreen-only VRR contract)
        "overwatch2",
        "overwatch2-hdr",
        "deadlock",
        "deadlock-hdr",
        "fortnite",
        "fortnite-hdr",
        # Emulators
        "slippi-melee",
        "slippi-melee-universal",
        "ryujinx-ssbu",
        # Rivals 2 no-sync lanes
        "rivals2-offline",
        "rivals2-online",
    ],
)
def test_balanced_profiles_get_always_safe_but_not_opt_in(profile_id, profiles_by_id) -> None:
    """Non-strict gaming profiles still get overlay sweep, but not sync/RGB tier."""
    profile = profiles_by_id[profile_id]
    killset = profile.launch_process_killset()

    assert killset.always_safe == tuple(ALWAYS_SAFE_LAUNCH_KILLSET)
    assert killset.opt_in == ()


@pytest.mark.parametrize(
    "profile_id",
    [
        "overwatch2-gsync-capture",
        "overwatch2-gsync-hdr-capture",
    ],
)
def test_capture_safe_profiles_get_balanced_tier(profile_id, profiles_by_id) -> None:
    """Capture-safe variants intentionally do NOT request overlay-free path so
    Medal/OBS can keep running. Killset stays at balanced tier (overlays only,
    no opt-in)."""
    profile = profiles_by_id[profile_id]
    killset = profile.launch_process_killset()

    # The capture profile is "balanced" - it still surfaces the always-safe
    # killset so the tray sanitizer has a list to operate on, but it cannot
    # auto-kill the user's capture stack. Capture stays alive because the
    # tray surface only invokes sweeps when the strict-overlay-free contract
    # demands it OR when the user explicitly opts in via aggressiveProcessJanitor.
    # The killset itself just describes "what would be safe to kill", not
    # "what will be killed". The decision lives in the tray's tick logic.
    assert killset.always_safe == tuple(ALWAYS_SAFE_LAUNCH_KILLSET)
    assert killset.opt_in == ()


def test_pokemon_auto_chess_browser_profile_gets_balanced_killset(profiles_by_id) -> None:
    """Browser-game profiles still benefit from killing GameBar/RTSS noise."""
    pac = profiles_by_id["pokemon-auto-chess"]
    killset = pac.launch_process_killset()

    assert killset.always_safe == tuple(ALWAYS_SAFE_LAUNCH_KILLSET)
    assert killset.opt_in == ()


def test_killset_to_dict_serializes_for_catalog_manifest() -> None:
    """The manifest JSON consumed by the tray must round-trip through to_dict."""
    sample = LaunchKillset(always_safe=("a.exe",), opt_in=("b.exe",))

    data = sample.to_dict()
    assert data == {"always_safe": ["a.exe"], "opt_in": ["b.exe"]}


def test_profile_manifest_includes_launch_process_killset() -> None:
    """`python -m abso profiles --json` must expose the killset for the tray."""
    from abso.profiles.catalog import get_profile_manifest

    manifest = get_profile_manifest()
    assert len(manifest) > 0

    for entry in manifest:
        assert "launch_process_killset" in entry, entry["id"]
        assert "requires_overlay_free_path" in entry, entry["id"]
        killset = entry["launch_process_killset"]
        assert "always_safe" in killset, entry["id"]
        assert "opt_in" in killset, entry["id"]


def test_strict_profiles_advertise_overlay_free_path_in_manifest() -> None:
    """Tray uses requires_overlay_free_path to color the menu entry."""
    from abso.profiles.catalog import get_profile_manifest

    manifest = {entry["id"]: entry for entry in get_profile_manifest()}
    strict_ids = {
        "overwatch2-gsync",
        "overwatch2-gsync-hdr",
        "deadlock-gsync",
        "deadlock-gsync-hdr",
    }
    for pid in strict_ids:
        assert manifest[pid]["requires_overlay_free_path"] is True, pid
