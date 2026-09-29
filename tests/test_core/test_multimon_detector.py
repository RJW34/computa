"""Tests for MultiMonitorDetector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from abso.core.multimon_detector import (
    DisplayEnvironment,
    MonitorInfo,
    MultiMonitorDetector,
    _query_hdr_capabilities_by_device,
)


class TestMultiMonitorDetector:
    """Tests for monitor and overlay detection behavior."""

    @pytest.fixture(autouse=True)
    def mock_hdr_query(self):
        """Topology unit tests must not probe the real display configuration."""
        with patch("abso.core.multimon_detector._query_hdr_capabilities_by_device", return_value={}) as query:
            yield query

    def test_hdr_capability_matches_device_identity_not_resolution_or_order(self, mock_hdr_query):
        mock_hdr_query.return_value = {r"\\.\display1": True, r"\\.\display2": False}
        rows = [
            {"name": "Identical panel", "device_name": device_name,
             "resolution": "2560x1440", "refresh_rate": 144, "is_primary": primary}
            for device_name, primary in [(r"\\.\DISPLAY2", False), (r"\\.\DISPLAY1", True), (None, False)]
        ]
        with (
            patch("abso.core.multimon_detector.HardwareDetector.detect_monitors", return_value=rows),
            patch.object(MultiMonitorDetector, "_enum_desktop_screens", return_value=[]),
            patch.object(MultiMonitorDetector, "_detect_overlays"),
        ):
            monitors = MultiMonitorDetector().detect().environment.monitors
        assert [m.is_hdr_capable for m in monitors] == [False, True, None]
        mock_hdr_query.assert_called_once_with()

    def test_desktop_fallback_gets_hdr_by_identity(self, mock_hdr_query):
        mock_hdr_query.return_value = {r"\\.\display2": True}
        monitor = MonitorInfo("Desktop", 2560, 1440, 60, True, device_name=r"\\.\DISPLAY2")
        with (
            patch("abso.core.multimon_detector.HardwareDetector.detect_monitors", return_value=[]),
            patch.object(MultiMonitorDetector, "_enum_desktop_screens", return_value=[monitor]),
            patch.object(MultiMonitorDetector, "_detect_overlays"),
        ):
            assert MultiMonitorDetector().detect().environment.monitors[0].is_hdr_capable is True
        mock_hdr_query.assert_called_once_with()

    def test_unavailable_hdr_query_serializes_as_unknown(self):
        from abso.core.display_stability import _monitor_row

        monitor = MonitorInfo("Unreadable", 2560, 1440, 60, True, device_name=r"\\.\DISPLAY1")
        env = DisplayEnvironment()
        with patch.object(MultiMonitorDetector, "_enum_display_monitors", return_value=[monitor]):
            MultiMonitorDetector()._detect_monitors(env)
        assert monitor.is_hdr_capable is None
        assert _monitor_row(monitor)["is_hdr_capable"] is None
        assert env.detection_confident is True

    @patch.object(MultiMonitorDetector, "_detect_overlays", return_value=None)
    @patch.object(MultiMonitorDetector, "_enum_desktop_screens", return_value=[])
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors")
    def test_detect_uses_hardware_detector_monitor_data(
        self,
        mock_detect_monitors,
        _mock_desktop_screens,
        _mock_overlays,
    ):
        """Monitor refresh/resolution should come from HardwareDetector when available."""
        mock_detect_monitors.return_value = [
            {
                "name": "Primary Monitor",
                "resolution": "2560x1440",
                "refresh_rate": 280,
                "max_refresh_rate": 280,
                "is_primary": True,
                "vrr_supported": True,
                "vrr_type": "gsync_compatible",
            },
            {
                "name": "Secondary Monitor",
                "resolution": "1920x1080",
                "refresh_rate": 60,
                "max_refresh_rate": 144,
                "is_primary": False,
                "vrr_supported": False,
            },
        ]

        detector = MultiMonitorDetector()
        result = detector.detect()
        env = result.environment

        assert env.monitor_count == 2
        assert env.primary_refresh == 280
        assert env.max_refresh == 280
        assert env.min_refresh == 60
        assert env.has_mixed_refresh is True
        assert env.has_mixed_resolution is True
        assert env.monitors[0].is_vrr_capable is True
        assert env.monitors[0].max_refresh_rate == 280
        assert env.monitors[0].vrr_type == "gsync_compatible"
        assert env.monitors[1].max_refresh_rate == 144
        assert all(m.is_hdr_capable is None for m in env.monitors)

    @patch.object(MultiMonitorDetector, "_detect_overlays", return_value=None)
    @patch.object(MultiMonitorDetector, "_enum_desktop_screens")
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors")
    def test_detect_fills_partial_hardware_topology_from_desktop_screens(
        self,
        mock_detect_monitors,
        mock_desktop_screens,
        _mock_overlays,
    ):
        """A partial non-empty hardware probe should not hide active desktops."""
        mock_detect_monitors.return_value = [
            {
                "name": "Primary Monitor",
                "resolution": "2560x1440",
                "refresh_rate": 300,
                "is_primary": True,
                "vrr_supported": True,
            },
        ]
        mock_desktop_screens.return_value = [
            MonitorInfo(
                name=r"\\.\DISPLAY1",
                width=2560,
                height=1440,
                refresh_rate=60.0,
                is_primary=True,
            ),
            MonitorInfo(
                name=r"\\.\DISPLAY2",
                width=2560,
                height=1440,
                refresh_rate=60.0,
                is_primary=False,
            ),
        ]

        detector = MultiMonitorDetector()
        result = detector.detect()
        env = result.environment

        assert env.monitor_count == 2
        assert env.is_multi_monitor is True
        assert env.has_mixed_refresh is True
        assert env.monitors[0].name == "Primary Monitor"
        assert env.monitors[1].name == r"\\.\DISPLAY2"
        mpo_warning = next(
            warning for warning in result.warnings
            if warning.code == "MULTIMON_MPO_GLITCH_RISK"
        )
        assert mpo_warning.message == (
            "MPO glitch risk: VRR-capable display (current VRR engagement unverified), "
            "mixed refresh (60Hz - 300Hz)"
        )

    @patch.object(MultiMonitorDetector, "_detect_overlays", return_value=None)
    @patch.object(MultiMonitorDetector, "_enum_desktop_screens", return_value=[])
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors")
    def test_detect_warns_when_monitor_runs_below_refresh_capability(
        self,
        mock_detect_monitors,
        _mock_desktop_screens,
        _mock_overlays,
    ):
        """Diagnostics should surface displays running below detected capability."""
        mock_detect_monitors.return_value = [
            {
                "name": "Secondary Monitor",
                "resolution": "2560x1440",
                "refresh_rate": 59.95,
                "max_refresh_rate": 144,
                "is_primary": False,
                "vrr_supported": True,
            },
            {
                "name": "Primary Monitor",
                "resolution": "2560x1440",
                "refresh_rate": 300,
                "is_primary": True,
                "vrr_supported": True,
            },
        ]

        detector = MultiMonitorDetector()
        result = detector.detect()

        refresh_warning = next(
            warning
            for warning in result.warnings
            if warning.code == "MULTIMON_REFRESH_BELOW_CAPABILITY"
        )
        assert "Secondary Monitor" in refresh_warning.message
        assert "59.95Hz" in refresh_warning.message
        assert "144Hz" in refresh_warning.message

    @patch.object(MultiMonitorDetector, "_detect_overlays", return_value=None)
    @patch.object(MultiMonitorDetector, "_enum_desktop_screens", return_value=[])
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors")
    def test_detect_treats_fractional_sixty_hz_as_uniform_refresh(
        self,
        mock_detect_monitors,
        _mock_desktop_screens,
        _mock_overlays,
    ):
        """59.95Hz and 60Hz are the same topology for compositor risk purposes."""
        mock_detect_monitors.return_value = [
            {
                "name": "Primary Monitor",
                "resolution": "2560x1440",
                "refresh_rate": 59.95,
                "is_primary": True,
            },
            {
                "name": "Secondary Monitor",
                "resolution": "1920x1080",
                "refresh_rate": 60,
                "is_primary": False,
            },
        ]

        detector = MultiMonitorDetector()
        result = detector.detect()

        assert result.environment.has_mixed_refresh is False
        assert all(
            warning.code != "MULTIMON_MIXED_REFRESH"
            for warning in result.warnings
        )

    @patch("abso.core.multimon_detector.subprocess.run")
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors", return_value=[])
    def test_overlay_detection_does_not_treat_steam_client_as_overlay(
        self,
        _mock_detect_monitors,
        mock_subprocess_run,
    ):
        """steam.exe alone should not trigger Steam overlay warning."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='"steam.exe","1111","Console","1","10000 K"\n'
                   '"gamebar.exe","2222","Console","1","12000 K"\n',
        )

        detector = MultiMonitorDetector()
        env = DisplayEnvironment()
        detector._detect_overlays(env)

        assert "Steam Overlay" not in env.detected_overlays
        assert "Xbox Game Bar" in env.detected_overlays

    @patch("abso.core.multimon_detector.subprocess.run")
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors", return_value=[])
    def test_overlay_detection_does_not_treat_discord_client_as_overlay(
        self,
        _mock_detect_monitors,
        mock_subprocess_run,
    ):
        """discord.exe alone should not trigger the strict Discord overlay blocker."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='"discord.exe","1111","Console","1","10000 K"\n',
        )

        detector = MultiMonitorDetector()
        env = DisplayEnvironment()
        detector._detect_overlays(env)

        assert "Discord Overlay" not in env.detected_overlays

    @patch("abso.core.multimon_detector.subprocess.run")
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors", return_value=[])
    def test_overlay_detection_treats_discord_hook_helper_as_overlay(
        self,
        _mock_detect_monitors,
        mock_subprocess_run,
    ):
        """Discord overlay helper processes should remain hard blockers for strict profiles."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='"DiscordHookHelper64.exe","1111","Console","1","10000 K"\n',
        )

        detector = MultiMonitorDetector()
        env = DisplayEnvironment()
        detector._detect_overlays(env)

        assert "Discord Overlay" in env.detected_overlays

    @patch("abso.core.multimon_detector.subprocess.run")
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors", return_value=[])
    def test_overlay_detection_uses_exact_tasklist_image_names(
        self,
        _mock_detect_monitors,
        mock_subprocess_run,
    ):
        """Process-name substrings should not create overlay false positives."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='"notobs64.exe","1111","Console","1","10000 K"\n'
                   '"xdiscordhookhelper64.exe","2222","Console","1","10000 K"\n',
        )

        detector = MultiMonitorDetector()
        env = DisplayEnvironment()
        detector._detect_overlays(env)

        assert env.detected_overlays == []

    @patch("abso.core.multimon_detector.subprocess.run")
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors", return_value=[])
    def test_overlay_detection_includes_medal(
        self,
        _mock_detect_monitors,
        mock_subprocess_run,
    ):
        """Medal should be treated as an overlay/capture blocker for strict profiles."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='"medal.exe","1111","Console","1","10000 K"\n'
                   '"medalencoder.exe","2222","Console","1","12000 K"\n',
        )

        detector = MultiMonitorDetector()
        env = DisplayEnvironment()
        detector._detect_overlays(env)

        assert "Medal Overlay" in env.detected_overlays
        assert env.detected_overlays.count("Medal Overlay") == 1


