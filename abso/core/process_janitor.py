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

from abso.core.overlay_policy import OVERLAY_PROCESS_IMAGES
from abso.core.process_list import parse_tasklist_csv_images
from abso.utils.proc import no_window_creationflags

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


# Processes ABSO will stop on every latency-sensitive profile sweep. These
# are either overlays/OSDs that cost frame-time, vendor daemons whose
# absence is confirmed safe for typical gaming hardware, or background
# clients with no in-game role. Killing these does not lose user data:
# overlays respawn on next desktop interaction, sync clients resume on
# next launch, and LLM/peripheral daemons can be re-launched by the user
# after the session.
ALWAYS_SAFE_LAUNCH_KILLSET: tuple[str, ...] = (
    # --- Canonical overlay/capture surfaces shared with apply-time detection ---
    *OVERLAY_PROCESS_IMAGES,
    # --- NVIDIA overlay sidecar not always surfaced by overlay detection ---
    "NVIDIA Overlay.exe",
    # nvcontainer.exe deliberately NOT in this list. Empirically (verified on
    # 2026-05-22 with NVIDIA 5xx-series drivers on a QD-OLED + WOLED multi-
    # monitor setup) killing nvcontainer.exe causes two compounding
    # display-pipeline problems:
    #
    #   1. Immediate (~5s after kill): per-display Digital Vibrance is reset
    #      to the hardware minimum — desktop renders desaturated/grayscale.
    #   2. Cumulative across multiple kill cycles: NVIDIA driver state
    #      corrupts in ways that aren't visible in any single setting (per-
    #      monitor ICC, ACM, WCG, sdr_white_nits and Output Dynamic Range all
    #      look correct, yet desktop colors still read as muted). Re-applying
    #      a "known-good" profile does NOT recover. On the affected machine
    #      a SINGLE Ctrl+Win+Shift+B DWM restart was not enough — the user
    #      had to fire the shortcut TWICE before the LG OLED's color pipeline
    #      came back to normal. Plan recovery flows accordingly.
    #
    # The earlier assumption that the user-session container was safe to stop
    # because "the service runs separately" turned out to be wrong on modern
    # driver branches: the user-session container is what holds DRS context,
    # color pipeline state, and the per-display USER-policy values.
    # --- Xbox Game Bar sidecar ---
    "gamebarpresencewriter.exe",
    # --- RTSS / Afterburner OSD sidecars ---
    "RTSSHooksLoader.exe",
    "RTSSHooksLoader64.exe",
    "MSIAfterburner.exe",
    "EVGAPrecision_X1.exe",
    # --- 32-bit capture sidecar ---
    "obs32.exe",
    # --- Audio enhancement DPC offenders ---
    "NahimicService.exe",
    "NahimicSvc64.exe",
    "NahimicSvc32.exe",
    "Sonic Studio 3.exe",
    # --- Browser PiP / streaming overlays that inject into fullscreen ---
    "GeForceNOW.exe",
    # --- LLM runtimes ---
    # Local LLM hosts have no role on a gaming-only PC. User explicitly called
    # this out; the dev-LLM workflows live on other machines.
    "ollama.exe",
    "ollama app.exe",  # Windows tray icon for Ollama - separate binary from the CLI
    "ollama_runner.exe",
    "ollama_llama_server.exe",
    "lmstudio.exe",
    "LM Studio.exe",
    "lms.exe",
    "GPT4All.exe",
    "Jan.exe",
    "cortex.exe",
    "llamafile.exe",
    "AnythingLLM.exe",
    "Open WebUI.exe",
    # --- VPN clients (UI / CLI / tray only) ---
    # VPN clients add a virtual NIC + encryption pipeline that increases tail
    # latency on competitive game traffic. The user explicitly called out
    # Tailscale. Only the UI/CLI/tray binaries are always-safe to stop; the
    # route-holding *daemons/services* live in OPT_IN (see below) because
    # force-killing them on a kill-switch VPN can blackhole ALL traffic and
    # take an online game offline - the opposite of the intent.
    "tailscale-ipn.exe",
    "tailscale.exe",
    "tailscale-tray.exe",
    "zerotier_desktop_ui.exe",
    "openvpn-gui.exe",
    "NordVPN.exe",
    "ExpressVPN.exe",
    "ProtonVPN.exe",
    "Mullvad VPN.exe",
    "Windscribe.exe",
    "AirVPN.exe",
    # --- Chat clients other than Discord (Discord stays protected for teammates) ---
    # Slack/Teams/Zoom run heavy Electron/Chromium backends that consume CPU
    # and RAM during gameplay. If you need them up during play, add them to
    # process_overrides.protect in abso.yaml.
    "Slack.exe",
    "ms-teams.exe",
    "Teams.exe",
    "msteams.exe",
    "Zoom.exe",
    "Zoom Meetings.exe",
    "CptHost.exe",
    "Signal.exe",
    "Telegram.exe",
    "WhatsApp.exe",
    "Skype.exe",
    # --- Crash reporters / telemetry helpers (typical bloatware tray icons) ---
    "CrashMailer.exe",
    "CrashMailer_64.exe",
    # --- Cloud sync ---
    # Sync uploads cause disk + network spikes mid-match. User opted in to
    # killing these globally; they resume automatically next session.
    "OneDrive.exe",
    "Dropbox.exe",
    "DropboxUpdate.exe",
    "GoogleDriveFS.exe",
    "googledrivesync.exe",
    # --- Peripheral vendor daemons (verified non-essential for user's hardware) ---
    # Logitech G502 stores DPI/buttons in onboard memory after first save;
    # G HUB is only required for LIGHTSYNC RGB animations, which do not
    # matter mid-game.
    "lghub.exe",
    "lghub_agent.exe",
    "lghub_updater.exe",
    "LogiAiPromptBuilder.exe",
    # Corsair K70 Lux RGB: HID typing always works without iCUE; RGB reverts
    # to last hardware profile.
    "iCUE.exe",
    "LCore.exe",
    "CorsairService.exe",
)


