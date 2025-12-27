"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class Issue:
    """Represents a configuration issue found during audit."""

    title: str
    severity: Literal["critical", "warning", "info"]
    current_value: str
    optimal_value: str
    explanation: str | None = None
    category: str = "general"
