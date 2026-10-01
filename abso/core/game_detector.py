"""Game installation detection module."""

from __future__ import annotations

import json
import logging
import os
import re
import winreg
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from abso.core.manifests import load_game_detection_manifest

logger = logging.getLogger(__name__)


@dataclass
class InstalledGame:
    """Represents a detected installed game."""

    name: str
    executable: str
    install_path: Path
    platform: str  # steam, epic, battle_net, standalone
    profile_match: str | None = None  # Matching profile name if any


DEFAULT_GAME_DETECTION_MANIFEST: dict[str, Any] = {
    "steam_game_patterns": {
        # Executable names verified against real installs; the old
        # "RivalsOfAether2.exe" guesses matched nothing on disk.
        "Rivals 2": ["Rivals2.exe", "Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe"],
        "Marvel Rivals": ["Marvel.exe", "Marvel-Win64-Shipping.exe"],
        "Counter-Strike 2": ["cs2.exe"],
        "Deadlock": ["deadlock.exe", "project8.exe"],
        "Diablo IV": ["Diablo IV.exe"],
        "Slippi Launcher": ["Slippi Dolphin.exe", "Dolphin.exe"],
        # Steam app 252950; never treat its generic launcher as the game.
        "Rocket League": ["RocketLeague.exe"],
    },
    "epic_paths": [
        "%PROGRAMFILES%\\Epic Games",
        "%PROGRAMFILES(X86)%\\Epic Games",
        "D:\\Epic Games",
        "E:\\Epic Games",
    ],
    "epic_game_patterns": {
        "Rocket League": ["RocketLeague.exe"],
        "Rivals 2": ["Rivals2.exe", "Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe"],
        "Fortnite": [
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe",
        ],
    },
    "epic_game_metadata": {
        "Rocket League": {"app_names": ["Sugar"], "display_names": ["RocketLeague"]},
    },
    "battle_net_games": {
        "Diablo IV": {
            "registry_key": r"SOFTWARE\WOW6432Node\Blizzard Entertainment\Diablo IV",
            "uninstall_display_names": ["Diablo IV"],
            "executables": ["Diablo IV.exe"],
        },
        "Overwatch 2": {
            "registry_key": r"SOFTWARE\WOW6432Node\Blizzard Entertainment\Overwatch",
            "uninstall_display_names": ["Overwatch"],
            "executables": ["Overwatch.exe"],
        },
        "Call of Duty": {
            "registry_key": r"SOFTWARE\WOW6432Node\Activision\Call of Duty",
            "uninstall_display_names": ["Call of Duty"],
            "executables": ["cod.exe", "ModernWarfare.exe"],
        },
    },
    # Games registered only in the Windows uninstall registry (installed
    # native apps outside Steam/Epic/Battle.net).
    "uninstall_games": {
        "PACDeluxe": {
            "uninstall_display_names": ["PACDeluxe"],
            "executables": ["pac-deluxe.exe"],
        },
    },
    "standalone_locations": [
        "%APPDATA%\\Slippi Launcher\\netplay",
        "%LOCALAPPDATA%\\SlippiOnline",
        "~\\AppData\\Roaming\\Slippi Launcher",
    ],
    "standalone_executables": ["Slippi Dolphin.exe", "Dolphin.exe"],
}

GAME_DETECTION_MANIFEST = load_game_detection_manifest(
    json.dumps(DEFAULT_GAME_DETECTION_MANIFEST, sort_keys=True)
)


def _resolve_path_template(template: str) -> Path:
    """Resolve manifest path templates using env vars and user home."""
    resolved = template
    for var_name in re.findall(r"%([^%]+)%", template):
        value = os.environ.get(var_name, "")
        resolved = resolved.replace(f"%{var_name}%", value)
    return Path(os.path.expanduser(resolved))


def detect_installed_games() -> list[InstalledGame]:
    """Detect installed games from common platforms.

    Scans:
    - Steam library folders
    - Epic Games installations
    - Battle.net games
    - Common standalone install locations

    Returns:
        List of detected installed games.
    """
    games: list[InstalledGame] = []

    detectors = [
        ("steam", _detect_steam_games),
        ("epic", _detect_epic_games),
        ("battle_net", _detect_battlenet_games),
        ("uninstall", _detect_uninstall_games),
        ("standalone", _detect_standalone_games),
    ]
    for name, detector in detectors:
        try:
            games.extend(detector())
        except Exception as e:
            logger.warning(f"Game detection for '{name}' failed: {e}")

    return games


