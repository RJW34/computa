"""Benchmark report generator for frame-time analysis.

Produces plain-text benchmark reports from PresentMon frame-time data,
including single-run summaries, before/after comparisons, and ASCII
histogram visualizations.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from pathlib import Path

from abso.core.benchmark import ComparisonResult, FrameTimeAnalysis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BLOCK_CHARS: list[str] = ["█", "▇", "▆", "▅", "▄", "▃", "▂", "▁"]
"""Block characters ordered from full to minimum fill."""

_METRIC_DISPLAY_NAMES: dict[str, str] = {
    "avg_fps": "Avg FPS",
    "avg_frame_time_ms": "Avg Frame Time",
    "p99_frame_time_ms": "P99 Frame Time",
    "p95_frame_time_ms": "P95 Frame Time",
    "p1_low_fps": "1% Low FPS",
    "p01_low_fps": "0.1% Low FPS",
    "frame_time_stdev": "Frame Time StDev",
    "dropped_frame_count": "Dropped Frames",
    "total_frames": "Total Frames",
}

_METRIC_UNITS: dict[str, str] = {
    "avg_fps": "fps",
    "avg_frame_time_ms": "ms",
    "p99_frame_time_ms": "ms",
    "p95_frame_time_ms": "ms",
    "p1_low_fps": "fps",
    "p01_low_fps": "fps",
    "frame_time_stdev": "ms",
    "dropped_frame_count": "",
    "total_frames": "",
}

_METRIC_HIGHER_IS_BETTER: dict[str, bool] = {
    "avg_fps": True,
    "avg_frame_time_ms": False,
    "p99_frame_time_ms": False,
    "p95_frame_time_ms": False,
    "p1_low_fps": True,
    "p01_low_fps": True,
    "frame_time_stdev": False,
    "dropped_frame_count": False,
    "total_frames": True,
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _format_delta(value: float, unit: str, higher_is_better: bool) -> str:
    """Format a metric delta with direction indicator.

    Args:
        value: The numeric delta (after - before).
        unit: Unit suffix (e.g. ``"ms"``, ``"fps"``).
        higher_is_better: Whether a positive delta is an improvement.

    Returns:
        A string like ``"+12.3 fps (better)"`` with appropriate arrow.
    """
    if value == 0.0:
        suffix = unit + " " if unit else ""
        return f"  0.0 {suffix}(no change)"

    sign = "+" if value > 0.0 else ""
    unit_str = f" {unit}" if unit else ""

    is_improvement = (value > 0.0) == higher_is_better
    if is_improvement:
        indicator = "better"
        arrow = "\u2191"  # ↑
    else:
        indicator = "worse"
        arrow = "\u2193"  # ↓

    return f"{sign}{value:.2f}{unit_str} {arrow} ({indicator})"


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------


class BenchmarkReportGenerator:
    """Generates text-based benchmark reports from frame-time data.

    All public methods return plain-text strings suitable for terminal
    display or file output.  No external dependencies are required.
    """

    # ------------------------------------------------------------------
    # Single-run report
    # ------------------------------------------------------------------

    def generate_text_report(
        self,
        analysis: FrameTimeAnalysis,
        profile_id: str | None = None,
        hardware_info: dict | None = None,
    ) -> str:
        """Generate a plain-text benchmark report for a single analysis.

        Args:
            analysis: Frame-time analysis to report on.
            profile_id: Optional profile name that was active.
            hardware_info: Optional dict with keys like ``"gpu"``,
                ``"cpu"``, ``"monitor"`` for the hardware summary line.

        Returns:
            The full report as a multi-line string.
        """
        lines: list[str] = []
        separator = "=" * 60

        # --- Header ---
        lines.append(separator)
        lines.append("  A.B.S.O. Benchmark Report")
        lines.append(separator)
        lines.append(f"  Timestamp : {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if profile_id:
            lines.append(f"  Profile   : {profile_id}")
        if hardware_info:
            hw_parts: list[str] = []
            for key in ("gpu", "cpu", "monitor"):
                if key in hardware_info:
                    hw_parts.append(str(hardware_info[key]))
            if hw_parts:
                lines.append(f"  Hardware  : {' | '.join(hw_parts)}")
        lines.append(separator)
        lines.append("")

        # --- Frame Time Summary ---
        lines.append("  Frame Time Summary")
        lines.append("  " + "-" * 40)
        lines.append(f"  Avg FPS           : {analysis.avg_fps:.2f}")
        lines.append(f"  1% Low FPS        : {analysis.p1_low_fps:.2f}")
        lines.append(f"  0.1% Low FPS      : {analysis.p01_low_fps:.2f}")
        lines.append(f"  Avg Frame Time    : {analysis.avg_frame_time_ms:.3f} ms")
        lines.append(f"  P95 Frame Time    : {analysis.p95_frame_time_ms:.3f} ms")
        lines.append(f"  P99 Frame Time    : {analysis.p99_frame_time_ms:.3f} ms")
        lines.append(f"  Frame Time StDev  : {analysis.frame_time_stdev:.3f} ms")
        lines.append(f"  Total Frames      : {analysis.total_frames}")
        lines.append("")

        # --- Frame Time Distribution ---
        if analysis.histogram_buckets:
            lines.append("  Frame Time Distribution")
            lines.append("  " + "-" * 40)
            max_count = max(b.count for b in analysis.histogram_buckets)
            for bucket in analysis.histogram_buckets:
                if bucket.upper_ms == float("inf"):
                    label = f"  {bucket.lower_ms:6.1f}+ ms"
                else:
                    label = f"  {bucket.lower_ms:6.1f}-{bucket.upper_ms:<6.1f} ms"

                if max_count > 0:
                    bar_len = int((bucket.count / max_count) * 20)
                else:
                    bar_len = 0
                bar = "\u2588" * bar_len
                lines.append(f"{label} |{bar:<20s}| {bucket.count:>6d} ({bucket.percentage:5.1f}%)")
            lines.append("")

        # --- Dropped Frames ---
        lines.append("  Dropped Frames")
        lines.append("  " + "-" * 40)
        if analysis.total_frames > 0:
            drop_pct = (analysis.dropped_frame_count / analysis.total_frames) * 100.0
        else:
            drop_pct = 0.0
        lines.append(
            f"  Count  : {analysis.dropped_frame_count} / {analysis.total_frames}"
            f"  ({drop_pct:.2f}%)"
        )
        lines.append("")
        lines.append(separator)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Comparison report
    # ------------------------------------------------------------------

    def generate_comparison_report(
        self,
        comparison: ComparisonResult,
        profile_id: str | None = None,
    ) -> str:
        """Generate a before/after comparison report.

        Displays side-by-side metrics with deltas and an ASCII bar chart
        showing relative improvement per metric.

        Args:
            comparison: Comparison result from
                :meth:`~abso.core.benchmark.FrameTimeBenchmark.compare`.
            profile_id: Optional profile name for the header.

        Returns:
            The full comparison report as a multi-line string.
        """
        lines: list[str] = []
        separator = "=" * 70

        # --- Header ---
        lines.append(separator)
        lines.append("  A.B.S.O. Benchmark Comparison Report")
        lines.append(separator)
        lines.append(f"  Timestamp : {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if profile_id:
            lines.append(f"  Profile   : {profile_id}")
        lines.append(separator)
        lines.append("")

        # --- Side-by-side metrics ---
        lines.append("  Metric                  Before      After       Delta")
        lines.append("  " + "-" * 64)

        # Ordered list of metrics to display.
        metric_order: list[str] = [
            "avg_fps", "p1_low_fps", "p01_low_fps",
            "avg_frame_time_ms", "p95_frame_time_ms", "p99_frame_time_ms",
            "frame_time_stdev", "dropped_frame_count", "total_frames",
        ]

        for metric_key in metric_order:
            delta = comparison.deltas.get(metric_key)
            if delta is None:
                continue

            display_name = _METRIC_DISPLAY_NAMES.get(metric_key, metric_key)
            unit = _METRIC_UNITS.get(metric_key, "")
            higher_is_better = _METRIC_HIGHER_IS_BETTER.get(metric_key, True)

            before_str = f"{delta.before:.2f}"
            after_str = f"{delta.after:.2f}"
            delta_str = _format_delta(delta.absolute, unit, higher_is_better)

            lines.append(
                f"  {display_name:<22s}  {before_str:>8s}  {after_str:>8s}    {delta_str}"
            )

        lines.append("")

        # --- ASCII bar chart of percentage changes ---
        lines.append("  Relative Change (%)")
        lines.append("  " + "-" * 64)

        # Find the maximum absolute percentage for scaling.
        max_abs_pct = 0.0
        for metric_key in metric_order:
            delta = comparison.deltas.get(metric_key)
            if delta is not None and math.isfinite(delta.percentage):
                max_abs_pct = max(max_abs_pct, abs(delta.percentage))
        if max_abs_pct == 0.0:
            max_abs_pct = 1.0  # avoid division by zero

        chart_half_width = 20  # characters per side of center

        for metric_key in metric_order:
            delta = comparison.deltas.get(metric_key)
            if delta is None:
                continue

            display_name = _METRIC_DISPLAY_NAMES.get(metric_key, metric_key)
            higher_is_better = _METRIC_HIGHER_IS_BETTER.get(metric_key, True)

            pct = delta.percentage if math.isfinite(delta.percentage) else 0.0
            # Normalize: positive percentage = improvement direction.
            # For lower-is-better metrics, flip sign so negative delta shows
            # as positive improvement.
            normalized = pct if higher_is_better else -pct

            bar_len = int(abs(normalized) / max_abs_pct * chart_half_width)
            bar_len = min(bar_len, chart_half_width)

            if normalized >= 0.0:
                left_bar = " " * chart_half_width
                right_bar = "\u2588" * bar_len + " " * (chart_half_width - bar_len)
            else:
                padding = chart_half_width - bar_len
                left_bar = " " * padding + "\u2588" * bar_len
                right_bar = " " * chart_half_width

            if delta.improved:
                arrow = "\u2191"
            elif delta.absolute == 0.0:
                arrow = " "
            else:
                arrow = "\u2193"

            pct_str = f"{pct:+.1f}%" if math.isfinite(pct) else "  N/A"
            lines.append(
                f"  {display_name:<18s} {left_bar}|{right_bar} {arrow} {pct_str}"
            )

        lines.append("")
        lines.append(separator)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # ASCII histogram
    # ------------------------------------------------------------------

    def generate_ascii_histogram(
        self,
        frame_times_ms: list[float],
        width: int = 40,
        height: int = 12,
    ) -> str:
        """Create an ASCII histogram of frame-time distribution.

        The X-axis shows frame time in milliseconds (auto-scaled), and the
        Y-axis shows frequency.  Block characters provide sub-row
        resolution.  Percentile markers for P95 and P99 are drawn with
        ``|`` indicators on the X-axis label row.

        Args:
            frame_times_ms: Raw frame-time values in milliseconds.
            width: Number of columns (buckets) in the histogram.
            height: Number of rows for the Y-axis.

        Returns:
            The rendered histogram as a multi-line string.
        """
        if not frame_times_ms:
            return "  (no frame-time data to plot)"

        sorted_ft = sorted(frame_times_ms)
        ft_min = sorted_ft[0]
        ft_max = sorted_ft[-1]

        # Compute percentiles for markers.
        p95 = self._percentile_value(sorted_ft, 95.0)
        p99 = self._percentile_value(sorted_ft, 99.0)

        # Build uniform buckets across the observed range.
        bucket_width = (ft_max - ft_min) / width if ft_max > ft_min else 1.0
        counts: list[int] = [0] * width

        for ft in frame_times_ms:
            idx = int((ft - ft_min) / bucket_width)
            idx = min(idx, width - 1)
            counts[idx] += 1

        max_count = max(counts) if counts else 1

        # Y-axis label width (accommodate the largest count).
        y_label_width = max(len(str(max_count)), 4)

        # Sub-character resolution: each row is divided into 8 levels.
        scale = (max_count / height) if height > 0 else 1.0
        if scale == 0.0:
            scale = 1.0

        lines: list[str] = []

        # Render rows from top to bottom.
        for row in range(height, 0, -1):
            threshold_full = (row - 1) * scale
            threshold_top = row * scale

            # Y-axis label: show count at this row's upper boundary.
            y_val = int(round(threshold_top))
            label = str(y_val).rjust(y_label_width)

            row_chars: list[str] = []
            for col in range(width):
                count = counts[col]
                if count >= threshold_top:
                    row_chars.append(_BLOCK_CHARS[0])  # full block
                elif count > threshold_full:
                    # Fractional fill within this row.
                    frac = (count - threshold_full) / scale
                    char_idx = max(0, min(len(_BLOCK_CHARS) - 1, int((1.0 - frac) * len(_BLOCK_CHARS))))
                    row_chars.append(_BLOCK_CHARS[char_idx])
                else:
                    row_chars.append(" ")

            lines.append(f"  {label} |{''.join(row_chars)}|")

        # X-axis border.
        lines.append(f"  {' ' * y_label_width} +{'-' * width}+")

        # X-axis labels: min, mid, max.
        ft_mid = (ft_min + ft_max) / 2.0
        min_label = f"{ft_min:.1f}"
        mid_label = f"{ft_mid:.1f}"
        max_label = f"{ft_max:.1f}"

        # Position labels under the chart.
        mid_pos = width // 2
        x_label_line = list(" " * (width + 2))
        # Place min label.
        for i, ch in enumerate(min_label):
            if i < len(x_label_line):
                x_label_line[i] = ch
        # Place mid label centered.
        mid_start = max(len(min_label) + 1, mid_pos - len(mid_label) // 2)
        for i, ch in enumerate(mid_label):
            pos = mid_start + i
            if pos < len(x_label_line):
                x_label_line[pos] = ch
        # Place max label at right edge.
        max_start = max(mid_start + len(mid_label) + 1, width + 2 - len(max_label))
        for i, ch in enumerate(max_label):
            pos = max_start + i
            if pos < len(x_label_line):
                x_label_line[pos] = ch

        lines.append(f"  {' ' * y_label_width} {''.join(x_label_line)}")
        lines.append(f"  {' ' * y_label_width} {'frame time (ms)':^{width + 2}}")

        # Percentile marker line.
        marker_line = list(" " * (width + 2))
        for pval, plabel in [(p95, "P95"), (p99, "P99")]:
            col_idx = int((pval - ft_min) / bucket_width) if bucket_width > 0 else 0
            col_idx = min(col_idx, width - 1)
            # Place the | marker.
            if 0 <= col_idx < len(marker_line):
                marker_line[col_idx] = "|"
            # Place the label next to it.
            label_start = col_idx + 1
            for i, ch in enumerate(plabel):
                pos = label_start + i
                if 0 <= pos < len(marker_line):
                    marker_line[pos] = ch

        lines.append(f"  {' ' * y_label_width} {''.join(marker_line)}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # File output
    # ------------------------------------------------------------------

    def save_report(
        self,
        content: str,
        filename: str,
        reports_dir: Path,
    ) -> Path:
        """Save a report string to a file.

        Creates the target directory if it does not exist.

        Args:
            content: Report text to write.
            filename: Name of the output file (e.g. ``"bench_2024.txt"``).
            reports_dir: Directory to write the file into.

        Returns:
            Absolute path to the saved report file.
        """
        reports_dir.mkdir(parents=True, exist_ok=True)
        file_path = reports_dir / filename
        file_path.write_text(content, encoding="utf-8")
        logger.info("Report saved to %s", file_path)
        return file_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _percentile_value(sorted_data: list[float], pct: float) -> float:
        """Return the *pct*-th percentile from pre-sorted data.

        Uses linear interpolation for values between data points.

        Args:
            sorted_data: Ascending-sorted list of numeric values.
            pct: Percentile in the range [0, 100].

        Returns:
            The interpolated value at the requested percentile.
        """
        if not sorted_data:
            return 0.0
        if len(sorted_data) == 1:
            return sorted_data[0]

        rank = (pct / 100.0) * (len(sorted_data) - 1)
        lower = int(math.floor(rank))
        upper = min(lower + 1, len(sorted_data) - 1)
        frac = rank - lower
        return sorted_data[lower] + frac * (sorted_data[upper] - sorted_data[lower])
