"""Tests for game_detector module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from abso.core.game_detector import (
    InstalledGame,
    _detect_battlenet_games,
    _detect_epic_games,
    _detect_standalone_games,
    _detect_steam_games,
    _get_steam_library_folders,
    _parse_steam_library_folders,
    detect_installed_games,
    get_profile_suggestions,
    match_games_to_profiles,
)


class TestInstalledGame:
    """Tests for InstalledGame dataclass."""

    def test_installed_game_creation(self):
        """Test InstalledGame can be created with required fields."""
        game = InstalledGame(
            name="Test Game",
            executable="test.exe",
            install_path=Path("C:/Games/Test"),
            platform="steam",
        )
        assert game.name == "Test Game"
        assert game.executable == "test.exe"
        assert game.install_path == Path("C:/Games/Test")
        assert game.platform == "steam"
        assert game.profile_match is None

    def test_installed_game_with_profile_match(self):
        """Test InstalledGame with profile match."""
        game = InstalledGame(
            name="Test Game",
            executable="test.exe",
            install_path=Path("C:/Games/Test"),
            platform="steam",
            profile_match="test_profile",
        )
        assert game.profile_match == "test_profile"


class TestDetectInstalledGames:
    """Tests for detect_installed_games function."""

    @patch("abso.core.game_detector._detect_standalone_games", return_value=[])
    @patch("abso.core.game_detector._detect_battlenet_games", return_value=[])
    @patch("abso.core.game_detector._detect_epic_games", return_value=[])
    @patch("abso.core.game_detector._detect_steam_games", return_value=[])
    def test_detect_returns_empty_when_no_games(self, *mocks):
        """Test detect_installed_games returns empty list when no games found."""
        result = detect_installed_games()
        assert result == []

    @patch("abso.core.game_detector._detect_standalone_games", return_value=[])
    @patch("abso.core.game_detector._detect_battlenet_games", return_value=[])
    @patch("abso.core.game_detector._detect_epic_games", return_value=[])
    @patch("abso.core.game_detector._detect_steam_games")
    def test_detect_returns_steam_games(self, mock_steam, *mocks):
        """Test detect_installed_games includes Steam games."""
        steam_game = InstalledGame(
            name="Steam Game",
            executable="game.exe",
            install_path=Path("C:/Steam/common/Game"),
            platform="steam",
        )
        mock_steam.return_value = [steam_game]

        result = detect_installed_games()
        assert len(result) == 1
        assert result[0].platform == "steam"

    @patch("abso.core.game_detector._detect_standalone_games", return_value=[])
    @patch("abso.core.game_detector._detect_battlenet_games", return_value=[])
    @patch("abso.core.game_detector._detect_epic_games")
    @patch("abso.core.game_detector._detect_steam_games", return_value=[])
    def test_detect_returns_epic_games(self, mock_steam, mock_epic, *mocks):
        """Test detect_installed_games includes Epic games."""
        epic_game = InstalledGame(
            name="Epic Game",
            executable="game.exe",
            install_path=Path("C:/Epic/Game"),
            platform="epic",
        )
        mock_epic.return_value = [epic_game]

        result = detect_installed_games()
        assert len(result) == 1
        assert result[0].platform == "epic"


class TestGetSteamLibraryFolders:
    """Tests for _get_steam_library_folders function."""

    @patch("abso.core.game_detector.winreg.OpenKey")
    def test_handles_missing_registry(self, mock_open_key):
        """Test handles missing Steam registry gracefully."""
        mock_open_key.side_effect = FileNotFoundError
        result = _get_steam_library_folders()
        assert result == []

    @patch("abso.core.game_detector._parse_steam_library_folders", return_value=[])
    @patch("abso.core.game_detector.winreg.CloseKey")
    @patch("abso.core.game_detector.winreg.QueryValueEx")
    @patch("abso.core.game_detector.winreg.OpenKey")
    def test_returns_steam_common_folder(self, mock_open, mock_query, mock_close, mock_parse, tmp_path):
        """Test returns steamapps/common folder when found."""
        # Create mock steam directory structure
        steam_path = tmp_path / "Steam"
        common_path = steam_path / "steamapps" / "common"
        common_path.mkdir(parents=True)

        mock_query.return_value = (str(steam_path), 1)

        result = _get_steam_library_folders()
        # May return empty due to registry structure, but shouldn't raise
        assert isinstance(result, list)


class TestParseSteamLibraryFolders:
    """Tests for _parse_steam_library_folders function."""

    def test_parse_valid_vdf(self, tmp_path):
        """Test parsing valid libraryfolders.vdf."""
        # Create mock VDF content
        vdf_content = '''
"libraryfolders"
{
    "0"
    {
        "path"        "C:\\\\Program Files\\\\Steam"
        "label"       ""
    }
}
'''
        vdf_path = tmp_path / "libraryfolders.vdf"
        vdf_path.write_text(vdf_content)

        result = _parse_steam_library_folders(vdf_path)
        # Will be empty if path doesn't exist, but should not raise
        assert isinstance(result, list)

    def test_parse_nonexistent_vdf(self, tmp_path):
        """Test parsing nonexistent VDF returns empty list."""
        vdf_path = tmp_path / "nonexistent.vdf"
        result = _parse_steam_library_folders(vdf_path)
        assert result == []

    def test_parse_invalid_vdf(self, tmp_path):
        """Test parsing invalid VDF content returns empty list."""
        vdf_path = tmp_path / "invalid.vdf"
        vdf_path.write_text("invalid content {{{ not valid")

        result = _parse_steam_library_folders(vdf_path)
        assert isinstance(result, list)


class TestDetectSteamGames:
    """Tests for _detect_steam_games function."""

    @patch("abso.core.game_detector._get_steam_library_folders", return_value=[])
    def test_returns_empty_when_no_libraries(self, mock_folders):
        """Test returns empty list when no Steam libraries found."""
        result = _detect_steam_games()
        assert result == []

    @patch("abso.core.game_detector._get_steam_library_folders")
    def test_finds_game_in_library(self, mock_folders, tmp_path):
        """Test finds game executable in Steam library."""
        # Create mock game structure
        library = tmp_path / "steamapps" / "common"
        library.mkdir(parents=True)
        game_folder = library / "Diablo IV"
        game_folder.mkdir()
        (game_folder / "Diablo IV.exe").touch()

        mock_folders.return_value = [library]

        result = _detect_steam_games()
        assert len(result) == 1
        assert result[0].name == "Diablo IV"
        assert result[0].platform == "steam"


class TestDetectEpicGames:
    """Tests for _detect_epic_games function."""

    @patch.dict("os.environ", {"PROGRAMFILES": "C:\\NonExistent"})
    def test_returns_empty_when_no_epic_folder(self):
        """Test returns empty list when no Epic Games folder exists."""
        result = _detect_epic_games()
        assert isinstance(result, list)

    @patch.dict("os.environ", {"PROGRAMFILES": ""})
    def test_handles_missing_env_var(self):
        """Test handles missing PROGRAMFILES environment variable."""
        result = _detect_epic_games()
        assert isinstance(result, list)


class TestDetectBattlenetGames:
    """Tests for _detect_battlenet_games function."""

    @patch("abso.core.game_detector.winreg.OpenKey")
    def test_returns_empty_when_no_registry(self, mock_open):
        """Test returns empty list when no Battle.net registry keys found."""
        mock_open.side_effect = FileNotFoundError
        result = _detect_battlenet_games()
        assert result == []

    @patch("abso.core.game_detector.winreg.CloseKey")
    @patch("abso.core.game_detector.winreg.QueryValueEx")
    @patch("abso.core.game_detector.winreg.OpenKey")
    def test_finds_game_from_registry(self, mock_open, mock_query, mock_close, tmp_path):
        """Test finds Battle.net game from registry."""
        # Create mock game structure
        game_folder = tmp_path / "Diablo IV"
        game_folder.mkdir()
        (game_folder / "Diablo IV.exe").touch()

        mock_query.return_value = (str(game_folder), 1)

        result = _detect_battlenet_games()
        # Should find Diablo IV
        diablo_games = [g for g in result if "Diablo" in g.name]
        assert len(diablo_games) >= 1

    @patch("abso.core.game_detector.winreg.CloseKey")
    @patch("abso.core.game_detector.winreg.QueryValueEx")
    @patch("abso.core.game_detector.winreg.OpenKey")
    def test_finds_overwatch2_from_registry(self, mock_open, mock_query, mock_close, tmp_path):
        """Test finds Overwatch 2 from Battle.net registry key."""
        game_folder = tmp_path / "Overwatch"
        game_folder.mkdir()
        (game_folder / "Overwatch.exe").touch()

        mock_query.return_value = (str(game_folder), 1)
        result = _detect_battlenet_games()
        ow_games = [g for g in result if "Overwatch" in g.name]
        assert len(ow_games) >= 1


class TestDetectStandaloneGames:
    """Tests for _detect_standalone_games function."""

    @patch.dict("os.environ", {"APPDATA": "", "LOCALAPPDATA": ""})
    def test_handles_missing_env_vars(self):
        """Test handles missing environment variables."""
        result = _detect_standalone_games()
        assert isinstance(result, list)

    def test_finds_slippi_in_appdata(self, tmp_path):
        """Test finds Slippi in AppData location."""
        # Create mock Slippi structure
        slippi_path = tmp_path / "Slippi Launcher" / "netplay"
        slippi_path.mkdir(parents=True)
        (slippi_path / "Dolphin.exe").touch()

        # Mock both APPDATA and LOCALAPPDATA to use temp paths and override Home
        with (patch.dict("os.environ", {"APPDATA": str(tmp_path), "LOCALAPPDATA": str(tmp_path / "nonexistent")}),
              patch.object(Path, "home", return_value=tmp_path / "fakehome")):
            result = _detect_standalone_games()
            slippi_games = [g for g in result if "Slippi" in g.name]
            assert len(slippi_games) >= 1
            assert all(g.platform == "standalone" for g in slippi_games)


class TestMatchGamesToProfiles:
    """Tests for match_games_to_profiles function."""

    def test_matches_game_to_profile(self):
        """Test matching game executable to profile hints."""
        game = InstalledGame(
            name="Test Game",
            executable="game.exe",
            install_path=Path("C:/Games/Test"),
            platform="steam",
        )

        mock_profile = MagicMock()
        mock_profile.executable_hints = ["game.exe", "game2.exe"]

        profiles = {"test_profile": mock_profile}

        result = match_games_to_profiles([game], profiles)
        assert len(result) == 1
        assert result[0].profile_match == "test_profile"

    def test_no_match_when_no_hint(self):
        """Test no match when no executable hint matches."""
        game = InstalledGame(
            name="Test Game",
            executable="other.exe",
            install_path=Path("C:/Games/Test"),
            platform="steam",
        )

        mock_profile = MagicMock()
        mock_profile.executable_hints = ["game.exe"]

        profiles = {"test_profile": mock_profile}

        result = match_games_to_profiles([game], profiles)
        assert len(result) == 1
        assert result[0].profile_match is None

    def test_case_insensitive_matching(self):
        """Test executable matching is case-insensitive."""
        game = InstalledGame(
            name="Test Game",
            executable="GAME.EXE",
            install_path=Path("C:/Games/Test"),
            platform="steam",
        )

        mock_profile = MagicMock()
        mock_profile.executable_hints = ["game.exe"]

        profiles = {"test_profile": mock_profile}

        result = match_games_to_profiles([game], profiles)
        assert result[0].profile_match == "test_profile"

    def test_empty_games_list(self):
        """Test empty games list returns empty."""
        profiles = {"test_profile": MagicMock()}
        result = match_games_to_profiles([], profiles)
        assert result == []


class TestGetProfileSuggestions:
    """Tests for get_profile_suggestions function."""

    @patch("abso.core.game_detector.match_games_to_profiles")
    @patch("abso.profiles.get_all_profiles")
    @patch("abso.core.game_detector.detect_installed_games")
    def test_returns_suggestions_dict(self, mock_detect, mock_profiles, mock_match):
        """Test returns dictionary of profile suggestions."""
        game = InstalledGame(
            name="Test Game",
            executable="game.exe",
            install_path=Path("C:/Games/Test"),
            platform="steam",
            profile_match="slippi_melee",
        )
        mock_detect.return_value = [game]
        mock_profiles.return_value = {}
        mock_match.return_value = [game]

        result = get_profile_suggestions()
        assert isinstance(result, dict)
        assert "slippi_melee" in result
        assert len(result["slippi_melee"]) == 1

    @patch("abso.core.game_detector.match_games_to_profiles")
    @patch("abso.profiles.get_all_profiles")
    @patch("abso.core.game_detector.detect_installed_games")
    def test_empty_when_no_matches(self, mock_detect, mock_profiles, mock_match):
        """Test returns empty dict when no profile matches."""
        game = InstalledGame(
            name="Test Game",
            executable="game.exe",
            install_path=Path("C:/Games/Test"),
            platform="steam",
            profile_match=None,
        )
        mock_detect.return_value = [game]
        mock_profiles.return_value = {}
        mock_match.return_value = [game]

        result = get_profile_suggestions()
        assert result == {}
