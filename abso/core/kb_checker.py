"""Known-bad Windows KB (update) detection and removal."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProblematicKB:
    """A Windows update known to cause gaming performance issues."""

    kb_id: str
    title: str
    severity: str  # "critical" or "warning"
    affected: str
    fix_action: str  # "uninstall"


KNOWN_BAD_KBS: list[ProblematicKB] = [
    # Source: Community reports of FPS drops on NVIDIA GPUs after this update.
    # Severity is "warning" (not "critical") since impact varies by system.
    ProblematicKB(
        kb_id="KB5074109",
        title="Reported NVIDIA FPS regression",
        severity="warning",
        affected="NVIDIA GPUs — reported FPS drops (impact varies by system)",
        fix_action="uninstall",
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


def check_problematic_kbs(installed_kbs: list[str] | None = None) -> list[ProblematicKB]:
    """Check if any known-bad KBs are installed.

    Args:
        installed_kbs: Pre-fetched list of installed KB IDs, or None to query.

    Returns:
        List of problematic KBs that are currently installed.
    """
    if installed_kbs is None:
        installed_kbs = get_installed_kbs()

    installed_set = {kb.upper() for kb in installed_kbs}
    found: list[ProblematicKB] = []

    for bad_kb in KNOWN_BAD_KBS:
        if bad_kb.kb_id.upper() in installed_set:
            found.append(bad_kb)

    return found


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
