"""GPU MSI (Message Signaled Interrupts) mode handler.

Line-based interrupts share an IRQ and add interrupt-dispatch latency; switching
the GPU to MSI mode (``MSISupported = 1``) removes that and measurably lowers
input-to-photon latency on some boards. The flag lives per PCI device under::

    HKLM\\SYSTEM\\CurrentControlSet\\Enum\\<PNPDeviceID>\\Device Parameters\\
        Interrupt Management\\MessageSignaledInterruptProperties\\MSISupported

It is a plain DWORD, fully restorable, but only takes effect after a reboot.
The GPU's PCI instance path is resolved from WMI ``Win32_VideoController``.
"""

from __future__ import annotations

import contextlib
import logging
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

_ENUM_ROOT = r"SYSTEM\CurrentControlSet\Enum"
_MSI_SUBPATH = r"Device Parameters\Interrupt Management\MessageSignaledInterruptProperties"


class InterruptModeHandler(SettingsHandler):
    """Enable MSI mode for the GPU(s) to reduce interrupt-dispatch latency."""

    # Reboot-gated and aggressive/optional: a verify miss is a WARNING, not a
    # CRITICAL apply failure.
    is_critical_verify = False

    @property
    def restore_guarantee(self) -> str:
        # Best-effort: the Enum\PCI keys can be ACL-restricted, so a failed
        # revert must not block a profile switch's baseline restore.
        return "partial"

    def detect(self) -> dict[str, Any]:
        """Return MSISupported state per GPU PCI instance."""
        gpu_msi: dict[str, int | None] = {}
        for pnp_id in self._get_gpu_pnp_ids():
            gpu_msi[pnp_id] = self._read_msi(pnp_id)
        return {"gpu_msi": gpu_msi}

    def audit(self) -> list[Issue]:
        """Flag GPUs that are not in MSI mode."""
        issues: list[Issue] = []
        gpu_msi = self.detect().get("gpu_msi", {})
        not_msi = [pnp for pnp, val in gpu_msi.items() if val != 1]
        if gpu_msi and not_msi:
            issues.append(
                Issue(
                    title="GPU is not using MSI interrupt mode",
                    severity="info",
                    current_value="MSISupported != 1 on "
                    + ", ".join(self._short_id(p) for p in not_msi),
                    optimal_value="MSISupported = 1 (reboot required)",
                    explanation=(
                        "Message Signaled Interrupts remove shared line-based IRQ "
                        "dispatch latency and can lower input-to-photon latency. "
                        "Takes effect after a reboot."
                    ),
                    category="nvidia",
                )
            )
        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply MSI mode.

        Settings:
            enable_msi: bool - when True, set MSISupported=1 for every GPU PCI
                instance. Requires a reboot to take effect.
        """
        if not settings.get("enable_msi"):
            return {"success": True, "error": None, "requires_reboot": False, "changed": False}

        warnings: list[str] = []
        changed_keys: list[str] = []
        gpu_ids = self._get_gpu_pnp_ids()
        if not gpu_ids:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "changed": False,
                "skipped": "No PCI GPU instance found",
            }

        for pnp_id in gpu_ids:
            try:
                if self._read_msi(pnp_id) != 1:
                    self._write_msi(pnp_id, 1)
                    changed_keys.append(self._short_id(pnp_id))
            except OSError as exc:
                # The Enum\PCI keys can be ACL-restricted even under admin.
                # Best-effort: warn rather than fail (and roll back) the profile.
                warnings.append(f"MSI mode: could not set {self._short_id(pnp_id)} ({exc})")

        return {
            "success": True,
            "error": None,
            # Only a reboot commits the interrupt-mode change.
            "requires_reboot": bool(changed_keys),
            "reboot_reasons": ["InterruptModeHandler.msi_mode"] if changed_keys else [],
            "changed": bool(changed_keys),
            "changed_keys": changed_keys,
            "warnings": warnings,
        }

    def backup(self) -> dict[str, Any]:
        """Capture MSISupported per GPU instance (None = value absent)."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Write back the captured MSISupported values (delete those absent)."""
        try:
            for pnp_id, original in (data.get("gpu_msi") or {}).items():
                self._restore_msi(pnp_id, original)
        except Exception as exc:  # noqa: BLE001 - best-effort, never block a switch
            logger.error("Failed to restore GPU MSI mode: %s", exc)
        return True

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify GPU MSI mode, honestly accounting for its reboot gate.

        MSISupported is a plain DWORD, but the interrupt-mode change only goes
        live after a reboot. Like ``GraphicsSettingsHandler`` does for MPO, this
        must not report a freshly-written value as fully active while the commit
        is still pending — otherwise the user is told MSI mode is live when it is
        not. Gating uses the MSI-*specific* reboot reason
        (``InterruptModeHandler.msi_mode``) rather than the global reboot bit, so
        an already-committed MSI mode is never mislabeled just because some other
        setting happens to need a reboot.
        """
        results: dict[str, Any] = {"all_active": True, "settings": {}}
        if not settings.get("enable_msi"):
            return results

        gpu_msi = self.detect().get("gpu_msi", {})
        if not gpu_msi:
            # No GPU PCI instance resolved (WMI failure or no PCI GPU). A
            # requested MSI enable that cannot be confirmed must fail closed
            # rather than report a vacuous all-active. is_critical_verify=False
            # keeps this a WARNING, not a CRITICAL apply failure.
            results["all_active"] = False
            results["settings"]["msi:unresolved"] = {
                "target": 1,
                "current": None,
                "active": False,
                "note": (
                    "No GPU PCI instance resolved; MSI mode could not be "
                    "verified (WMI unavailable?)."
                ),
            }
            results.setdefault("pending_apply_settings", []).append("msi_mode")
            return results

        msi_reboot_pending = self._msi_reboot_pending(settings)
        for pnp_id, value in gpu_msi.items():
            written = value == 1
            # Reboot-gated: registry written != live until the reboot commits it.
            live = written and not msi_reboot_pending
            key = f"msi:{self._short_id(pnp_id)}"
            results["settings"][key] = {
                "target": 1,
                "current": value,
                "active": live,
                "reboot_gated": True,
                "activation": "after_reboot",
                "registry_target_written": written,
                "live_activation_verifiable": False,
            }
            if not written:
                results["all_active"] = False
                results.setdefault("pending_apply_settings", []).append(key)
            elif msi_reboot_pending:
                results["all_active"] = False
                results.setdefault("pending_reboot_gated_settings", []).append(key)
        return results

    @staticmethod
    def _msi_reboot_pending(settings: dict[str, Any]) -> bool:
        """Return True when an MSI-mode change is written but not yet committed.

        Reads the MSI-specific reboot reason from the injected
        ``_reboot_reasons`` (when a caller threads it through), otherwise falls
        back to the persisted state snapshot. Never raises — a state-IO failure
        degrades to "not pending" so verify can still run.
        """
        reasons = settings.get("_reboot_reasons")
        if reasons is None:
            try:
                from abso.core.app_paths import app_state_file
                from abso.core.state_store import read_state_snapshot

                reasons = read_state_snapshot([app_state_file()]).get("reboot_reasons") or []
            except Exception:  # noqa: BLE001 — verify must never fail on state IO
                reasons = []
        return "InterruptModeHandler.msi_mode" in set(reasons)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _short_id(pnp_id: str) -> str:
        """Trim a long PNPDeviceID to its VEN/DEV head for display."""
        parts = pnp_id.split("\\")
        return parts[1] if len(parts) > 1 else pnp_id

    def _get_gpu_pnp_ids(self) -> list[str]:
        """Resolve GPU PCI instance paths via WMI Win32_VideoController."""
        try:
            import wmi  # type: ignore[import-untyped]

            client = wmi.WMI()
            ids: list[str] = []
            for controller in client.Win32_VideoController():
                pnp = getattr(controller, "PNPDeviceID", None)
                if pnp and str(pnp).upper().startswith("PCI\\"):
                    ids.append(str(pnp))
            return ids
        except Exception as exc:  # noqa: BLE001 - WMI may be unavailable
            logger.debug("Could not resolve GPU PCI instance via WMI: %s", exc)
            return []

    @staticmethod
    def _msi_subkey(pnp_id: str) -> str:
        return f"{_ENUM_ROOT}\\{pnp_id}\\{_MSI_SUBPATH}"

    def _read_msi(self, pnp_id: str) -> int | None:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, self._msi_subkey(pnp_id), 0, winreg.KEY_READ
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.debug("Cannot read MSI key for %s: %s", self._short_id(pnp_id), exc)
            return None
        try:
            try:
                value, _ = winreg.QueryValueEx(key, "MSISupported")
                return int(value)
            except FileNotFoundError:
                return None
        finally:
            winreg.CloseKey(key)

    def _write_msi(self, pnp_id: str, value: int) -> None:
        key = winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE, self._msi_subkey(pnp_id), 0, winreg.KEY_SET_VALUE
        )
        try:
            winreg.SetValueEx(key, "MSISupported", 0, winreg.REG_DWORD, int(value))
        finally:
            winreg.CloseKey(key)

    def _restore_msi(self, pnp_id: str, original: int | None) -> None:
        if original is None:
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, self._msi_subkey(pnp_id), 0, winreg.KEY_SET_VALUE
                )
            except FileNotFoundError:
                return
            try:
                with contextlib.suppress(FileNotFoundError):
                    winreg.DeleteValue(key, "MSISupported")
            finally:
                winreg.CloseKey(key)
            return
        self._write_msi(pnp_id, int(original))
