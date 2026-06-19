"""NIC driver advanced-property tuning handler.

The active network adapter ships vendor defaults that favor throughput and
power savings over latency. For competitive online play the tail latency of
the receive path matters more than the headline bandwidth, so this handler
tunes the adapter's *driver advanced properties* toward a low-jitter profile:

- ``*InterruptModeration`` -> Disabled - the NIC raises an interrupt per
  packet instead of coalescing, trading a little CPU for lower receive latency.
- ``*RSS`` (Receive Side Scaling) -> Enabled - spreads receive processing
  across CPU cores so one saturated core does not stall the rx queue.
- ``*FlowControl`` (802.3x) -> Disabled - stops the link partner from pausing
  our transmit path, which otherwise injects multi-millisecond stalls.
- ``*EEE`` (Energy Efficient Ethernet) -> Disabled - keeps the PHY out of
  low-power idle so the first packet after an idle gap is not delayed.

This is *per-NIC, opt-in* tuning. Advanced-property registry keywords vary by
vendor (Intel, Realtek, Killer, Aquantia all spell them differently), so each
target keyword is matched case-insensitively against a vendor-neutral suffix
and any keyword the adapter does not expose is simply skipped. All writes are
plain driver advanced properties that fully restore and take effect without a
reboot, though setting them may briefly reset the link.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler
from abso.utils.proc import no_window_creationflags

logger = logging.getLogger(__name__)

_PS_TIMEOUT = 20

# Vendor-neutral keyword suffix -> (human label, optimal RegistryValue string).
# Keywords are matched case-insensitively against the suffix because vendors
# prefix them differently (e.g. ``*InterruptModeration`` vs ``EnableInterrupt
# Moderation``). The leading ``*`` is part of the canonical Windows keyword for
# standardized properties and is preserved when matching by suffix.
_TARGETS: dict[str, tuple[str, str]] = {
    "InterruptModeration": ("Interrupt Moderation", "0"),
    "RSS": ("Receive Side Scaling", "1"),
    "FlowControl": ("Flow Control", "0"),
    "EEE": ("Energy Efficient Ethernet", "0"),
}


class NicDriverHandler(SettingsHandler):
    """Tune the active network adapter's driver advanced properties for latency."""

    # Opt-in best-effort latency add-on: a verify miss is a WARNING, not a
    # CRITICAL apply failure (apply is best-effort too).
    is_critical_verify = False

    @property
    def restore_guarantee(self) -> str:
        # Best-effort: a driver rejecting a keyword on restore must not block a
        # profile switch's baseline restore.
        return "partial"

    # -- SettingsHandler contract -----------------------------------------

    def detect(self) -> dict[str, Any]:
        """Detect the active adapter and its targeted advanced-property values.

        Returns:
            ``{"adapter": name|None, "properties": {keyword: registry_value}}``
            where ``properties`` only contains the targeted keywords the
            adapter actually exposes (vendor spelling preserved).
        """
        adapter = self._active_adapter()
        if adapter is None:
            return {"adapter": None, "properties": {}}
        return {"adapter": adapter, "properties": self._targeted_properties(adapter)}

    def audit(self) -> list[Issue]:
        """Flag any targeted advanced property not at its optimal value.

        Emits a single ``info`` issue describing the opt-in, per-NIC tuning so
        it never escalates above the other latency tweaks during a scan.
        """
        issues: list[Issue] = []
        current = self.detect()
        adapter = current.get("adapter")
        properties: dict[str, str] = current.get("properties", {})
        if not adapter or not properties:
            return issues

        suboptimal: list[str] = []
        for keyword, value in properties.items():
            target = self._target_for(keyword)
            if target is not None and str(value) != target[1]:
                suboptimal.append(target[0])

        if suboptimal:
            issues.append(
                Issue(
                    title="NIC driver latency properties are not tuned",
                    severity="info",
                    current_value=f"{adapter}: " + ", ".join(sorted(suboptimal)),
                    optimal_value=(
                        "Interrupt Moderation off, RSS on, Flow Control off, EEE off"
                    ),
                    explanation=(
                        "Opt-in, per-NIC tuning: disabling interrupt moderation, flow "
                        "control, and Energy Efficient Ethernet while enabling RSS lowers "
                        "receive tail latency for online play. Applies only to the active "
                        "adapter and may briefly reset the link."
                    ),
                    category="network",
                )
            )
        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply the low-latency driver profile when ``nic_tuning`` is requested.

        Settings:
            nic_tuning: bool - when True, set each targeted keyword the adapter
                exposes to its optimal RegistryValue. Absent keywords are
                skipped. When no active adapter exists, this is a graceful
                no-op.
        """
        if not settings.get("nic_tuning"):
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "changed": False,
                "note": "NIC tuning not requested",
            }

        adapter = self._active_adapter()
        if adapter is None:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "changed": False,
                "note": "No active (Up) physical adapter found; skipped",
            }

        properties = self._targeted_properties(adapter)
        warnings: list[str] = []
        changed_keys: list[str] = []
        for keyword in properties:
            target = self._target_for(keyword)
            if target is None:
                continue
            try:
                if self._set_property(adapter, keyword, target[1]):
                    changed_keys.append(keyword)
                else:
                    warnings.append(f"NIC tuning: {keyword} could not be set")
            except Exception as exc:  # noqa: BLE001 - one keyword must not abort the rest
                warnings.append(f"NIC tuning: {keyword} ({exc})")

        # Best-effort: this is an opt-in, per-NIC latency add-on, so a driver
        # rejecting a keyword surfaces as a warning rather than failing (and
        # rolling back) the whole profile apply. verify_active still reports it.
        return {
            "success": True,
            "error": None,
            "requires_reboot": False,
            "changed": bool(changed_keys),
            "changed_keys": changed_keys,
            "warnings": warnings,
            "note": "Adapter may briefly reset while properties are applied",
        }

    def backup(self) -> dict[str, Any]:
        """Capture the adapter name and the original value of each targeted key.

        Returns:
            ``{"adapter": name|None, "properties": {keyword: registry_value}}``
            mirroring :meth:`detect` so :meth:`restore` can write the exact
            originals back.
        """
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore each captured keyword to its original RegistryValue.

        Only keywords present in the backup are touched; anything the adapter
        did not expose at backup time is left alone.
        """
        adapter = data.get("adapter")
        properties: dict[str, str] = data.get("properties", {})
        if not adapter or not properties:
            # Nothing was captured (no active adapter / no targeted keys); the
            # original state is already intact.
            return True
        try:
            for keyword, value in properties.items():
                self._set_property(adapter, keyword, str(value))
        except Exception as exc:  # noqa: BLE001 - best-effort, never block a switch
            logger.error("Failed to restore NIC driver settings: %s", exc)
        return True

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Confirm each exposed targeted keyword sits at its optimal value."""
        results: dict[str, Any] = {"all_active": True, "settings": {}}
        if not settings.get("nic_tuning"):
            return results

        current = self.detect()
        properties: dict[str, str] = current.get("properties", {})
        for keyword, value in properties.items():
            target = self._target_for(keyword)
            if target is None:
                continue
            active = str(value) == target[1]
            results["settings"][keyword] = {
                "target": target[1],
                "current": value,
                "active": active,
            }
            if not active:
                results["all_active"] = False
        return results

    # -- PowerShell entry point -------------------------------------------

    def _run_ps(self, script: str) -> subprocess.CompletedProcess:
        """Run a PowerShell script and return the completed process.

        This is the single PowerShell entry point for the handler so tests can
        inject a fake without touching real Get/Set-NetAdapterAdvancedProperty
        cmdlets.

        Args:
            script: The PowerShell command text to execute.

        Returns:
            The :class:`subprocess.CompletedProcess` result.
        """
        return subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=_PS_TIMEOUT,
            creationflags=no_window_creationflags(),
        )

    # -- helpers ----------------------------------------------------------

    def _active_adapter(self) -> str | None:
        """Return the name of the first Up physical adapter, or None."""
        script = (
            "Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | "
            "Select-Object -First 1 Name | ConvertTo-Json"
        )
        data = self._run_json(script)
        if isinstance(data, list):
            data = data[0] if data else None
        if isinstance(data, dict):
            name = data.get("Name")
            return str(name) if name else None
        return None

    def _targeted_properties(self, adapter: str) -> dict[str, str]:
        """Return ``{keyword: registry_value}`` for targeted keys on ``adapter``.

        Only keywords whose suffix matches one of :data:`_TARGETS` (case
        insensitively) are returned, preserving the vendor's exact spelling.
        """
        script = (
            f"Get-NetAdapterAdvancedProperty -Name '{self._escape(adapter)}' | "
            "Select-Object RegistryKeyword,DisplayValue,RegistryValue | ConvertTo-Json"
        )
        data = self._run_json(script)
        rows = self._as_rows(data)

        properties: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            keyword = row.get("RegistryKeyword")
            if not keyword or self._target_for(str(keyword)) is None:
                continue
            properties[str(keyword)] = self._coerce_registry_value(row.get("RegistryValue"))
        return properties

    def _set_property(self, adapter: str, keyword: str, registry_value: str) -> bool:
        """Set one advanced property by registry keyword. Returns success."""
        script = (
            f"Set-NetAdapterAdvancedProperty -Name '{self._escape(adapter)}' "
            f"-RegistryKeyword '{self._escape(keyword)}' "
            f"-RegistryValue '{self._escape(registry_value)}' -NoRestart"
        )
        result = self._run_ps(script)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            logger.debug("Set %s on %s failed: %s", keyword, adapter, err)
        return result.returncode == 0

    def _run_json(self, script: str) -> Any:
        """Run a script and parse its stdout as JSON, defensively.

        Returns ``None`` on any failure (non-zero exit, empty output, or
        malformed JSON) so callers degrade gracefully rather than raising.
        """
        try:
            result = self._run_ps(script)
        except subprocess.TimeoutExpired:
            logger.warning("Timeout running PowerShell for NIC driver query")
            return None
        except Exception as exc:  # noqa: BLE001 - detection must never crash
            logger.debug("PowerShell NIC driver query failed: %s", exc)
            return None

        if result.returncode != 0:
            return None
        stdout = (result.stdout or "").strip()
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except (ValueError, TypeError) as exc:
            logger.debug("Could not parse NIC driver JSON: %s", exc)
            return None

    @staticmethod
    def _as_rows(data: Any) -> list[Any]:
        """Normalize ConvertTo-Json output (object for one item, list for many)."""
        if data is None:
            return []
        if isinstance(data, list):
            return data
        return [data]

    @staticmethod
    def _coerce_registry_value(value: Any) -> str:
        """Coerce a RegistryValue (string, number, or single-element list) to str."""
        if isinstance(value, list):
            value = value[0] if value else ""
        return str(value)

    @staticmethod
    def _target_for(keyword: str) -> tuple[str, str] | None:
        """Return the (label, optimal value) target a keyword maps to, or None."""
        lowered = keyword.lower()
        for suffix, target in _TARGETS.items():
            if lowered.endswith(suffix.lower()):
                return target
        return None

    @staticmethod
    def _escape(value: str) -> str:
        """Escape single quotes for embedding in a single-quoted PS string."""
        return value.replace("'", "''")
