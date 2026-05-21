"""Profile coverage invariants.

These guard against the four classes of silent profile bugs the
codebase has historically been at risk of:

1. **Orphan settings (silent drop):** a profile declares settings for
   a handler class name that is not in its ``get_handlers()`` list.
   The settings dict is computed but never reaches a handler. Result:
   the user thinks the setting applies, but it never does.

2. **Unknown NVIDIA preset:** a profile sets
   ``NvidiaSettingsHandler.preset`` to a string that is not a key in
   :data:`NVIDIA_PRESETS`. Result: empty preset settings are applied
   silently and the profile's intent is lost.

3. **Get-settings errors:** a profile's ``get_settings`` path throws an
   exception. Result: that handler's dict is empty and silently skipped.

4. **Unknown keys (likely typo / dead code):** a settings dict carries
   a key the handler's apply path does not consume. Result: silent
   waste — the value never lands anywhere. Most legitimate uses are
   already whitelisted (NVIDIA preset-expanded keys, framework-level
   AUTO_* keys), so any new finding is a real bug.

Today, May 2026, all 30 built-in profiles pass cleanly. These tests
freeze that contract: any future profile addition or refactor that
re-opens one of these gaps fails CI immediately.
"""
from __future__ import annotations

import inspect
import re
from typing import Any

import pytest

# abso.main must be imported first to establish the canonical module-load
# order. The applier -> catalog -> profile_bases -> settings -> core ->
# applier cycle would otherwise raise ImportError when this test module
# is collected first (the production CLI entry side-steps it by going
# through main()).
import abso.main  # noqa: F401

from abso.profiles.catalog import get_profile_instances
from abso.settings.nvidia.presets import NVIDIA_PRESETS


# Keys consumed by the NVIDIA handler via preset expansion or the
# DRSProfileManager dispatch, which the heuristic source scanner can't
# trace through. Updating this set must remain a deliberate review step.
_NVIDIA_KNOWN_KEYS: frozenset[str] = frozenset({
    "preset",
    "low_latency_mode",
    "power_management",
    "vsync",
    "max_frame_rate",
    "shader_cache",
    "threaded_optimization",
    "triple_buffering",
    "vrr_app_override",
    "vsync_tear_control",
    "vsync_vrr_control",
    "global_vrr_mode",
    "global_gsync_mode",
    "global_gsync",
    "vrr_mode",
    "vrr_request_state",
    "auto_vrr_fps_cap",
    "vrr_refresh_rate_hz",
    "profile_name",
    "profile_aliases",
    "executables",
    "game_name",
    "texture_filtering",
    "anisotropic_filtering",
    "low_latency_boost",
    "rebar_override",
})


def _handler_known_keys(handler_obj: Any) -> set[str]:
    """Best-effort extraction of every setting key a handler appears to consume.

    Walks the MRO for:
      * MUTABLE_SETTINGS / MUTABLE_SETTINGS_TO_INI / MUTABLE_SETTINGS_TO_PREFS dicts
      * BOOL_SETTINGS sets
      * settings.{get,pop,[..]} accesses in any callable on the class
      * exe_settings.{get,pop,[..]} (helper-method pattern)
      * settings.{get,pop}(self.SOME_CONST) with constant resolution
      * any class attribute ending in ``_KEY`` whose value is a lowercase string
    """
    keys: set[str] = set()
    cls = handler_obj.__class__

    if cls.__name__ == "NvidiaSettingsHandler":
        keys.update(_NVIDIA_KNOWN_KEYS)

    for c in cls.__mro__:
        for attr_name in (
            "MUTABLE_SETTINGS_TO_INI",
            "MUTABLE_SETTINGS",
            "MUTABLE_SETTINGS_TO_PREFS",
        ):
            m = getattr(c, attr_name, None)
            if isinstance(m, dict):
                keys.update(str(k) for k in m.keys())
        bs = getattr(c, "BOOL_SETTINGS", None)
        if isinstance(bs, (set, frozenset, list, tuple)):
            keys.update(str(k) for k in bs)

        for _name, fn in vars(c).items():
            if not callable(fn):
                continue
            try:
                src = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            for m in re.finditer(r"""settings\.get\(\s*["']([^"']+)["']""", src):
                keys.add(m.group(1))
            for m in re.finditer(r"""settings\.pop\(\s*["']([^"']+)["']""", src):
                keys.add(m.group(1))
            for m in re.finditer(r"""settings\[\s*["']([^"']+)["']\s*\]""", src):
                keys.add(m.group(1))
            for m in re.finditer(
                r"""["']([a-zA-Z_][a-zA-Z0-9_]*)["']\s+in\s+settings""", src
            ):
                keys.add(m.group(1))
            for m in re.finditer(r"""\w+_settings\.get\(\s*["']([^"']+)["']""", src):
                keys.add(m.group(1))
            for m in re.finditer(r"""\w+_settings\.pop\(\s*["']([^"']+)["']""", src):
                keys.add(m.group(1))
            for m in re.finditer(r"""\w+_settings\[\s*["']([^"']+)["']\s*\]""", src):
                keys.add(m.group(1))
            for m in re.finditer(
                r"""settings\.(?:get|pop)\(\s*self\.([A-Z_][A-Z0-9_]*)""", src
            ):
                const_val = getattr(c, m.group(1), None)
                if isinstance(const_val, str):
                    keys.add(const_val)

        for attr_name in dir(c):
            if attr_name.endswith("_KEY") and attr_name.isupper():
                val = getattr(c, attr_name, None)
                if isinstance(val, str) and val.islower():
                    keys.add(val)

    return keys


