"""Tests for hardware detect payload helpers."""

from types import SimpleNamespace

from abso.core.hardware_summary import (
    bios_info_to_payload,
    build_detect_payload,
    infer_cpu_topology,
)


def test_infer_cpu_topology_for_14th_gen_hybrid_cpu():
    assert infer_cpu_topology(
        {
            "name": "Intel(R) Core(TM) i9-14900F",
            "cores": 24,
            "threads": 32,
        }
    ) == {"type": "hybrid", "p_cores": 8, "e_cores": 16}


def test_infer_cpu_topology_does_not_invent_split_without_smt():
    for name in ("Intel Core i9-14900F", "Intel Core Ultra 9 285K"):
        assert infer_cpu_topology(
            {"name": name, "cores": 24, "threads": 24}
        ) == {"type": "hybrid"}


def test_infer_cpu_topology_rejects_impossible_thread_count():
    assert infer_cpu_topology(
        {"name": "Intel Core i9-14900F", "cores": 24, "threads": 64}
    ) == {"type": "hybrid"}


def test_infer_cpu_topology_for_homogeneous_cpu():
    assert infer_cpu_topology(
        {
            "name": "AMD Ryzen 7 7800X3D",
            "cores": 8,
            "threads": 16,
        }
    ) == {"type": "homogeneous"}


def test_infer_cpu_topology_handles_missing_or_unusable_data():
    assert infer_cpu_topology(None) is None
    assert infer_cpu_topology({"name": "Unknown", "cores": None, "threads": None}) is None
    assert infer_cpu_topology({"name": "Intel Core Ultra", "cores": 0, "threads": 0}) is None


def test_bios_info_to_payload_preserves_detect_contract():
    bios_info = SimpleNamespace(
        rebar_status="enabled",
        memory_profile="xmp_enabled",
        rated_speed_mhz=6000,
        current_speed_mhz=6000,
        vbs_status="enabled",
        memory_integrity="disabled",
        secure_boot="enabled",
        tpm_present=True,
        tpm_version="2.0",
    )

    assert bios_info_to_payload(bios_info) == {
        "rebar_status": "enabled",
        "xmp_status": "xmp_enabled",
        "xmp_rated_mhz": 6000,
        "xmp_current_mhz": 6000,
        "vbs_status": "enabled",
        "memory_integrity": "disabled",
        "secure_boot": "enabled",
        "tpm_present": True,
        "tpm_version": "2.0",
    }


def test_build_detect_payload_handles_optional_sections():
    payload = build_detect_payload(
        {
            "system": {"manufacturer": "MSI"},
            "gpu": None,
            "cpu": {"name": "Intel(R) Core(TM) i9-14900F", "cores": 24, "threads": 32},
            "ram": None,
            "monitors": None,
        },
        bios_info=None,
        is_admin=False,
    )

    assert payload == {
        "system": {"manufacturer": "MSI"},
        "gpu": None,
        "cpu": {"name": "Intel(R) Core(TM) i9-14900F", "cores": 24, "threads": 32},
        "cpu_topology": {"type": "hybrid", "p_cores": 8, "e_cores": 16},
        "ram_gb": None,
        "monitors": [],
        "is_admin": False,
        "bios": None,
    }
