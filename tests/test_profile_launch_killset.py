"""Profile-level launch killset resolution tests.

These cover the BaseProfile.launch_process_killset() derivation across the
catalog so the launch sanitizer behaves predictably for every profile family
without requiring per-profile override boilerplate.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from abso.core.process_janitor import (
    ALWAYS_SAFE_LAUNCH_KILLSET,
    OPT_IN_LAUNCH_KILLSET,
    LaunchKillset,
)
from abso.profiles.catalog import get_profile_instances


@pytest.fixture(autouse=True)
def _no_user_process_overrides():
    """Suppress per-machine YAML overrides so tests are deterministic.

    ``BaseProfile.launch_process_killset()`` and ``ProcessJanitor.__init__``
    both consult the user's ``abso.yaml::process_overrides`` block. On a
    developer machine that block can append kill targets and add protect
    entries, which would inflate ``always_safe`` and confuse equality
    checks. Patching the loader to an empty pair pins the test to the
    built-in defaults.
    """
    with patch(
        "abso.core.process_janitor._load_user_process_overrides",
        return_value=(frozenset(), ()),
    ):
        yield


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
        # Rivals 2 G-SYNC lanes (merged rollback-safe, fullscreen-only VRR)
        "rivals2-gsync",
        "rivals2-gsync-hdr",
        # Diablo 4 (Reflex + fullscreen-only G-SYNC by default)
        "diablo4",
        "diablo4-sdr",
        # Marvel Rivals (Reflex + fullscreen-only G-SYNC)
        "marvel-rivals-sdr",
        "marvel-rivals-hdr",
    ],
)
def test_strict_overlay_free_profiles_get_full_killset(profile_id, profiles_by_id) -> None:
    """Strict overlay-free gaming profiles get always-safe + opt-in tiers.

    Fullscreen-only VRR profiles get this from their display path; the OW2
    overlay-free borderless lanes opt in with an explicit profile contract.
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
        "rivals2-nosync",
        "rivals2-nosync-hdr",
    ],
)
def test_non_strict_gaming_profiles_now_get_full_killset(profile_id, profiles_by_id) -> None:
    """Every non-productivity gaming profile gets both tiers by default.

    Previously the opt-in tier was strict-G-SYNC-only. After the May 2026
    aggressive-sweep change, ABSO promotes overlay-free behavior on every
    gaming profile so cloud sync, NVIDIA Experience, and OEM RGB daemons
    cannot eat frame-time mid-session.
    """
    profile = profiles_by_id[profile_id]
    killset = profile.launch_process_killset()

    assert killset.always_safe == tuple(ALWAYS_SAFE_LAUNCH_KILLSET)
    assert killset.opt_in == tuple(OPT_IN_LAUNCH_KILLSET)


@pytest.mark.parametrize(
    "profile_id",
    [
        "overwatch2-gsync-capture",
        "overwatch2-gsync-hdr-capture",
        "rivals2-gsync-hdr-capture",
    ],
)
def test_capture_safe_profiles_get_filtered_killset(profile_id, profiles_by_id) -> None:
    """Capture-safe profiles filter the capture/overlay/peripheral stack out.

    Updated 2026-05-21: previously the killset was full and the tray's
    tick logic was the only thing keeping overlays alive. That was
    hypocritical - launch-sweep killed Medal/Discord overlay/OBS at
    game-detect anyway. The is_capture_safe trait now filters
    CAPTURE_ALLOWED_IMAGES out of the killset entirely so the capture
    promise is honored at the data layer, not just the policy layer.

    Non-capture entries (LLM runtimes, cloud sync, VPN, non-Discord chat,
    audio enhancements, crash reporters) still die because they are not
    capture-related.
    """
    from abso.core.process_janitor import CAPTURE_ALLOWED_IMAGES

    profile = profiles_by_id[profile_id]
    killset = profile.launch_process_killset()

    expected_always_safe = tuple(
        img for img in ALWAYS_SAFE_LAUNCH_KILLSET
        if img.lower() not in CAPTURE_ALLOWED_IMAGES
    )
    expected_opt_in = tuple(
        img for img in OPT_IN_LAUNCH_KILLSET
        if img.lower() not in CAPTURE_ALLOWED_IMAGES
    )
    assert killset.always_safe == expected_always_safe
    assert killset.opt_in == expected_opt_in

    # Sanity: at least one canonical capture image was actually filtered.
    all_killset_lower = {img.lower() for img in killset.always_safe + killset.opt_in}
    assert "medal.exe" not in all_killset_lower
    assert "discordhookhelper64.exe" not in all_killset_lower
    assert "rtss.exe" not in all_killset_lower


