"""Persistence + comparison for PresentMon frame-time benchmark artifacts.

The :mod:`abso.core.benchmark` module captures and analyzes frame-time data but
keeps nothing on disk. This module turns those analyses into durable,
JSON-serialized artifacts under ``reports/benchmarks/<profile>/`` so a profile
can accumulate the before/after evidence the quality rubric requires before it
may be graded ``measured`` / ``optimal``.

Artifact kinds:
* ``capture`` - one analyzed capture (baseline or post-apply), with metadata.
* ``comparison`` - a stored before/after delta linking two captures.

Everything here is pure/data-only and dependency-injectable (``reports_dir``,
timestamp, hardware) so it is fully hermetic-testable without PresentMon or a
running game.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from abso.utils.atomic_io import atomic_write_json

if TYPE_CHECKING:
    from abso.core.benchmark import ComparisonResult, FrameTimeAnalysis

SCHEMA_VERSION = 1


def analysis_to_dict(analysis: FrameTimeAnalysis) -> dict[str, Any]:
    """Serialize a :class:`FrameTimeAnalysis` (including histogram) to a dict."""
    data = asdict(analysis)
    # asdict already converts the nested HistogramBucket dataclasses to dicts;
    # inf upper bounds are JSON-unsafe, so encode them as a sentinel string.
    for bucket in data.get("histogram_buckets", []):
        if bucket.get("upper_ms") == float("inf"):
            bucket["upper_ms"] = "inf"
    return data


def analysis_from_dict(data: dict[str, Any]) -> FrameTimeAnalysis:
    """Reconstruct a :class:`FrameTimeAnalysis` from a serialized capture dict."""
    from abso.core.benchmark import FrameTimeAnalysis, HistogramBucket

    buckets: list[HistogramBucket] = []
    for raw in data.get("histogram_buckets", []) or []:
        upper = raw.get("upper_ms")
        upper_ms = float("inf") if upper in ("inf", "Infinity") else float(upper)
        buckets.append(
            HistogramBucket(
                lower_ms=float(raw.get("lower_ms", 0.0)),
                upper_ms=upper_ms,
                count=int(raw.get("count", 0)),
                percentage=float(raw.get("percentage", 0.0)),
            )
        )

    return FrameTimeAnalysis(
        avg_fps=float(data.get("avg_fps", 0.0)),
        avg_frame_time_ms=float(data.get("avg_frame_time_ms", 0.0)),
        p99_frame_time_ms=float(data.get("p99_frame_time_ms", 0.0)),
        p95_frame_time_ms=float(data.get("p95_frame_time_ms", 0.0)),
        p1_low_fps=float(data.get("p1_low_fps", 0.0)),
        p01_low_fps=float(data.get("p01_low_fps", 0.0)),
        frame_time_stdev=float(data.get("frame_time_stdev", 0.0)),
        dropped_frame_count=int(data.get("dropped_frame_count", 0)),
        total_frames=int(data.get("total_frames", 0)),
        histogram_buckets=buckets,
    )


def comparison_to_dict(comparison: ComparisonResult) -> dict[str, Any]:
    """Serialize a :class:`ComparisonResult` to a JSON-friendly dict."""
    return {
        "before": analysis_to_dict(comparison.before),
        "after": analysis_to_dict(comparison.after),
        "deltas": {name: asdict(delta) for name, delta in comparison.deltas.items()},
    }


def summarize_comparison(comparison: ComparisonResult) -> dict[str, Any]:
    """Produce a compact verdict from a comparison's deltas.

    Latency-focused profiles care most about frame-time consistency, so the
    headline metrics are the 1% low FPS and the 99th-percentile frame time.
    """
    deltas = comparison.deltas
    improved = sum(1 for d in deltas.values() if d.improved and d.absolute != 0.0)
    regressed = sum(1 for d in deltas.values() if not d.improved and d.absolute != 0.0)

    headline = []
    for key in ("p1_low_fps", "p99_frame_time_ms", "avg_fps", "frame_time_stdev"):
        delta = deltas.get(key)
        if delta is not None:
            headline.append(
                {
                    "metric": key,
                    "before": delta.before,
                    "after": delta.after,
                    "percentage": delta.percentage,
                    "improved": delta.improved,
                }
            )

    p1 = deltas.get("p1_low_fps")
    p99 = deltas.get("p99_frame_time_ms")
    consistency_improved = bool(
        (p1 and p1.improved and p1.absolute != 0.0)
        or (p99 and p99.improved and p99.absolute != 0.0)
    )

    if improved == 0 and regressed == 0:
        verdict = "no measurable change"
    elif improved and not regressed:
        verdict = "improved"
    elif regressed and not improved:
        verdict = "regressed"
    else:
        verdict = "mixed (consistency improved)" if consistency_improved else "mixed"

    return {
        "improved_metrics": improved,
        "regressed_metrics": regressed,
        "consistency_improved": consistency_improved,
        "verdict": verdict,
        "headline": headline,
    }


def _slugify(value: str) -> str:
    """Filesystem-safe slug for a profile/label fragment."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    return slug.strip("-_.") or "unknown"


