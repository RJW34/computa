"""Read-only Windows display event diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

DISPLAY_EVENT_PROVIDERS = (
    "Display",
    "nvlddmkm",
    "Kernel-PnP",
    "Microsoft-Windows-UserModePowerService",
    "Microsoft-Windows-Kernel-Power",
)
DISPLAY_EVENT_CHANNELS = (
    "Microsoft-Windows-DxgKrnl-Admin",
    "Microsoft-Windows-DxgKrnl-Operational",
)
MAX_MESSAGE_CHARS = 700
DEFAULT_QUERY_TIMEOUT_SECONDS = 5


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _ps_single_quote(value: str) -> str:
    """Return a PowerShell single-quoted literal body."""
    return value.replace("'", "''")


def _display_event_script(*, lookback_minutes: int, max_events: int) -> str:
    """Build the PowerShell event-log query script."""
    providers = ", ".join(f"'{_ps_single_quote(provider)}'" for provider in DISPLAY_EVENT_PROVIDERS)
    channels = ", ".join(f"'{_ps_single_quote(channel)}'" for channel in DISPLAY_EVENT_CHANNELS)
    return f"""
$ErrorActionPreference = 'Stop'
$providers = @({providers})
$channels = @({channels})
$start = (Get-Date).AddMinutes(-{lookback_minutes})
$rawEvents = @()
$channelErrors = @()
$rawEvents += @(
    Get-WinEvent -FilterHashtable @{{ LogName = 'System'; StartTime = $start; ProviderName = $providers }} -ErrorAction SilentlyContinue
)
foreach ($channel in $channels) {{
    try {{
        $rawEvents += @(
            Get-WinEvent -FilterHashtable @{{ LogName = $channel; StartTime = $start }} -ErrorAction Stop
        )
    }} catch {{
        $message = if ($_.Exception -and $_.Exception.Message) {{
            ($_.Exception.Message -replace '\\s+', ' ').Trim()
        }} else {{
            'unknown channel query error'
        }}
        $errorId = [string]$_.FullyQualifiedErrorId
        if ($errorId -like 'NoMatchingEventsFound,*' -or $message -like 'No events were found*') {{
            continue
        }}
        $channelErrors += [pscustomobject]@{{
            channel = $channel
            error = $message
        }}
    }}
}}
$events = @(
    $rawEvents |
    Sort-Object TimeCreated -Descending |
    Select-Object -First {max_events} `
        @{{ Name = 'time_created'; Expression = {{ $_.TimeCreated.ToString('o') }} }}, `
        @{{ Name = 'log_name'; Expression = {{ $_.LogName }} }}, `
        @{{ Name = 'provider'; Expression = {{ $_.ProviderName }} }}, `
        @{{ Name = 'id'; Expression = {{ $_.Id }} }}, `
        @{{ Name = 'level'; Expression = {{ $_.LevelDisplayName }} }}, `
        @{{ Name = 'message'; Expression = {{
            if ($_.Message) {{ ($_.Message -replace '\\s+', ' ').Trim() }} else {{ '' }}
        }} }}
)
$payload = [pscustomobject]@{{
    events = @($events)
    channel_errors = @($channelErrors)
}}
$payload | ConvertTo-Json -Depth 5
""".strip()


def _trim_message(value: Any, *, max_chars: int = MAX_MESSAGE_CHARS) -> str:
    message = str(value or "").strip()
    if len(message) <= max_chars:
        return message
    return f"{message[: max_chars - 3]}..."


def _normalize_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "time_created": item.get("time_created"),
        "log_name": item.get("log_name"),
        "provider": item.get("provider"),
        "id": item.get("id"),
        "level": item.get("level"),
        "message": _trim_message(item.get("message")),
    }


def _normalize_channel_error(item: dict[str, Any]) -> dict[str, str]:
    return {
        "channel": str(item.get("channel") or "").strip(),
        "error": _trim_message(item.get("error"), max_chars=300),
    }


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def parse_display_event_payload(output: str) -> dict[str, list[dict[str, Any]]]:
    """Parse display-event PowerShell output into events and channel errors."""
    text = output.strip()
    if not text:
        return {"events": [], "channel_errors": []}

    parsed = json.loads(text)
    if isinstance(parsed, dict) and (
        "events" in parsed or "channel_errors" in parsed
    ):
        events = _as_dict_list(parsed.get("events"))
        channel_errors = _as_dict_list(parsed.get("channel_errors"))
    elif isinstance(parsed, dict):
        events = [parsed]
        channel_errors = []
    elif isinstance(parsed, list):
        events = _as_dict_list(parsed)
        channel_errors = []
    else:
        events = []
        channel_errors = []

    return {
        "events": [_normalize_event(item) for item in events],
        "channel_errors": [
            _normalize_channel_error(item) for item in channel_errors
        ],
    }


def parse_display_events_json(output: str) -> list[dict[str, Any]]:
    """Parse PowerShell ConvertTo-Json output into normalized event rows."""
    return parse_display_event_payload(output)["events"]


def collect_recent_display_events(
    *,
    lookback_minutes: int = 360,
    max_events: int = 20,
    timeout_seconds: int = DEFAULT_QUERY_TIMEOUT_SECONDS,
    platform: str | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Collect recent display/driver/power events without changing system state."""
    active_platform = platform or sys.platform
    lookback_minutes = max(1, int(lookback_minutes))
    max_events = max(1, int(max_events))
    timeout_seconds = max(1, int(timeout_seconds))

    payload: dict[str, Any] = {
        "supported": active_platform.startswith("win"),
        "lookback_minutes": lookback_minutes,
        "max_events": max_events,
        "timeout_seconds": timeout_seconds,
        "query_scope": "system_provider_and_channels",
        "providers": list(DISPLAY_EVENT_PROVIDERS),
        "channels": list(DISPLAY_EVENT_CHANNELS),
        "events": [],
        "count": 0,
        "channel_errors": [],
        "channel_error_count": 0,
    }
    if not payload["supported"]:
        payload["note"] = "Windows System event log is only available on Windows."
        return payload

    script = _display_event_script(
        lookback_minutes=lookback_minutes,
        max_events=max_events,
    )
    command: Sequence[str] = (
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    )
    start = time.perf_counter()
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        payload["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
        payload["timed_out"] = True
        payload["error"] = f"display event log query timed out after {timeout_seconds}s"
        return payload
    except OSError as exc:
        payload["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
        payload["error"] = str(exc)
        return payload
    payload["elapsed_ms"] = int((time.perf_counter() - start) * 1000)

    if result.returncode != 0:
        payload["error"] = (result.stderr or result.stdout or "").strip()
        return payload

    try:
        parsed_payload = parse_display_event_payload(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        payload["error"] = f"Failed to parse display event output: {exc}"
        return payload

    events = parsed_payload["events"]
    channel_errors = parsed_payload["channel_errors"]
    payload["events"] = events
    payload["count"] = len(events)
    payload["channel_errors"] = channel_errors
    payload["channel_error_count"] = len(channel_errors)
    return payload
