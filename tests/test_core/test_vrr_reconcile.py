"""Tests for post-apply borderless-VRR enabler reconciliation.

Regression: applying a borderless G-SYNC profile left the global NVIDIA
``vrr_mode`` at fullscreen-only and the Windows windowed-VRR flags off (a later
handler's HDR/MPO display re-enumeration dropped them), so G-SYNC never engaged
and the game locked to half refresh (150 fps on a 300 Hz panel).
"""

from __future__ import annotations

from abso.core.vrr_reconcile import (
    VrrEnablers,
    extract_vrr_enablers,
    reconcile_vrr_enablers,
)

GSYNC_HDR_MAP = {
    "NvidiaSettingsHandler": {
        "preset": "reflex_gsync",
        "global_vrr_mode": "fullscreen_and_windowed",
    },
    "WindowsSettingsHandler": {
        "hdr": True,
        "windowed_optimizations": True,
        "vrr_optimize": True,
    },
}

NO_SYNC_MAP = {
    "NvidiaSettingsHandler": {"preset": "reflex_no_sync", "global_vrr_mode": "off"},
    "WindowsSettingsHandler": {"hdr": False},
}


class FakeDRS:
    """vrr_mode read sequence: successive get_app_settings() pops the next value."""

    def __init__(self, read_sequence: list[int | None]) -> None:
        self._seq = list(read_sequence)
        self.global_writes: list[dict] = []

    def get_app_settings(self, *_a, **_k) -> dict:
        value = self._seq.pop(0) if self._seq else None
        return {"_profile": "Base Profile", "vrr_mode": value}

    def apply_settings_to_global(self, settings: dict) -> dict:
        self.global_writes.append(settings)
        return {"settings_applied": settings, "errors": []}


class FakeWindows:
    def __init__(self, before: dict, after: dict | None = None) -> None:
        self._flags = dict(before)
        self._after = after
        self.applied: list[dict] = []

    def get_windowed_vrr_flags(self) -> dict:
        return dict(self._flags)

    def apply(self, settings: dict) -> dict:
        self.applied.append(settings)
        if self._after is not None:
            self._flags = dict(self._after)
        else:
            self._flags.update({k: bool(v) for k, v in settings.items()})
        return {"success": True, "applied": list(settings)}


# --------------------------------------------------------------------------- #
# extract / intent detection
# --------------------------------------------------------------------------- #
class TestExtract:
    def test_borderless_gsync_intent(self) -> None:
        e = extract_vrr_enablers(GSYNC_HDR_MAP)
        assert e.global_vrr_mode == "fullscreen_and_windowed"
        assert e.windowed_optimizations is True
        assert e.vrr_optimize is True
        assert e.wants_windowed_vrr is True

    def test_no_sync_profile_is_not_windowed_vrr(self) -> None:
        e = extract_vrr_enablers(NO_SYNC_MAP)
        assert e.global_vrr_mode == "off"
        assert e.wants_windowed_vrr is False

    def test_global_gsync_bool_maps_to_fullscreen_only(self) -> None:
        e = extract_vrr_enablers({"NvidiaSettingsHandler": {"global_gsync": True}})
        assert e.global_vrr_mode == "fullscreen_only"
        assert e.wants_windowed_vrr is False

    def test_empty_map(self) -> None:
        assert extract_vrr_enablers({}).wants_windowed_vrr is False

    def test_windowed_flag_alone_counts(self) -> None:
        e = VrrEnablers(windowed_optimizations=True)
        assert e.wants_windowed_vrr is True


