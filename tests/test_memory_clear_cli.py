"""The manual cache-purge CLI must propagate native failure to clients."""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from abso.main import cli


@pytest.mark.parametrize("success", [True, False])
def test_memory_clear_json_reports_actual_purge_result(success):
    with (
        patch("abso.main.is_admin", return_value=True),
        patch("abso.settings.standby_list.StandbyListHandler") as handler,
    ):
        handler.return_value.detect.side_effect = [
            {"available_mb": 2048, "memory_load_percent": 50},
            {"available_mb": 2040, "memory_load_percent": 50},
        ]
        handler.return_value.clear_standby_list.return_value = success
        result = CliRunner().invoke(cli, ["memory-clear", "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == (0 if success else 1)
    assert payload["success"] is success
    if success:
        assert payload["data"]["success"] is True
        assert payload["data"]["available_delta_mb"] == -8
    else:
        assert payload["data"] is None
        assert "Failed to purge" in payload["error"]
