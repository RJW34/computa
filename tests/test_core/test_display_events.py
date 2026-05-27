"""Tests for read-only display event diagnostics."""

from __future__ import annotations

import subprocess
from typing import Any

from abso.core.display_events import (
    collect_recent_display_events,
    parse_display_event_payload,
    parse_display_events_json,
)


def test_parse_display_events_json_normalizes_single_event() -> None:
    event = parse_display_events_json(
        """
{
  "time_created": "2026-05-26T08:00:00.0000000-04:00",
  "provider": "Display",
  "id": 4101,
  "level": "Warning",
  "message": "  Display driver recovered.  "
}
""",
    )

    assert event == [
        {
            "time_created": "2026-05-26T08:00:00.0000000-04:00",
            "log_name": None,
            "provider": "Display",
            "id": 4101,
            "level": "Warning",
            "message": "Display driver recovered.",
        }
    ]


def test_parse_display_event_payload_supports_legacy_event_list() -> None:
    payload = parse_display_event_payload(
        """
[
  {
    "time_created": "2026-05-26T08:00:00.0000000-04:00",
    "log_name": "System",
    "provider": "Display",
    "id": 4101,
    "level": "Warning",
    "message": "Display driver recovered."
  }
]
""",
    )

    assert payload["events"] == [
        {
            "time_created": "2026-05-26T08:00:00.0000000-04:00",
            "log_name": "System",
            "provider": "Display",
            "id": 4101,
            "level": "Warning",
            "message": "Display driver recovered.",
        }
    ]
    assert payload["channel_errors"] == []


def test_parse_display_event_payload_includes_optional_channel_errors() -> None:
    payload = parse_display_event_payload(
        """
{
  "events": [],
  "channel_errors": {
    "channel": "Microsoft-Windows-DxgKrnl-Admin",
    "error": "  The specified channel could not be found.  "
  }
}
""",
    )

    assert payload == {
        "events": [],
        "channel_errors": [
            {
                "channel": "Microsoft-Windows-DxgKrnl-Admin",
                "error": "The specified channel could not be found.",
            }
        ],
    }


def test_collect_recent_display_events_reports_unsupported_platform() -> None:
    payload = collect_recent_display_events(platform="linux")

    assert payload["supported"] is False
    assert payload["count"] == 0
    assert payload["events"] == []
    assert payload["channel_errors"] == []
    assert payload["channel_error_count"] == 0


def test_collect_recent_display_events_uses_read_only_powershell_runner() -> None:
    calls: list[tuple[Any, ...]] = []

    def runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 5
        command = args[0]
        script = command[-1]
        assert "Get-WinEvent" in script
        assert "ProviderName = $providers" in script
        assert "$channels" in script
        assert "$channelErrors" in script
        assert "channel_errors" in script
        assert "NoMatchingEventsFound" in script
        assert "Microsoft-Windows-DxgKrnl-Admin" in script
        assert "Microsoft-Windows-DxgKrnl-Operational" in script
        assert "Where-Object" not in script
        assert "Set-" not in script
        assert "Remove-" not in script
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"events":[],"channel_errors":[]}',
            stderr="",
        )

    payload = collect_recent_display_events(
        platform="win32",
        runner=runner,
        lookback_minutes=30,
        max_events=5,
    )

    assert calls
    assert payload["supported"] is True
    assert payload["lookback_minutes"] == 30
    assert payload["max_events"] == 5
    assert payload["timeout_seconds"] == 5
    assert payload["elapsed_ms"] >= 0
    assert payload["query_scope"] == "system_provider_and_channels"
    assert payload["channels"] == [
        "Microsoft-Windows-DxgKrnl-Admin",
        "Microsoft-Windows-DxgKrnl-Operational",
    ]
    assert payload["count"] == 0
    assert payload["channel_errors"] == []
    assert payload["channel_error_count"] == 0


def test_collect_recent_display_events_uses_custom_timeout() -> None:
    def runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == 2
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout='{"events":[],"channel_errors":[]}',
            stderr="",
        )

    payload = collect_recent_display_events(platform="win32", runner=runner, timeout_seconds=2)

    assert payload["timeout_seconds"] == 2
    assert payload["elapsed_ms"] >= 0
    assert payload["channel_error_count"] == 0


def test_collect_recent_display_events_surfaces_optional_channel_errors() -> None:
    def runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                '{"events":[],"channel_errors":['
                '{"channel":"Microsoft-Windows-DxgKrnl-Operational",'
                '"error":"access denied"}]}'
            ),
            stderr="",
        )

    payload = collect_recent_display_events(platform="win32", runner=runner)

    assert payload["count"] == 0
    assert payload["events"] == []
    assert payload["channel_error_count"] == 1
    assert payload["channel_errors"] == [
        {
            "channel": "Microsoft-Windows-DxgKrnl-Operational",
            "error": "access denied",
        }
    ]


def test_collect_recent_display_events_compacts_timeout_error() -> None:
    def runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        command = args[0]
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs["timeout"])

    payload = collect_recent_display_events(platform="win32", runner=runner, timeout_seconds=2)

    assert payload["timed_out"] is True
    assert payload["timeout_seconds"] == 2
    assert payload["elapsed_ms"] >= 0
    assert payload["error"] == "display event log query timed out after 2s"
    assert "Get-WinEvent" not in payload["error"]
    assert payload["events"] == []


def test_collect_recent_display_events_surfaces_query_error() -> None:
    def runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="access denied",
        )

    payload = collect_recent_display_events(platform="win32", runner=runner)

    assert payload["supported"] is True
    assert payload["error"] == "access denied"
    assert payload["elapsed_ms"] >= 0
    assert payload["events"] == []
