"""OS release introspection.

Single source of truth for Windows version/build/UBR. Profiles, capability
checks, and feature-gated handlers depend on knowing whether the current OS
is new enough to expose a given surface (Xbox Mode, AI agents, Secure Boot
cert rollout, etc.).

Reads ``HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion``. Values are
cached for the lifetime of the process; call :func:`invalidate_cache` after
a cumulative-update detection (e.g. fresh ``Get-HotFix`` result) so future
:func:`detect_os_release` calls re-read the registry.
"""

from __future__ import annotations

import logging
import winreg
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)

_REG_PATH: Final = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
_cache: OsRelease | None = None

# Build floor for the Experimental (Future Platforms) Canary 29xxx series.
# Microsoft split the experimental channel in February 2026 (build 29531+);
# anything at or above this floor is on the future-platforms branch that is
# expected to eventually feed 27H2 (Strontium). The branch is explicitly
# "not matched to any specific release of Windows" per the Insider release
# notes, so feature surface here is volatile.
_FUTURE_PLATFORMS_BUILD_FLOOR: Final = 29000

# Build floor where Win11 25H2 (Germanium-track GA) became identifiable.
_25H2_BUILD_FLOOR: Final = 26200


@dataclass(frozen=True)
class OsRelease:
    """Snapshot of the Windows release identity.

    Fields mirror the underlying CurrentVersion registry values. ``build``
    and ``ubr`` are the parts callers usually compare against (e.g. is this
    machine on 26200.8457 or newer?).
    """

    product_name: str
    display_version: str
    edition_id: str
    installation_type: str
    build: int
    ubr: int

    @property
    def build_revision(self) -> tuple[int, int]:
        """Return (build, ubr) as a tuple for ordering comparisons."""
        return (self.build, self.ubr)

    @property
    def is_windows_11(self) -> bool:
        """Whether this OS reports as Windows 11.

        The product_name field still reads ``Windows 10 ...`` on 25H2 — Win11
        is identified by build (>= 22000) rather than ProductName.
        """
        return self.build >= 22000

    @property
    def is_25h2_or_newer(self) -> bool:
        """Whether this OS is Win11 25H2 or any later release."""
        return self.build >= _25H2_BUILD_FLOOR

    @property
    def is_experimental_future_platform(self) -> bool:
        """Whether this OS is on the Canary 29xxx / Experimental future track.

        These builds are pre-27H2 (Strontium) candidates. Microsoft labels
        them as not matched to any specific Windows release, so ABSO treats
        them as best-effort: detection still runs, but audit findings and
        registry-surface guesses may be wrong until the branch settles.
        """
        return self.build >= _FUTURE_PLATFORMS_BUILD_FLOOR

    @property
    def release_branch(self) -> str:
        """Coarse-grained branch label for reports and banners.

        Returns one of:
          * ``"experimental_future_platforms"`` — Canary 29xxx / pre-27H2
          * ``"25h2_track"`` — Germanium-track 25H2 / 26H1 / 26H2 builds
          * ``"pre_25h2"`` — Win11 24H2 or earlier
          * ``"unknown"`` — registry was unreadable
        """
        if self.build == 0:
            return "unknown"
        if self.is_experimental_future_platform:
            return "experimental_future_platforms"
        if self.is_25h2_or_newer:
            return "25h2_track"
        return "pre_25h2"

    def at_least(self, build: int, ubr: int = 0) -> bool:
        """Whether this release is at or above the given (build, ubr) floor."""
        return self.build_revision >= (build, ubr)

    def at_most(self, build: int, ubr: int = 0) -> bool:
        """Whether this release is at or below the given (build, ubr) ceiling."""
        return self.build_revision <= (build, ubr)

    def to_dict(self) -> dict[str, object]:
        """JSON-safe serialization for reports and backups."""
        return {
            "product_name": self.product_name,
            "display_version": self.display_version,
            "edition_id": self.edition_id,
            "installation_type": self.installation_type,
            "build": self.build,
            "ubr": self.ubr,
            "build_revision": f"{self.build}.{self.ubr}",
            "release_branch": self.release_branch,
            "is_experimental_future_platform": self.is_experimental_future_platform,
        }


def _read_str(key, name: str, default: str = "") -> str:
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return str(value) if value is not None else default
    except FileNotFoundError:
        return default


def _read_int(key, name: str, default: int = 0) -> int:
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def detect_os_release(cached: bool = True) -> OsRelease:
    """Read the current Windows release from the registry.

    Args:
        cached: When True (default), return the cached value if available.
            When False, force a fresh registry read.

    Returns:
        An :class:`OsRelease` snapshot. On unreadable registry the returned
        snapshot has empty strings and zeroed build/ubr — never raises.
    """
    global _cache
    if cached and _cache is not None:
        return _cache

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _REG_PATH, 0, winreg.KEY_READ)
    except OSError as exc:
        logger.warning("Failed to open CurrentVersion key: %s", exc)
        return OsRelease(
            product_name="",
            display_version="",
            edition_id="",
            installation_type="",
            build=0,
            ubr=0,
        )

    try:
        product_name = _read_str(key, "ProductName")
        display_version = _read_str(key, "DisplayVersion")
        edition_id = _read_str(key, "EditionID")
        installation_type = _read_str(key, "InstallationType")
        build_str = _read_str(key, "CurrentBuildNumber", "0")
        try:
            build = int(build_str)
        except ValueError:
            build = _read_int(key, "CurrentBuild", 0)
        ubr = _read_int(key, "UBR", 0)
    finally:
        winreg.CloseKey(key)

    release = OsRelease(
        product_name=product_name,
        display_version=display_version,
        edition_id=edition_id,
        installation_type=installation_type,
        build=build,
        ubr=ubr,
    )
    _cache = release
    return release


def invalidate_cache() -> None:
    """Drop the cached OsRelease so the next call re-reads the registry.

    Call this after detecting a cumulative-update install (or in tests) so
    stale build/UBR values do not leak across phases.
    """
    global _cache
    _cache = None
