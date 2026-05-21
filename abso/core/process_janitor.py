"""Profile-aware process janitor for launch-time sanitization.

Where ``OverlayManager`` runs once at apply time against a fixed set of overlay
labels surfaced by ``MultiMonitorDetector``, ``ProcessJanitor`` is the broader
launch-time sweeper that the tray watcher calls whenever a profile's game
binary is detected running. It:

- Accepts a flat list of process image names (no label mapping)
- Reports stopped / skipped / failed per image
- Distinguishes "image was not running" from "image refused to stop"
- Stays purely additive over ``OverlayManager`` so existing apply-time
  remediation paths keep working unchanged

The killset itself is *profile-derived* via
``BaseProfile.launch_process_killset()`` and crosses into PowerShell via the
profile catalog manifest, so the tray never has to hardcode game-specific
process lists.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProcessSweepResult:
    """Structured outcome of a single janitor sweep."""

    attempted: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)
    not_running: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.stopped)

    def to_dict(self) -> dict[str, object]:
        return {
            "attempted": list(self.attempted),
            "stopped": list(self.stopped),
            "not_running": list(self.not_running),
            "failed": list(self.failed),
            "notices": list(self.notices),
            "warnings": list(self.warnings),
            "changed": self.changed,
        }


# Overlay / capture / OSD / vendor processes that latency-sensitive profiles
# should always be safe to kill mid-session. Killing these does not lose user
# data; they typically respawn on next desktop interaction.
ALWAYS_SAFE_LAUNCH_KILLSET: tuple[str, ...] = (
    # NVIDIA capture + overlay
    "NVIDIA Share.exe",
    "NVIDIA Overlay.exe",
    "nvcontainer.exe",  # Only the user-session container - service handler runs in services.msc
    # Steam overlay (not Steam itself)
    "GameOverlayUI.exe",
    # Xbox Game Bar
    "GameBar.exe",
    "GameBarFTServer.exe",
    "gamebarpresencewriter.exe",
    # Discord in-game overlay (NOT Discord itself - voice/text stay alive)
    "DiscordHookHelper.exe",
    "DiscordHookHelper64.exe",
    # RTSS / MSI Afterburner OSD
    "RTSS.exe",
    "RTSSHooksLoader.exe",
    "RTSSHooksLoader64.exe",
    "MSIAfterburner.exe",
    "EVGAPrecision_X1.exe",
    # Capture clients
    "obs64.exe",
    "obs32.exe",
    "Medal.exe",
    "MedalEncoder.exe",
    # Audio enhancement DPC offenders
    "NahimicService.exe",
    "NahimicSvc64.exe",
    "NahimicSvc32.exe",
    "Sonic Studio 3.exe",
    # Browser PiP / hardware-accel overlay that injects into fullscreen games
    "GeForceNOW.exe",
)


# Background daemons that may genuinely matter to the user (cloud sync mid-
# upload, OEM RGB hotkeys, vendor updaters). Only swept when the profile or
# tray config explicitly opts in.
OPT_IN_LAUNCH_KILLSET: tuple[str, ...] = (
    # Cloud sync
    "OneDrive.exe",
    "Dropbox.exe",
    "GoogleDriveFS.exe",
    # Vendor updaters
    "GeForce Experience.exe",
    "NVIDIA Web Helper.exe",
    "AdobeUpdateService.exe",
    "Adobe Desktop Service.exe",
    "Creative Cloud.exe",
    # OEM RGB / peripheral daemons
    "Razer Synapse 3.exe",
    "RzSynapse.exe",
    "RazerCortex.exe",
    "lghub.exe",
    "lghub_agent.exe",
    "LCore.exe",
    "iCUE.exe",
    "ArmouryCrate.exe",
    "ArmourySocketServer.exe",
    "ROGLiveService.exe",
    # Windows housekeeping that produces I/O spikes
    "SearchIndexer.exe",
    "SearchProtocolHost.exe",
    "SearchFilterHost.exe",
)


# Image names we will NEVER auto-kill regardless of caller request. Anti-cheat,
# game launchers, and ABSO itself live here. If a caller passes one of these
# in the killset, the janitor skips it and emits a warning.
NEVER_KILL_IMAGES: frozenset[str] = frozenset(
    name.lower()
    for name in (
        # Anti-cheat
        "EasyAntiCheat.exe",
        "EasyAntiCheat_EOS.exe",
        "EasyAntiCheat_launcher.exe",
        "BEService.exe",
        "BEServiceLauncher.exe",
        "vgc.exe",
        "vgtray.exe",
        # Launchers the games depend on
        "Steam.exe",
        "steamwebhelper.exe",
        "Battle.net.exe",
        "BlizzardError.exe",
        "Agent.exe",
        "EpicGamesLauncher.exe",
        "EpicWebHelper.exe",
        "RiotClientServices.exe",
        # ABSO + tray (cannot kill self)
        "abso.exe",
        "python.exe",
        "pythonw.exe",
        "powershell.exe",
        "pwsh.exe",
        # Critical Windows infrastructure
        "explorer.exe",
        "dwm.exe",
        "csrss.exe",
        "winlogon.exe",
        "lsass.exe",
        "services.exe",
        "svchost.exe",
        "smss.exe",
        "wininit.exe",
        "audiodg.exe",
    )
)


class ProcessJanitor:
    """Stops latency-impacting processes against a profile-supplied killset."""

    def __init__(self) -> None:
        self._never_kill = NEVER_KILL_IMAGES

    def sweep(self, image_names: list[str], *, dry_run: bool = False) -> ProcessSweepResult:
        """Sweep the given process image names.

        Args:
            image_names: Process image filenames (e.g. ``"Medal.exe"``).
            dry_run: When True, only report what would be stopped without
                calling ``taskkill``. Useful for diagnostics from the tray.

        Returns:
            Structured result with stopped / not_running / failed buckets.
        """
        result = ProcessSweepResult()
        seen: set[str] = set()

        for raw_name in image_names:
            normalized = self._normalize_image_name(raw_name)
            if not normalized:
                continue
            if normalized.lower() in seen:
                continue
            seen.add(normalized.lower())

            result.attempted.append(normalized)

            if normalized.lower() in self._never_kill:
                warning = f"ProcessJanitor refused to sweep protected image: {normalized}"
                result.warnings.append(warning)
                logger.warning(warning)
                continue

            if not self._is_process_running(normalized):
                result.not_running.append(normalized)
                continue

            if dry_run:
                result.notices.append(f"Would stop {normalized} (dry-run)")
                continue

            if self._stop_process_image(normalized):
                result.stopped.append(normalized)
                result.notices.append(f"Stopped {normalized}")
            elif self._is_process_running(normalized):
                result.failed.append(normalized)
                result.warnings.append(
                    f"ProcessJanitor could not stop {normalized}; it is still running."
                )
            else:
                # taskkill returned non-zero but the image is gone (race with
                # natural exit). Treat as stopped.
                result.stopped.append(normalized)

        return result

    @staticmethod
    def _normalize_image_name(name: str) -> str:
        if not name:
            return ""
        cleaned = str(name).strip().strip('"').strip("'")
        return cleaned

    def _is_process_running(self, image_name: str) -> bool:
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError:
            logger.debug("tasklist unavailable; assuming %s is not running", image_name)
            return False
        except Exception as exc:
            logger.debug("Process existence check failed for %s: %s", image_name, exc)
            return False

        if completed.returncode != 0:
            return False
        output = (completed.stdout or "").strip().lower()
        return image_name.lower() in output

    def _stop_process_image(self, image_name: str) -> bool:
        try:
            completed = subprocess.run(
                ["taskkill", "/F", "/T", "/IM", image_name],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except FileNotFoundError:
            logger.warning("taskkill unavailable; cannot stop %s", image_name)
            return False
        except Exception as exc:
            logger.warning("Stopping %s failed: %s", image_name, exc)
            return False

        if completed.returncode == 0:
            logger.info("Stopped process image: %s", image_name)
            return True

        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        logger.debug(
            "taskkill non-zero for %s (exit=%s): %s %s",
            image_name,
            completed.returncode,
            stdout,
            stderr,
        )
        return False


@dataclass(frozen=True)
class LaunchKillset:
    """A profile-resolved launch-time killset.

    ``always_safe`` is killed unconditionally when the janitor runs against
    this profile. ``opt_in`` is held back unless the caller explicitly opts
    in (tray config flag or CLI ``--include-opt-in``).
    """

    always_safe: tuple[str, ...] = ()
    opt_in: tuple[str, ...] = ()

    def resolve(self, *, include_opt_in: bool = False) -> list[str]:
        if include_opt_in:
            return list(self.always_safe) + list(self.opt_in)
        return list(self.always_safe)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "always_safe": list(self.always_safe),
            "opt_in": list(self.opt_in),
        }