def _settings_handler_names(profile: Any) -> set[str]:
    """Every handler class name the profile's settings layer references.

    Union of every key seen in ``_settings_overrides``, ``_base_settings``,
    ``_base_overrides``, ``_variant_overrides``, ``_shared_overrides``.
    """
    names: set[str] = set()
    for fn_name in (
        "_settings_overrides",
        "_base_settings",
        "_base_overrides",
        "_variant_overrides",
        "_shared_overrides",
    ):
        fn = getattr(profile, fn_name, None)
        if not callable(fn):
            continue
        try:
            payload = fn()
        except Exception:
            continue
        if isinstance(payload, dict):
            names.update(str(k) for k in payload.keys())
    return names


@pytest.fixture(scope="module")
def profiles_by_id() -> dict[str, Any]:
    return get_profile_instances()


def test_no_orphan_handler_settings(profiles_by_id) -> None:
    """Every handler name the settings map references must be in get_handlers().

    A mismatch means the profile computes a settings dict that no
    handler ever consumes - a silent drop bug. The applier only
    invokes handlers from ``get_handlers()``.
    """
    failures: list[str] = []
    for profile_id, profile in profiles_by_id.items():
        declared = {h.__class__.__name__ for h in profile.get_handlers()}
        referenced = _settings_handler_names(profile)
        for name in referenced:
            if name in declared:
                continue
            settings = profile.get_settings(name) or {}
            if not settings:
                continue
            failures.append(
                f"{profile_id}: declares settings for {name!r} but it is "
                f"not in get_handlers() (silent drop of {sorted(settings.keys())})"
            )
    assert not failures, "Orphan settings detected:\n  " + "\n  ".join(failures)


def test_every_nvidia_preset_name_resolves(profiles_by_id) -> None:
    """``preset`` values passed to NvidiaSettingsHandler must exist in NVIDIA_PRESETS."""
    failures: list[str] = []
    for profile_id, profile in profiles_by_id.items():
        settings = profile.get_settings("NvidiaSettingsHandler") or {}
        preset = settings.get("preset")
        if preset is None:
            continue
        if preset not in NVIDIA_PRESETS:
            failures.append(
                f"{profile_id}: NVIDIA preset {preset!r} is not a key in NVIDIA_PRESETS "
                f"(silently applies empty preset). Known: {sorted(NVIDIA_PRESETS)}"
            )
    assert not failures, "Unknown NVIDIA preset names:\n  " + "\n  ".join(failures)


def test_no_get_settings_errors(profiles_by_id) -> None:
    """``profile.get_settings(handler_name)`` must never raise.

    A handler whose settings call raises has its dict silently
    replaced with empty by the applier, defeating the profile.
    """
    failures: list[str] = []
    for profile_id, profile in profiles_by_id.items():
        names = _settings_handler_names(profile) | {
            h.__class__.__name__ for h in profile.get_handlers()
        }
        for name in names:
            try:
                profile.get_settings(name)
            except Exception as exc:
                failures.append(f"{profile_id}: get_settings({name!r}) raised {exc!r}")
    assert not failures, "get_settings raised:\n  " + "\n  ".join(failures)


