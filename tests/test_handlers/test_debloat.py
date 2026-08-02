"""Tests for DebloatHandler bulk detect paths.

detect() previously spawned one PowerShell per managed appx package and two
``sc`` processes per managed service; these tests pin the bulk-listing fast
paths and their per-item fallbacks.
"""

from unittest.mock import MagicMock, patch

from abso.settings.debloat import DebloatHandler


def _make_handler() -> DebloatHandler:
    return DebloatHandler(tier=1)


class TestDebloatBulkAppx:
    """Bulk appx listing behavior in detect()."""

    @patch("abso.settings.debloat.query_services", return_value={})
    @patch.object(DebloatHandler, "_get_service_start_type", return_value=None)
    @patch.object(DebloatHandler, "_read_registry_value", return_value=None)
    @patch.object(DebloatHandler, "_is_appx_installed")
    @patch.object(DebloatHandler, "_list_installed_appx_names")
    def test_detect_uses_bulk_appx_listing(
        self, mock_list, mock_single, _reg, _svc, _bulk_svc
    ):
        """A successful bulk listing answers every package with zero per-package spawns."""
        handler = _make_handler()
        managed = [t.name for t in handler._tweaks.appx]
        assert managed, "expected managed appx packages in debloat_tweaks.yaml"
        # Mark exactly one managed package as installed (case-insensitively).
        mock_list.return_value = {managed[0].lower(), "unrelated.package"}

        state = handler.detect()

        assert mock_single.call_count == 0
        assert state["appx"][managed[0]]["installed"] is True
        for name in managed[1:]:
            assert state["appx"][name]["installed"] is False

    @patch("abso.settings.debloat.query_services", return_value={})
    @patch.object(DebloatHandler, "_get_service_start_type", return_value=None)
    @patch.object(DebloatHandler, "_read_registry_value", return_value=None)
    @patch.object(DebloatHandler, "_is_appx_installed", return_value=True)
    @patch.object(DebloatHandler, "_list_installed_appx_names", return_value=None)
    def test_detect_falls_back_per_package_when_listing_fails(
        self, _mock_list, mock_single, _reg, _svc, _bulk_svc
    ):
        """A failed bulk listing falls back to the per-package check."""
        handler = _make_handler()
        managed = [t.name for t in handler._tweaks.appx]

        state = handler.detect()

        assert mock_single.call_count == len(managed)
        assert all(info["installed"] for info in state["appx"].values())

    def test_list_installed_appx_names_parses_output(self):
        """The bulk lister lowercases and strips one name per line."""
        handler = _make_handler()
        completed = MagicMock(
            returncode=0,
            stdout="Microsoft.BingNews\n  Microsoft.GetHelp  \n\nMicrosoft.ZuneMusic\n",
        )
        with patch("abso.settings.debloat.subprocess.run", return_value=completed) as run:
            names = handler._list_installed_appx_names()

        assert names == {"microsoft.bingnews", "microsoft.gethelp", "microsoft.zunemusic"}
        command = run.call_args.args[0]
        assert "Get-AppxPackage" in " ".join(command)

    def test_list_installed_appx_names_returns_none_on_error(self):
        """A failing PowerShell listing returns None (fallback signal)."""
        handler = _make_handler()
        completed = MagicMock(returncode=1, stdout="", stderr="boom")
        with patch("abso.settings.debloat.subprocess.run", return_value=completed):
            assert handler._list_installed_appx_names() is None


class TestDebloatBulkServices:
    """Bulk SCM service reads in detect()."""

    @patch.object(DebloatHandler, "_read_registry_value", return_value=None)
    @patch.object(DebloatHandler, "_list_installed_appx_names", return_value=set())
    @patch.object(DebloatHandler, "_get_service_start_type")
    def test_detect_uses_bulk_service_answers(self, mock_single, _appx, _reg):
        """Definitive bulk answers skip the per-service sc reader."""
        handler = _make_handler()
        service_names = [t.service for t in handler._tweaks.services]
        assert service_names, "expected managed services in debloat_tweaks.yaml"
        bulk = {
            name: {"exists": True, "start_type": 4, "state": "stopped"}
            for name in service_names
        }

        with patch("abso.settings.debloat.query_services", return_value=bulk):
            state = handler.detect()

        assert mock_single.call_count == 0
        assert all(info["current_start"] == 4 for info in state["services"].values())

    @patch.object(DebloatHandler, "_read_registry_value", return_value=None)
    @patch.object(DebloatHandler, "_list_installed_appx_names", return_value=set())
    @patch.object(DebloatHandler, "_get_service_start_type", return_value=2)
    def test_detect_falls_back_when_bulk_unavailable(self, mock_single, _appx, _reg):
        """A dead SCM bulk query falls back to sc per service."""
        handler = _make_handler()
        service_names = [t.service for t in handler._tweaks.services]

        with patch("abso.settings.debloat.query_services", return_value=None):
            state = handler.detect()

        assert mock_single.call_count == len(service_names)
        assert all(info["current_start"] == 2 for info in state["services"].values())
