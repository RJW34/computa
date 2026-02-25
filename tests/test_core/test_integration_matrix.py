"""Contract tests for integration test matrix manifest."""

from __future__ import annotations

import json
from pathlib import Path

from abso.profiles.catalog import PROFILE_CATALOG

MATRIX_PATH = Path("abso/core/manifests/integration_test_matrix.json")


def test_integration_matrix_has_required_schema() -> None:
    data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    assert isinstance(data.get("version"), int)
    scenarios = data.get("scenarios")
    assert isinstance(scenarios, list)
    assert scenarios, "integration matrix must include at least one scenario"

    ids: set[str] = set()
    for scenario in scenarios:
        assert isinstance(scenario.get("id"), str) and scenario["id"]
        assert isinstance(scenario.get("profile_id"), str) and scenario["profile_id"]
        assert scenario["id"] not in ids
        ids.add(scenario["id"])
        expected = scenario.get("expected")
        assert isinstance(expected, dict)
        assert expected.get("transaction_state") in {"committed", "failed", "rolled_back"}
        assert isinstance(expected.get("apply_success"), bool)


def test_integration_matrix_covers_all_registered_profiles() -> None:
    data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    scenarios = data.get("scenarios", [])
    covered_profiles = {s["profile_id"] for s in scenarios if "profile_id" in s}
    catalog_profiles = set(PROFILE_CATALOG.keys())

    assert catalog_profiles.issubset(covered_profiles), (
        "Integration matrix is missing profile coverage for: "
        + ", ".join(sorted(catalog_profiles - covered_profiles))
    )
