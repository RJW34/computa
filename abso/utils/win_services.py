"""Bulk Windows service queries over one Service Control Manager handle.

Backup/detect scans previously spawned two subprocesses per service
(``sc query`` + ``sc qc``). One SCM connection answers every query with no
process spawns at all; callers keep their ``sc``-based readers as the
fallback for any service this module cannot answer definitively.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

_ERROR_SERVICE_DOES_NOT_EXIST = 1060

# Parity with the sc-output parsers: only auto/demand/disabled are reported;
# boot/system driver start types read as None exactly like before.
_KNOWN_START_TYPES = frozenset({2, 3, 4})
_STATE_STOPPED = 1
_STATE_RUNNING = 4


def query_services(names: Iterable[str]) -> dict[str, dict[str, Any] | None] | None:
    """Query state and start type for many services in one SCM session.

    Args:
        names: Service names to query.

    Returns:
        None when the SCM API is unavailable entirely (caller should fall
        back to ``sc`` for everything). Otherwise a dict keyed by service
        name where each value is either a definitive
        ``{"exists": bool, "start_type": int | None, "state": str | None}``
        dict, or None when this service could not be answered definitively
        (access denied, transient error) and the caller should fall back to
        its per-service ``sc`` reader for that name.
    """
    try:
        import pywintypes
        import win32service
    except ImportError as exc:
        logger.debug("win32service unavailable, falling back to sc: %s", exc)
        return None

    try:
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
    except pywintypes.error as exc:
        logger.debug("OpenSCManager failed, falling back to sc: %s", exc)
        return None

    results: dict[str, dict[str, Any] | None] = {}
    try:
        for name in names:
            results[name] = _query_one(win32service, pywintypes, scm, name)
    finally:
        win32service.CloseServiceHandle(scm)

    return results


def _query_one(
    win32service: Any,
    pywintypes: Any,
    scm: Any,
    name: str,
) -> dict[str, Any] | None:
    """Query a single service handle; None means "caller must fall back"."""
    info: dict[str, Any] = {"exists": False, "start_type": None, "state": None}

    try:
        service = win32service.OpenService(
            scm,
            name,
            win32service.SERVICE_QUERY_STATUS | win32service.SERVICE_QUERY_CONFIG,
        )
    except pywintypes.error as exc:
        if getattr(exc, "winerror", None) == _ERROR_SERVICE_DOES_NOT_EXIST:
            return info
        logger.debug("OpenService(%s) failed (%s); deferring to sc fallback", name, exc)
        return None

    try:
        info["exists"] = True
        try:
            status = win32service.QueryServiceStatus(service)
            current_state = status[1]
            if current_state == _STATE_RUNNING:
                info["state"] = "running"
            elif current_state == _STATE_STOPPED:
                info["state"] = "stopped"
        except pywintypes.error as exc:
            logger.debug("QueryServiceStatus(%s) failed: %s", name, exc)

        try:
            config = win32service.QueryServiceConfig(service)
            start_type = config[1]
            if start_type in _KNOWN_START_TYPES:
                info["start_type"] = start_type
        except pywintypes.error as exc:
            logger.debug("QueryServiceConfig(%s) failed: %s", name, exc)
    finally:
        win32service.CloseServiceHandle(service)

    return info