def test_pokemon_auto_chess_browser_profile_gets_full_killset(profiles_by_id) -> None:
    """Browser-game profiles still benefit from killing GameBar/RTSS noise and OEM RGB."""
    pac = profiles_by_id["pokemon-auto-chess"]
    killset = pac.launch_process_killset()

    assert killset.always_safe == tuple(ALWAYS_SAFE_LAUNCH_KILLSET)
    assert killset.opt_in == tuple(OPT_IN_LAUNCH_KILLSET)


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
        "rivals2-gsync",
        "rivals2-gsync-hdr",
    }
    for pid in strict_ids:
        assert manifest[pid]["requires_overlay_free_path"] is True, pid


# ---------------------------------------------------------------------------
# Aggressive-sweep coverage: confirm the May 2026 expansion landed and stays.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "image",
    [
        # LLM runtimes the user explicitly called out
        "ollama.exe",
        "ollama app.exe",  # Windows tray icon (with space) - distinct from CLI
        "ollama_runner.exe",
        "lmstudio.exe",
        "LM Studio.exe",
        "GPT4All.exe",
        "Jan.exe",
        "AnythingLLM.exe",
        # Cloud sync (moved up from opt-in)
        "OneDrive.exe",
        "Dropbox.exe",
        "GoogleDriveFS.exe",
        # Peripheral daemons. Declared killable by default for the frame-time
        # win; machines whose peripherals rely on G HUB *software* profiles
        # (rather than onboard memory) protect them via abso.yaml
        # process_overrides.protect - see the protect-filter tests below.
        "lghub.exe",
        "lghub_agent.exe",
        "iCUE.exe",
        "LCore.exe",
        # VPN UI/CLI/tray (user explicitly called out Tailscale). Route-holding
        # daemons live in OPT_IN to avoid kill-switch traffic blackholes.
        "tailscale-ipn.exe",
        "tailscale.exe",
        "openvpn-gui.exe",
        "NordVPN.exe",
        "ExpressVPN.exe",
        "ProtonVPN.exe",
        # Chat clients other than Discord
        "slack.exe",
        "Teams.exe",
        "ms-teams.exe",
        "Zoom.exe",
        "Signal.exe",
        "Telegram.exe",
        "WhatsApp.exe",
    ],
)
def test_aggressive_targets_are_in_always_safe(image: str) -> None:
    """User explicitly requested these die at game time on every Reflex profile."""
    images_lower = {name.lower() for name in ALWAYS_SAFE_LAUNCH_KILLSET}
    assert image.lower() in images_lower, f"{image} should be in ALWAYS_SAFE_LAUNCH_KILLSET"


