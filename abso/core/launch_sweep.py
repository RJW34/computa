"""Profile-aware launch killset and sweep helpers.

The tray calls these paths when a game process appears. Keeping this policy
outside the Click module makes the runtime behavior testable without dragging
in CLI formatting or display-sensitive apply code.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from abso.core.apply_hooks import enforce_running_process_priority
from abso.core.process_janitor import ProcessJanitor
from abso.profiles.catalog import get_profile_instances, get_profile_manifest, resolve_profile_id


class LaunchProfileError(ValueError):
    """Raised when launch-sweep policy cannot resolve a requested profile."""


def _canonical_profile_id(profile_name: str) -> str:
    return resolve_profile_id(profile_name) or profile_name


def _profile_instances() -> dict[str, Any]:
    return get_profile_instances()


def build_launch_killset_payload(profile_name: str, *, include_opt_in: bool) -> dict[str, Any]:
    """Return the read-only launch killset payload for a profile."""

    canonical = _canonical_profile_id(profile_name)
    manifest_ids = {entry["id"] for entry in get_profile_manifest()}
    if canonical not in manifest_ids:
        raise LaunchProfileError(f"Unknown profile: {profile_name}")

    profile = _profile_instances().get(canonical)
    if profile is None:
        raise LaunchProfileError(f"Profile instance unavailable: {canonical}")

    killset = profile.launch_process_killset()
    return {
        "profile": canonical,
        "executables": profile.executable_hints,
        "killset": killset.to_dict(),
        "resolved": killset.resolve(include_opt_in=include_opt_in),
        "include_opt_in": include_opt_in,
    }


def _empty_sweep_payload(
    canonical: str, *, include_opt_in: bool, dry_run: bool
) -> dict[str, Any]:
    return {
        "profile": canonical,
        "include_opt_in": include_opt_in,
        "dry_run": dry_run,
        "resolved": [],
        "result": {
            "attempted": [],
            "stopped": [],
            "not_running": [],
            "failed": [],
            "notices": [f"No launch killset images defined for profile '{canonical}'."],
            "warnings": [],
            "changed": False,
        },
        "priority_enforcement": None,
    }


def run_launch_sweep(
    profile_name: str,
    *,
    include_opt_in: bool,
    dry_run: bool,
    janitor_factory: Callable[[], ProcessJanitor] = ProcessJanitor,
    priority_enforcer: Callable[[Any], dict[str, Any] | None] = enforce_running_process_priority,
) -> dict[str, Any]:
    """Run or dry-run the launch-time process sweep for a profile."""

    canonical = _canonical_profile_id(profile_name)
    profile = _profile_instances().get(canonical)
    if profile is None:
        raise LaunchProfileError(f"Unknown profile: {profile_name}")

    killset = profile.launch_process_killset()
    resolved = killset.resolve(include_opt_in=include_opt_in)
    if not resolved:
        return _empty_sweep_payload(canonical, include_opt_in=include_opt_in, dry_run=dry_run)

    sweep_result = janitor_factory().sweep(resolved, dry_run=dry_run)
    priority_enforcement = None
    if not dry_run:
        priority_enforcement = priority_enforcer(profile)

    return {
        "profile": canonical,
        "include_opt_in": include_opt_in,
        "dry_run": dry_run,
        # The exact image set this sweep acted on, after per-machine
        # process_overrides.protect filtering. The tray uses it to decide
        # whether a later tick has anything to sweep at all, so it must be the
        # resolved list -- the committed catalog cache is deliberately
        # machine-independent and still lists protected images.
        "resolved": list(resolved),
        "result": sweep_result.to_dict(),
        "priority_enforcement": priority_enforcement,
    }