def _fake_hdr_user32(path_rows, source_names, hdr_values, legacy_values=None):
    """Exercise the actual HDR getter against hermetic native API responses."""
    api = MagicMock()

    def sizes(flags, num_paths, num_modes):
        assert flags == 2  # QDC_ONLY_ACTIVE_PATHS
        num_paths._obj.value = len(path_rows)
        num_modes._obj.value = len(path_rows)
        return 0

    def query(flags, num_paths, paths, num_modes, modes, topology):
        assert flags == 2 and topology is None
        for path, (source_key, target_key) in zip(paths, path_rows, strict=True):
            for info, key in ((path.sourceInfo, source_key), (path.targetInfo, target_key)):
                info.adapterId.LowPart, info.adapterId.HighPart, info.id = key
            path.flags = 1
            path.targetInfo.targetAvailable = True
        return 0

    def device_info(pointer):
        info = pointer._obj
        header = info.header
        key = (header.adapterId.LowPart, header.adapterId.HighPart, header.id)
        if header.type == 1:
            if key not in source_names:
                return 5
            info.viewGdiDeviceName = source_names[key]
        elif header.type == 15:
            value = hdr_values.get(key)
            if isinstance(value, Exception):
                raise value
            if value is None:
                return 50
            info.value, info.activeColorMode = value
        elif header.type == 9:
            value = (legacy_values or {}).get(key)
            if value is None:
                return 50
            info.value = value
        else:
            pytest.fail(f"Unexpected display request type {header.type}")
        return 0

    api.GetDisplayConfigBufferSizes.side_effect = sizes
    api.QueryDisplayConfig.side_effect = query
    api.DisplayConfigGetDeviceInfo.side_effect = device_info
    return api


