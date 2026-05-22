"""Base profile class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from abso.core.process_janitor import LaunchKillset
    from abso.settings.base import SettingsHandler


@dataclass(frozen=True)
class DisplayPathRequirements:
    """Runtime display-path requirements for a profile.

    These requirements are evaluated against the user's active display
    environment before ABSO applies any system changes.
    """

    require_overlay_free_path: bool = False


class BaseProfile(ABC):
    """Abstract base class for game optimization profiles.

    Each game profile defines:
    - Target settings for each settings handler
    - In-game settings recommendations
    - Game-specific logic (e.g., executable detection)

    Validation Metadata (optional overrides):
    - is_online_profile: Whether this profile is for online/rollback gameplay
    - is_emulator_profile: Whether this is for an emulator (fixed framerate)
    - requires_reflex: Whether the game uses NVIDIA Reflex
    - is_sdr_only: Whether the game is SDR-only (no HDR support)
    - network_scope: What network optimizations are allowed
    - graphics_api: Primary graphics API (dx11, dx12, vulkan)
    """

    @property
    @abstractmethod
    def profile_id(self) -> str:
        """Unique identifier for the profile."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of the profile."""
        pass

    @property
    @abstractmethod
    def optimization_target(self) -> str:
        """What this profile optimizes for (e.g., 'minimum_latency')."""
        pass

    @property
    @abstractmethod
    def executable_hints(self) -> list[str]:
        """Executable names to identify the game."""
        pass

    # === Optional Validation Metadata ===
    # Subclasses can override these for more precise validation

    @property
    def is_online_profile(self) -> bool:
        """Whether this profile is for online/rollback gameplay.

        When True, RollbackGuard will enforce stricter settings.
        Default: Inferred from optimization_target.
        """
        return self.optimization_target in {
            "stable_online",
            "online",
            "ranked",
            "matchmaking",
        }

    @property
    def is_emulator_profile(self) -> bool:
        """Whether this is an emulator profile (fixed framerate).

        Emulator profiles running at fixed framerates (e.g., 60fps)
        don't benefit from VRR and should disable G-Sync.
        Default: Inferred from executable hints.
        """
        emulator_exes = {
            "dolphin.exe", "slippi dolphin.exe",
            "ryujinx.exe", "ryujinx.ava.exe", "ryujinx.headless.sdl2.exe",
            "yuzu.exe", "cemu.exe", "rpcs3.exe",
        }
        return any(
            exe.lower() in emulator_exes
            for exe in self.executable_hints
        )

    @property
    def requires_reflex(self) -> bool:
        """Whether the game uses NVIDIA Reflex.

        When True, driver LLM should be OFF to avoid conflicts.
        Default: False (override in profiles with Reflex support).
        """
        return False

    @property
    def enforces_reflex_in_config(self) -> bool:
        """Whether ABSO actually writes the NVIDIA Reflex toggle into game config.

        ``requires_reflex`` only states that the game supports Reflex and that
        ABSO should keep driver LLM off. It does not imply ABSO enables Reflex
        for the user. Only profiles whose associated config handler writes the
        in-game Reflex key (e.g. Diablo4ConfigHandler.reflex,
        MarvelRivalsConfigHandler.nvidia_reflex) should override this to True.

        Profiles where ``requires_reflex`` is True but
        ``enforces_reflex_in_config`` is False MUST tell the user to enable
        Reflex manually in-game — both in the description and in-game
        guidance text. The Reflex-contract invariant test enforces this.
        """
        return False

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        """Whether profile should only run when VRR/G-SYNC support is confirmed.

        Use this for VRR-dependent profiles that should fail fast when the
        monitor stack is not reporting VRR capability.
        """
        return False

    @property
    def is_sdr_only(self) -> bool:
        """Whether the game is SDR-only (no native HDR).

        When True, HDR should be disabled to prevent washed-out colors.
        Default: Inferred from profile characteristics.
        """
        # Emulators are typically SDR
        if self.is_emulator_profile:
            return True

        # Check for known SDR games
        sdr_indicators = {"rivals", "melee", "slippi"}
        name_lower = self.display_name.lower()
        return any(ind in name_lower for ind in sdr_indicators)

    @property
    def network_scope(self) -> Literal["full", "limited", "none"]:
        """What network optimizations are allowed.

        - "full": Allow all network optimizations (Nagle disable, TCP tuning)
        - "limited": Reserved for narrowly verified TCP tuning (no Nagle disable)
        - "none": Use OS defaults

        Default: "none". Profiles must opt into TCP/global network changes
        because most games use UDP for live gameplay and global TCP edits can
        affect downloads, streaming, and general browsing.
        """
        return "none"

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Primary graphics API used by the game/emulator.

        Used to determine HAGS compatibility and LLM effectiveness.
        Default: "unknown" (override in profiles with known API).
        """
        return "unknown"

    @property
    def allows_aggressive_settings(self) -> bool:
        """Whether this profile allows aggressive gated settings.

        When False, StabilityGate will use safe fallbacks.
        Default: Based on optimization_target.
        """
        return self.optimization_target in {
            "minimum_latency",
            "minimum_latency_offline",
        }

    @property
    def cpu_affinity_strategy(self) -> str | None:
        """CPU affinity strategy for this profile.

        Returns None to skip affinity management, or one of:
        - "p_cores_only": Pin to performance cores (Intel hybrid)
        - "all_cores": Use all cores (default behavior)
        - "custom": Use custom affinity mask from get_settings()

        Default: None (don't manage affinity).
        Only effective on hybrid CPU architectures (Intel 12th gen+).
        """
        return None

    @property
    def include_legacy_tweaks(self) -> bool:
        """Whether to apply legacy/unverified registry and memory tweaks.

        Legacy tweaks include settings commonly found in gaming optimization
        guides that have no documented effect on modern Windows 11:
        - SystemResponsiveness (MMCSS scheduling hint)
        - NetworkThrottlingIndex (multimedia network throttling)
        - DisablePagingExecutive (kernel paging — no-op with 16GB+ RAM)
        - LargeSystemCache (already 0 on desktop Windows)

        These are NOT applied by default. Override to True if you want
        them for completeness or placebo comfort.
        Default: False.
        """
        return False

    @property
    def nvidia_profile_name(self) -> str | None:
        """Stable NVIDIA DRS profile identity for this profile family.

        Override this when multiple ABSO variants should reuse one driver
        profile instead of creating display-name-specific leftovers.
        """
        return None

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        """Legacy or variant NVIDIA profile names worth reusing when bound."""
        return []

    @property
    def nvidia_binding_executables(self) -> list[str]:
        """Executable names ABSO should use for NVIDIA profile binding proof.

        ``executable_hints`` is intentionally broad and powers process detection,
        launch matching, and other runtime heuristics. NVIDIA driver binding is a
        different concern: it should target the canonical game binary, not every
        alias or launcher name a profile might recognize.

        Profiles with multiple detection aliases should override this with the
        narrowest set of real game executables that should belong to the driver
        profile.
        """
        return list(self.executable_hints)

    @property
    def allow_dual_limiter(self) -> bool:
        """Whether this profile deliberately layers an in-game and driver FPS cap.

        Blur Busters G-SYNC 101 recommends a single authoritative limiter
        (in-game preferred, driver/RTSS as fallback). ABSO enforces that policy
        via a profile invariant test: a profile must not set both
        ``NvidiaSettingsHandler.auto_vrr_fps_cap`` and a native game-config
        ``auto_vrr_fps_cap`` unless it overrides this property to ``True`` and
        documents why in-code.

        Typical acceptable reason: the game's native config file is known to
        drift (e.g., the game rewrites the INI on exit or on multi-monitor
        changes), so the driver cap is kept as a safety net that catches the
        drift. Both caps compute the same value (refresh - 3), so the effective
        cap is deterministic.
        """
        return False

    @property
    def allow_unverified_nvidia_profile_reuse(self) -> bool:
        """Whether strict NVIDIA preflight may reuse a stable bound profile.

        Some ABSO-managed custom profile families cannot be enumerated exactly by
        NVAPI on every driver branch even when the intended profile already
        exists and has bound applications. Profiles should opt into this only
        when they reuse a stable driver-profile identity and ABSO can still rule
        out conflicting owners.
        """
        return False

    def _safe_get_handler_settings(self, handler_name: str) -> dict[str, Any]:
        """Best-effort access to a handler's settings without surfacing profile exceptions."""
        try:
            settings = self.get_settings(handler_name)
        except Exception:
            return {}
        return settings if isinstance(settings, dict) else {}

    @property
    def uses_fullscreen_only_vrr_path(self) -> bool:
        """Whether this profile relies on the strict fullscreen-only VRR path.

        This is derived from the effective NVIDIA settings so strict VRR
        behavior stays consistent across profile families without requiring
        every variant to manually duplicate the same safety contract.
        """
        nvidia_settings = self._safe_get_handler_settings("NvidiaSettingsHandler")
        global_vrr_mode = (
            nvidia_settings.get("global_vrr_mode")
            or nvidia_settings.get("global_gsync_mode")
            or nvidia_settings.get("vrr_mode")
        )
        return str(global_vrr_mode or "").strip().lower() == "fullscreen_only"

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        """Runtime requirements for the target gaming display path.

        Fullscreen-only VRR profiles automatically inherit the strict
        overlay-free contract used by the hardened Overwatch profiles.
        """
        return DisplayPathRequirements(
            require_overlay_free_path=self.uses_fullscreen_only_vrr_path
        )

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        """Whether NVIDIA app binding must be proven before ABSO applies.

        Fullscreen-only VRR profiles should fail closed when ABSO cannot
        prove the executable is really bound to the intended NVIDIA profile.
        """
        return self.uses_fullscreen_only_vrr_path

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        """Per-executable Fullscreen Optimizations (FSO) overrides.

        Maps an executable name (or full path) to a bool:
          - ``True``  = disable FSO (write ``DISABLEDXMAXIMIZEDWINDOWEDMODE``
            into ``HKCU\\...\\AppCompatFlags\\Layers``), forcing Windows to
            keep the app on the true exclusive-fullscreen path and out of
            the composited FSO borderless shim.
          - ``False`` = clear any prior FSO-disable entry for that exe so
            borderless/capture variants are not fighting a stale flag from
            a previously-applied exclusive profile.

        Override in strict exclusive-fullscreen profiles to prevent
        silent fallback to borderless (the compositor adds ~3-7% FPS cost
        on high-refresh VRR setups) and in borderless capture variants to
        make the hand-off deterministic when users switch lanes.
        """
        return {}

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        """Optional fallback profile to suggest when overlays block a strict path."""
        return None

    @property
    def auto_disable_blocking_overlays(self) -> bool:
        """Whether ABSO should try to shut down blocking overlays automatically."""
        return bool(self.display_path_requirements.require_overlay_free_path)

    @property
    def is_capture_safe(self) -> bool:
        """Whether this profile is explicitly designed to coexist with the
        capture / overlay / peripheral stack.

        When True, the launch-time killset is filtered to exclude every
        image in :data:`CAPTURE_ALLOWED_IMAGES` (Discord overlay helpers,
        Medal, OBS, RTSS, NVIDIA Share/Overlay, GameOverlayUI, G HUB,
        iCUE, etc.) so those tools stay alive during play. LLM runtimes,
        cloud sync, VPN clients, and non-Discord chat are still killed.

        Default False - the standard "strict" / no-sync / G-SYNC lanes
        deliberately kill overlays for the latency benefit.
        """
        return False

    def launch_process_killset(self) -> "LaunchKillset":
        """Processes the launch-time janitor may stop while this profile's game is alive.

        Data-driven from existing profile traits; built-in lanes do not need
        a per-profile override:

        - ``productivity`` returns an empty killset (the user is actively in
          these apps; killing their overlays would be disruptive).
        - Profiles flagged ``is_capture_safe`` filter out
          :data:`CAPTURE_ALLOWED_IMAGES` so Medal / Discord overlay / OBS /
          peripheral RGB stay alive during play.
        - Every other profile (Reflex shooters, no-sync, emulator, online,
          ARPG, browser-game) returns the always-safe killset PLUS the
          opt-in tier. ABSO is aggressive by default on any gaming profile
          so cloud sync, LLM runtimes, peripheral RGB daemons, and OEM
          updaters cannot eat frame-time mid-session.

        User per-machine overrides from ``abso.yaml::process_overrides.kill``
        are appended to ``always_safe`` so they apply to every gaming profile.
        The complementary ``process_overrides.protect`` list is enforced by
        :class:`ProcessJanitor`, not here, so it survives even if a profile
        mis-declares its killset.

        Returns:
            ``LaunchKillset`` resolved against this profile's traits.
        """
        from abso.core.process_janitor import (
            ALWAYS_SAFE_LAUNCH_KILLSET,
            CAPTURE_ALLOWED_IMAGES,
            OPT_IN_LAUNCH_KILLSET,
            LaunchKillset,
            _load_user_process_overrides,
        )

        target = (self.optimization_target or "").lower()

        # Productivity intentionally returns an empty killset: nothing on the
        # always-safe list is "background" when the user is actively using
        # Discord/OBS/Medal at the desktop level.
        if target == "productivity":
            return LaunchKillset()

        _user_protect, user_kill = _load_user_process_overrides()

        # Capture-safe profiles deliberately preserve the capture / overlay
        # / peripheral stack so the profile name honors what it promises.
        # All other categories (LLM, cloud sync, VPN, chat-other-than-
        # Discord, audio enhancements) still die because they are not what
        # "capture-safe" is for.
        capture_filter = (
            CAPTURE_ALLOWED_IMAGES if self.is_capture_safe else frozenset()
        )

        # Deduplicate while preserving order (built-in items first, then the
        # user's per-machine additions). Capture-allowed entries are filtered
        # out entirely when is_capture_safe is True.
        seen: set[str] = set()
        merged_always_safe: list[str] = []
        for image in tuple(ALWAYS_SAFE_LAUNCH_KILLSET) + user_kill:
            key = image.lower()
            if key in seen:
                continue
            if key in capture_filter:
                continue
            seen.add(key)
            merged_always_safe.append(image)

        filtered_opt_in = tuple(
            image
            for image in OPT_IN_LAUNCH_KILLSET
            if image.lower() not in capture_filter
        )

        return LaunchKillset(
            always_safe=tuple(merged_always_safe),
            opt_in=filtered_opt_in,
        )

    @property
    def min_os_build(self) -> tuple[int, int] | None:
        """Minimum (build, ubr) required to apply this profile.

        Return ``None`` (default) if the profile does not require a
        specific Windows build. When set, the capability engine blocks
        apply on older builds with the ``OS_BUILD_BELOW_FLOOR`` finding.
        """
        return None

    @property
    def validated_os_build(self) -> tuple[int, int] | None:
        """Last (build, ubr) where this profile was end-to-end validated.

        Set this when bumping a profile that targets surfaces known to
        shift across Patch Tuesdays (HDR, HAGS, Xbox Mode, etc.). The
        capability engine surfaces an info finding when the user is on a
        newer build than the recorded validation point.
        """
        return None

    @property
    def xbox_mode(self) -> Literal["off", "on", "leave"]:
        """Desired Xbox Mode state for this profile.

        Xbox Mode (Win11 25H2 26200.8457+) replaces Game Mode + Full Screen
        Experience. Latency, Reflex, and capture workflows generally want
        it off; productivity / casual profiles can ``leave`` it alone.

        Default: ``"leave"`` — the apply path is wired in Phase 3 and only
        actuates when the profile explicitly overrides this.
        """
        return "leave"

    @property
    def ai_agents(self) -> Literal["off", "on", "leave"]:
        """Desired Agents-on-the-Taskbar state for this profile.

        AI agents (Researcher etc.) run background work that can cost a
        latency-sensitive session frame-time stability. Reflex paths,
        emulators, and capture lanes set this to ``"off"``.

        Default: ``"leave"`` — Phase 3 wires the apply path; until then
        the value is purely informational.
        """
        return "leave"

    @property
    def application_scope(self) -> Literal["system_only", "system_plus_native_config"]:
        """Describe how much of the profile ABSO can enforce directly.

        ``system_plus_native_config`` means ABSO applies both OS/driver state
        and a title-specific config file or emulator config handler.
        ``system_only`` means ABSO applies the machine-level path but still
        relies on manual in-app guidance for the title itself.
        """
        handler_names = {handler.__class__.__name__ for handler in self.get_handlers()}
        if any(name.endswith("ConfigHandler") for name in handler_names):
            return "system_plus_native_config"
        return "system_only"

    @abstractmethod
    def get_handlers(self) -> list[SettingsHandler]:
        """Get settings handlers used by this profile.

        Returns:
            List of SettingsHandler instances.
        """
        pass

    @abstractmethod
    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings for a specific handler.

        Args:
            handler_name: Name of the handler class.

        Returns:
            Settings dictionary for that handler.
        """
        pass

    def has_in_game_settings(self) -> bool:
        """Check if this profile has in-game settings recommendations.

        Returns:
            True if there are in-game recommendations.
        """
        return len(self.get_in_game_settings()) > 0

    @abstractmethod
    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get in-game settings recommendations.

        Returns:
            List of dicts with 'category', 'setting', 'value', 'reason' keys.
        """
        pass

    def generate_in_game_report(self) -> str:
        """Generate markdown report of in-game settings.

        Returns:
            Markdown formatted string.
        """
        lines = [
            f"# {self.display_name} - In-Game Settings",
            "",
            f"**Optimization Target:** {self.optimization_target}",
            "",
            "These settings should be configured within the game itself.",
            "",
        ]

        settings = self.get_in_game_settings()
        if not settings:
            lines.append("*No specific in-game settings recommendations.*")
            return "\n".join(lines)

        # Group by category
        categories: dict[str, list[dict[str, str]]] = {}
        for s in settings:
            cat = s.get("category", "General")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(s)

        for category, cat_settings in categories.items():
            lines.append(f"## {category}")
            lines.append("")

            for s in cat_settings:
                lines.append(f"- **{s['setting']}:** {s['value']}")
                if s.get("reason"):
                    lines.append(f"  - *{s['reason']}*")

            lines.append("")

        return "\n".join(lines)

    def validate_settings(self, applied_settings: dict[str, Any]) -> list[str]:
        """Validate the final handler settings map before ABSO applies it.

        Profiles can override this to enforce profile-specific prohibitions or
        invariants after overrides/gating have been merged.
        """
        return []
