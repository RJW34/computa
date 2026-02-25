"""Tests for MultiMonitorDetector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.core.multimon_detector import DisplayEnvironment, MultiMonitorDetector


class TestMultiMonitorDetector:
    """Tests for monitor and overlay detection behavior."""

    @patch.object(MultiMonitorDetector, "_detect_overlays", return_value=None)
    @patch("abso.core.multimon_detector.HardwareDetector.detect_monitors")
    def test_detect_uses_hardware_detector_monitor_data(self, mock_detect_monitors, _mock_overlays):
        """Monitor refresh/resolution should come from HardwareDetector when available."""
        mock_detect_monitors.return_value = [
            {
                "name": "Primary Monitor",
                "resolution": "2560x1440",
                "refresh_rate": 280,
                "is_primary": True,
                "vrr_supported": True,
            },
            {
                "name": "Secondary Monitor",
                "resolution": "1920x1080",
                "refresh_rate": 60,
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