def _get_steam_library_folders() -> list[Path]:
    """Get all Steam library folders from registry and config."""
    folders: list[Path] = []

    # Try to get Steam install path from registry
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Valve\Steam"
        )
        try:
            steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
            steam_folder = Path(steam_path)
            if steam_folder.exists():
                folders.append(steam_folder / "steamapps" / "common")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass

    # Also check current user registry
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Valve\Steam"
        )
        try:
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            steam_folder = Path(steam_path)
            if steam_folder.exists():
                common_folder = steam_folder / "steamapps" / "common"
                if common_folder not in folders and common_folder.exists():
                    folders.append(common_folder)

                # Parse libraryfolders.vdf for additional library locations
                vdf_path = steam_folder / "steamapps" / "libraryfolders.vdf"
                if vdf_path.exists():
                    additional = _parse_steam_library_folders(vdf_path)
                    for folder in additional:
                        if folder not in folders:
                            folders.append(folder)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass

    return folders


def _parse_steam_library_folders(vdf_path: Path) -> list[Path]:
    """Parse Steam's libraryfolders.vdf to find additional library locations."""
    folders: list[Path] = []

    try:
        content = vdf_path.read_text(encoding="utf-8")

        # Simple VDF parsing - look for "path" entries
        import re
        path_pattern = re.compile(r'"path"\s+"([^"]+)"')

        for match in path_pattern.finditer(content):
            path_str = match.group(1).replace("\\\\", "\\")
            library_path = Path(path_str) / "steamapps" / "common"
            if library_path.exists():
                folders.append(library_path)

    except Exception as e:
        logger.debug(f"Failed to parse Steam library folders: {e}")

    return folders


def _get_epic_manifest_locations() -> list[Path]:
    """Get candidate Epic Games Launcher manifest directories."""
    locations: list[Path] = []

    # Standard launcher manifest location
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    standard = Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    locations.append(standard)

    # Registry-derived launcher data path (if available)
    registry_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Epic Games\EpicGamesLauncher"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Epic Games\EpicGamesLauncher"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Epic Games\EpicGamesLauncher"),
    ]
    for hive, key_path in registry_roots:
        try:
            key = winreg.OpenKey(hive, key_path)
            try:
                app_data_path, _ = winreg.QueryValueEx(key, "AppDataPath")
                base = Path(app_data_path)
                candidates = [
                    base / "Manifests",
                    base / "Data" / "Manifests",
                    base,
                ]
                for candidate in candidates:
                    if candidate not in locations:
                        locations.append(candidate)
            except FileNotFoundError:
                pass
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            continue
        except OSError as e:
            logger.debug(f"Failed to read Epic launcher registry key '{key_path}': {e}")

    return locations


def _append_unique_game(games: list[InstalledGame], candidate: InstalledGame) -> None:
    """Append game only when the same platform/path/executable isn't already present."""
    key = (candidate.platform, str(candidate.install_path).lower(), candidate.executable.lower())
    existing = {
        (g.platform, str(g.install_path).lower(), g.executable.lower())
        for g in games
    }
    if key not in existing:
        games.append(candidate)