class TestReadOnlyHdrCapabilities:
    def test_adapter_local_id_collisions_and_sticky_intent_do_not_confuse_hdr(self):
        first, second = (10, 0, 0), (20, 0, 0)
        target1, target2 = (10, 0, 4355), (20, 0, 4355)
        api = _fake_hdr_user32(
            [(second, target2), (first, target1), (first, target1)],
            {first: r"\\.\DISPLAY1", second: r"\\.\DISPLAY2"},
            # Both user intent bits are On; only the first supports HDR.
            {target1: (0x73, 2), target2: (0x65, 0)},
        )
        with (
            patch("abso.core.multimon_detector.ctypes.windll.user32", api),
            patch("abso.settings.windows.WindowsSettingsHandler.detect") as full_detect,
            patch("abso.settings.windows.WindowsSettingsHandler._get_hdr_state_summary") as summary,
        ):
            result = _query_hdr_capabilities_by_device()
        assert result == {r"\\.\display2": False, r"\\.\display1": True}
        api.GetDisplayConfigBufferSizes.assert_called_once()
        api.QueryDisplayConfig.assert_called_once()
        assert api.DisplayConfigGetDeviceInfo.call_count == 4  # Two sources, two unique targets.
        api.DisplayConfigSetDeviceInfo.assert_not_called()
        api.SetDisplayConfig.assert_not_called()
        full_detect.assert_not_called()
        summary.assert_not_called()

    @pytest.mark.parametrize("raw_value, expected", [(0x10, True), (0, False), (0x65, False)])
    def test_hdr_capability_is_not_active_mode_or_user_intent(self, raw_value, expected):
        source, target = (1, 0, 9), (1, 0, 20)
        api = _fake_hdr_user32(
            [(source, target)], {source: r"\\.\DISPLAY7"}, {target: (raw_value, 0)},
        )
        with patch("abso.core.multimon_detector.ctypes.windll.user32", api):
            assert _query_hdr_capabilities_by_device() == {r"\\.\display7": expected}

    @pytest.mark.parametrize("other", [(0x10, 0), (0, 0), None, OSError("unreadable target")])
    def test_clone_targets_must_agree_and_failed_target_does_not_erase_other_source(self, other):
        source, other_source = (1, 0, 2), (1, 0, 3)
        first, second, third = (1, 0, 20), (1, 0, 21), (1, 0, 22)
        api = _fake_hdr_user32(
            [(source, first), (source, second), (other_source, third)],
            {source: r"\\.\DISPLAY1", other_source: r"\\.\DISPLAY2"},
            {first: (0x10, 0), second: other, third: (0, 0)},
        )
        with patch("abso.core.multimon_detector.ctypes.windll.user32", api):
            result = _query_hdr_capabilities_by_device()
        assert result[r"\\.\display1"] is (True if other == (0x10, 0) else None)
        assert result[r"\\.\display2"] is False

    @pytest.mark.parametrize("legacy_value, expected", [(1, True), (0, False), (None, None)])
    def test_legacy_hdr_api_fallback_or_unknown(self, legacy_value, expected):
        source, target = (1, -2, 0), (1, -2, 20)
        api = _fake_hdr_user32(
            [(source, target)], {source: r"\\.\DISPLAY1"}, {}, {target: legacy_value},
        )
        with patch("abso.core.multimon_detector.ctypes.windll.user32", api):
            assert _query_hdr_capabilities_by_device() == {r"\\.\display1": expected}

    @pytest.mark.parametrize("failure", ["sizes", "query", "no_paths", "source_name"])
    def test_failed_or_missing_topology_produces_no_guessed_capability(self, failure):
        source, target = (1, 0, 0), (1, 0, 20)
        api = _fake_hdr_user32(
            [] if failure == "no_paths" else [(source, target)],
            {} if failure == "source_name" else {source: r"\\.\DISPLAY1"},
            {target: (0x10, 0)},
        )
        if failure == "sizes":
            api.GetDisplayConfigBufferSizes.side_effect = lambda *args: 5
        if failure == "query":
            api.QueryDisplayConfig.side_effect = lambda *args: 122  # Topology changed.
        with patch("abso.core.multimon_detector.ctypes.windll.user32", api):
            assert _query_hdr_capabilities_by_device() == {}
        assert api.QueryDisplayConfig.call_count <= 1
