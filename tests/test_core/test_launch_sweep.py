import pytest

from abso.core.launch_sweep import (
    LaunchProfileError,
    build_launch_killset_payload,
    run_launch_sweep,
)
from abso.core.process_janitor import CAPTURE_ALLOWED_IMAGES, ProcessSweepResult


@pytest.mark.parametrize("include_opt_in", [False, True])
def test_build_launch_killset_payload_resolves_profile_aliases(include_opt_in):
    payload = build_launch_killset_payload(
        "overwatch2-gsync-hdr-streaming", include_opt_in=include_opt_in
    )

    assert payload["profile"] == "overwatch2-gsync-hdr-capture"
    assert "Overwatch.exe" in payload["executables"]
    assert payload["killset"]["always_safe"]
    assert payload["killset"]["opt_in"]
    assert not {image.lower() for image in payload["resolved"]} & CAPTURE_ALLOWED_IMAGES
    if not include_opt_in:
        assert "SearchIndexer.exe" not in payload["resolved"]


@pytest.mark.parametrize(
    ("alias", "canonical", "strict_sibling"),
    [
        ("ssbm-streaming", "slippi-melee-capture", "slippi-melee"),
        ("ssbm-streaming-hdr", "slippi-melee-hdr-capture", "slippi-melee-hdr"),
        ("roa2-streaming", "rivals2-gsync-capture", "rivals2-gsync"),
        ("roa2-streaming-hdr", "rivals2-gsync-hdr-capture", "rivals2-gsync-hdr"),
        ("fortnite-streaming", "fortnite-gsync-capture", "fortnite"),
        (
            "fortnite-streaming-hdr",
            "fortnite-gsync-hdr-capture",
            "fortnite-gsync-hdr",
        ),
        (
            "overwatch2-streaming",
            "overwatch2-gsync-capture",
            "overwatch2-gsync",
        ),
        (
            "overwatch2-streaming-hdr",
            "overwatch2-gsync-hdr-capture",
            "overwatch2-gsync-hdr",
        ),
        (
            "cs2-streaming",
            "counter-strike-2-gsync-capture",
            "counter-strike-2-gsync",
        ),
        (
            "cs2-streaming-hdr",
            "counter-strike-2-gsync-hdr-capture",
            "counter-strike-2-gsync-hdr",
        ),
    ],
)
def test_streaming_alias_launch_killsets_preserve_obs(
    alias: str,
    canonical: str,
    strict_sibling: str,
) -> None:
    payload = build_launch_killset_payload(alias, include_opt_in=True)
    strict = build_launch_killset_payload(strict_sibling, include_opt_in=True)

    assert payload["profile"] == canonical
    streaming_images = {image.lower() for image in payload["resolved"]}
    strict_images = {image.lower() for image in strict["resolved"]}
    assert "obs64.exe" not in streaming_images
    assert "obs32.exe" not in streaming_images
    assert "obs64.exe" in strict_images
    assert "obs32.exe" in strict_images
    assert "searchindexer.exe" in streaming_images


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
