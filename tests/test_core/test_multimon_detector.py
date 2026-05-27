"""Tests for MultiMonitorDetector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.core.multimon_detector import DisplayEnvironment, MonitorInfo, MultiMonitorDetector


class TestMultiMonitorDetector:
    """Tests for monitor and overlay detection behavior."""

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
        assert any(warning.code == "MULTIMON_MPO_GLITCH_RISK" for warning in result.warnings)

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