# Background daemons that may matter on machines with other hardware
# (Razer / ASUS peripherals, Adobe creative suite, NVIDIA Experience
# overlay calibration). Off by default for non-strict profiles; strict
# G-SYNC and Reflex profiles include them automatically.
OPT_IN_LAUNCH_KILLSET: tuple[str, ...] = (
    # NVIDIA updaters (separate from the always-safe overlay container)
    "GeForce Experience.exe",
    "NVIDIA Web Helper.exe",
    # Adobe creative suite background services
    "AdobeUpdateService.exe",
    "Adobe Desktop Service.exe",
    "Creative Cloud.exe",
    # Razer / ASUS RGB + macro daemons (user may not have these; safe on this PC)
    "Razer Synapse 3.exe",
    "RzSynapse.exe",
    "RazerCortex.exe",
    "ArmouryCrate.exe",
    "ArmourySocketServer.exe",
    "ROGLiveService.exe",
    # Windows housekeeping that produces I/O spikes
    "SearchIndexer.exe",
    "SearchProtocolHost.exe",
    "SearchFilterHost.exe",
    # VPN route-holding daemons/services. Force-killing these on a kill-switch
    # VPN can blackhole ALL traffic, so they are opt-in: strict profiles
    # include them automatically (the user's explicit aggressive choice), while
    # productivity/casual profiles leave the tunnel - and any online game
    # routed through it - intact.
    "tailscaled.exe",
    "ZeroTier One.exe",
    "wireguard.exe",
    "openvpn.exe",
    "nordvpn-service.exe",
    "ProtonVPNService.exe",
    "mullvad-daemon.exe",
)


