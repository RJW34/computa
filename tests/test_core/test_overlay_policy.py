"""Tests for shared overlay process policy."""

from __future__ import annotations

from abso.core.overlay_policy import (
    OVERLAY_PROCESS_IMAGES,
    OVERLAY_PROCESS_LABELS,
    OVERLAY_PROCESS_MAP,
    unique_overlay_labels,
)


def test_overlay_process_labels_are_derived_from_shared_map() -> None:
    assert OVERLAY_PROCESS_LABELS["discordhookhelper64.exe"] == "Discord Overlay"
    assert OVERLAY_PROCESS_LABELS["gameoverlayui.exe"] == "Steam Overlay"
    assert "OBS Studio" in OVERLAY_PROCESS_MAP
    assert "MedalEncoder.exe" in OVERLAY_PROCESS_IMAGES
    assert len(OVERLAY_PROCESS_IMAGES) == len(set(OVERLAY_PROCESS_IMAGES))


def test_unique_overlay_labels_preserves_first_seen_order() -> None:
    assert unique_overlay_labels(["", "Discord Overlay", " Discord Overlay ", "OBS Studio"]) == [
        "Discord Overlay",
        "OBS Studio",
    ]
