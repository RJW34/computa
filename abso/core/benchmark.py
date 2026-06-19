"""PresentMon frame-time measurement and analysis module.

Provides automated frame-time capture via Intel PresentMon CLI,
statistical analysis of frame pacing, and before/after comparison
for validating optimization profile effectiveness.
"""

from __future__ import annotations

import csv
import logging
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from abso.core.exceptions import ABSOError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PresentMonNotFoundError(ABSOError):
    """PresentMon executable could not be located."""
    pass


class CaptureError(ABSOError):
    """Frame-time capture failed."""
    pass


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CaptureResult:
    """Raw frame-time data returned from a PresentMon capture session.

    Attributes:
        raw_data: List of row dicts parsed from the PresentMon CSV.
        process_name: Executable name that was captured.
        duration_seconds: Requested capture duration.
        csv_path: Path to the CSV file (may be a temp file).
        timestamp: UTC timestamp when the capture started.
    """

    raw_data: list[dict[str, str]]
    process_name: str
    duration_seconds: int
    csv_path: Path
    timestamp: datetime


@dataclass
class HistogramBucket:
    """A single bucket in a frame-time histogram.

    Attributes:
        lower_ms: Lower bound of the bucket (inclusive).
        upper_ms: Upper bound of the bucket (exclusive).
        count: Number of frames in this bucket.
        percentage: Percentage of total frames in this bucket.
    """

    lower_ms: float
    upper_ms: float
    count: int
    percentage: float


@dataclass
class FrameTimeAnalysis:
    """Statistical analysis of captured frame times.

    Attributes:
        avg_fps: Average frames per second.
        avg_frame_time_ms: Mean frame time in milliseconds.
        p99_frame_time_ms: 99th percentile frame time.
        p95_frame_time_ms: 95th percentile frame time.
        p1_low_fps: 1% low FPS (FPS at 99th percentile frame time).
        p01_low_fps: 0.1% low FPS (FPS at 99.9th percentile frame time).
        frame_time_stdev: Standard deviation of frame times.
        dropped_frame_count: Number of dropped frames reported by PresentMon.
        total_frames: Total number of frames captured.
        histogram_buckets: Frame-time distribution for visualization.
    """

    avg_fps: float
    avg_frame_time_ms: float
    p99_frame_time_ms: float
    p95_frame_time_ms: float
    p1_low_fps: float
    p01_low_fps: float
    frame_time_stdev: float
    dropped_frame_count: int
    total_frames: int
    histogram_buckets: list[HistogramBucket] = field(default_factory=list)


@dataclass
class MetricDelta:
    """Change in a single metric between two analyses.

    Attributes:
        name: Human-readable metric name.
        before: Value before optimization.
        after: Value after optimization.
        absolute: Absolute change (after - before).
        percentage: Percentage change relative to *before*.
        improved: Whether the change is an improvement.
    """

    name: str
    before: float
    after: float
    absolute: float
    percentage: float
    improved: bool


@dataclass
class ComparisonResult:
    """Before/after comparison of two frame-time analyses.

    Attributes:
        before: Analysis from the baseline capture.
        after: Analysis from the post-optimization capture.
        deltas: Mapping of metric name to its delta.
    """

    before: FrameTimeAnalysis
    after: FrameTimeAnalysis
    deltas: dict[str, MetricDelta]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRESENTMON_SEARCH_PATHS: list[Path] = [
    Path(r"C:\Program Files\PresentMon\PresentMon.exe"),
    Path(r"C:\PresentMon\PresentMon-2.3.0-x64.exe"),
]

_PRESENTMON_CLI_NAMES: list[str] = [
    "PresentMon.exe",
    "presentmon-cli.exe",
]

