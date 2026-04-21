"""Tests for DiagnosticsSettingsHandler."""

from __future__ import annotations

from unittest.mock import patch

from abso.settings.diagnostics import DiagnosticsSettingsHandler


def _make_handler_with_stub_detect(**overrides):
    defaults = {
        "gpu_preferences": None,
        "background_capture_enabled": None,
        "active_downloads": {},
        "running_overlays": [],
        "nvidia_driver": None,
        "memory_profile": None,
        "resizable_bar": None,
        "directstorage": None,
        "display_topology": None,
    }
    defaults.update(overrides)
    handler = DiagnosticsSettingsHandler()
    return handler, defaults


def test_audit_flags_background_capture() -> None:
    handler, detect = _make_handler_with_stub_detect(background_capture_enabled=True)
    with patch.object(handler, "detect", return_value=detect):
        issues = handler.audit()
    titles = [i.title for i in issues]
    assert any("Background game recording" in t for t in titles)


def test_audit_flags_system_default_gpu_preference() -> None:
    prefs = {"C:\\Games\\foo.exe": "GpuPreference=0;"}
    handler, detect = _make_handler_with_stub_detect(gpu_preferences=prefs)
    with patch.object(handler, "detect", return_value=detect):
        issues = handler.audit()
    titles = [i.title for i in issues]
    assert any("system-default GPU preference" in t for t in titles)


def test_audit_quiet_when_no_issues() -> None:
    handler, detect = _make_handler_with_stub_detect()
    with patch.object(handler, "detect", return_value=detect):
        issues = handler.audit()
    assert issues == []


def test_audit_flags_mixed_refresh_multi_monitor() -> None:
    topology = {"count": 2, "refresh_rates": [60.0, 300.0]}
    handler, detect = _make_handler_with_stub_detect(display_topology=topology)
    with patch.object(handler, "detect", return_value=detect):
        issues = handler.audit()
    assert any("Mixed refresh rates" in i.title for i in issues)


def test_audit_flags_disabled_resizable_bar() -> None:
    handler, detect = _make_handler_with_stub_detect(resizable_bar=False)
    with patch.object(handler, "detect", return_value=detect):
        issues = handler.audit()
    assert any("Resizable BAR is disabled" in i.title for i in issues)


def test_audit_flags_old_driver_branch() -> None:
    handler, detect = _make_handler_with_stub_detect(
        nvidia_driver={"driver_version": "470.82"}
    )
    with patch.object(handler, "detect", return_value=detect):
        issues = handler.audit()
    assert any("older than recommended" in i.title for i in issues)


def test_audit_skips_modern_driver_branch() -> None:
    handler, detect = _make_handler_with_stub_detect(
        nvidia_driver={"driver_version": "560.70"}
    )
    with patch.object(handler, "detect", return_value=detect):
        issues = handler.audit()
    assert not any("older than recommended" in i.title for i in issues)


def test_audit_flags_ram_below_rated_speed() -> None:
    profile = {
        "rated_speeds_mhz": [6000, 6000],
        "configured_speeds_mhz": [4800, 4800],
    }
    handler, detect = _make_handler_with_stub_detect(memory_profile=profile)
    with patch.object(handler, "detect", return_value=detect):
        issues = handler.audit()
    assert any("RAM appears to be running below" in i.title for i in issues)


def test_audit_flags_no_nvme_for_directstorage() -> None:
    handler, detect = _make_handler_with_stub_detect(
        directstorage={"runtime_present": True, "nvme_present": False}
    )
    with patch.object(handler, "detect", return_value=detect):
        issues = handler.audit()
    assert any("No NVMe SSD detected" in i.title for i in issues)


def test_apply_is_noop() -> None:
    handler = DiagnosticsSettingsHandler()
    result = handler.apply({"anything": True})
    assert result["success"] is True
    assert result["requires_reboot"] is False
    assert result["applied"] == []
