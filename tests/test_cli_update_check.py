"""Tests for the abso update-check command."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

from click.testing import CliRunner

from abso.main import _version_sort_key, cli


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _release_payload(tag: str) -> _FakeResponse:
    body = json.dumps(
        {"tag_name": tag, "html_url": f"https://example.test/releases/{tag}"}
    ).encode("utf-8")
    return _FakeResponse(body)


def test_version_sort_key_handles_prefixes_and_suffixes() -> None:
    assert _version_sort_key("1.2.3") == (1, 2, 3)
    assert _version_sort_key("10.0") > _version_sort_key("9.9.9")
    assert _version_sort_key("1.2.3-beta") == (1, 2, 3)


def test_update_check_reports_newer_release() -> None:
    runner = CliRunner()
    with (
        patch("urllib.request.urlopen", return_value=_release_payload("v99.0.0")),
        patch("abso.__version__.__version__", "1.1.0"),
    ):
        result = runner.invoke(cli, ["update-check", "--json"])

    assert result.exit_code == 0
    assert '"update_available": true' in result.output
    assert '"latest_version": "99.0.0"' in result.output


def test_update_check_reports_up_to_date() -> None:
    runner = CliRunner()
    with (
        patch("urllib.request.urlopen", return_value=_release_payload("v0.0.1")),
    ):
        result = runner.invoke(cli, ["update-check", "--json"])

    assert result.exit_code == 0
    assert '"update_available": false' in result.output


def test_update_check_honors_repo_override(monkeypatch) -> None:
    monkeypatch.setenv("ABSO_UPDATE_REPO", "someone/fork")
    captured: dict[str, str] = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        return _release_payload("v0.0.1")

    runner = CliRunner()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = runner.invoke(cli, ["update-check", "--json"])

    assert result.exit_code == 0
    assert captured["url"] == "https://api.github.com/repos/someone/fork/releases/latest"


def test_update_check_handles_missing_releases(monkeypatch) -> None:
    error = urllib.error.HTTPError(
        url="https://api.github.com/x", code=404, msg="Not Found", hdrs=None, fp=None
    )

    runner = CliRunner()
    with patch("urllib.request.urlopen", side_effect=error):
        result = runner.invoke(cli, ["update-check"])

    assert result.exit_code == 1
    assert "no releases published yet" in result.output
