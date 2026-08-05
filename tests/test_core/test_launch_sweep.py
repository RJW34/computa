import pytest

from abso.core.launch_sweep import (
    LaunchProfileError,
    build_launch_killset_payload,
    run_launch_sweep,
)
from abso.core.process_janitor import ProcessSweepResult


def test_build_launch_killset_payload_resolves_profile_aliases():
    payload = build_launch_killset_payload("overwatch2-gsync-hdr-streaming", include_opt_in=False)

    assert payload["profile"] == "overwatch2-gsync-hdr"
    assert "Overwatch.exe" in payload["executables"]
    assert payload["killset"]["always_safe"]
    assert payload["killset"]["opt_in"]
    assert "Medal.exe" in payload["resolved"]
    assert "SearchIndexer.exe" not in payload["resolved"]


def test_build_launch_killset_payload_rejects_unknown_profile():
    with pytest.raises(LaunchProfileError, match="Unknown profile"):
        build_launch_killset_payload("missing-profile", include_opt_in=False)


def test_run_launch_sweep_empty_profile_has_no_actions():
    payload = run_launch_sweep(
        "productivity",
        include_opt_in=False,
        dry_run=False,
        priority_enforcer=lambda profile: {"unexpected": profile},
    )

    assert payload["profile"] == "productivity"
    assert payload["result"]["attempted"] == []
    assert payload["result"]["changed"] is False
    assert payload["priority_enforcement"] is None
    assert payload["result"]["notices"] == [
        "No launch killset images defined for profile 'productivity'."
    ]


def test_run_launch_sweep_dry_run_uses_janitor_without_priority_enforcement():
    priority_calls = []

    class FakeJanitor:
        def sweep(self, images, *, dry_run):
            assert dry_run is True
            return ProcessSweepResult(
                attempted=list(images),
                not_running=list(images),
            )

    payload = run_launch_sweep(
        "overwatch2-gsync-hdr",
        include_opt_in=False,
        dry_run=True,
        janitor_factory=FakeJanitor,
        priority_enforcer=lambda profile: priority_calls.append(profile),
    )

    assert payload["dry_run"] is True
    assert payload["result"]["attempted"]
    assert payload["result"]["stopped"] == []
    assert payload["priority_enforcement"] is None
    assert priority_calls == []


def test_run_launch_sweep_live_reports_priority_enforcement():
    class FakeJanitor:
        def sweep(self, images, *, dry_run):
            assert dry_run is False
            return ProcessSweepResult(
                attempted=list(images),
                stopped=["Medal.exe"],
            )

    payload = run_launch_sweep(
        "overwatch2-gsync-hdr",
        include_opt_in=False,
        dry_run=False,
        janitor_factory=FakeJanitor,
        priority_enforcer=lambda profile: {
            "targeted": list(profile.executable_hints),
            "priority_name": "High",
        },
    )

    assert payload["result"]["changed"] is True
    assert payload["result"]["stopped"] == ["Medal.exe"]
    assert payload["priority_enforcement"]["targeted"] == ["Overwatch.exe"]


def test_run_launch_sweep_payload_reports_the_images_it_swept():
    """The payload's resolved list must match what the janitor received.

    The tray gates its per-tick backend spawn on this list, so it has to be
    the protect-filtered set the sweep really acted on -- not the committed
    catalog killset, which stays machine-independent and still lists images
    this machine protects.
    """
    swept: list[list[str]] = []

    class FakeJanitor:
        def sweep(self, images, *, dry_run):
            swept.append(list(images))
            return ProcessSweepResult(attempted=list(images), not_running=list(images))

    payload = run_launch_sweep(
        "overwatch2-gsync-hdr",
        include_opt_in=False,
        dry_run=True,
        janitor_factory=FakeJanitor,
        priority_enforcer=lambda profile: None,
    )

    assert swept and payload["resolved"] == swept[0]


def test_run_launch_sweep_resolved_excludes_protected_images(monkeypatch):
    """process_overrides.protect entries must not reach the tray pre-check."""
    monkeypatch.setattr(
        "abso.core.process_janitor._load_user_process_overrides",
        lambda: (frozenset({"medal.exe"}), ()),
    )

    class FakeJanitor:
        def sweep(self, images, *, dry_run):
            return ProcessSweepResult(attempted=list(images), not_running=list(images))

    payload = run_launch_sweep(
        "overwatch2-gsync-hdr",
        include_opt_in=False,
        dry_run=True,
        janitor_factory=FakeJanitor,
        priority_enforcer=lambda profile: None,
    )

    assert payload["resolved"]
    assert "Medal.exe" not in payload["resolved"]


def test_empty_launch_sweep_payload_still_carries_resolved_key():
    """Payload shape must be stable so the tray can read it unconditionally."""
    payload = run_launch_sweep("productivity", include_opt_in=False, dry_run=False)

    assert payload["resolved"] == []