@pytest.mark.parametrize(
    "image",
    [
        # Code editors / agentic work
        "Code.exe",
        "Code-Insiders.exe",
        "Cursor.exe",
        "Windsurf.exe",
        "idea64.exe",
        "pycharm64.exe",
        "webstorm64.exe",
        "devenv.exe",
        # Terminals
        "WindowsTerminal.exe",
        "wezterm-gui.exe",
        "alacritty.exe",
        # WSL / Docker
        "wsl.exe",
        "Docker Desktop.exe",
        # Discord (teammate comms - Discord.exe itself, not the overlay helpers)
        "Discord.exe",
        "DiscordPTB.exe",
        "DiscordCanary.exe",
        # Dev tooling
        "claude.exe",
        "codex.exe",
        "git.exe",
        "gh.exe",
        # Game / emulator launchers
        "Slippi Launcher.exe",
        "Slippi Dolphin.exe",
        "Ryujinx.exe",
    ],
)
def test_protected_processes_are_never_killable(image: str) -> None:
    """Agentic / interactive workflows must never be killed regardless of profile."""
    from abso.core.process_janitor import NEVER_KILL_IMAGES

    assert image.lower() in NEVER_KILL_IMAGES, (
        f"{image} should be in NEVER_KILL_IMAGES to protect interactive work"
    )


@pytest.mark.parametrize(
    "image",
    [
        "tailscaled.exe",
        "ZeroTier One.exe",
        "wireguard.exe",
        "openvpn.exe",
        "nordvpn-service.exe",
        "ProtonVPNService.exe",
        "mullvad-daemon.exe",
    ],
)
def test_vpn_daemons_are_opt_in_not_always_safe(image: str) -> None:
    """Route-holding VPN daemons must not be killed by default.

    Force-killing them on a kill-switch VPN can blackhole all traffic and take
    an online game offline, so they belong in the opt-in tier (strict profiles
    include them explicitly) rather than always-safe.
    """
    always = {name.lower() for name in ALWAYS_SAFE_LAUNCH_KILLSET}
    opt_in = {name.lower() for name in OPT_IN_LAUNCH_KILLSET}
    assert image.lower() in opt_in, f"{image} should be opt-in (kill-switch safety)"
    assert image.lower() not in always, f"{image} must NOT be always-safe"


def test_janitor_refuses_to_kill_vscode_even_when_listed() -> None:
    """A misconfigured profile cannot interrupt an open VS Code session."""
    from abso.core.process_janitor import ProcessJanitor

    janitor = ProcessJanitor()
    result = janitor.sweep(["Code.exe"], dry_run=True)

    assert result.stopped == []
    assert "Code.exe" not in result.not_running
    assert any("protected image" in w for w in result.warnings)


