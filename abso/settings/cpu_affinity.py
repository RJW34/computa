"""CPU affinity and core isolation settings handler.

Detects CPU topology (P-cores vs E-cores on Intel hybrid, CCDs on AMD Zen),
audits whether game executables are pinned to requested cores, and applies
affinity masks via PowerShell and AppCompatFlags registry entries.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import winreg
from dataclasses import dataclass, field
from typing import Any

from abso.core.exceptions import RegistryWriteError
from abso.core.models import EvidenceTier, Issue
from abso.settings.base import SettingsHandler
from abso.utils.validation import validate_executable_name

logger = logging.getLogger(__name__)


@dataclass
class CpuTopology:
    """Describes the physical layout of the CPU.

    Attributes:
        total_physical: Number of physical cores.
        total_logical: Number of logical processors (includes HT/SMT).
        p_cores: Logical-processor IDs classified as performance cores.
        e_cores: Logical-processor IDs classified as efficiency cores.
        is_hybrid: True when both P-cores and E-cores are present.
        vendor: CPU vendor string (e.g. "GenuineIntel", "AuthenticAMD").
        architecture: Micro-architecture hint (e.g. "Alder Lake", "Zen 4").
    """

    total_physical: int = 0
    total_logical: int = 0
    p_cores: list[int] = field(default_factory=list)
    e_cores: list[int] = field(default_factory=list)
    is_hybrid: bool = False
    vendor: str = "Unknown"
    architecture: str = "Unknown"


# ---------------------------------------------------------------------------
# Registry paths
# ---------------------------------------------------------------------------
_CENTRAL_PROCESSOR_KEY = r"HARDWARE\DESCRIPTION\System\CentralProcessor"
_APPCOMPAT_LAYERS_KEY = (
    r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
)
_WIN_ERR_FILE_NOT_FOUND = 2
_APPCOMPAT_LAYER_MARKER = "~"
_AFFINITY_TOKEN_PREFIX = "PROCESSORAFFINITYMASK="


class CpuAffinityHandler(SettingsHandler):
    """Manages CPU affinity masks and core isolation for game executables.

    Strategies:
      * ``p_cores_only`` -- restrict the process to performance cores
        (experimental on Intel hybrid CPUs; can reduce scheduler movement
        but may also block Thread Director from making better decisions).
      * ``all_cores`` -- use every available logical processor.
      * ``custom`` -- caller supplies an explicit ``affinity_mask``.

    Persistence is achieved via the ``AppCompatFlags\\Layers`` registry
    value ``PROCESSORAFFINITYMASK`` which Windows applies at process
    creation.  For already-running processes the handler also sets the
    mask live through PowerShell ``ProcessorAffinity``.
    """

    # backup() can reach WMI on the live-affinity path; keep it on the main
    # thread during the concurrent backup scan (see SettingsHandler).
    backup_requires_main_thread = True

    def __init__(self, executables: list[str] | None = None) -> None:
        """Initialize handler with list of executables to manage.

        Args:
            executables: List of executable names (e.g., ``["game.exe"]``).
        """
        self.executables = executables or []
        self._topology_cache: CpuTopology | None = None

    # ------------------------------------------------------------------
    # SettingsHandler interface
    # ------------------------------------------------------------------

    def detect(self) -> dict[str, Any]:
        """Detect current CPU affinity state.

        Returns a dictionary with:
          * ``topology`` -- serialized :class:`CpuTopology`.
          * ``executables`` -- per-exe affinity info (mask, strategy).
        """
        topology = self._get_topology()

        exe_info: dict[str, Any] = {}
        for exe in self.executables:
            exe_info[exe] = self._get_exe_affinity(exe)

        return {
            "topology": {
                "total_physical": topology.total_physical,
                "total_logical": topology.total_logical,
                "p_cores": topology.p_cores,
                "e_cores": topology.e_cores,
                "is_hybrid": topology.is_hybrid,
                "vendor": topology.vendor,
                "architecture": topology.architecture,
            },
            "executables": exe_info,
        }

    def audit(self) -> list[Issue]:
        """Audit CPU affinity configuration for gaming issues."""
        issues: list[Issue] = []
        topology = self._get_topology()

        for exe in self.executables:
            affinity = self._get_exe_affinity(exe)
            current_mask = affinity.get("affinity_mask")

            # -- Hybrid CPU with no affinity set --------------------------
            if topology.is_hybrid and current_mask is None:
                p_mask = self._cores_to_mask(topology.p_cores)
                issues.append(Issue(
                    title=f"No CPU affinity set for {exe} on hybrid CPU",
                    severity="warning",
                    current_value="Not set (all cores)",
                    optimal_value=f"Profile-dependent; P-cores only mask 0x{p_mask:X}",
                    explanation=(
                        "On Intel hybrid CPUs the Windows scheduler may "
                        "migrate game threads to efficiency cores, causing "
                        "frame-time spikes. Pinning to P-cores is an "
                        "experimental profile tradeoff, not a universal win."
                    ),
                    category="cpu_affinity",
                    evidence_tier=EvidenceTier.EXPERIMENTAL,
                ))

            # -- Game currently running on E-cores ------------------------
            if (
                topology.is_hybrid
                and current_mask is not None
                and topology.e_cores
            ):
                e_mask = self._cores_to_mask(topology.e_cores)
                # If the current mask overlaps with E-cores but has no
                # overlap with P-cores the game is *only* on E-cores.
                p_mask = self._cores_to_mask(topology.p_cores)
                if (current_mask & p_mask) == 0 and (current_mask & e_mask) != 0:
                    issues.append(Issue(
                        title=f"{exe} is pinned exclusively to E-cores",
                        severity="critical",
                        current_value=f"Mask 0x{current_mask:X} (E-cores only)",
                        optimal_value=f"P-cores only (mask 0x{p_mask:X})",
                        explanation=(
                            "The game executable is restricted to efficiency "
                            "cores which have significantly lower single-thread "
                            "performance.  This will cause major frame-rate and "
                            "latency degradation."
                        ),
                        category="cpu_affinity",
                        evidence_tier=EvidenceTier.VERIFIED,
                    ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply CPU affinity settings.

        Args:
            settings: Dictionary with keys:
                * ``strategy`` -- ``"p_cores_only"`` | ``"all_cores"`` |
                  ``"custom"``.
                * ``affinity_mask`` -- required when strategy is ``"custom"``.
                * ``executables`` -- optional override list of exe names.

        Returns:
            Result dict ``{success, error, requires_reboot}``.
        """
        errors: list[str] = []
        strategy = settings.get("strategy")

        # None = don't manage affinity (default). Skip entirely.
        if strategy is None:
            return {"success": True, "error": None, "requires_reboot": False}

        topology = self._get_topology()
        target_exes: list[str] = settings.get("executables", self.executables)

        # Resolve the mask from the chosen strategy.
        mask = self._resolve_mask(strategy, topology, settings)
        if mask is None:
            return {
                "success": False,
                "error": (
                    f"Cannot compute affinity mask for strategy '{strategy}': "
                    "no P-cores detected or no mask provided"
                ),
                "requires_reboot": False,
            }

        for exe in target_exes:
            try:
                validate_executable_name(exe)
            except Exception as exc:
                errors.append(f"{exe}: invalid name -- {exc}")
                continue

            # 1. Persist via AppCompatFlags registry.
            try:
                self._set_appcompat_affinity(exe, mask)
            except RegistryWriteError as exc:
                errors.append(f"{exe}: registry -- {exc}")

            # 2. Apply live to any running instances.
            try:
                self._set_running_process_affinity(exe, mask)
            except Exception as exc:
                # Non-fatal: the process might not be running right now.
                logger.debug("Live affinity set skipped for %s: %s", exe, exc)

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Export current affinity settings for all managed executables."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore affinity settings from a previous backup.

        Args:
            data: Backup payload previously returned by :meth:`backup`.

        Returns:
            ``True`` if every executable's restore completed without failure.
        """
        try:
            exe_data: dict[str, Any] = data.get("executables", {})
            for exe, info in exe_data.items():
                mask = info.get("affinity_mask")
                if mask is not None:
                    self._set_appcompat_affinity(exe, mask)
                    self._set_running_process_affinity(exe, mask)
                else:
                    # No affinity was set before -- remove any we added.
                    self._remove_appcompat_affinity(exe)
            return True
        except Exception as exc:
            logger.error("Failed to restore CPU affinity settings: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Topology detection
    # ------------------------------------------------------------------

    def _get_topology(self) -> CpuTopology:
        """Return cached CPU topology, detecting on first call."""
        if self._topology_cache is None:
            self._topology_cache = self._detect_core_topology()
        return self._topology_cache

    def _detect_core_topology(self) -> CpuTopology:
        """Build a :class:`CpuTopology` from the Windows registry.

        Reads ``HKLM\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\{n}``
        for every logical processor.  The ``~MHz`` value recorded by Windows
        is used to distinguish performance cores from efficiency cores on
        Intel hybrid architectures.  Non-hybrid CPUs (all cores at the
        same frequency) treat every core as a P-core.
        """
        topology = CpuTopology()
        core_freqs: dict[int, int] = {}  # logical-processor-id -> MHz

        try:
            parent_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                _CENTRAL_PROCESSOR_KEY,
                0,
                winreg.KEY_READ,
            )
        except OSError as exc:
            logger.warning("Cannot open CentralProcessor registry key: %s", exc)
            return topology

        try:
            idx = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(parent_key, idx)
                except OSError:
                    break
                idx += 1

                try:
                    core_id = int(subkey_name)
                except ValueError:
                    continue

                try:
                    core_key = winreg.OpenKey(
                        parent_key, subkey_name, 0, winreg.KEY_READ
                    )
                except OSError:
                    continue

                try:
                    # Read vendor on first core.
                    if core_id == 0:
                        with contextlib.suppress(OSError):
                            topology.vendor = str(
                                winreg.QueryValueEx(core_key, "VendorIdentifier")[0]
                            )
                        with contextlib.suppress(OSError):
                            topology.architecture = str(
                                winreg.QueryValueEx(core_key, "Identifier")[0]
                            )

                    # Read clock speed.
                    try:
                        mhz = int(
                            winreg.QueryValueEx(core_key, "~MHz")[0]
                        )
                        core_freqs[core_id] = mhz
                    except (OSError, ValueError):
                        pass
                finally:
                    winreg.CloseKey(core_key)
        finally:
            winreg.CloseKey(parent_key)

        if not core_freqs:
            return topology

        topology.total_logical = len(core_freqs)

        # Heuristic: physical core count is half the logical count when
        # Hyper-Threading / SMT is enabled.  WMI would give us a definitive
        # answer but is expensive; the registry-based approach is faster.
        topology.total_physical = self._estimate_physical_cores(topology)

        # -- Classify P-cores vs E-cores ----------------------------------
        # On hybrid CPUs the P-cores report a noticeably higher ~MHz than
        # E-cores.  We cluster by frequency: the group with the highest
        # frequency is labelled P, the rest E.
        unique_freqs = sorted(set(core_freqs.values()), reverse=True)

        if len(unique_freqs) >= 2:
            # Multiple distinct frequencies detected -- likely hybrid.
            max_freq = unique_freqs[0]
            # Allow a small tolerance (50 MHz) for turbo-boost jitter when
            # deciding whether a core belongs to the "fast" group.
            freq_threshold = max_freq - 50

            for core_id, mhz in sorted(core_freqs.items()):
                if mhz >= freq_threshold:
                    topology.p_cores.append(core_id)
                else:
                    topology.e_cores.append(core_id)

            topology.is_hybrid = len(topology.e_cores) > 0
        else:
            # All cores at the same frequency -- not hybrid.
            topology.p_cores = sorted(core_freqs.keys())
            topology.is_hybrid = False

        # Refine architecture hint based on vendor.
        topology.architecture = self._refine_architecture(topology)

        return topology

    def _estimate_physical_cores(self, topology: CpuTopology) -> int:
        """Estimate physical core count from WMI or processor count / 2.

        Falls back to ``total_logical // 2`` when WMI is unavailable.
        """
        try:
            import wmi  # type: ignore[import-untyped]

            wmi_conn = wmi.WMI()
            for cpu in wmi_conn.Win32_Processor():
                return int(cpu.NumberOfCores)
        except Exception:
            logger.debug(
                "WMI unavailable for physical core count; using heuristic"
            )

        # Fallback: assume SMT is enabled (2 threads per core).
        return max(1, topology.total_logical // 2)

    @staticmethod
    def _refine_architecture(topology: CpuTopology) -> str:
        """Return a human-friendly architecture string."""
        vendor = topology.vendor.lower()

        if "intel" in vendor:
            if topology.is_hybrid:
                # 12th-gen+ Alder Lake / Raptor Lake / Arrow Lake ...
                return "Intel Hybrid (Alder Lake+)"
            return "Intel"

        if "amd" in vendor:
            # Rough heuristic for Zen generation based on core counts.
            physical = topology.total_physical
            if physical >= 16:
                return "AMD Zen (16+ core, multi-CCD)"
            if physical >= 8:
                return "AMD Zen (8-core CCD)"
            return "AMD Zen"

        return topology.architecture  # keep whatever the registry had

    # ------------------------------------------------------------------
    # Per-executable affinity queries
    # ------------------------------------------------------------------

    def _get_exe_affinity(self, exe_name: str) -> dict[str, Any]:
        """Read the persisted affinity mask for *exe_name*.

        Checks ``HKCU\\...\\AppCompatFlags\\Layers`` for a
        ``PROCESSORAFFINITYMASK`` entry.

        Returns:
            ``{"affinity_mask": int | None, "source": str}``.
        """
        result: dict[str, Any] = {
            "affinity_mask": None,
            "source": "none",
        }

        try:
            validate_executable_name(exe_name)
        except Exception:
            return result

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                _APPCOMPAT_LAYERS_KEY,
                0,
                winreg.KEY_READ,
            )
        except OSError:
            return result

        try:
            # The value name is the full path to the executable.  We also
            # check for the bare exe name because some entries use paths.
            idx = 0
            while True:
                try:
                    value_name, value_data, _ = winreg.EnumValue(key, idx)
                except OSError:
                    break
                idx += 1

                if not isinstance(value_data, str):
                    continue

                # Match on the executable name at the end of the path.
                if not value_name.lower().endswith(exe_name.lower()):
                    continue

                mask = self._parse_affinity_from_layers(value_data)
                if mask is not None:
                    result["affinity_mask"] = mask
                    result["source"] = "AppCompatFlags"
                    break
        finally:
            winreg.CloseKey(key)

        return result

    @staticmethod
    def _parse_affinity_from_layers(layers_value: str) -> int | None:
        """Extract the affinity mask from an AppCompatFlags Layers string.

        The Layers value is a space-separated list of compatibility flags.
        The affinity entry looks like ``PROCESSORAFFINITYMASK=<hex>``.
        """
        for token in layers_value.split():
            upper = token.upper()
            if upper.startswith(_AFFINITY_TOKEN_PREFIX):
                hex_str = upper.split("=", 1)[1]
                try:
                    return int(hex_str, 16)
                except ValueError:
                    return None
        return None

    @staticmethod
    def _is_registry_value_missing(exc: OSError) -> bool:
        """Return True only for the registry value/key-not-found case."""
        return isinstance(exc, FileNotFoundError) or (
            getattr(exc, "winerror", None) == _WIN_ERR_FILE_NOT_FOUND
        )

    @staticmethod
    def _appcompat_tokens_without_affinity(layers_value: str) -> list[str]:
        """Return compatibility tokens, excluding marker and affinity token."""
        return [
            token
            for token in layers_value.split()
            if token
            and token != _APPCOMPAT_LAYER_MARKER
            and not token.upper().startswith(_AFFINITY_TOKEN_PREFIX)
        ]

    @staticmethod
    def _format_appcompat_layers(tokens: list[str]) -> str:
        """Format non-empty AppCompat layer tokens with the marker prefix."""
        return f"{_APPCOMPAT_LAYER_MARKER} {' '.join(tokens)}"

    # ------------------------------------------------------------------
    # Affinity application helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cores_to_mask(core_ids: list[int]) -> int:
        """Convert a list of logical-processor IDs to a bitmask."""
        mask = 0
        for cid in core_ids:
            mask |= 1 << cid
        return mask

    def _resolve_mask(
        self,
        strategy: str,
        topology: CpuTopology,
        settings: dict[str, Any],
    ) -> int | None:
        """Compute the affinity mask for the requested strategy.

        Returns:
            The bitmask, or ``None`` when computation is impossible.
        """
        if strategy == "p_cores_only":
            if not topology.p_cores:
                return None
            return self._cores_to_mask(topology.p_cores)

        if strategy == "all_cores":
            # Set a bit for every logical processor.
            if topology.total_logical > 0:
                return (1 << topology.total_logical) - 1
            return 0xFFFFFFFF

        if strategy == "custom":
            mask = settings.get("affinity_mask")
            if isinstance(mask, int):
                return mask
            return None

        logger.warning("Unknown affinity strategy '%s'", strategy)
        return None

    def _set_appcompat_affinity(self, exe_name: str, mask: int) -> None:
        """Persist an affinity mask in AppCompatFlags\\Layers.

        If the executable already has other compatibility flags they are
        preserved; only the ``PROCESSORAFFINITYMASK`` portion is updated.

        Args:
            exe_name: Bare executable name (e.g., ``"game.exe"``).
            mask: Processor affinity bitmask.

        Raises:
            RegistryWriteError: If the write fails.
        """
        try:
            key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, _APPCOMPAT_LAYERS_KEY
            )
        except OSError as exc:
            raise RegistryWriteError(
                "Cannot open AppCompatFlags\\Layers for writing",
                details=str(exc),
            ) from exc

        try:
            # Read any existing flags for this executable. Treating every
            # QueryValueEx failure as "no value" is unsafe: a transient access
            # error would drop HIGHDPIAWARE / FSO / RUNASINVOKER tokens.
            try:
                existing_flags = str(winreg.QueryValueEx(key, exe_name)[0])
            except OSError as exc:
                if self._is_registry_value_missing(exc):
                    existing_flags = ""
                else:
                    raise RegistryWriteError(
                        f"Failed to read AppCompatFlags\\Layers[{exe_name}]",
                        details=str(exc),
                    ) from exc

            # Strip old affinity flag if present, then append the new one.
            tokens = self._appcompat_tokens_without_affinity(existing_flags)
            tokens.append(f"{_AFFINITY_TOKEN_PREFIX}{mask:X}")
            new_value = self._format_appcompat_layers(tokens)

            winreg.SetValueEx(
                key, exe_name, 0, winreg.REG_SZ, new_value
            )
            logger.info(
                "Set AppCompatFlags affinity for %s to 0x%X", exe_name, mask
            )
        except OSError as exc:
            raise RegistryWriteError(
                f"Failed to write affinity for {exe_name}",
                details=str(exc),
            ) from exc
        finally:
            winreg.CloseKey(key)

    def _remove_appcompat_affinity(self, exe_name: str) -> None:
        """Remove the affinity flag from AppCompatFlags\\Layers.

        If other compatibility flags remain the value is preserved without
        the affinity portion.  If it was the only flag the value is deleted.
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                _APPCOMPAT_LAYERS_KEY,
                0,
                winreg.KEY_ALL_ACCESS,
            )
        except OSError as exc:
            if self._is_registry_value_missing(exc):
                return  # Key does not exist -- nothing to remove.
            raise RegistryWriteError(
                "Cannot open AppCompatFlags\\Layers for affinity restore",
                details=str(exc),
            ) from exc

        try:
            try:
                existing_flags = str(winreg.QueryValueEx(key, exe_name)[0])
            except OSError as exc:
                if self._is_registry_value_missing(exc):
                    return  # No value for this exe.
                raise RegistryWriteError(
                    f"Failed to read AppCompatFlags\\Layers[{exe_name}]",
                    details=str(exc),
                ) from exc

            remaining = self._appcompat_tokens_without_affinity(existing_flags)

            if remaining:
                winreg.SetValueEx(
                    key,
                    exe_name,
                    0,
                    winreg.REG_SZ,
                    self._format_appcompat_layers(remaining),
                )
            else:
                try:
                    winreg.DeleteValue(key, exe_name)
                except OSError as exc:
                    if not self._is_registry_value_missing(exc):
                        raise RegistryWriteError(
                            f"Failed to delete affinity for {exe_name}",
                            details=str(exc),
                        ) from exc

            logger.info("Removed AppCompatFlags affinity for %s", exe_name)
        finally:
            winreg.CloseKey(key)

    def _set_running_process_affinity(self, exe_name: str, mask: int) -> None:
        """Set affinity on currently running instances of *exe_name*.

        Uses PowerShell to locate and update the ``ProcessorAffinity``
        property.  Failures are logged but not raised -- the process
        may not be running and that is fine.
        """
        process_name = exe_name.replace(".exe", "").replace(".EXE", "")
        # Escape single quotes to prevent PowerShell injection.
        process_name = process_name.replace("'", "''")

        ps_script = (
            f"$procs = Get-Process -Name '{process_name}' "
            f"-ErrorAction SilentlyContinue; "
            f"foreach ($p in $procs) {{ "
            f"try {{ $p.ProcessorAffinity = [IntPtr]{mask} }} "
            f"catch {{}} }}"
        )

        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                timeout=5,
            )
            logger.debug(
                "Set live affinity for running %s to 0x%X", exe_name, mask
            )
        except subprocess.TimeoutExpired:
            logger.warning("Timeout setting live affinity for %s", exe_name)
        except Exception as exc:
            logger.debug(
                "Could not set live affinity for %s: %s", exe_name, exc
            )