def _to_iso(timestamp: datetime | str) -> str:
    return timestamp if isinstance(timestamp, str) else timestamp.isoformat()


def _stamp_token(timestamp: datetime | str) -> str:
    """Compact sortable token (UTC-ish) used in artifact filenames."""
    iso = _to_iso(timestamp)
    return re.sub(r"[^0-9]", "", iso)[:14] or "00000000000000"


class BenchmarkArtifactStore:
    """Reads/writes benchmark artifacts under ``<reports_dir>/benchmarks``."""

    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = Path(reports_dir)
        self.benchmarks_dir = self.reports_dir / "benchmarks"

    def _profile_dir(self, profile_id: str) -> Path:
        return self.benchmarks_dir / _slugify(profile_id)

    def save_capture(
        self,
        *,
        profile_id: str,
        label: str,
        process_name: str,
        duration_seconds: int,
        analysis: FrameTimeAnalysis,
        timestamp: datetime | str,
        presentmon_path: str | None = None,
        hardware: dict[str, Any] | None = None,
    ) -> Path:
        """Persist one analyzed capture and return the artifact path."""
        profile_dir = self._profile_dir(profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "capture",
            "profile_id": profile_id,
            "label": label,
            "process_name": process_name,
            "captured_at": _to_iso(timestamp),
            "duration_seconds": duration_seconds,
            "presentmon_path": presentmon_path,
            "hardware": hardware or {},
            "analysis": analysis_to_dict(analysis),
        }

        filename = f"{_stamp_token(timestamp)}_{_slugify(label)}.json"
        path = profile_dir / filename
        atomic_write_json(path, payload, indent=2)
        return path

    def save_comparison(
        self,
        *,
        profile_id: str,
        comparison: ComparisonResult,
        baseline_ref: str | None,
        after_ref: str | None,
        timestamp: datetime | str,
    ) -> Path:
        """Persist a before/after comparison and return the artifact path."""
        profile_dir = self._profile_dir(profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "comparison",
            "profile_id": profile_id,
            "created_at": _to_iso(timestamp),
            "baseline_ref": baseline_ref,
            "after_ref": after_ref,
            "summary": summarize_comparison(comparison),
            "comparison": comparison_to_dict(comparison),
        }

        filename = f"{_stamp_token(timestamp)}_comparison.json"
        path = profile_dir / filename
        atomic_write_json(path, payload, indent=2)
        return path

    def list_artifacts(self, profile_id: str) -> list[dict[str, Any]]:
        """Return all artifacts for a profile, newest first (by filename)."""
        profile_dir = self._profile_dir(profile_id)
        if not profile_dir.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for path in sorted(profile_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            data["_path"] = str(path)
            data["_filename"] = path.name
            out.append(data)
        return out

    def latest_capture(
        self, profile_id: str, label: str | None = None
    ) -> dict[str, Any] | None:
        """Return the newest capture artifact (optionally filtered by label)."""
        for artifact in self.list_artifacts(profile_id):
            if artifact.get("kind") != "capture":
                continue
            if label is not None and artifact.get("label") != label:
                continue
            return artifact
        return None
