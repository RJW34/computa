"""Tests for shared settings value parsing helpers."""

from __future__ import annotations

import pytest

from abso.settings.value_parsing import parse_bool_like


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (2.0, True),
        ("1", True),
        ("0", False),
        ("true", True),
        ("false", False),
        ("YES", True),
        ("no", False),
        (" on ", True),
        (" off ", False),
    ],
)
def test_parse_bool_like_accepts_common_bool_values(value, expected) -> None:
    assert parse_bool_like(value) is expected


@pytest.mark.parametrize("value", ["", "maybe", object(), None])
def test_parse_bool_like_rejects_unsupported_values(value) -> None:
    assert parse_bool_like(value) is None
