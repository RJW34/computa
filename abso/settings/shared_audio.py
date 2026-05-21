"""Shared Audio (Bluetooth LE Audio broadcast) handler.

Shared Audio is the Bluetooth LE Audio broadcast feature that lets one
Windows 11 PC stream the same audio to two paired LE Audio devices at the
same time. It surfaced in the Experimental (Future Platforms) Canary
29xxx track (build 29591.1000, May 15 2026) and has appeared in earlier
24H2 / 25H2 cumulative previews. The opt-in lives under
``Quick Settings > Shared audio``.

For ABSO's latency-sensitive profiles (Reflex shooters, Slippi, capture
lanes) the feature is relevant because:

* The Bluetooth LE Audio broadcast path keeps the BT radio active and
  may share the audio engine path that ABSO wants to keep on the wired
  ASIO/WASAPI shortest-route during play.
* Background discovery / pairing wake-ups can introduce jitter even
  when no broadcast is active.

Like :mod:`abso.settings.xbox_mode` and :mod:`abso.settings.ai_agents`
this is a **detect-only** handler. Microsoft has not published a stable
policy or per-user key name for the broadcast on/off state, so the
``apply`` path returns a clear "not yet implemented" error rather than
writing to undocumented keys. Backup/restore are no-ops and
``restore_guarantee`` is ``"none"`` so backup summaries do not treat a
skipped Shared Audio restore as a blocking issue.

When Microsoft documents the key surface (or community reverse
engineering confirms it on the Experimental Future Platforms branch),
flip ``apply()`` to a real registry write and add a latency-profile trait
that pins Shared Audio off during play.
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

# Floor build/UBR at which Shared Audio first appeared in the GA-track
# cumulative previews. 25H2 received it in the same KB5089549 family that
# brought Xbox Mode and AI agents; 24H2 received it at the parallel UBR.
_SHARED_AUDIO_MIN_BUILD = 26100
_SHARED_AUDIO_MIN_UBR = 8457

# Candidate registry surface. Microsoft has not documented a stable name,
# so each candidate is best-effort and probed until one yields a value.
# "Broadcast"/"LEAudio"/"SharedAudio" naming follows the parallel BT LE
# Audio rollout. If none populate we revisit during the apply-path spike.
_SHARED_AUDIO_HKCU_CANDIDATES: tuple[tuple[str, str], ...] = (
    (r"Software\Microsoft\Bluetooth\AudioGateway\SharedAudio", "Enabled"),
    (r"Software\Microsoft\Bluetooth\LEAudio\Broadcast", "SharedAudioEnabled"),
    (r"Software\Microsoft\Windows\CurrentVersion\Bluetooth\SharedAudio", "Enabled"),
)
_SHARED_AUDIO_HKLM_CANDIDATES: tuple[tuple[str, str], ...] = (
    (r"SOFTWARE\Policies\Microsoft\Bluetooth", "AllowSharedAudio"),
    (r"SOFTWARE\Policies\Microsoft\Bluetooth", "DisableSharedAudio"),
    (r"SOFTWARE\Microsoft\Bluetooth\AudioGateway\SharedAudio", "Enabled"),
)


class SharedAudioSettingsHandler(SettingsHandler):
    """Reads (only) the Shared Audio broadcast state when exposed."""

    def detect(self) -> dict[str, Any]:
        release = detect_os_release()
        if not release.at_least(_SHARED_AUDIO_MIN_BUILD, _SHARED_AUDIO_MIN_UBR):
            return {
                "build_supported": False,
                "feature_present": False,
                "shared_audio_enabled": None,
                "source": None,
                "release_branch": release.release_branch,
            }

        for subkey, value_name in _SHARED_AUDIO_HKCU_CANDIDATES:
            if value_exists(winreg.HKEY_CURRENT_USER, subkey, value_name):
                raw = read_registry_dword(
                    winreg.HKEY_CURRENT_USER, subkey, value_name
                )
                return {
                    "build_supported": True,
                    "feature_present": True,
                    "shared_audio_enabled": bool(raw) if raw is not None else None,
                    "source": f"HKCU\\{subkey}\\{value_name}",
                    "release_branch": release.release_branch,
                }

        for subkey, value_name in _SHARED_AUDIO_HKLM_CANDIDATES:
            if value_exists(winreg.HKEY_LOCAL_MACHINE, subkey, value_name):
                raw = read_registry_dword(
                    winreg.HKEY_LOCAL_MACHINE, subkey, value_name
                )
                # "Disable*" semantics invert; "Allow*"/"Enabled" stay direct.
                if "Disable" in value_name:
                    enabled = not bool(raw) if raw is not None else None
                else:
                    enabled = bool(raw) if raw is not None else None
                return {
                    "build_supported": True,
                    "feature_present": True,
                    "shared_audio_enabled": enabled,
                    "source": f"HKLM\\{subkey}\\{value_name}",
                    "release_branch": release.release_branch,
                }

        # Build is new enough but the feature flag has not lit up here.
        return {
            "build_supported": True,
            "feature_present": False,
            "shared_audio_enabled": None,
            "source": None,
            "release_branch": release.release_branch,
        }

    def audit(self) -> list[Issue]:
        state = self.detect()
        if not state["build_supported"]:
            return []
        if not state["feature_present"]:
            return [
                Issue(
                    title="Shared Audio (BT LE Audio broadcast) rollout not yet active",
                    severity="info",
                    current_value="Feature flag not yet present",
                    optimal_value="Pending Microsoft rollout",
                    explanation=(
                        "Build is new enough for Shared Audio (the Bluetooth "
                        "LE Audio broadcast feature) but Windows has not "
                        "lit up the registry surface on this device. ABSO "
                        "will start managing it once the keys are stable."
                    ),
                    category="shared_audio",
                )
            ]

        if state["shared_audio_enabled"]:
            return [
                Issue(
                    title="Shared Audio broadcast is enabled",
                    severity="info",
                    current_value="Shared Audio on",
                    optimal_value="Profile-dependent (Reflex / Slippi / capture lanes prefer off)",
                    explanation=(
                        "Shared Audio uses the Bluetooth LE Audio broadcast "
                        "stack, which keeps the BT radio active and shares "
                        "the audio engine path. Latency-sensitive profiles "
                        "will recommend disabling it during play; the apply "
                        "path will be wired once the key surface is stable."
                    ),
                    category="shared_audio",
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
                "Shared Audio apply path is not yet implemented - the "
                "registry surface will be wired once Microsoft documents "
                "the broadcast on/off key (or community reverse "
                "engineering confirms it on the future-platforms branch)."
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
