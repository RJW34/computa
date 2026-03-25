"""Windows debloat and privacy settings handler.

Loads tweaks from a bundled YAML database (debloat_tweaks.yaml) with optional
user overrides at ~/.abso/debloat_tweaks.yaml.  Tweaks are organized into tiers:

  Tier 1 — Always safe: telemetry/privacy with zero functionality loss.
  Tier 2 — Moderate: disables features some users may rely on.
  Tier 3 — Aggressive: appx package removal, partially irreversible.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import winreg
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from abso.core.models import EvidenceTier, Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

HIVE_MAP: dict[str, int] = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
}

REG_TYPE_MAP: dict[str, int] = {
    "DWORD": winreg.REG_DWORD,
    "QWORD": winreg.REG_QWORD,
    "SZ": winreg.REG_SZ,
    "EXPAND_SZ": winreg.REG_EXPAND_SZ,
}


@dataclass(frozen=True)
class RegistryTweak:
    """A single registry-based debloat tweak."""

    name: str
    tier: int
    description: str
    hive: str
    key: str
    value: str
    reg_type: str
    desired: int | str
    default: int | str


@dataclass(frozen=True)
class ServiceTweak:
    """A single service-based debloat tweak."""

    name: str
    tier: int
    description: str
    service: str
    desired_start: int
    default_start: int


@dataclass(frozen=True)
class AppxTweak:
    """An appx package to remove."""

    name: str
    display_name: str
    tier: int


@dataclass
class DebloatTweaks:
    """Container for all debloat tweaks loaded from YAML."""

    registry: list[RegistryTweak] = field(default_factory=list)
    services: list[ServiceTweak] = field(default_factory=list)
    appx: list[AppxTweak] = field(default_factory=list)


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

_BUNDLED_YAML = Path(__file__).resolve().parent.parent / "data" / "debloat_tweaks.yaml"
_USER_YAML = Path.home() / ".abso" / "debloat_tweaks.yaml"


def _parse_registry_tweaks(raw: list[dict[str, Any]]) -> list[RegistryTweak]:
    """Parse registry tweak dicts from YAML into typed dataclasses."""
    tweaks: list[RegistryTweak] = []
    for entry in raw:
        try:
            tweaks.append(RegistryTweak(
                name=entry["name"],
                tier=int(entry["tier"]),
                description=entry.get("description", ""),
                hive=entry["hive"],
                key=entry["key"],
                value=entry["value"],
                reg_type=entry.get("type", "DWORD"),
                desired=entry["desired"],
                default=entry["default"],
            ))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed registry tweak %r: %s", entry.get("name"), exc)
    return tweaks


def _parse_service_tweaks(raw: list[dict[str, Any]]) -> list[ServiceTweak]:
    """Parse service tweak dicts from YAML into typed dataclasses."""
    tweaks: list[ServiceTweak] = []
    for entry in raw:
        try:
            tweaks.append(ServiceTweak(
                name=entry["name"],
                tier=int(entry["tier"]),
                description=entry.get("description", ""),
                service=entry["service"],
                desired_start=int(entry["desired_start"]),
                default_start=int(entry["default_start"]),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed service tweak %r: %s", entry.get("name"), exc)
    return tweaks


def _parse_appx_tweaks(raw: list[dict[str, Any]]) -> list[AppxTweak]:
    """Parse appx package dicts from YAML into typed dataclasses."""
    tweaks: list[AppxTweak] = []
    for entry in raw:
        try:
            tweaks.append(AppxTweak(
                name=entry["name"],
                display_name=entry.get("display_name", entry["name"]),
                tier=int(entry.get("tier", 3)),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed appx tweak %r: %s", entry.get("name"), exc)
    return tweaks


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML file, returning empty dict on failure."""
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return {}


def load_debloat_tweaks(user_yaml: Path | None = None) -> DebloatTweaks:
    """Load tweaks from bundled YAML, then merge with user overrides.

    User YAML entries are appended (not replaced) so users can add custom
    tweaks without losing the bundled defaults.

    Args:
        user_yaml: Path to user override YAML. Defaults to ~/.abso/debloat_tweaks.yaml.

    Returns:
        Fully parsed DebloatTweaks container.
    """
    bundled = _load_yaml(_BUNDLED_YAML)
    user = _load_yaml(user_yaml or _USER_YAML)

    registry_raw = bundled.get("registry_tweaks", []) + user.get("registry_tweaks", [])
    service_raw = bundled.get("service_tweaks", []) + user.get("service_tweaks", [])
    appx_raw = bundled.get("appx_packages", []) + user.get("appx_packages", [])

    return DebloatTweaks(
        registry=_parse_registry_tweaks(registry_raw),
        services=_parse_service_tweaks(service_raw),
        appx=_parse_appx_tweaks(appx_raw),
    )


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