# Process images the "capture-safe" profile variants intentionally preserve.
# These are the tools whose entire purpose is to coexist with the running
# game: capture clients, in-game overlays, frame-time OSDs, peripheral
# RGB/macro daemons. The general always-safe killset stops them because
# they cost frame-time, but a profile labeled "-capture" promises the
# user it will not interfere with the clipping / overlay / peripheral
# stack - so the capture variants filter these out of their killset.
#
# This list intentionally does NOT include LLM runtimes, cloud sync,
# VPN clients, or chat-other-than-Discord. Those are always-safe to
# stop on any gaming profile regardless of capture intent.
CAPTURE_ALLOWED_IMAGES: frozenset[str] = frozenset(
    name.lower()
    for name in (
        # Steam overlay (friends list, screenshot, in-game messages)
        "GameOverlayUI.exe",
        # Discord in-game overlay
        "DiscordHookHelper.exe",
        "DiscordHookHelper64.exe",
        # Frame-time / FPS / OSD overlays
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
        # NVIDIA capture / overlay (ShadowPlay)
        "NVIDIA Share.exe",
        "NVIDIA Overlay.exe",
        # nvcontainer.exe removed from the always-safe killset entirely
        # (see comment in ALWAYS_SAFE_LAUNCH_KILLSET above) — no need to
        # whitelist it here because it is never enqueued for killing.
        # Peripheral RGB / macro daemons (user may want LIGHTSYNC etc.
        # alive during a recorded session)
        "lghub.exe",
        "lghub_agent.exe",
        "lghub_updater.exe",
        "LogiAiPromptBuilder.exe",
        "iCUE.exe",
        "LCore.exe",
        "CorsairService.exe",
    )
)


# Image names we will NEVER auto-kill regardless of caller request. Anti-cheat,
# game launchers, ABSO itself, and the user's interactive / agentic workflow
# (editors, terminals, Discord, dev tooling) live here. If a caller passes one
# of these in the killset, the janitor skips it and emits a warning.
#
# This list is the safety net: even a misconfigured profile or a stale tray
# config cannot kill an in-progress Claude Code session, an open VS Code
# window, or Discord voice chat.
NEVER_KILL_IMAGES: frozenset[str] = frozenset(
    name.lower()
    for name in (
        # --- Anti-cheat ---
        "EasyAntiCheat.exe",
        "EasyAntiCheat_EOS.exe",
        "EasyAntiCheat_launcher.exe",
        "BEService.exe",
        "BEServiceLauncher.exe",
        "vgc.exe",
        "vgtray.exe",
        # --- Launchers the games depend on ---
        "Steam.exe",
        "steamwebhelper.exe",
        "Battle.net.exe",
        "BlizzardError.exe",
        "Agent.exe",
        "EpicGamesLauncher.exe",
        "EpicWebHelper.exe",
        "RiotClientServices.exe",
        "Slippi Launcher.exe",  # Slippi Dolphin launcher (drives Melee setup)
        "Slippi Dolphin.exe",
        "Ryujinx.exe",
        "Ryubing.exe",
        # --- ABSO + tray + interpreter (cannot kill self) ---
        "abso.exe",
        "python.exe",
        "pythonw.exe",
        "powershell.exe",
        "pwsh.exe",
        # --- Critical Windows infrastructure ---
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
        # --- Code editors / IDEs (agentic work in progress) ---
        # VS Code family
        "Code.exe",
        "Code - Insiders.exe",
        "Code-Insiders.exe",
        # Cursor / Windsurf (AI-powered editors)
        "Cursor.exe",
        "Windsurf.exe",
        # JetBrains family (each IDE has a 64-bit and unsuffixed launcher)
        "idea64.exe", "idea.exe",
        "pycharm64.exe", "pycharm.exe",
        "webstorm64.exe", "webstorm.exe",
        "clion64.exe", "clion.exe",
        "goland64.exe", "goland.exe",
        "rider64.exe", "rider.exe",
        "phpstorm64.exe", "phpstorm.exe",
        "rubymine64.exe", "rubymine.exe",
        "datagrip64.exe", "datagrip.exe",
        "studio64.exe", "studio.exe",  # Android Studio
        # Other editors
        "devenv.exe",  # Visual Studio
        "sublime_text.exe",
        "notepad++.exe",
        "Zed.exe",
        # --- Terminals (interactive sessions / agentic CLIs) ---
        "WindowsTerminal.exe",
        "OpenConsole.exe",
        "wezterm-gui.exe",
        "wezterm.exe",
        "alacritty.exe",
        "cmd.exe",
        # --- WSL ---
        "wsl.exe",
        "wslhost.exe",
        "wslservice.exe",
        "wslg.exe",
        # --- Docker ---
        "Docker Desktop.exe",
        "dockerd.exe",
        "com.docker.proxy.exe",
        "com.docker.service.exe",
        "com.docker.backend.exe",
        # --- Discord (teammate comms — overlay helpers ARE killed, app stays) ---
        "Discord.exe",
        "DiscordPTB.exe",
        "DiscordCanary.exe",
        "DiscordDevelopment.exe",
        "Discord Updater.exe",
        # --- Dev tooling (in-flight git ops, agentic CLIs, build tools) ---
        "git.exe",
        "gh.exe",
        "claude.exe",
        "codex.exe",   # OpenAI/Codex CLI - same agentic-work category as claude.exe
        "node.exe",
        "npm.exe",
        "cargo.exe",
        "rustc.exe",
    )
)