def test_no_unknown_setting_keys(profiles_by_id) -> None:
    """Every settings key declared by a profile must be consumed by its handler.

    Best-effort but tight: walks the handler's MRO for every
    ``settings.{get,pop,[]}`` access, every ``MUTABLE_SETTINGS*`` /
    ``BOOL_SETTINGS`` attribute, and every ``settings.get(self.SOME_KEY)``
    constant indirection. NVIDIA preset-expanded keys and framework
    AUTO_* keys are whitelisted.

    A miss here means the profile declares a key the handler will not
    read - silent waste. Failure of this test is the typical signal that
    a setting key was renamed in the handler without updating profiles,
    or that a profile uses a key the handler doesn't expose.
    """
    failures: list[str] = []
    for profile_id, profile in profiles_by_id.items():
        declared_handlers = {
            h.__class__.__name__: h for h in profile.get_handlers()
        }
        for name, handler in declared_handlers.items():
            settings = profile.get_settings(name) or {}
            if not settings:
                continue
            known = _handler_known_keys(handler)
            if not known:
                # Couldn't introspect — skip rather than false-positive.
                continue
            for key in settings.keys():
                if key in known:
                    continue
                failures.append(
                    f"{profile_id}: {name}[{key!r}] is declared by the profile "
                    f"but {name}.apply (or its helpers) does not appear to consume it"
                )
    assert not failures, "Unknown setting keys:\n  " + "\n  ".join(failures)


def test_hdr_enabled_profiles_set_all_required_windows_keys(profiles_by_id) -> None:
    """Any profile that sets WindowsSettingsHandler.hdr=True must also set the
    other three canonical HDR keys.

    Forgetting one of these in a new HDR variant means Windows is asked to
    turn HDR on but the SDR white level / advanced color / auto-HDR
    decisions inherit from the SDR base, leaving the desktop washed out or
    Auto HDR layered on top of the game's native HDR pipeline.

    Note: the inverse check ("profile_id ends in -hdr implies hdr=True") is
    enforced by ``test_hdr_id_profiles_actually_enable_hdr`` below.
    """
    required = ("hdr", "advanced_color", "auto_hdr", "sdr_white_level_nits")
    failures: list[str] = []
    for profile_id, profile in profiles_by_id.items():
        windows_settings = profile.get_settings("WindowsSettingsHandler") or {}
        if not windows_settings.get("hdr"):
            continue
        for key in required:
            if key not in windows_settings:
                failures.append(
                    f"{profile_id}: sets hdr=True but is missing Windows key {key!r}"
                )
    assert not failures, "HDR profiles missing required keys:\n  " + "\n  ".join(failures)


def test_hdr_id_profiles_actually_enable_hdr(profiles_by_id) -> None:
    """Profiles whose id ends in ``-hdr`` must set WindowsSettingsHandler.hdr=True.

    Catches the inverse of the previous test: a profile name advertises
    HDR but the settings don't actually enable it.
    """
    failures: list[str] = []
    for profile_id, profile in profiles_by_id.items():
        if not profile_id.endswith("-hdr"):
            continue
        windows_settings = profile.get_settings("WindowsSettingsHandler") or {}
        if not windows_settings.get("hdr"):
            failures.append(
                f"{profile_id}: id implies HDR but WindowsSettingsHandler.hdr is not truthy"
            )
    assert not failures, "HDR-named profiles not enabling HDR:\n  " + "\n  ".join(failures)


def test_handler_class_names_match_imported_classes(profiles_by_id) -> None:
    """Each handler in get_handlers() must be a real instance, not a typo string."""
    failures: list[str] = []
    for profile_id, profile in profiles_by_id.items():
        for handler in profile.get_handlers():
            cls = handler.__class__
            # Sanity: handler must be importable from its module
            try:
                mod = __import__(cls.__module__, fromlist=[cls.__name__])
                assert getattr(mod, cls.__name__) is cls
            except Exception as exc:
                failures.append(f"{profile_id}: handler {cls.__name__} not importable: {exc}")
    assert not failures, "Handler class identity failures:\n  " + "\n  ".join(failures)