# Default histogram bucket edges (milliseconds).
_DEFAULT_BUCKET_EDGES: list[float] = [
    0.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 20.0, 25.0, 33.4, 50.0, 100.0,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(data: list[float], pct: float) -> float:
    """Return the *pct*-th percentile of *data* using nearest-rank.

    Args:
        data: Sorted list of numeric values.
        pct: Percentile in the range [0, 100].

    Returns:
        The value at the requested percentile.
    """
    if not data:
        return 0.0
    # statistics.quantiles needs at least 2 data points.
    if len(data) == 1:
        return data[0]
    # Use n=100 cuts so the returned boundaries match standard percentiles.
    quantiles = statistics.quantiles(data, n=1000)
    # Index for the requested percentile (0-based).
    idx = max(0, min(int(pct * 10) - 1, len(quantiles) - 1))
    return quantiles[idx]


def _safe_float(value: str, default: float = 0.0) -> float:
    """Parse a string to float, returning *default* on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _row_get_ci(row: dict[str, str], *names: str) -> str:
    """Return the first present column value, tolerant of header casing.

    PresentMon 1.x emitted ``msBetweenPresents``; PresentMon 2.x emits
    ``MsBetweenPresents``. Match case-insensitively so the analyzer works
    across both CLI generations.
    """
    for name in names:
        if name in row:
            return row[name]
    lowered = {k.lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return ""


def _safe_int(value: str, default: int = 0) -> int:
    """Parse a string to int, returning *default* on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _build_histogram(
    frame_times: list[float],
    edges: list[float] | None = None,
) -> list[HistogramBucket]:
    """Build a histogram of *frame_times* using the given bucket *edges*.

    Args:
        frame_times: Frame-time values in milliseconds.
        edges: Sorted list of bucket boundaries.  The last edge is treated
            as an open upper bound (values >= last edge go into a final
            overflow bucket).

    Returns:
        Ordered list of histogram buckets.
    """
    if not frame_times:
        return []

    edges = edges or _DEFAULT_BUCKET_EDGES
    total = len(frame_times)
    counts: list[int] = [0] * (len(edges))  # one extra for overflow

    for ft in frame_times:
        placed = False
        for i in range(len(edges) - 1):
            if edges[i] <= ft < edges[i + 1]:
                counts[i] += 1
                placed = True
                break
        if not placed:
            # Overflow: >= last edge.
            counts[-1] += 1

    buckets: list[HistogramBucket] = []
    for i in range(len(edges) - 1):
        buckets.append(HistogramBucket(
            lower_ms=edges[i],
            upper_ms=edges[i + 1],
            count=counts[i],
            percentage=(counts[i] / total) * 100.0 if total else 0.0,
        ))
    # Overflow bucket.
    buckets.append(HistogramBucket(
        lower_ms=edges[-1],
        upper_ms=float("inf"),
        count=counts[-1],
        percentage=(counts[-1] / total) * 100.0 if total else 0.0,
    ))
    return buckets


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------


class FrameTimeBenchmark:
    """Manages PresentMon frame-time capture, analysis, and comparison.

    Usage::

        bench = FrameTimeBenchmark()
        before = bench.capture("game.exe", duration_seconds=30)
        # ... apply optimization profile ...
        after = bench.capture("game.exe", duration_seconds=30)
        comparison = bench.compare(
            bench.analyze(before),
            bench.analyze(after),
        )
    """

    _presentmon_path: Path | None

    def __init__(self) -> None:
        self._presentmon_path = None

    # ------------------------------------------------------------------
    # PresentMon location
    # ------------------------------------------------------------------

    def set_presentmon_path(self, path: str | Path) -> None:
        """Manually override the PresentMon executable path.

        Args:
            path: Absolute path to a PresentMon executable.

        Raises:
            FileNotFoundError: If *path* does not exist.
        """
        resolved = Path(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"PresentMon executable not found: {resolved}")
        self._presentmon_path = resolved
        logger.info("PresentMon path set to %s", self._presentmon_path)

    def _find_presentmon(self) -> Path:
        """Locate the PresentMon executable.

        Search order:
        1. Manually configured path (via :meth:`set_presentmon_path`).
        2. Well-known installation directories.
        3. ``PATH`` environment variable (``PresentMon.exe`` then
           ``presentmon-cli.exe``).

        Returns:
            Path to the located executable.

        Raises:
            PresentMonNotFoundError: If no PresentMon binary can be found.
        """
        # 1. Manual override.
        if self._presentmon_path is not None:
            if self._presentmon_path.is_file():
                return self._presentmon_path
            logger.warning(
                "Configured PresentMon path no longer valid: %s",
                self._presentmon_path,
            )

        # 2. Well-known paths.
        for candidate in _PRESENTMON_SEARCH_PATHS:
            if candidate.is_file():
                logger.debug("Found PresentMon at %s", candidate)
                return candidate

        # 3. Search PATH.
        for name in _PRESENTMON_CLI_NAMES:
            found = shutil.which(name)
            if found is not None:
                logger.debug("Found PresentMon on PATH: %s", found)
                return Path(found)

        raise PresentMonNotFoundError(
            "PresentMon is not installed",
            details=(
                "Install PresentMon from https://github.com/GameTechDev/PresentMon "
                "or set the path manually via set_presentmon_path()."
            ),
        )

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture(
        self,
        process_name: str,
        duration_seconds: int = 30,
    ) -> CaptureResult:
        """Capture frame-time data for a running process.

        Launches PresentMon in timed mode, waits for it to complete, then
        parses the resulting CSV.

        Args:
            process_name: Name of the target process (e.g. ``"game.exe"``).
            duration_seconds: How many seconds to record.

        Returns:
            A :class:`CaptureResult` containing the parsed frame-time rows.

        Raises:
            PresentMonNotFoundError: PresentMon could not be located.
            CaptureError: The capture subprocess failed or produced no data.
        """
        presentmon = self._find_presentmon()

        # Create a temp file for CSV output.  PresentMon writes to this path.
        tmp_dir = Path(tempfile.mkdtemp(prefix="abso_bench_"))
        csv_path = tmp_dir / f"{process_name}_{int(datetime.now(tz=UTC).timestamp())}.csv"

        cmd: list[str] = [
            str(presentmon),
            "--process_name", process_name,
            "--terminate_after_timed",
            "--timed_duration", str(duration_seconds),
            "--output_file", str(csv_path),
        ]

        logger.info(
            "Starting PresentMon capture: process=%s duration=%ds",
            process_name,
            duration_seconds,
        )
        logger.debug("PresentMon command: %s", " ".join(cmd))

        capture_start = datetime.now(tz=UTC)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=duration_seconds + 30,  # generous grace period
            )
        except FileNotFoundError as exc:
            raise PresentMonNotFoundError(
                "PresentMon executable could not be launched",
                details=str(exc),
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise CaptureError(
                "PresentMon capture timed out",
                details=f"Process '{process_name}' did not complete within "
                        f"{duration_seconds + 30}s.",
            ) from exc
        except OSError as exc:
            raise CaptureError(
                "Failed to launch PresentMon",
                details=str(exc),
            ) from exc

        if result.returncode != 0:
            stderr_snippet = (result.stderr or "").strip()[:500]
            raise CaptureError(
                f"PresentMon exited with code {result.returncode}",
                details=stderr_snippet or "(no stderr output)",
            )

        # Parse the CSV.
        raw_data = self._parse_csv(csv_path, process_name)

        logger.info(
            "Capture complete: %d frames from %s (%ds)",
            len(raw_data),
            process_name,
            duration_seconds,
        )

        return CaptureResult(
            raw_data=raw_data,
            process_name=process_name,
            duration_seconds=duration_seconds,
            csv_path=csv_path,
            timestamp=capture_start,
        )

    def _parse_csv(self, csv_path: Path, process_name: str) -> list[dict[str, str]]:
        """Parse a PresentMon CSV into a list of row dicts.

        Args:
            csv_path: Path to the CSV file written by PresentMon.
            process_name: Expected process name (for error messages).

        Returns:
            List of dictionaries keyed by CSV column header.

        Raises:
            CaptureError: If the CSV cannot be read or contains no data rows.
        """
        if not csv_path.is_file():
            raise CaptureError(
                "PresentMon produced no output file",
                details=f"Expected CSV at {csv_path}.  The target process "
                        f"'{process_name}' may not be running.",
            )

        rows: list[dict[str, str]] = []
        try:
            with csv_path.open(newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    rows.append(row)
        except (OSError, csv.Error) as exc:
            raise CaptureError(
                "Failed to parse PresentMon CSV",
                details=str(exc),
            ) from exc

        if not rows:
            raise CaptureError(
                "PresentMon CSV contains no frame data",
                details=f"The file at {csv_path} has headers but zero data "
                        f"rows.  Was '{process_name}' actively rendering?",
            )

        return rows

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze(self, capture: CaptureResult) -> FrameTimeAnalysis:
        """Compute statistical metrics from captured frame times.

        Args:
            capture: A :class:`CaptureResult` from :meth:`capture`.

        Returns:
            A :class:`FrameTimeAnalysis` with all computed metrics.
        """
        frame_times: list[float] = []
        dropped_count = 0

        for row in capture.raw_data:
            # PresentMon 2.x: MsBetweenPresents; 1.x: msBetweenPresents.
            ft = _safe_float(_row_get_ci(row, "MsBetweenPresents", "msBetweenPresents"))
            if ft > 0.0:
                frame_times.append(ft)

            if _safe_int(_row_get_ci(row, "Dropped") or "0") == 1:
                dropped_count += 1

        total_frames = len(frame_times)

        if total_frames == 0:
            logger.warning("No valid frame-time samples in capture data.")
            return FrameTimeAnalysis(
                avg_fps=0.0,
                avg_frame_time_ms=0.0,
                p99_frame_time_ms=0.0,
                p95_frame_time_ms=0.0,
                p1_low_fps=0.0,
                p01_low_fps=0.0,
                frame_time_stdev=0.0,
                dropped_frame_count=dropped_count,
                total_frames=0,
                histogram_buckets=[],
            )

        sorted_ft = sorted(frame_times)

        avg_ft = statistics.mean(frame_times)
        stdev_ft = statistics.stdev(frame_times) if total_frames >= 2 else 0.0

        p95_ft = _percentile(sorted_ft, 95.0)
        p99_ft = _percentile(sorted_ft, 99.0)
        p999_ft = _percentile(sorted_ft, 99.9)

        avg_fps = 1000.0 / avg_ft if avg_ft > 0.0 else 0.0
        # 1% low: FPS derived from the 99th percentile frame time.
        p1_low_fps = 1000.0 / p99_ft if p99_ft > 0.0 else 0.0
        # 0.1% low: FPS derived from the 99.9th percentile frame time.
        p01_low_fps = 1000.0 / p999_ft if p999_ft > 0.0 else 0.0

        histogram = _build_histogram(frame_times)

        return FrameTimeAnalysis(
            avg_fps=round(avg_fps, 2),
            avg_frame_time_ms=round(avg_ft, 3),
            p99_frame_time_ms=round(p99_ft, 3),
            p95_frame_time_ms=round(p95_ft, 3),
            p1_low_fps=round(p1_low_fps, 2),
            p01_low_fps=round(p01_low_fps, 2),
            frame_time_stdev=round(stdev_ft, 3),
            dropped_frame_count=dropped_count,
            total_frames=total_frames,
            histogram_buckets=histogram,
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def compare(
        self,
        before: FrameTimeAnalysis,
        after: FrameTimeAnalysis,
    ) -> ComparisonResult:
        """Compare two frame-time analyses and compute deltas.

        For FPS-based metrics, an increase is an improvement.  For frame-time
        and stdev metrics, a decrease is an improvement.

        Args:
            before: Baseline analysis (before optimization).
            after: Post-optimization analysis.

        Returns:
            A :class:`ComparisonResult` containing per-metric deltas.
        """
        # (metric_name, before_value, after_value, higher_is_better)
        metric_specs: list[tuple[str, float, float, bool]] = [
            ("avg_fps",              before.avg_fps,              after.avg_fps,              True),
            ("avg_frame_time_ms",    before.avg_frame_time_ms,    after.avg_frame_time_ms,    False),
            ("p99_frame_time_ms",    before.p99_frame_time_ms,    after.p99_frame_time_ms,    False),
            ("p95_frame_time_ms",    before.p95_frame_time_ms,    after.p95_frame_time_ms,    False),
            ("p1_low_fps",           before.p1_low_fps,           after.p1_low_fps,           True),
            ("p01_low_fps",          before.p01_low_fps,          after.p01_low_fps,          True),
            ("frame_time_stdev",     before.frame_time_stdev,     after.frame_time_stdev,     False),
            ("dropped_frame_count",  float(before.dropped_frame_count), float(after.dropped_frame_count), False),
            ("total_frames",         float(before.total_frames),  float(after.total_frames),  True),
        ]

        deltas: dict[str, MetricDelta] = {}
        for name, bval, aval, higher_is_better in metric_specs:
            absolute = aval - bval
            if bval != 0.0:
                percentage = (absolute / abs(bval)) * 100.0
            else:
                percentage = 0.0 if absolute == 0.0 else float("inf")

            if higher_is_better:
                improved = absolute > 0.0
            else:
                improved = absolute < 0.0

            deltas[name] = MetricDelta(
                name=name,
                before=round(bval, 3),
                after=round(aval, 3),
                absolute=round(absolute, 3),
                percentage=round(percentage, 2),
                improved=improved,
            )

        return ComparisonResult(
            before=before,
            after=after,
            deltas=deltas,
        )
