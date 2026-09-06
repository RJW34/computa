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


class TestBundledCatalogIntegrity:
    """Invariants over the bundled debloat_tweaks.yaml catalog."""

    def _tweaks(self, tmp_path):
        from abso.settings.debloat import load_debloat_tweaks

        # Point the user-override path at an empty location so the machine's
        # real ~/.abso/debloat_tweaks.yaml never leaks into the assertions.
        return load_debloat_tweaks(user_yaml=tmp_path / "none.yaml")

    def test_bundled_catalog_parses_completely(self, tmp_path):
        tweaks = self._tweaks(tmp_path)
        assert len(tweaks.registry) >= 30
        assert len(tweaks.services) >= 5
        assert len(tweaks.appx) >= 15

    def test_all_rows_have_valid_shape(self, tmp_path):
        from abso.settings.debloat import HIVE_MAP, REG_TYPE_MAP

        tweaks = self._tweaks(tmp_path)
        for t in tweaks.registry:
            assert t.tier in (1, 2, 3), t.name
            assert t.hive in HIVE_MAP, t.name
            assert t.reg_type in REG_TYPE_MAP, t.name
        for s in tweaks.services:
            assert s.tier in (1, 2, 3), s.name
            assert s.desired_start in (2, 3, 4), s.name
            assert s.default_start in (2, 3, 4), s.name

    def test_no_bundled_hklm_tweak_hits_blocked_paths(self, tmp_path):
        from abso.settings.debloat import _is_blocked_hklm_path

        tweaks = self._tweaks(tmp_path)
        offenders = [
            t.name
            for t in tweaks.registry
            if t.hive == "HKLM" and _is_blocked_hklm_path(t.key)
        ]
        assert offenders == [], f"bundled tweaks hit blocked HKLM paths: {offenders}"

    def test_winutil_parity_imports_present(self, tmp_path):
        """The 2026-09 WinUtil parity audit imported exactly these deltas."""
        tweaks = self._tweaks(tmp_path)
        by_name = {t.name: t for t in tweaks.registry}

        expected_tier1 = {
            "Disable User Activity Publishing": ("PublishUserActivities", 0),
            "Disable Implicit Ink Data Collection": ("RestrictImplicitInkCollection", 1),
            "Disable Implicit Text Data Collection": ("RestrictImplicitTextCollection", 1),
            "Disable Contact Harvesting": ("HarvestContacts", 0),
            "Disable Personalization Data Consent": ("AcceptedPrivacyPolicy", 0),
        }
        for name, (value, desired) in expected_tier1.items():
            row = by_name.get(name)
            assert row is not None, f"missing tier-1 parity row: {name}"
            assert row.tier == 1 and row.value == value and row.desired == desired, name

        expected_tier2 = {
            "Prevent Device Metadata Download": ("PreventDeviceMetadataFromNetwork", 1),
            "Disable WPBT Vendor Software Execution": ("DisableWpbtExecution", 1),
        }
        for name, (value, desired) in expected_tier2.items():
            row = by_name.get(name)
            assert row is not None, f"missing tier-2 parity row: {name}"
            assert row.tier == 2 and row.value == value and row.desired == desired, name

        maps = {s.name: s for s in tweaks.services}.get("MapsBroker to Manual")
        assert maps is not None and maps.tier == 2 and maps.desired_start == 3

    def test_registry_names_are_unique(self, tmp_path):
        tweaks = self._tweaks(tmp_path)
        names = [t.name for t in tweaks.registry]
        assert len(names) == len(set(names)), "duplicate registry tweak names"
