"""YAML template generation for user-created profiles."""

from __future__ import annotations

from collections.abc import Sequence

import yaml


def base_to_preset(base: str) -> str:
    """Map a base template name to a sensible default NVIDIA preset."""
    return {
        "competitive_fps": "no_sync_fighting_game",
        "reflex_shooter": "reflex_game",
        "emulator": "no_sync_fighting_game",
        "browser": "vrr_optimal",
        "balanced": "vrr_optimal",
    }.get(base, "vrr_optimal")


def build_user_profile_yaml_template(
    *,
    profile_id: str,
    game: str,
    exe: Sequence[str],
    base: str,
    category: str,
) -> str:
    """Build the starter YAML for a user profile."""
    game_comment = _one_line_text(game)
    game_value = _yaml_quoted_scalar(game)
    exe_list = "\n".join(f"  - {_yaml_quoted_scalar(e)}" for e in exe)
    description = _yaml_quoted_scalar(f"Custom optimization profile for {game}")
    tray_subtitle = _yaml_quoted_scalar(f"Custom | {game}")

    return f"""# ABSO User Profile: {game_comment}
# Created by: abso profile-create
# Documentation: https://github.com/your-repo/abso/docs/profiles.md

profile_id: {_yaml_quoted_scalar(profile_id)}
display_name: {game_value}
description: {description}
optimization_target: "minimum_latency"
executable_hints:
{exe_list}

# Base template - inherits sensible defaults
# Options: competitive_fps, reflex_shooter, emulator, browser, balanced
base: {_yaml_quoted_scalar(base)}

# Profile metadata (optional)
# metadata:
#   is_online_profile: false
#   graphics_api: dx12
#   is_sdr_only: true

# Settings overrides - only include handlers you want to customize
# Full list: WindowsSettingsHandler, NvidiaSettingsHandler, PowerSettingsHandler,
#            RegistrySettingsHandler, NetworkSettingsHandler, MouseSettingsHandler,
#            GraphicsSettingsHandler, ServicesSettingsHandler, ProcessPriorityHandler,
#            ColorProfileSettingsHandler
settings:
  NvidiaSettingsHandler:
    preset: {_yaml_quoted_scalar(base_to_preset(base))}
  WindowsSettingsHandler:
    max_refresh_rate: true

# Tray app appearance
tray_category: {_yaml_quoted_scalar(category)}
tray_subtitle: {tray_subtitle}
sync_mode: "off"

# In-game settings recommendations (shown after profile apply)
# in_game_settings:
#   - category: Video
#     setting: V-Sync
#     value: "Off"
#     reason: "Driver handles sync"
"""


def _one_line_text(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _yaml_quoted_scalar(value: object) -> str:
    """Return a one-line quoted YAML scalar."""
    return yaml.safe_dump(
        _one_line_text(value),
        default_style='"',
        allow_unicode=False,
    ).strip()