# Map tier numbers to evidence tiers for audit reporting
_TIER_EVIDENCE: dict[int, EvidenceTier] = {
    1: EvidenceTier.VERIFIED,
    2: EvidenceTier.EMPIRICAL,
    3: EvidenceTier.EMPIRICAL,
}

# Map service start type integers to sc.exe config keywords
_SC_START_MAP: dict[int, str] = {
    2: "auto",
    3: "demand",
    4: "disabled",
}


class DebloatHandler(SettingsHandler):
    """Applies Windows debloat and privacy tweaks by tier.

    Tier 1 tweaks are always safe to apply. Tier 2 may disable features some
    users rely on. Tier 3 removes appx packages which requires Store/DISM to
    reinstall.

    Args:
        tier: Maximum tier to operate on (1, 2, or 3). Defaults to 1.
    """

    def __init__(self, tier: int = 1) -> None:
        self._tier = max(1, min(tier, 3))
        self._tweaks = load_debloat_tweaks()

    # -- Helpers: filtering by tier ------------------------------------------

    def _registry_tweaks(self, tier: int | None = None) -> list[RegistryTweak]:
        """Return registry tweaks up to *tier* (inclusive)."""
        max_tier = tier if tier is not None else self._tier
        return [t for t in self._tweaks.registry if t.tier <= max_tier]

    def _service_tweaks(self, tier: int | None = None) -> list[ServiceTweak]:
        """Return service tweaks up to *tier* (inclusive)."""
        max_tier = tier if tier is not None else self._tier
        return [t for t in self._tweaks.services if t.tier <= max_tier]

    def _appx_tweaks(self, tier: int | None = None) -> list[AppxTweak]:
        """Return appx tweaks up to *tier* (inclusive)."""
        max_tier = tier if tier is not None else self._tier
        return [t for t in self._tweaks.appx if t.tier <= max_tier]

    # -- Registry helpers ----------------------------------------------------

    def _read_registry_value(self, tweak: RegistryTweak) -> int | str | None:
        """Read the current value of a registry tweak. Returns None if missing."""
        hive_int = HIVE_MAP.get(tweak.hive)
        if hive_int is None:
            logger.warning("Unknown registry hive %r in tweak %r", tweak.hive, tweak.name)
            return None

        try:
            with winreg.OpenKey(hive_int, tweak.key, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, tweak.value)
                return val  # type: ignore[no-any-return]
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.debug("Cannot read %s\\%s\\%s: %s", tweak.hive, tweak.key, tweak.value, exc)
            return None

    def _write_registry_value(self, tweak: RegistryTweak, value: int | str) -> None:
        """Write a value into the registry, creating the key if needed."""
        hive_int = HIVE_MAP.get(tweak.hive)
        reg_type = REG_TYPE_MAP.get(tweak.reg_type, winreg.REG_DWORD)
        if hive_int is None:
            raise ValueError(f"Unknown hive {tweak.hive!r}")

        with winreg.CreateKeyEx(hive_int, tweak.key, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, tweak.value, 0, reg_type, value)

    # -- Service helpers -----------------------------------------------------

    def _get_service_start_type(self, service_name: str) -> int | None:
        """Query the start type of a Windows service via sc qc."""
        try:
            result = subprocess.run(
                ["sc", "qc", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return None
            for line in result.stdout.splitlines():
                if "START_TYPE" in line:
                    if "AUTO_START" in line:
                        return 2
                    if "DEMAND_START" in line:
                        return 3
                    if "DISABLED" in line:
                        return 4
            return None
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.debug("sc qc %s failed: %s", service_name, exc)
            return None

    def _set_service_start_type(self, service_name: str, start_type: int) -> bool:
        """Set the start type of a Windows service via sc config."""
        sc_keyword = _SC_START_MAP.get(start_type)
        if sc_keyword is None:
            logger.error("Invalid start type %d for service %s", start_type, service_name)
            return False
        try:
            result = subprocess.run(
                ["sc", "config", service_name, f"start={sc_keyword}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.error(
                    "sc config %s start=%s failed: %s",
                    service_name, sc_keyword,
                    result.stderr.strip() or result.stdout.strip(),
                )
                return False
            return True
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.error("sc config %s failed: %s", service_name, exc)
            return False

    def _stop_service(self, service_name: str) -> bool:
        """Stop a running Windows service."""
        try:
            result = subprocess.run(
                ["sc", "stop", service_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.debug("sc stop %s failed: %s", service_name, exc)
            return False

    # -- Appx helpers --------------------------------------------------------

    def _is_appx_installed(self, package_name: str) -> bool:
        """Check if an appx package is installed for the current user."""
        try:
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f"if (Get-AppxPackage -Name '{package_name}') {{ 'INSTALLED' }} else {{ 'MISSING' }}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return "INSTALLED" in result.stdout
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.debug("Appx check for %s failed: %s", package_name, exc)
            return False

    def _remove_appx_package(self, package_name: str) -> bool:
        """Remove an appx package for the current user."""
        try:
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f"Get-AppxPackage -Name '{package_name}' | Remove-AppxPackage -ErrorAction SilentlyContinue",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0 and result.stderr.strip():
                logger.warning("Remove-AppxPackage %s stderr: %s", package_name, result.stderr.strip())
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("Timeout removing appx package %s", package_name)
            return False
        except OSError as exc:
            logger.error("Failed to remove appx package %s: %s", package_name, exc)
            return False

    # -----------------------------------------------------------------------
    # SettingsHandler interface
    # -----------------------------------------------------------------------

    def detect(self) -> dict[str, Any]:
        """Read current state of all managed registry keys, services, and packages.

        Returns a dict keyed by category, each containing per-tweak state.
        The result is suitable for both auditing and backup/restore.
        """
        state: dict[str, Any] = {
            "registry": {},
            "services": {},
            "appx": {},
        }

        # Registry tweaks — read ALL tiers so backup captures everything
        for tweak in self._tweaks.registry:
            current = self._read_registry_value(tweak)
            state["registry"][tweak.name] = {
                "tier": tweak.tier,
                "hive": tweak.hive,
                "key": tweak.key,
                "value_name": tweak.value,
                "reg_type": tweak.reg_type,
                "current": current,
                "desired": tweak.desired,
                "default": tweak.default,
            }

        # Service tweaks — read ALL tiers
        for tweak in self._tweaks.services:
            start_type = self._get_service_start_type(tweak.service)
            state["services"][tweak.name] = {
                "tier": tweak.tier,
                "service": tweak.service,
                "current_start": start_type,
                "desired_start": tweak.desired_start,
                "default_start": tweak.default_start,
            }

        # Appx packages — read ALL tiers
        for tweak in self._tweaks.appx:
            installed = self._is_appx_installed(tweak.name)
            state["appx"][tweak.name] = {
                "tier": tweak.tier,
                "display_name": tweak.display_name,
                "installed": installed,
            }

        return state

    def audit(self) -> list[Issue]:
        """Report which telemetry/privacy items are still enabled.

        Returns one Issue per enabled/non-optimal item, tagged with its tier.
        Only items up to the configured tier are reported.
        """
        issues: list[Issue] = []
        current = self.detect()

        # Registry tweaks
        for tweak in self._registry_tweaks():
            info = current["registry"].get(tweak.name, {})
            cur_val = info.get("current")
            if cur_val is None:
                # Key doesn't exist — treat as needing the tweak
                issues.append(Issue(
                    title=f"[Debloat T{tweak.tier}] {tweak.name} — not configured",
                    severity="info",
                    current_value="(not set)",
                    optimal_value=str(tweak.desired),
                    explanation=tweak.description,
                    category="debloat",
                    evidence_tier=_TIER_EVIDENCE.get(tweak.tier, EvidenceTier.EMPIRICAL),
                ))
            elif cur_val != tweak.desired:
                issues.append(Issue(
                    title=f"[Debloat T{tweak.tier}] {tweak.name}",
                    severity="warning" if tweak.tier == 1 else "info",
                    current_value=str(cur_val),
                    optimal_value=str(tweak.desired),
                    explanation=tweak.description,
                    category="debloat",
                    evidence_tier=_TIER_EVIDENCE.get(tweak.tier, EvidenceTier.EMPIRICAL),
                ))

        # Service tweaks
        for tweak in self._service_tweaks():
            info = current["services"].get(tweak.name, {})
            cur_start = info.get("current_start")
            if cur_start is not None and cur_start != tweak.desired_start:
                start_names = {2: "Automatic", 3: "Manual", 4: "Disabled"}
                issues.append(Issue(
                    title=f"[Debloat T{tweak.tier}] {tweak.name}",
                    severity="info",
                    current_value=start_names.get(cur_start, str(cur_start)),
                    optimal_value=start_names.get(tweak.desired_start, str(tweak.desired_start)),
                    explanation=tweak.description,
                    category="debloat",
                    evidence_tier=_TIER_EVIDENCE.get(tweak.tier, EvidenceTier.EMPIRICAL),
                ))

        # Appx packages (only at tier 3)
        for tweak in self._appx_tweaks():
            info = current["appx"].get(tweak.name, {})
            if info.get("installed"):
                issues.append(Issue(
                    title=f"[Debloat T3] {tweak.display_name} is installed",
                    severity="info",
                    current_value="Installed",
                    optimal_value="Removed",
                    explanation=(
                        f"Appx package {tweak.name} can be removed to reduce background "
                        f"activity. Reinstall via Microsoft Store if needed."
                    ),
                    category="debloat",
                    evidence_tier=EvidenceTier.EMPIRICAL,
                ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply debloat tweaks up to the requested tier.

        Args:
            settings: Dict with optional ``debloat_tier`` key (1-3).
                      Falls back to the tier set in ``__init__``.

        Returns:
            Result dict with ``success``, ``error``, ``requires_reboot``,
            ``applied``, and ``warnings`` keys.
        """
        tier = settings.get("debloat_tier", self._tier)
        tier = max(1, min(tier, 3))

        applied: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []

        # --- Registry tweaks ---
        for tweak in self._registry_tweaks(tier):
            try:
                self._write_registry_value(tweak, tweak.desired)
                applied.append(f"registry:{tweak.name}")
                logger.info("Applied debloat tweak: %s", tweak.name)
            except PermissionError:
                errors.append(f"{tweak.name}: Access denied (requires admin)")
                logger.error("Permission denied writing %s", tweak.name)
            except Exception as exc:
                errors.append(f"{tweak.name}: {exc}")
                logger.error("Failed to apply tweak %s: %s", tweak.name, exc)

        # --- Service tweaks ---
        for tweak in self._service_tweaks(tier):
            ok = self._set_service_start_type(tweak.service, tweak.desired_start)
            if ok:
                applied.append(f"service:{tweak.name}")
                logger.info("Configured service %s start=%d", tweak.service, tweak.desired_start)
                # Stop the service if we are disabling it
                if tweak.desired_start == 4:
                    self._stop_service(tweak.service)
            else:
                errors.append(f"{tweak.name}: Failed to configure service {tweak.service}")

        # --- Appx packages (tier 3 only) ---
        if tier >= 3:
            for tweak in self._appx_tweaks(tier):
                if not self._is_appx_installed(tweak.name):
                    logger.debug("Appx %s already removed, skipping", tweak.name)
                    continue
                ok = self._remove_appx_package(tweak.name)
                if ok:
                    applied.append(f"appx:{tweak.name}")
                    logger.info("Removed appx package %s (%s)", tweak.name, tweak.display_name)
                else:
                    errors.append(f"appx:{tweak.name}: Failed to remove")

            warnings.append(
                "Tier 3 appx packages were removed. "
                "Reinstall via Microsoft Store or DISM if needed."
            )

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
            "applied": applied,
            "warnings": warnings,
        }

    def backup(self) -> dict[str, Any]:
        """Store current state for restore.

        Captures the full state across all tiers so that a restore can undo
        changes regardless of the tier that was originally applied.
        """
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore registry and service settings from backup.

        Appx packages cannot be automatically reinstalled — a warning is logged
        for any packages that were present in the backup but are now missing.

        Args:
            data: Previously backed up state from :meth:`backup`.

        Returns:
            True if all restorable items succeeded, False otherwise.
        """
        success = True

        # Restore registry values
        for tweak_name, info in data.get("registry", {}).items():
            restore_val = info.get("current")
            if restore_val is None:
                # Value didn't exist before — attempt to delete it
                hive_int = HIVE_MAP.get(info.get("hive", ""), 0)
                if hive_int:
                    with contextlib.suppress(OSError):
                        with winreg.OpenKey(hive_int, info["key"], 0, winreg.KEY_SET_VALUE) as key:
                            winreg.DeleteValue(key, info["value_name"])
                continue

            # Reconstruct a lightweight tweak for _write_registry_value
            try:
                tweak = RegistryTweak(
                    name=tweak_name,
                    tier=info.get("tier", 1),
                    description="",
                    hive=info["hive"],
                    key=info["key"],
                    value=info["value_name"],
                    reg_type=info.get("reg_type", "DWORD"),
                    desired=restore_val,
                    default=info.get("default", 0),
                )
                self._write_registry_value(tweak, restore_val)
                logger.info("Restored registry tweak: %s = %s", tweak_name, restore_val)
            except Exception as exc:
                logger.error("Failed to restore registry tweak %s: %s", tweak_name, exc)
                success = False

        # Restore service start types
        for tweak_name, info in data.get("services", {}).items():
            cur_start = info.get("current_start")
            if cur_start is not None:
                ok = self._set_service_start_type(info["service"], cur_start)
                if ok:
                    logger.info("Restored service %s to start=%d", info["service"], cur_start)
                else:
                    logger.error("Failed to restore service %s", info["service"])
                    success = False

        # Warn about appx packages — cannot auto-reinstall
        for pkg_name, info in data.get("appx", {}).items():
            if info.get("installed") and not self._is_appx_installed(pkg_name):
                logger.warning(
                    "Appx package %s (%s) was installed before but is now removed. "
                    "Reinstall via Microsoft Store or DISM.",
                    pkg_name,
                    info.get("display_name", pkg_name),
                )

        return success