def _detect_epic_games_from_manifests(
    epic_game_patterns: dict[str, list[str]],
) -> list[InstalledGame]:
    """Detect Epic installs using launcher manifest metadata."""
    games: list[InstalledGame] = []

    manifest_dirs = _get_epic_manifest_locations()
    metadata = GAME_DETECTION_MANIFEST.get(
        "epic_game_metadata", DEFAULT_GAME_DETECTION_MANIFEST["epic_game_metadata"]
    )
    for manifest_dir in manifest_dirs:
        if not manifest_dir.exists():
            continue

        try:
            manifest_files = list(manifest_dir.glob("*.item"))
        except OSError as e:
            logger.debug(f"Skipping unreadable Epic manifest directory '{manifest_dir}': {e}")
            continue

        for manifest_file in manifest_files:
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.debug(f"Failed to parse Epic manifest '{manifest_file}': {e}")
                continue

            install_location = data.get("InstallLocation")
            launch_executable = data.get("LaunchExecutable", "")
            display_name = data.get("DisplayName", "")
            app_name = data.get("AppName", "")
            if not install_location:
                continue

            install_path = Path(str(install_location))
            if not install_path.exists():
                continue

            launch_name = Path(str(launch_executable)).name if launch_executable else ""
            matched = False
            for game_name, executables in epic_game_patterns.items():
                executable_match = (
                    bool(launch_name)
                    and any(launch_name.lower() == exe.lower() for exe in executables)
                )
                display_match = bool(display_name) and game_name.lower() in str(display_name).lower()
                identity = metadata.get(game_name, {})
                identity_match = (
                    str(app_name).casefold()
                    in {str(name).casefold() for name in identity.get("app_names", [])}
                    or str(display_name).casefold()
                    in {str(name).casefold() for name in identity.get("display_names", [])}
                )
                if not executable_match and not display_match and not identity_match:
                    continue

                # Prefer launcher-provided executable when it matches known patterns.
                chosen_exe = launch_name if executable_match else executables[0]
                if identity and not executable_match:
                    # Sugar launches Launcher.exe, which is shared by unrelated
                    # games. Confirm the real game binary before accepting that
                    # metadata; never expose Launcher.exe for binding/detection.
                    found = _find_game_executables(install_path, executables)
                    chosen_exe = next((exe for exe in executables if exe.lower() in found), "")
                    if not chosen_exe:
                        continue
                _append_unique_game(
                    games,
                    InstalledGame(
                        name=game_name,
                        executable=chosen_exe,
                        install_path=install_path,
                        platform="epic",
                    ),
                )
                matched = True
                break

            # Fallback for known launch executable when display name is unexpected.
            if not matched and launch_name:
                for game_name, executables in epic_game_patterns.items():
                    if any(launch_name.lower() == exe.lower() for exe in executables):
                        _append_unique_game(
                            games,
                            InstalledGame(
                                name=game_name,
                                executable=launch_name,
                                install_path=install_path,
                                platform="epic",
                            ),
                        )
                        break

    return games


def _find_game_executables(
    root: Path, executables: list[str], *, max_depth: int = 3, max_directories: int = 2048
) -> set[str]:
    """Scan an install once, without traversing unbounded trees or junctions.

    Names are case-insensitive, matching Windows. Depth three covers the
    usual UE Game/Binaries/Win64 and Source2 game/bin/win64 layouts.
    This fallback is intentionally bounded; launcher metadata remains preferred.
    """
    remaining = {name.lower() for name in executables}
    found: set[str] = set()
    pending = deque([(root, 0)])
    visited = 0
    while pending and remaining and visited < max_directories:
        folder, depth = pending.popleft()
        visited += 1
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        name = entry.name.lower()
                        if name in remaining and entry.is_file(follow_symlinks=False):
                            found.add(name)
                            remaining.remove(name)
                        elif depth < max_depth and entry.is_dir(follow_symlinks=False):
                            # Junctions are reparse points but not necessarily symlinks.
                            attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
                            if not attrs & 0x400 and len(pending) < max_directories - visited:
                                pending.append((Path(entry.path), depth + 1))
                    except OSError:
                        continue
        except OSError as exc:
            logger.debug("Cannot scan game directory %s: %s", folder, exc)
    return found


def _detect_steam_games() -> list[InstalledGame]:
    """Detect installed Steam games."""
    games: list[InstalledGame] = []

    library_folders = _get_steam_library_folders()

    steam_game_patterns: dict[str, list[str]] = GAME_DETECTION_MANIFEST.get(
        "steam_game_patterns",
        DEFAULT_GAME_DETECTION_MANIFEST["steam_game_patterns"],
    )

    for library_folder in library_folders:
        if not library_folder.exists():
            continue

        try:
            game_folders = list(library_folder.iterdir())
        except OSError as e:
            logger.debug(f"Skipping unreadable Steam library folder '{library_folder}': {e}")
            continue

        wanted = [exe for names in steam_game_patterns.values() for exe in names]
        for game_folder in game_folders:
            if not game_folder.is_dir():
                continue
            found = _find_game_executables(game_folder, wanted)
            for game_name, executables in steam_game_patterns.items():
                for exe_name in executables:
                    if exe_name.lower() in found:
                        games.append(InstalledGame(
                            name=game_name,
                            executable=exe_name,
                            install_path=game_folder,
                            platform="steam",
                        ))
                        break

    return games


