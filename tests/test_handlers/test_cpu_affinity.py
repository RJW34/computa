"""Tests for CpuAffinityHandler AppCompat affinity persistence."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from abso.core.exceptions import RegistryWriteError
from abso.settings.cpu_affinity import CpuAffinityHandler


class TestCpuAffinityAppCompat:
    """Regression coverage for AppCompatFlags\\Layers token preservation."""

    def _patched_layers_registry(self):
        state: dict[str, str] = {}

        def open_or_create_key(_hive, path, *_args, **_kwargs):
            return ("FAKE_KEY", path)

        def query_value(_key, name):
            if name not in state:
                raise FileNotFoundError(name)
            return state[name], 1

        def set_value(_key, name, _reserved, _type, value):
            state[name] = value

        def delete_value(_key, name):
            if name not in state:
                raise FileNotFoundError(name)
            del state[name]

        return state, open_or_create_key, query_value, set_value, delete_value

    def test_set_affinity_preserves_dpi_and_fso_layers(self) -> None:
        state, open_key, query, setval, delval = self._patched_layers_registry()
        state["Overwatch.exe"] = "~ HIGHDPIAWARE DISABLEDXMAXIMIZEDWINDOWEDMODE"

        with (
            patch("abso.settings.cpu_affinity.winreg.CreateKey", open_key),
            patch("abso.settings.cpu_affinity.winreg.QueryValueEx", query),
            patch("abso.settings.cpu_affinity.winreg.SetValueEx", setval),
            patch("abso.settings.cpu_affinity.winreg.DeleteValue", delval),
            patch("abso.settings.cpu_affinity.winreg.CloseKey"),
        ):
            CpuAffinityHandler()._set_appcompat_affinity("Overwatch.exe", 0xFF)

        value = state["Overwatch.exe"]
        assert value.startswith("~ ")
        assert set(value.split()[1:]) == {
            "HIGHDPIAWARE",
            "DISABLEDXMAXIMIZEDWINDOWEDMODE",
            "PROCESSORAFFINITYMASK=FF",
        }

    def test_set_affinity_writes_appcompat_marker_for_new_entry(self) -> None:
        state, open_key, query, setval, delval = self._patched_layers_registry()

        with (
            patch("abso.settings.cpu_affinity.winreg.CreateKey", open_key),
            patch("abso.settings.cpu_affinity.winreg.QueryValueEx", query),
            patch("abso.settings.cpu_affinity.winreg.SetValueEx", setval),
            patch("abso.settings.cpu_affinity.winreg.DeleteValue", delval),
            patch("abso.settings.cpu_affinity.winreg.CloseKey"),
        ):
            CpuAffinityHandler()._set_appcompat_affinity("Overwatch.exe", 0xF)

        assert state["Overwatch.exe"] == "~ PROCESSORAFFINITYMASK=F"

    def test_set_affinity_aborts_on_non_missing_read_error(self) -> None:
        state, open_key, _query, setval, delval = self._patched_layers_registry()

        def flaky_query(_key, _name):
            err = OSError("access denied")
            err.winerror = 5
            raise err

        with (
            patch("abso.settings.cpu_affinity.winreg.CreateKey", open_key),
            patch("abso.settings.cpu_affinity.winreg.QueryValueEx", flaky_query),
            patch("abso.settings.cpu_affinity.winreg.SetValueEx", setval),
            patch("abso.settings.cpu_affinity.winreg.DeleteValue", delval),
            patch("abso.settings.cpu_affinity.winreg.CloseKey"),
            pytest.raises(RegistryWriteError),
        ):
            CpuAffinityHandler()._set_appcompat_affinity("Overwatch.exe", 0xFF)

        assert "Overwatch.exe" not in state

    def test_remove_affinity_preserves_dpi_and_fso_layers(self) -> None:
        state, open_key, query, setval, delval = self._patched_layers_registry()
        state["Overwatch.exe"] = (
            "~ HIGHDPIAWARE PROCESSORAFFINITYMASK=FF "
            "DISABLEDXMAXIMIZEDWINDOWEDMODE"
        )

        with (
            patch("abso.settings.cpu_affinity.winreg.OpenKey", open_key),
            patch("abso.settings.cpu_affinity.winreg.QueryValueEx", query),
            patch("abso.settings.cpu_affinity.winreg.SetValueEx", setval),
            patch("abso.settings.cpu_affinity.winreg.DeleteValue", delval),
            patch("abso.settings.cpu_affinity.winreg.CloseKey"),
        ):
            CpuAffinityHandler()._remove_appcompat_affinity("Overwatch.exe")

        value = state["Overwatch.exe"]
        assert value.startswith("~ ")
        assert set(value.split()[1:]) == {
            "HIGHDPIAWARE",
            "DISABLEDXMAXIMIZEDWINDOWEDMODE",
        }

    def test_remove_affinity_deletes_marker_only_value(self) -> None:
        state, open_key, query, setval, delval = self._patched_layers_registry()
        state["Overwatch.exe"] = "~ PROCESSORAFFINITYMASK=FF"

        with (
            patch("abso.settings.cpu_affinity.winreg.OpenKey", open_key),
            patch("abso.settings.cpu_affinity.winreg.QueryValueEx", query),
            patch("abso.settings.cpu_affinity.winreg.SetValueEx", setval),
            patch("abso.settings.cpu_affinity.winreg.DeleteValue", delval),
            patch("abso.settings.cpu_affinity.winreg.CloseKey"),
        ):
            CpuAffinityHandler()._remove_appcompat_affinity("Overwatch.exe")

        assert "Overwatch.exe" not in state

    def test_remove_affinity_raises_on_non_missing_read_error(self) -> None:
        _state, open_key, _query, setval, delval = self._patched_layers_registry()

        def flaky_query(_key, _name):
            err = OSError("access denied")
            err.winerror = 5
            raise err

        with (
            patch("abso.settings.cpu_affinity.winreg.OpenKey", open_key),
            patch("abso.settings.cpu_affinity.winreg.QueryValueEx", flaky_query),
            patch("abso.settings.cpu_affinity.winreg.SetValueEx", setval),
            patch("abso.settings.cpu_affinity.winreg.DeleteValue", delval),
            patch("abso.settings.cpu_affinity.winreg.CloseKey"),
            pytest.raises(RegistryWriteError),
        ):
            CpuAffinityHandler()._remove_appcompat_affinity("Overwatch.exe")
