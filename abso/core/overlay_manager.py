"""Overlay process remediation for strict fullscreen profiles."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OverlayRemediationResult:
    """Result of attempting to disable overlay processes."""

    attempted_labels: list[str] = field(default_factory=list)
    stopped_labels: list[str] = field(default_factory=list)
    remaining_labels: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.stopped_labels)


class OverlayManager:
    """Stops known overlay processes for strict exclusive-fullscreen profiles."""

    OVERLAY_PROCESS_MAP: dict[str, tuple[str, ...]] = {
        "NVIDIA Share Overlay": ("NVIDIA Share.exe",),
        "Steam Overlay": ("GameOverlayUI.exe",),
        "Xbox Game Bar": ("GameBar.exe",),
        "Xbox Game Bar Server": ("GameBarFTServer.exe",),
        "Discord Overlay": ("DiscordHookHelper.exe", "DiscordHookHelper64.exe"),
        "RivaTuner Statistics Server": ("RTSS.exe",),
        "OBS Studio": ("obs64.exe",),
        "Medal Overlay": ("Medal.exe", "MedalEncoder.exe"),
    }

    def remediate(self, overlay_labels: list[str]) -> OverlayRemediationResult:
        """Attempt to stop overlay processes behind detected labels."""
        result = OverlayRemediationResult()

        for label in self._unique_labels(overlay_labels):
            result.attempted_labels.append(label)
            process_names = self.OVERLAY_PROCESS_MAP.get(label)
            if not process_names:
                message = (
                    f"Overlay '{label}' was detected, but ABSO does not know how to disable it automatically."
                )
                result.warnings.append(message)
                logger.warning(message)
                result.remaining_labels.append(label)
                continue

            stopped_any = False
            process_errors: list[str] = []
            for process_name in process_names:
                if not self._is_process_running(process_name):
                    continue

                if self._stop_process_image(process_name):
                    stopped_any = True
                elif self._is_process_running(process_name):
                    process_errors.append(process_name)

            if process_errors:
                result.remaining_labels.append(label)
                result.warnings.append(
                    f"ABSO could not fully disable {label}. Remaining processes: {', '.join(process_errors)}."
                )
                continue

            if stopped_any:
                result.stopped_labels.append(label)
                result.notices.append(
                    f"ABSO disabled {label} automatically so the strict fullscreen path could be applied."
                )
            else:
                # Label was detected earlier but no matching processes remain now.
                result.notices.append(
                    f"ABSO rechecked {label}; no running overlay processes remained to disable."
                )

        return result

    @staticmethod
    def _unique_labels(labels: list[str]) -> list[str]:
        ordered: list[str] = []
        for label in labels:
            normalized = str(label or "").strip()
            if normalized and normalized not in ordered:
                ordered.append(normalized)
        return ordered

    def _is_process_running(self, process_name: str) -> bool:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False

            output = (result.stdout or "").strip().lower()
            return process_name.lower() in output
        except Exception as e:
            logger.debug("Process existence check failed for %s: %s", process_name, e)
            return False

    def _stop_process_image(self, process_name: str) -> bool:
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/IM", process_name],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0:
                logger.info("Stopped overlay process image: %s", process_name)
                return True

            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            logger.warning(
                "Failed to stop overlay process %s (exit=%s): %s %s",
                process_name,
                result.returncode,
                stdout,
                stderr,
            )
            return False
        except Exception as e:
            logger.warning("Stopping overlay process %s failed: %s", process_name, e)
            return False