def _detect_epic_games() -> list[InstalledGame]:
    """Detect installed Epic Games."""
    games: list[InstalledGame] = []

    path_templates = GAME_DETECTION_MANIFEST.get(
        "epic_paths",
        DEFAULT_GAME_DETECTION_MANIFEST["epic_paths"],
    )
    epic_paths = [_resolve_path_template(path) for path in path_templates]

    epic_game_patterns: dict[str, list[str]] = GAME_DETECTION_MANIFEST.get(
        "epic_game_patterns",
        DEFAULT_GAME_DETECTION_MANIFEST["epic_game_patterns"],
    )

    # Use launcher metadata first (more reliable than fixed drive/path assumptions).
    for game in _detect_epic_games_from_manifests(epic_game_patterns):
        _append_unique_game(games, game)

    for epic_path in epic_paths:
        if not epic_path.exists():
            continue

        try:
            game_folders = list(epic_path.iterdir())
        except OSError as e:
            logger.debug(f"Skipping unreadable Epic path '{epic_path}': {e}")
            continue

        for game_folder in game_folders:
            if not game_folder.is_dir():
                continue

            found = _find_game_executables(
                game_folder, [exe for names in epic_game_patterns.values() for exe in names]
            )
            for game_name, executables in epic_game_patterns.items():
                for exe_name in executables:
                    if exe_name.lower() in found:
                        _append_unique_game(
                            games,
                            InstalledGame(
                                name=game_name,
                                executable=exe_name,
                                install_path=game_folder,
                                platform="epic",
                            ),
                        )
                        break

    return games


_UNINSTALL_REGISTRY_ROOTS: tuple[tuple[int, str], ...] = (
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
)


def _iter_uninstall_entries():
    """Yield (display_name, install_location) from the uninstall registry."""
    for hive, root in _UNINSTALL_REGISTRY_ROOTS:
        try:
            root_key = winreg.OpenKey(hive, root)
        except OSError:
            continue
        try:
            index = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(root_key, index)
                except OSError:
                    break
                index += 1
                try:
                    sub_key = winreg.OpenKey(root_key, sub_name)
                except OSError:
                    continue
                try:
                    try:
                        display, _ = winreg.QueryValueEx(sub_key, "DisplayName")
                    except OSError:
                        continue
                    try:
                        location, _ = winreg.QueryValueEx(sub_key, "InstallLocation")
                    except OSError:
                        location = ""
                    yield str(display), str(location)
                finally:
                    winreg.CloseKey(sub_key)
        finally:
            winreg.CloseKey(root_key)


def _detect_uninstall_registry_games(
    games_config: dict[str, dict[str, Any]],
    already_found: set[str],
    platform: str = "battle_net",
) -> list[InstalledGame]:
    """Find games via the Windows uninstall registry.

    Matches uninstall entries by DisplayName and verifies the configured
    executable exists under InstallLocation. Modern Battle.net installs
    stopped writing legacy per-game keys, and installed native apps
    (e.g. Tauri games) register here too.
    """
    games: list[InstalledGame] = []
    wanted: dict[str, tuple[str, dict[str, Any]]] = {}
    for game_name, config in games_config.items():
        if game_name in already_found:
            continue
        for display in config.get("uninstall_display_names") or []:
            wanted[str(display).strip().lower()] = (game_name, config)
    if not wanted:
        return games

    found: set[str] = set()
    for display, location in _iter_uninstall_entries():
        entry = wanted.get(display.strip().lower())
        if entry is None:
            continue
        game_name, config = entry
        if game_name in found:
            continue
        # Some installers record InstallLocation wrapped in literal quotes.
        location = location.strip().strip('"')
        if not location:
            continue
        game_folder = Path(location)
        if not game_folder.exists():
            continue
        for exe_name in config["executables"]:
            # Root or one level down (Battle.net keeps some exes in
            # subfolders like _retail_); bounded on purpose, no rglob.
            if (game_folder / exe_name).exists() or any(
                candidate.is_file() for candidate in game_folder.glob(f"*/{exe_name}")
            ):
                games.append(InstalledGame(
                    name=game_name,
                    executable=exe_name,
                    install_path=game_folder,
                    platform=platform,
                ))
                found.add(game_name)
                break
    return games


