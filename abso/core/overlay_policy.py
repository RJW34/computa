"""Shared overlay process identity policy."""

from __future__ import annotations

from collections.abc import Iterable

OVERLAY_PROCESS_MAP: dict[str, tuple[str, ...]] = {
    "NVIDIA Share Overlay": ("NVIDIA Share.exe",),
    "Steam Overlay": ("GameOverlayUI.exe",),
    "Xbox Game Bar": ("GameBar.exe",),
    "Xbox Game Bar Server": ("GameBarFTServer.exe",),
    "Discord Overlay": ("DiscordHookHelper.exe", "DiscordHookHelper64.exe"),
    "RivaTuner Statistics Server": ("RTSS.exe",),
    "OBS Studio": ("obs64.exe",),
    "Medal Overlay": ("Medal.exe", "MedalEncoder.exe"),
}

OVERLAY_PROCESS_LABELS: dict[str, str] = {
    image_name.lower(): label
    for label, image_names in OVERLAY_PROCESS_MAP.items()
    for image_name in image_names
}

OVERLAY_PROCESS_IMAGES: tuple[str, ...] = tuple(
    image_name
    for image_names in OVERLAY_PROCESS_MAP.values()
    for image_name in image_names
)


def unique_overlay_labels(labels: Iterable[object]) -> list[str]:
    """Return non-empty overlay labels in first-seen order."""
    ordered: list[str] = []
    for label in labels:
        normalized = str(label or "").strip()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return ordered
