"""Helpers for shaping hardware detection output."""

from __future__ import annotations

from typing import Any


def detect_bios_info() -> Any | None:
    """Best-effort BIOS detection for CLI/GUI hardware summaries."""
    try:
        from abso.core.bios_detector import BiosDetector

        return BiosDetector().detect_all()
    except Exception:
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def infer_cpu_topology(cpu_data: dict[str, Any] | None) -> dict[str, int | str] | None:
    """Infer CPU topology from WMI-style CPU name/core/thread data."""
    if not cpu_data:
        return None

    cpu_name = str(cpu_data.get("name", "")).lower()
    core_count = _as_int(cpu_data.get("cores", 0))
    thread_count = _as_int(cpu_data.get("threads", 0))
    is_hybrid = (
        "12th gen" in cpu_name
        or "13th gen" in cpu_name
        or "14th gen" in cpu_name
        or (
            any(tag in cpu_name for tag in ["core ultra", "-12", "-13", "-14"])
            and ("intel" in cpu_name or "core" in cpu_name)
        )
    )

    if is_hybrid and core_count > 0 and thread_count > 0:
        # With SMT on P-cores only: C = P + E, T = 2P + E.
        # Equal counts (SMT disabled, or non-SMT Core Ultra) cannot establish
        # the split from WMI totals; do not invent an all-P-core topology.
        p_cores = thread_count - core_count
        e_cores = core_count - p_cores
        if "core ultra" not in cpu_name and p_cores > 0 and e_cores >= 0:
            return {"type": "hybrid", "p_cores": p_cores, "e_cores": e_cores}
        return {"type": "hybrid"}

    if core_count > 0:
        return {"type": "homogeneous"}

    return None


def bios_info_to_payload(bios_info: Any | None) -> dict[str, Any] | None:
    """Convert BiosInfo-like objects to the detect JSON contract."""
    if not bios_info:
        return None

    return {
        "rebar_status": bios_info.rebar_status,
        "xmp_status": bios_info.memory_profile,
        "xmp_rated_mhz": bios_info.rated_speed_mhz,
        "xmp_current_mhz": bios_info.current_speed_mhz,
        "vbs_status": bios_info.vbs_status,
        "memory_integrity": bios_info.memory_integrity,
        "secure_boot": bios_info.secure_boot,
        "tpm_present": bios_info.tpm_present,
        "tpm_version": bios_info.tpm_version,
    }


def build_detect_payload(
    hardware: dict[str, Any],
    *,
    bios_info: Any | None,
    is_admin: bool,
) -> dict[str, Any]:
    """Build the stable JSON payload for `abso detect --json`."""
    return {
        "system": hardware.get("system"),
        "gpu": hardware.get("gpu"),
        "cpu": hardware.get("cpu"),
        "cpu_topology": infer_cpu_topology(hardware.get("cpu")),
        "ram_gb": (hardware.get("ram") or {}).get("total_gb"),
        "monitors": hardware.get("monitors") or [],
        "is_admin": is_admin,
        "bios": bios_info_to_payload(bios_info),
    }
