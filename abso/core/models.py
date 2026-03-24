"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class EvidenceTier(Enum):
    """Evidence basis for an optimization setting.

    Used to communicate confidence level to users so they can make
    informed decisions about which optimizations to apply.
    """

    VERIFIED = "verified"
    """Published benchmarks, hardware documentation, or driver API specs.
    Examples: NVIDIA Reflex, VSync latency, refresh rate scanout math."""

    EMPIRICAL = "empirical"
    """Consistent community testing but no vendor documentation.
    Examples: HAGS per-backend toggle, threaded optimization for emulators."""

    LEGACY_UNVERIFIED = "legacy_unverified"
    """Common in optimization guides but no evidence of effect on modern
    Windows 11 with current hardware. May be placebo.
    Examples: SystemResponsiveness, NetworkThrottlingIndex, DisablePagingExecutive."""

    COSMETIC = "cosmetic"
    """User preference with no performance impact.
    Examples: Digital vibrance, ICC profile selection."""

    @property
    def label(self) -> str:
        labels = {
            EvidenceTier.VERIFIED: "Verified",
            EvidenceTier.EMPIRICAL: "Empirical",
            EvidenceTier.LEGACY_UNVERIFIED: "Legacy/Unverified",
            EvidenceTier.COSMETIC: "Cosmetic",
        }
        return labels[self]


@dataclass
class Issue:
    """Represents a configuration issue found during audit."""

    title: str
    severity: Literal["critical", "warning", "info"]
    current_value: str
    optimal_value: str
    explanation: str | None = None
    category: str = "general"
    evidence_tier: EvidenceTier = EvidenceTier.VERIFIED
