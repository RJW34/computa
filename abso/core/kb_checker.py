"""Known-bad Windows KB (update) detection and removal.

The list is hand-maintained — Microsoft publishes per-KB release notes but
does not enumerate gaming-impacting regressions in a stable feed. Each entry
encodes:

* ``severity`` — ``critical`` blocks profile apply outright via the audit
  pipeline; ``warning`` surfaces in the report but doesn't block.
* ``fix_action`` — ``uninstall`` runs ``wusa /uninstall``; ``install_kb``
  tells the user to install a specific later cumulative; ``advisory`` is
  pure surfacing with no action.
* ``superseded_by`` — when set, the warning is suppressed if that newer KB
  is also installed. Use this for regressions that were fixed in a later
  Patch Tuesday so audits stay quiet on patched machines.
* ``fixed_in_build`` — alternative supersession by OS build/UBR (handy for
  in-place 25H2 enablement transitions).
* ``discovered_in_build`` — records the build floor this entry was scoped
  for. Helps cross-check whether older entries still apply on new OS lines.

Module-level ``LAST_REVIEWED_UTC`` is bumped whenever this list is touched;
the audit hook flags it if more than ``STALENESS_DAYS`` have elapsed so we
don't drift across Patch Tuesdays.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Bump this whenever KNOWN_BAD_KBS or the surrounding audit logic is touched.
# 2026-05-21: reviewed Insider build 29591.1000 (Experimental Future Platforms,
# Canary 29xxx) release notes. No gaming-impacting regressions called out;
# the branch is pre-27H2 (Strontium) and not yet a GA candidate. No new
# KNOWN_BAD_KBS entries added.
LAST_REVIEWED_UTC = datetime(2026, 5, 21, tzinfo=timezone.utc)

# Audit flags the list as stale beyond this window since LAST_REVIEWED_UTC.
STALENESS_DAYS = 60


@dataclass
class ProblematicKB:
    """A Windows update known to cause gaming or stability issues."""

    kb_id: str
    title: str
    severity: str  # "critical" or "warning"
    affected: str
    fix_action: str  # "uninstall" | "install_kb" | "advisory"
    superseded_by: str | None = None  # KB that fixed this regression
    fixed_in_build: tuple[int, int] | None = None  # (build, ubr) floor at which the fix lands
    discovered_in_build: str | None = None  # KB/build context for the original regression
    notes: str | None = None


KNOWN_BAD_KBS: list[ProblematicKB] = [
    # Source: Community reports of FPS drops on NVIDIA GPUs after this update.
    # Severity is "warning" (not "critical") since impact varies by system.
    ProblematicKB(
        kb_id="KB5074109",
        title="Reported NVIDIA FPS regression",
        severity="warning",
        affected="NVIDIA GPUs — reported FPS drops (impact varies by system)",
        fix_action="uninstall",
        notes="Pre-2026 community reports; no Microsoft-confirmed root cause.",
    ),
    # April 2026 cumulative caused BitLocker recovery loops on devices with
    # incorrect PCR7 TPM configurations. Microsoft fixed it in KB5089549.
    # See: support.microsoft.com KB5089549 release notes (2026-05-12).
    ProblematicKB(
        kb_id="KB5083769",
        title="BitLocker PCR7 recovery loop (fixed in KB5089549)",
        severity="warning",
        affected="BitLocker-enabled devices with PCR7 misconfiguration — boot file updates triggered recovery key prompt",
        fix_action="install_kb",
        superseded_by="KB5089549",
        fixed_in_build=(26200, 8457),
        discovered_in_build="26200.8246",
        notes="If KB5089549 is installed the regression is patched; warning is suppressed automatically.",
    ),
]


def get_installed_kbs() -> list[str]:
    """Get list of installed KB IDs via WMI.

    Returns:
        List of KB ID strings (e.g. ["KB5074109", "KB5034441"]).
    """
    try:
        import wmi

        w = wmi.WMI()
        kbs = []
        for hotfix in w.Win32_QuickFixEngineering():
            kb_id = hotfix.HotFixID
            if kb_id:
                kbs.append(kb_id.strip())
        return kbs
    except ImportError:
        logger.warning("WMI module not available for KB detection")
        return []
    except Exception as e:
        logger.error(f"Failed to query installed KBs: {e}")
        return []


def _is_superseded(
    kb: ProblematicKB,
    installed_set: set[str],
    build_revision: tuple[int, int] | None,
) -> bool:
    """Return True if the regression is patched on this machine."""
    if kb.superseded_by and kb.superseded_by.upper() in installed_set:
        return True
    if kb.fixed_in_build and build_revision is not None:
        if build_revision >= kb.fixed_in_build:
            return True
    return False


def check_problematic_kbs(
    installed_kbs: list[str] | None = None,
    build_revision: tuple[int, int] | None = None,
) -> list[ProblematicKB]:
    """Check if any known-bad KBs are installed and not yet patched.

    Args:
        installed_kbs: Pre-fetched list of installed KB IDs, or None to query.
        build_revision: Current OS (build, ubr) — when provided, supersession
            via ``fixed_in_build`` is honored. When omitted, only KB-level
            supersession is considered.

    Returns:
        List of problematic KBs that are currently installed and not patched.
    """
    if installed_kbs is None:
        installed_kbs = get_installed_kbs()

    installed_set = {kb.upper() for kb in installed_kbs}
    found: list[ProblematicKB] = []

    for bad_kb in KNOWN_BAD_KBS:
        if bad_kb.kb_id.upper() not in installed_set:
            continue
        if _is_superseded(bad_kb, installed_set, build_revision):
            logger.debug(
                "%s is installed but superseded by %s / build %s — skipping warning",
                bad_kb.kb_id,
                bad_kb.superseded_by,
                bad_kb.fixed_in_build,
            )
            continue
        found.append(bad_kb)

    return found


def list_review_staleness(now: datetime | None = None) -> int:
    """Return whole days elapsed since ``LAST_REVIEWED_UTC``.

    Args:
        now: Override the reference time (used by tests).

    Returns:
        Days elapsed since the list was last reviewed.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    delta = current - LAST_REVIEWED_UTC
    return max(delta.days, 0)


def is_review_stale(now: datetime | None = None) -> bool:
    """Whether the known-bad list is older than ``STALENESS_DAYS``."""
    return list_review_staleness(now) > STALENESS_DAYS


def uninstall_kb(kb_id: str) -> bool:
    """Uninstall a Windows KB update.

    Uses wusa.exe (Windows Update Standalone Installer) which is a built-in
    Windows tool. Requires admin privileges.

    Args:
        kb_id: The KB identifier (e.g. "KB5074109").

    Returns:
        True if uninstall succeeded or was queued, False on failure.
    """
    # Strip "KB" prefix if present for the wusa command
    kb_number = kb_id.upper().replace("KB", "")

    try:
        result = subprocess.run(
            ["wusa", "/uninstall", f"/kb:{kb_number}", "/quiet", "/norestart"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info(f"Successfully uninstalled {kb_id}")
            return True
        elif result.returncode == 0x80240017:
            # Not applicable / not installed
            logger.info(f"{kb_id} not installed or not applicable")
            return True
        else:
            logger.error(f"Failed to uninstall {kb_id}: return code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout uninstalling {kb_id}")
        return False
    except OSError as e:
        logger.error(f"Failed to run wusa for {kb_id}: {e}")
        return False