# --------------------------------------------------------------------------- #
# reconcile
# --------------------------------------------------------------------------- #
class TestReconcile:
    def test_no_windowed_vrr_intent_is_noop(self) -> None:
        drs = FakeDRS([1])
        out = reconcile_vrr_enablers(
            NO_SYNC_MAP, drs_factory=lambda: drs, windows_factory=lambda: FakeWindows({})
        )
        assert out["ran"] is False
        assert drs.global_writes == []

    def test_reasserts_dropped_nvidia_vrr_mode(self) -> None:
        # Live driver dropped to fullscreen-only (1); write should restore to 2.
        drs = FakeDRS([1, 2])
        win = FakeWindows(
            {"windowed_optimizations": True, "vrr_optimize": True}
        )
        out = reconcile_vrr_enablers(
            GSYNC_HDR_MAP, drs_factory=lambda: drs, windows_factory=lambda: win
        )
        assert out["ran"] is True
        assert out["verified"] is True
        assert drs.global_writes == [{"vrr_mode": "fullscreen_and_windowed"}]
        assert any("NVIDIA global vrr_mode" in r for r in out["reasserted"])

    def test_nvidia_already_correct_is_noop(self) -> None:
        drs = FakeDRS([2])  # already fullscreen_and_windowed
        out = reconcile_vrr_enablers(
            GSYNC_HDR_MAP,
            drs_factory=lambda: drs,
            windows_factory=lambda: FakeWindows(
                {"windowed_optimizations": True, "vrr_optimize": True}
            ),
        )
        assert drs.global_writes == []
        assert all("NVIDIA" not in r for r in out["reasserted"])
        assert out["verified"] is True

    def test_nvidia_persist_failure_is_flagged(self) -> None:
        drs = FakeDRS([1, 1])  # write didn't stick
        out = reconcile_vrr_enablers(
            GSYNC_HDR_MAP,
            drs_factory=lambda: drs,
            windows_factory=lambda: FakeWindows(
                {"windowed_optimizations": True, "vrr_optimize": True}
            ),
        )
        assert out["verified"] is False
        assert any("did not persist" in w for w in out["warnings"])

    def test_reasserts_dropped_windows_flags(self) -> None:
        win = FakeWindows({"windowed_optimizations": False, "vrr_optimize": False})
        out = reconcile_vrr_enablers(
            GSYNC_HDR_MAP, drs_factory=lambda: FakeDRS([2]), windows_factory=lambda: win
        )
        assert win.applied  # a write happened
        assert out["verified"] is True
        assert any("windowed_optimizations" in r for r in out["reasserted"])
        assert any("vrr_optimize" in r for r in out["reasserted"])

    def test_windows_already_correct_is_noop(self) -> None:
        win = FakeWindows({"windowed_optimizations": True, "vrr_optimize": True})
        out = reconcile_vrr_enablers(
            GSYNC_HDR_MAP, drs_factory=lambda: FakeDRS([2]), windows_factory=lambda: win
        )
        assert win.applied == []
        assert out["verified"] is True

    def test_windows_persist_failure_is_flagged(self) -> None:
        win = FakeWindows(
            {"windowed_optimizations": False, "vrr_optimize": False},
            after={"windowed_optimizations": False, "vrr_optimize": False},
        )
        out = reconcile_vrr_enablers(
            GSYNC_HDR_MAP, drs_factory=lambda: FakeDRS([2]), windows_factory=lambda: win
        )
        assert out["verified"] is False
        assert any("did not persist" in w for w in out["warnings"])

    def test_unavailable_nvidia_is_silent(self) -> None:
        def boom() -> object:
            raise RuntimeError("NVAPI not available")

        out = reconcile_vrr_enablers(
            GSYNC_HDR_MAP,
            drs_factory=boom,
            windows_factory=lambda: FakeWindows(
                {"windowed_optimizations": True, "vrr_optimize": True}
            ),
        )
        # Missing subsystem must not pollute warnings or flip verified.
        assert out["warnings"] == []
        assert out["verified"] is True

    def test_full_drop_both_reasserted(self) -> None:
        drs = FakeDRS([1, 2])
        win = FakeWindows({"windowed_optimizations": False, "vrr_optimize": False})
        out = reconcile_vrr_enablers(
            GSYNC_HDR_MAP, drs_factory=lambda: drs, windows_factory=lambda: win
        )
        assert out["verified"] is True
        assert len(out["reasserted"]) == 3  # nvidia + 2 windows flags