def _detect_uninstall_games() -> list[InstalledGame]:
    """Detect installed native games registered in the uninstall registry."""
    config: dict[str, dict[str, Any]] = GAME_DETECTION_MANIFEST.get(
        "uninstall_games",
        DEFAULT_GAME_DETECTION_MANIFEST["uninstall_games"],
    )
    return _detect_uninstall_registry_games(config, set(), platform="installer")


def _detect_battlenet_games() -> list[InstalledGame]:
    """Detect installed Battle.net games."""
    games: list[InstalledGame] = []

    bnet_games_config: dict[str, dict[str, Any]] = GAME_DETECTION_MANIFEST.get(
        "battle_net_games",
        DEFAULT_GAME_DETECTION_MANIFEST["battle_net_games"],
    )

    for game_name, config in bnet_games_config.items():
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, config["registry_key"])
            try:
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                game_folder = Path(install_path)

                if game_folder.exists():
                    for exe_name in config["executables"]:
                        exe_path = game_folder / exe_name
                        if exe_path.exists():
                            games.append(InstalledGame(
                                name=game_name,
                                executable=exe_name,
                                install_path=game_folder,
                                platform="battle_net",
                            ))
                            break

                        # Also search subdirectories
                        for found_exe in game_folder.rglob(exe_name):
                            if found_exe.is_file():
                                games.append(InstalledGame(
                                    name=game_name,
                                    executable=exe_name,
                                    install_path=game_folder,
                                    platform="battle_net",
                                ))
                                break
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass

    games.extend(
        _detect_uninstall_registry_games(
            bnet_games_config,
            {game.name for game in games},
        )
    )

    return games


def _detect_standalone_games() -> list[InstalledGame]:
    """Detect games installed in common standalone locations."""
    games: list[InstalledGame] = []

    location_templates = GAME_DETECTION_MANIFEST.get(
        "standalone_locations",
        DEFAULT_GAME_DETECTION_MANIFEST["standalone_locations"],
    )
    slippi_locations = [_resolve_path_template(path) for path in location_templates]
    executables = GAME_DETECTION_MANIFEST.get(
        "standalone_executables",
        DEFAULT_GAME_DETECTION_MANIFEST["standalone_executables"],
    )

    for slippi_path in slippi_locations:
        if slippi_path.exists():
            found = _find_game_executables(slippi_path, executables, max_depth=5)
            for exe_name in executables:
                if exe_name.lower() in found:
                    games.append(InstalledGame(
                        name="Slippi Melee",
                        executable=exe_name,
                        install_path=slippi_path,
                        platform="standalone",
                    ))

    return games


def match_games_to_profiles(
    games: list[InstalledGame],
    profiles: dict[str, Any]
) -> list[InstalledGame]:
    """Match detected games to available profiles.

    Args:
        games: List of detected installed games.
        profiles: Dictionary of profile name -> profile instance.

    Returns:
        List of games with profile_match populated.
    """
    for game in games:
        exe_lower = game.executable.lower()

        for profile_name, profile in profiles.items():
            hints = profile.executable_hints
            for hint in hints:
                if hint.lower() == exe_lower:
                    game.profile_match = profile_name
                    break
            if game.profile_match:
                break

    return games


def get_profile_suggestions() -> dict[str, list[InstalledGame]]:
    """Get profile suggestions based on detected installed games.

    Returns:
        Dictionary mapping profile names to lists of matching installed games.
    """
    from abso.profiles import get_all_profiles

    games = detect_installed_games()
    profiles = get_all_profiles()

    matched_games = match_games_to_profiles(games, profiles)

    suggestions: dict[str, list[InstalledGame]] = {}
    for game in matched_games:
        if game.profile_match:
            if game.profile_match not in suggestions:
                suggestions[game.profile_match] = []
            suggestions[game.profile_match].append(game)

    return suggestions