def test_janitor_refuses_to_kill_discord_even_when_listed() -> None:
    """Discord teammate comms must survive even an explicit kill request."""
    from abso.core.process_janitor import ProcessJanitor

    janitor = ProcessJanitor()
    result = janitor.sweep(["Discord.exe"], dry_run=True)

    assert result.stopped == []
    assert any("protected image" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Per-machine YAML override mechanism (process_overrides.protect / .kill)
# ---------------------------------------------------------------------------

def test_user_protect_override_extends_never_kill() -> None:
    """A user-declared protect entry survives even when passed to the janitor."""
    from abso.core import process_janitor as janitor_module

    with patch.object(
        janitor_module,
        "_load_user_process_overrides",
        return_value=(frozenset({"mycustomeditor.exe"}), ()),
    ):
        janitor = janitor_module.ProcessJanitor()
        result = janitor.sweep(["MyCustomEditor.exe"], dry_run=True)

    assert result.stopped == []
    assert any("protected image" in w for w in result.warnings)


def test_user_protect_override_is_filtered_from_resolved_killset() -> None:
    """A protected image never reaches a sweep caller, in either tier.

    Regression: ``launch_process_killset()`` used to load the protect list
    and throw it away, so the only thing standing between a protected image
    and ``taskkill`` was ``ProcessJanitor``'s own NEVER_KILL check. Anything
    that resolved a killset without going through the janitor -- including
    the read-only ``launch-killset`` payload the tray logs -- reported
    protected images as kill targets.
    """
    from abso.core import process_janitor as janitor_module

    with patch.object(
        janitor_module,
        "_load_user_process_overrides",
        return_value=(frozenset({"lghub.exe", "lghub_agent.exe"}), ()),
    ):
        # Strict lane: lghub* live in the always-safe tier.
        killset = get_profile_instances()["overwatch2-gsync-hdr"].launch_process_killset()

        resolved = {name.lower() for name in killset.resolve()}
        assert "lghub.exe" not in resolved
        assert "lghub_agent.exe" not in resolved
        # Unprotected always-safe entries are untouched.
        assert "onedrive.exe" in resolved

        resolved_opt_in = {name.lower() for name in killset.resolve(include_opt_in=True)}
        assert "lghub.exe" not in resolved_opt_in
        assert "searchindexer.exe" in resolved_opt_in


def test_user_protect_override_filters_the_opt_in_tier_too() -> None:
    """Protect wins over the opt-in tier, not just always-safe."""
    from abso.core import process_janitor as janitor_module

    with patch.object(
        janitor_module,
        "_load_user_process_overrides",
        return_value=(frozenset({"searchindexer.exe"}), ()),
    ):
        killset = get_profile_instances()["overwatch2"].launch_process_killset()

    resolved = {name.lower() for name in killset.resolve(include_opt_in=True)}
    assert "searchindexer.exe" not in resolved
    assert "searchprotocolhost.exe" in resolved


def test_user_protect_override_does_not_change_the_serialized_killset() -> None:
    """The catalog manifest must stay machine-independent.

    ``abso/tray/profile-catalog-cache.json`` is committed and
    ``tests/test_tray_profile_catalog_cache.py`` asserts it equals the live
    manifest. If protect entries pruned the declared tuples, that cache
    would differ on every machine with a protect list and the comparison
    would fail for everyone but its author. Protect is a *resolve-time*
    filter for exactly this reason.
    """
    from abso.core import process_janitor as janitor_module
    from abso.profiles.catalog import get_profile_manifest

    with patch.object(
        janitor_module,
        "_load_user_process_overrides",
        return_value=(frozenset(), ()),
    ):
        baseline = {
            entry["id"]: entry["launch_process_killset"] for entry in get_profile_manifest()
        }

    with patch.object(
        janitor_module,
        "_load_user_process_overrides",
        return_value=(frozenset({"lghub.exe", "lghub_agent.exe"}), ()),
    ):
        with_protect = {
            entry["id"]: entry["launch_process_killset"] for entry in get_profile_manifest()
        }

    assert with_protect == baseline
    assert "lghub.exe" in baseline["overwatch2-gsync-hdr"]["always_safe"]


def test_user_kill_override_appends_to_profile_killset() -> None:
    """A user kill entry is added to every gaming profile's always-safe tier."""
    from abso.core import process_janitor as janitor_module

    with patch.object(
        janitor_module,
        "_load_user_process_overrides",
        return_value=(frozenset(), ("MyPersonalApp.exe",)),
    ):
        profile = get_profile_instances()["overwatch2"]
        killset = profile.launch_process_killset()

    assert "MyPersonalApp.exe" in killset.always_safe


def test_user_kill_override_deduped_against_builtins() -> None:
    """Duplicating a built-in entry in user kill list does not create dupes."""
    from abso.core import process_janitor as janitor_module

    with patch.object(
        janitor_module,
        "_load_user_process_overrides",
        return_value=(frozenset(), ("Ollama.exe",)),
    ):
        profile = get_profile_instances()["overwatch2"]
        killset = profile.launch_process_killset()

    lowered = [name.lower() for name in killset.always_safe]
    assert lowered.count("ollama.exe") == 1


def test_productivity_profile_stays_empty_with_user_kill_overrides() -> None:
    """Productivity stays empty even when user declares kill overrides."""
    from abso.core import process_janitor as janitor_module

    with patch.object(
        janitor_module,
        "_load_user_process_overrides",
        return_value=(frozenset(), ("MyPersonalApp.exe",)),
    ):
        profile = get_profile_instances()["productivity"]
        killset = profile.launch_process_killset()

    assert killset.always_safe == ()
    assert killset.opt_in == ()
