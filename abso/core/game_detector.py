"""Game installation detection module."""

from __future__ import annotations

import json
import logging
import os
import re
import winreg
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
        "Rivals of Aether 2": ["RivalsOfAether2.exe", "RivalsOfAether2-Win64-Shipping.exe"],
        "Marvel Rivals": ["Marvel.exe", "Marvel-Win64-Shipping.exe"],
        "Counter-Strike 2": ["cs2.exe"],
        "Diablo IV": ["Diablo IV.exe"],
        "Slippi Launcher": ["Slippi Dolphin.exe", "Dolphin.exe"],
    },
    "epic_paths": [
        "%PROGRAMFILES%\\Epic Games",
        "%PROGRAMFILES(X86)%\\Epic Games",
        "D:\\Epic Games",
        "E:\\Epic Games",
    ],
    "epic_game_patterns": {
        "Rivals of Aether 2": ["RivalsOfAether2.exe", "RivalsOfAether2-Win64-Shipping.exe"],
        "Fortnite": [
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe",
        ],
    },
    "battle_net_games": {
        "Diablo IV": {
            "registry_key": r"SOFTWARE\WOW6432Node\Blizzard Entertainment\Diablo IV",
            "executables": ["Diablo IV.exe"],
        },
        "Overwatch 2": {
            "registry_key": r"SOFTWARE\WOW6432Node\Blizzard Entertainment\Overwatch",
            "executables": ["Overwatch.exe"],
        },
        "Call of Duty": {
            "registry_key": r"SOFTWARE\WOW6432Node\Activision\Call of Duty",
            "executables": ["cod.exe", "ModernWarfare.exe"],
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
                if not executable_match and not display_match:
                    continue

                # Prefer launcher-provided executable when it matches known patterns.
                chosen_exe = launch_name if executable_match else executables[0]
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

        for game_name, executables in steam_game_patterns.items():
            # Look for game folders that might contain these executables
            for game_folder in game_folders:
                if not game_folder.is_dir():
                    continue

                for exe_name in executables:
                    # Search for executable in game folder (up to 3 levels deep)
                    try:
                        matches = list(game_folder.rglob(exe_name))
                    except OSError as e:
                        logger.debug(f"Failed to scan '{game_folder}' for '{exe_name}': {e}")
                        continue

                    for exe_path in matches:
                        if exe_path.is_file():
                            games.append(InstalledGame(
                                name=game_name,
                                executable=exe_name,
                                install_path=game_folder,
                                platform="steam",
                            ))
                            break
                    else:
                        continue
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

            for game_name, executables in epic_game_patterns.items():
                for exe_name in executables:
                    try:
                        matches = list(game_folder.rglob(exe_name))
                    except OSError as e:
                        logger.debug(f"Failed to scan '{game_folder}' for '{exe_name}': {e}")
                        continue

                    for exe_path in matches:
                        if exe_path.is_file():
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
            for exe_name in executables:
                try:
                    matches = list(slippi_path.rglob(exe_name))
                except OSError as e:
                    logger.debug(f"Failed to scan standalone path '{slippi_path}' for '{exe_name}': {e}")
                    continue

                for exe_path in matches:
                    if exe_path.is_file():
                        games.append(InstalledGame(
                            name="Slippi Melee",
                            executable=exe_name,
                            install_path=slippi_path,
                            platform="standalone",
                        ))
                        break

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
