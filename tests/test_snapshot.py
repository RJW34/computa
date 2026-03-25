"""Profile settings snapshot test.

Captures the exact handler list and settings dict every profile produces.
Used as a safety net during refactoring — any diff means the refactor
changed behavior. Run BEFORE and AFTER every structural change.

Usage:
    pytest tests/test_snapshot.py -v          # Verify against golden file
    pytest tests/test_snapshot.py --update    # Regenerate golden file
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

GOLDEN_FILE = Path(__file__).parent / "snapshot_golden.json"


def _build_snapshot() -> dict[str, Any]:
    """Build the current snapshot of all profile settings."""
    from abso.profiles.catalog import get_profile_classes

    snapshot: dict[str, Any] = {}
    for pid, cls in sorted(get_profile_classes().items()):
        profile = cls()
        handlers = [type(h).__name__ for h in profile.get_handlers()]
        settings = {}
        for handler_name in handlers:
            s = profile.get_settings(handler_name)
            # Convert any non-serializable values
            settings[handler_name] = _make_serializable(s)
        snapshot[pid] = {
            "handlers": handlers,
            "settings": settings,
            "display_name": profile.display_name,
            "optimization_target": profile.optimization_target,
            "is_online_profile": profile.is_online_profile,
            "is_emulator_profile": profile.is_emulator_profile,
            "requires_reflex": profile.requires_reflex,
            "is_sdr_only": profile.is_sdr_only,
            "network_scope": profile.network_scope,
            "graphics_api": profile.graphics_api,
            "allows_aggressive_settings": profile.allows_aggressive_settings,
            "include_legacy_tweaks": profile.include_legacy_tweaks,
        }
    return snapshot


def _make_serializable(obj: Any) -> Any:
    """Convert non-JSON-serializable values for snapshot comparison."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def test_profile_settings_snapshot() -> None:
    """Verify all profile settings match the golden snapshot.

    If the golden file doesn't exist, create it and skip (first run).
    On subsequent runs, compare against the golden file.
    """
    current = _build_snapshot()

    if not GOLDEN_FILE.exists():
        GOLDEN_FILE.write_text(
            json.dumps(current, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        pytest.skip(f"Golden file created at {GOLDEN_FILE} — run again to verify")

    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))

    # Compare profile IDs
    current_ids = set(current.keys())
    golden_ids = set(golden.keys())
    assert current_ids == golden_ids, (
        f"Profile ID mismatch.\n"
        f"  Added: {current_ids - golden_ids}\n"
        f"  Removed: {golden_ids - current_ids}"
    )

    # Compare each profile
    diffs: list[str] = []
    for pid in sorted(current_ids):
        cur = current[pid]
        gld = golden[pid]

        # Compare handler lists
        if cur["handlers"] != gld["handlers"]:
            diffs.append(
                f"{pid}: handlers changed\n"
                f"  was:  {gld['handlers']}\n"
                f"  now:  {cur['handlers']}"
            )

        # Compare settings per handler
        for handler in set(cur["settings"]) | set(gld.get("settings", {})):
            cur_s = cur["settings"].get(handler, {})
            gld_s = gld.get("settings", {}).get(handler, {})
            if cur_s != gld_s:
                # Find specific key differences
                all_keys = set(cur_s) | set(gld_s)
                for k in sorted(all_keys):
                    cv = cur_s.get(k)
                    gv = gld_s.get(k)
                    if cv != gv:
                        diffs.append(f"{pid}.{handler}.{k}: {gv!r} → {cv!r}")

        # Compare metadata
        for key in ["display_name", "optimization_target", "is_online_profile",
                     "is_emulator_profile", "requires_reflex", "is_sdr_only",
                     "network_scope", "graphics_api", "allows_aggressive_settings",
                     "include_legacy_tweaks"]:
            if cur.get(key) != gld.get(key):
                diffs.append(f"{pid}.{key}: {gld.get(key)!r} → {cur.get(key)!r}")

    assert not diffs, (
        f"Profile settings changed ({len(diffs)} diff(s)):\n"
        + "\n".join(f"  {d}" for d in diffs)
    )


def test_profile_count() -> None:
    """Verify the expected number of profiles are loaded."""
    from abso.profiles.catalog import get_profile_classes

    classes = get_profile_classes()
    assert len(classes) >= 28, f"Expected at least 28 profiles, got {len(classes)}"


if __name__ == "__main__":
    # Allow running directly to generate/update golden file
    if "--update" in sys.argv:
        snapshot = _build_snapshot()
        GOLDEN_FILE.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        print(f"Golden file updated: {GOLDEN_FILE} ({len(snapshot)} profiles)")
    else:
        # Print current snapshot for inspection
        snapshot = _build_snapshot()
        print(json.dumps(snapshot, indent=2, sort_keys=True, default=str))