def _load_user_process_overrides() -> tuple[frozenset[str], tuple[str, ...]]:
    """Read per-machine process overrides from ``abso.yaml``.

    Returns a ``(protect, kill)`` pair where ``protect`` is a lowercased
    frozenset that should augment :data:`NEVER_KILL_IMAGES`, and ``kill``
    is a tuple that should append to the always-safe sweep list. Both are
    empty if the config file is absent or has no ``process_overrides``
    section.

    Failures are silent (return empty) so a malformed user config never
    breaks the janitor on a live machine.
    """
    try:
        from abso.core.config import get_config

        config = get_config()
        overrides = getattr(config, "process_overrides", None)
        if overrides is None:
            return frozenset(), ()
        protect_raw = list(getattr(overrides, "protect", []) or [])
        kill_raw = list(getattr(overrides, "kill", []) or [])
    except Exception as exc:
        logger.debug("Skipping user process overrides (load failed): %s", exc)
        return frozenset(), ()

    protect = frozenset(
        str(name).strip().lower() for name in protect_raw if str(name).strip()
    )
    kill = tuple(
        str(name).strip() for name in kill_raw if str(name).strip()
    )
    return protect, kill


class ProcessJanitor:
    """Stops latency-impacting processes against a profile-supplied killset."""

    def __init__(self) -> None:
        user_protect, _ = _load_user_process_overrides()
        # Merge built-in NEVER_KILL with user-declared protect list so a
        # misconfigured profile + an in-flight agentic editor cannot collide.
        self._never_kill = NEVER_KILL_IMAGES | user_protect

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
            elif self._query_process_running(normalized) is False:
                # taskkill returned non-zero but tasklist positively confirms
                # the image is gone (race with natural exit). Treat as stopped.
                result.stopped.append(normalized)
                result.notices.append(f"Stopped {normalized}")
            else:
                # Still running, or could not verify the kill — surface as a
                # failure rather than claim an unproven success.
                result.failed.append(normalized)
                result.warnings.append(
                    f"ProcessJanitor could not stop {normalized}; it is still running."
                )

        return result

    @staticmethod
    def _normalize_image_name(name: str) -> str:
        if not name:
            return ""
        cleaned = str(name).strip().strip('"').strip("'")
        return cleaned

    def _query_process_running(self, image_name: str) -> bool | None:
        """Return True/False when tasklist can confirm, or None when it cannot.

        A tasklist failure (unavailable / timeout / non-zero exit) returns None
        so callers can distinguish "confirmed gone" from "could not verify" and
        never report an unverifiable kill as a success.
        """
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=no_window_creationflags(),
            )
        except FileNotFoundError:
            logger.debug("tasklist unavailable; cannot confirm %s", image_name)
            return None
        except Exception as exc:
            logger.debug("Process existence check failed for %s: %s", image_name, exc)
            return None

        if completed.returncode != 0:
            return None
        return image_name.lower() in parse_tasklist_csv_images(completed.stdout or "")

    def _is_process_running(self, image_name: str) -> bool:
        # Unknown (tasklist failure) is treated as "not running" for the
        # pre-kill gate: ABSO cannot stop an image it cannot observe.
        return self._query_process_running(image_name) is True

    def _stop_process_image(self, image_name: str) -> bool:
        try:
            # No /T: /IM already stops every process with this image name, and
            # tree-killing (/T) could reach a NEVER_KILL child (anti-cheat, the
            # game, a protected editor) parented under a swept image.
            completed = subprocess.run(
                ["taskkill", "/F", "/IM", image_name],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=no_window_creationflags(),
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
