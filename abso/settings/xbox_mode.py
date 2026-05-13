"""Xbox Mode settings handler (Win11 25H2 26200.8457+).

KB5089549 (May 2026) introduced **Xbox Mode** as the streamlined fullscreen
shell that Microsoft positions as the replacement for both classic Game
Mode and the Full Screen Experience. The rollout is feature-flag gated, so
the registry surface may be absent for an extended period even after the
underlying cumulative is installed.

This handler is **detect-only**: it reads candidate registry locations,
reports what (if anything) was found, and surfaces audit issues. The
``apply`` path raises ``NotImplementedError`` until the Phase 3 decision
matrix is wired up — that's intentional so profiles cannot accidentally
mutate state we haven't yet characterized end-to-end.

Backup/restore are no-ops because the handler does not mutate state.
``restore_guarantee`` therefore reports ``"none"`` so backup summaries do
not treat a skipped Xbox Mode restore as a blocking issue.
"""

from __future__ import annotations

import logging
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler
from abso.utils.os_release import detect_os_release
from abso.utils.registry import read_registry_dword, value_exists

logger = logging.getLogger(__name__)

# Minimum OS build/UBR that ships Xbox Mode keys. KB5089549 lifts 25H2 to
# 26200.8457 and 24H2 to 26100.8457. Anything earlier predates the feature.
_XBOX_MODE_MIN_BUILD = 26100
_XBOX_MODE_MIN_UBR = 8457

# Candidate registry paths. The rollout is feature-flag gated; Microsoft
# has not yet documented stable key names. Each candidate is probed until
# one yields a value. Names are educated guesses based on parallel features
# (Game Mode, Full Screen Experience). If none populate within a few
# cumulatives we revisit the list — see Phase 4.1 spike notes.
_XBOX_MODE_HKCU_CANDIDATES: tuple[tuple[str, str], ...] = (
    (r"Software\Microsoft\GameBar", "XboxModeEnabled"),
    (r"Software\Microsoft\GameBar", "UseXboxMode"),
    (r"Software\Microsoft\Xbox", "XboxModeEnabled"),
    (r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "XboxModeEnabled"),
)
_XBOX_MODE_HKLM_CANDIDATES: tuple[tuple[str, str], ...] = (
    (r"SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowXboxMode"),
    (r"SOFTWARE\Microsoft\GameBar", "XboxModeEnabled"),
)


class XboxModeSettingsHandler(SettingsHandler):
    """Reads (only) the Xbox Mode state when the feature is exposed."""

    def detect(self) -> dict[str, Any]:
        release = detect_os_release()
        if not release.at_least(_XBOX_MODE_MIN_BUILD, _XBOX_MODE_MIN_UBR):
            return {
                "build_supported": False,
                "feature_present": False,
                "xbox_mode_enabled": None,
                "source": None,
            }

        for subkey, value_name in _XBOX_MODE_HKCU_CANDIDATES:
            if value_exists(winreg.HKEY_CURRENT_USER, subkey, value_name):
                raw = read_registry_dword(
                    winreg.HKEY_CURRENT_USER, subkey, value_name
                )
                return {
                    "build_supported": True,
                    "feature_present": True,
                    "xbox_mode_enabled": bool(raw) if raw is not None else None,
                    "source": f"HKCU\\{subkey}\\{value_name}",
                }

        for subkey, value_name in _XBOX_MODE_HKLM_CANDIDATES:
            if value_exists(winreg.HKEY_LOCAL_MACHINE, subkey, value_name):
                raw = read_registry_dword(
                    winreg.HKEY_LOCAL_MACHINE, subkey, value_name
                )
                return {
                    "build_supported": True,
                    "feature_present": True,
                    "xbox_mode_enabled": bool(raw) if raw is not None else None,
                    "source": f"HKLM\\{subkey}\\{value_name}",
                }

        # Build is new enough but the feature flag hasn't lit up on this PC.
        return {
            "build_supported": True,
            "feature_present": False,
            "xbox_mode_enabled": None,
            "source": None,
        }

    def audit(self) -> list[Issue]:
        state = self.detect()
        if not state["build_supported"]:
            return []
        if not state["feature_present"]:
            # Feature flag hasn't lit up yet — surface as info so users know
            # the auditor is aware of the rollout but isn't acting on it.
            return [
                Issue(
                    title="Xbox Mode rollout not yet active",
                    severity="info",
                    current_value="Feature flag not yet present",
                    optimal_value="Pending Microsoft rollout",
                    explanation=(
                        "Build is new enough for Xbox Mode (the Game Mode + "
                        "Full Screen Experience successor) but Windows has "
                        "not enabled it on this device. ABSO will start "
                        "managing it once the registry surface appears."
                    ),
                    category="xbox_mode",
                )
            ]

        if state["xbox_mode_enabled"]:
            return [
                Issue(
                    title="Xbox Mode is enabled",
                    severity="info",
                    current_value="Xbox Mode on",
                    optimal_value="Profile-dependent (Reflex / capture lanes prefer off)",
                    explanation=(
                        "Xbox Mode replaces Game Mode + Full Screen "
                        "Experience with a streamlined shell. For Reflex "
                        "and capture-oriented profiles ABSO will recommend "
                        "leaving it off; the apply path will be wired in "
                        "the next phase."
                    ),
                    category="xbox_mode",
                )
            ]
        return []

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        # Phase 1: detect-only. The applier should not call us, but if a
        # profile mis-declares we surface a clear failure rather than
        # silently mutating an undocumented key.
        return {
            "success": False,
            "error": (
                "Xbox Mode apply path is not yet implemented — Phase 3 "
                "will wire the registry writes after the key surface is "
                "characterized on a feature-flagged device."
            ),
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        # Nothing to mutate; report success so backup summaries do not
        # treat this handler as failed.
        return True

    @property
    def restore_guarantee(self) -> str:
        # Detect-only handler has no state to restore.
        return "none"
