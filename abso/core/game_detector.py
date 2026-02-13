"""Game installation detection module."""

from __future__ import annotations

import logging
import os
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class InstalledGame:
    """Represents a detected installed game."""

    name: str
    executable: str
    install_path: Path
    platform: str  # steam, epic, battle_net, standalone
    profile_match: str | None = None  # Matching profile name if any


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

    # Detect Steam games
    steam_games = _detect_steam_games()
    games.extend(steam_games)

    # Detect Epic Games
    epic_games = _detect_epic_games()
    games.extend(epic_games)

    # Detect Battle.net games
    bnet_games = _detect_battlenet_games()
    games.extend(bnet_games)

    # Detect common standalone locations
    standalone_games = _detect_standalone_games()
    games.extend(standalone_games)

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


def _detect_steam_games() -> list[InstalledGame]:
    """Detect installed Steam games."""
    games: list[InstalledGame] = []

    library_folders = _get_steam_library_folders()

    # Known Steam game executables to look for
    steam_game_patterns: dict[str, list[str]] = {
        "Rivals of Aether 2": ["RivalsOfAether2.exe", "RivalsOfAether2-Win64-Shipping.exe"],
        "Diablo IV": ["Diablo IV.exe"],
        "Slippi Launcher": ["Slippi Dolphin.exe", "Dolphin.exe"],
    }

    for library_folder in library_folders:
        if not library_folder.exists():
            continue

        for game_name, executables in steam_game_patterns.items():
            # Look for game folders that might contain these executables
            for game_folder in library_folder.iterdir():
                if not game_folder.is_dir():
                    continue

                for exe_name in executables:
                    # Search for executable in game folder (up to 3 levels deep)
                    for exe_path in game_folder.rglob(exe_name):
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

    # Epic Games default install locations
    epic_paths = [
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Epic Games",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Epic Games",
        Path("D:\\Epic Games"),
        Path("E:\\Epic Games"),
    ]

    epic_game_patterns: dict[str, list[str]] = {
        "Rivals of Aether 2": ["RivalsOfAether2.exe", "RivalsOfAether2-Win64-Shipping.exe"],
        "Fortnite": [
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe",
        ],
    }

    for epic_path in epic_paths:
        if not epic_path.exists():
            continue

        for game_folder in epic_path.iterdir():
            if not game_folder.is_dir():
                continue

            for game_name, executables in epic_game_patterns.items():
                for exe_name in executables:
                    for exe_path in game_folder.rglob(exe_name):
                        if exe_path.is_file():
                            games.append(InstalledGame(
                                name=game_name,
                                executable=exe_name,
                                install_path=game_folder,
                                platform="epic",
                            ))
                            break

    return games


def _detect_battlenet_games() -> list[InstalledGame]:
    """Detect installed Battle.net games."""
    games: list[InstalledGame] = []

    # Battle.net game install locations from registry
    bnet_games_config: dict[str, dict[str, Any]] = {
        "Diablo IV": {
            "registry_key": r"SOFTWARE\WOW6432Node\Blizzard Entertainment\Diablo IV",
            "executables": ["Diablo IV.exe"],
        },
        "Call of Duty": {
            "registry_key": r"SOFTWARE\WOW6432Node\Activision\Call of Duty",
            "executables": ["cod.exe", "BlackOps7.exe", "ModernWarfare.exe"],
        },
    }

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

    # Slippi is commonly installed standalone
    slippi_locations = [
        Path(os.environ.get("APPDATA", "")) / "Slippi Launcher" / "netplay",
        Path(os.environ.get("LOCALAPPDATA", "")) / "SlippiOnline",
        Path.home() / "AppData" / "Roaming" / "Slippi Launcher",
    ]

    for slippi_path in slippi_locations:
        if slippi_path.exists():
            for exe_name in ["Slippi Dolphin.exe", "Dolphin.exe"]:
                for exe_path in slippi_path.rglob(exe_name):
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
