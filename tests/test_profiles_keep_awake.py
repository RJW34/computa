"""Tests for the keep_awake_while_gaming profile flag and its manifest plumbing."""

from __future__ import annotations

from abso.profiles.catalog import get_profile_classes, get_profile_manifest


def _profile(profile_id: str):
    return get_profile_classes()[profile_id]()


class TestKeepAwakeFlag:
    def test_emulator_profiles_keep_awake(self) -> None:
        # Gamepad-driven emulators are the non-redundant win for anti-sleep.
        assert _profile("slippi-melee").keep_awake_while_gaming is True
        assert _profile("ryujinx-ssbu").keep_awake_while_gaming is True

    def test_non_emulator_profiles_do_not_keep_awake(self) -> None:
        # Fullscreen shooters self-assert display-required; desktop must sleep.
        assert _profile("overwatch2").keep_awake_while_gaming is False
        assert _profile("rivals2-nosync").keep_awake_while_gaming is False
        assert _profile("productivity").keep_awake_while_gaming is False


class TestKeepAwakeManifest:
    def test_manifest_exposes_keep_awake_for_every_profile(self) -> None:
        manifest = get_profile_manifest()
        assert manifest, "manifest should not be empty"
        assert all("keep_awake_while_gaming" in entry for entry in manifest)

    def test_manifest_values_match_profiles(self) -> None:
        by_id = {entry["id"]: entry for entry in get_profile_manifest()}
        assert by_id["slippi-melee"]["keep_awake_while_gaming"] is True
        assert by_id["ryujinx-ssbu"]["keep_awake_while_gaming"] is True
        assert by_id["overwatch2"]["keep_awake_while_gaming"] is False

    def test_manifest_exposes_is_online_profile(self) -> None:
        # Used by the tray to pass --online (watchdog demote-only gating).
        manifest = get_profile_manifest()
        assert all("is_online_profile" in entry for entry in manifest)
        assert all(isinstance(entry["is_online_profile"], bool) for entry in manifest)
