"""AI taskbar agents settings handler (Win11 25H2 26200.8457+).

KB5089549 introduced "Agents on the Taskbar" — first- and third-party AI
agents that pin to the taskbar like apps and may run background tasks
(notably the Researcher agent). For Reflex paths, emulators, and capture
workflows, any always-on background process is a jitter risk.

Like the Xbox Mode handler, this is **detect-only**. The rollout is
feature-flag gated; the registry surface may not yet exist on a given PC
even after KB5089549 is installed. We probe several candidate paths and
also surface the well-known WindowsCopilot policy / ShowCopilotButton
state because those are the most useful adjacent signals today.

``apply`` raises a clear "not yet implemented" error so a misconfigured
profile fails loudly rather than mutating undocumented state. Backup/
restore are no-ops; ``restore_guarantee`` is ``"none"``.
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

# Minimum build for the AI taskbar agent rollout.
_AI_AGENTS_MIN_BUILD = 26100
_AI_AGENTS_MIN_UBR = 8457

# Candidate policy / state paths. Microsoft has not published a stable
# documented surface yet — these are best-effort guesses based on the
# parallel "Windows Copilot" rollout.
_AI_AGENTS_HKLM_CANDIDATES: tuple[tuple[str, str], ...] = (
    (r"SOFTWARE\Policies\Microsoft\Windows\AI", "DisableAIAgents"),
    (r"SOFTWARE\Policies\Microsoft\Windows\AI", "AllowAIAgents"),
    (r"SOFTWARE\Microsoft\Windows\Shell\Agents", "Enabled"),
)
_AI_AGENTS_HKCU_CANDIDATES: tuple[tuple[str, str], ...] = (
    (r"Software\Microsoft\Windows\Shell\Agents", "Enabled"),
    (r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "ShowAIAgentsButton"),
)

# Adjacent signals we already understand (Copilot rollout).
_COPILOT_POLICY_KEY = r"SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot"
_COPILOT_BUTTON_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"


class AIAgentsSettingsHandler(SettingsHandler):
    """Reads (only) AI taskbar agent state when the feature is exposed."""

    def detect(self) -> dict[str, Any]:
        release = detect_os_release()
        if not release.at_least(_AI_AGENTS_MIN_BUILD, _AI_AGENTS_MIN_UBR):
            return {
                "build_supported": False,
                "feature_present": False,
                "ai_agents_state": None,
                "source": None,
                "copilot_disabled": None,
                "copilot_button_hidden": None,
            }

        ai_state: bool | None = None
        ai_source: str | None = None
        for subkey, value_name in _AI_AGENTS_HKLM_CANDIDATES:
            if value_exists(winreg.HKEY_LOCAL_MACHINE, subkey, value_name):
                raw = read_registry_dword(
                    winreg.HKEY_LOCAL_MACHINE, subkey, value_name
                )
                # "Disable*" semantics invert; "Allow*"/Enabled keep direct.
                if "Disable" in value_name:
                    ai_state = not bool(raw) if raw is not None else None
                else:
                    ai_state = bool(raw) if raw is not None else None
                ai_source = f"HKLM\\{subkey}\\{value_name}"
                break

        if ai_state is None:
            for subkey, value_name in _AI_AGENTS_HKCU_CANDIDATES:
                if value_exists(winreg.HKEY_CURRENT_USER, subkey, value_name):
                    raw = read_registry_dword(
                        winreg.HKEY_CURRENT_USER, subkey, value_name
                    )
                    ai_state = bool(raw) if raw is not None else None
                    ai_source = f"HKCU\\{subkey}\\{value_name}"
                    break

        copilot_disabled = self._read_copilot_disabled()
        copilot_button_hidden = self._read_copilot_button_hidden()

        feature_present = ai_state is not None or ai_source is not None

        return {
            "build_supported": True,
            "feature_present": feature_present,
            "ai_agents_state": ai_state,
            "source": ai_source,
            "copilot_disabled": copilot_disabled,
            "copilot_button_hidden": copilot_button_hidden,
        }

    @staticmethod
    def _read_copilot_disabled() -> bool | None:
        if not value_exists(
            winreg.HKEY_LOCAL_MACHINE, _COPILOT_POLICY_KEY, "TurnOffWindowsCopilot"
        ):
            return None
        raw = read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE, _COPILOT_POLICY_KEY, "TurnOffWindowsCopilot"
        )
        return bool(raw) if raw is not None else None

    @staticmethod
    def _read_copilot_button_hidden() -> bool | None:
        if not value_exists(
            winreg.HKEY_CURRENT_USER, _COPILOT_BUTTON_KEY, "ShowCopilotButton"
        ):
            return None
        raw = read_registry_dword(
            winreg.HKEY_CURRENT_USER, _COPILOT_BUTTON_KEY, "ShowCopilotButton"
        )
        if raw is None:
            return None
        return raw == 0

    def audit(self) -> list[Issue]:
        state = self.detect()
        issues: list[Issue] = []

        if not state["build_supported"]:
            return issues

        if not state["feature_present"]:
            issues.append(
                Issue(
                    title="AI taskbar agents rollout not yet active",
                    severity="info",
                    current_value="Feature flag not yet present",
                    optimal_value="Pending Microsoft rollout",
                    explanation=(
                        "Build is new enough for Agents on the Taskbar but "
                        "Windows has not enabled the surface on this device. "
                        "ABSO will start managing it once the registry "
                        "surface appears."
                    ),
                    category="ai_agents",
                )
            )
        elif state["ai_agents_state"] is True:
            issues.append(
                Issue(
                    title="AI taskbar agents are active",
                    severity="info",
                    current_value="Enabled",
                    optimal_value="Disabled for Reflex / emulator / capture profiles",
                    explanation=(
                        "Idle AI agents (notably the Researcher agent) can "
                        "wake background workers that introduce frame-time "
                        "jitter. Latency-sensitive profiles will recommend "
                        "disabling agents during the gaming session."
                    ),
                    category="ai_agents",
                )
            )

        if state["copilot_disabled"] is False:
            issues.append(
                Issue(
                    title="Windows Copilot is not policy-disabled",
                    severity="info",
                    current_value="Copilot policy unset / allowed",
                    optimal_value="TurnOffWindowsCopilot = 1 for gaming systems",
                    explanation=(
                        "Copilot shares background scheduling with the "
                        "AI agent surface. Disabling it via policy gives a "
                        "stable baseline before the agents rollout."
                    ),
                    category="ai_agents",
                )
            )

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": False,
            "error": (
                "AI agents apply path is not yet implemented — Phase 3 will "
                "wire the registry writes after the key surface stabilizes."
            ),
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        return True

    @property
    def restore_guarantee(self) -> str:
        return "none"
