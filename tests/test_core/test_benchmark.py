"""Hermetic tests for FrameTimeBenchmark analysis + PresentMon column casing.

These do not invoke PresentMon: synthetic CaptureResult rows are analyzed
directly, covering the PresentMon 1.x (msBetweenPresents) and 2.x
(MsBetweenPresents) header-casing difference.
"""

from __future__ import annotations

from datetime import datetime

from abso.core.benchmark import CaptureResult, FrameTimeBenchmark


def _capture(rows: list[dict[str, str]]) -> CaptureResult:
    return CaptureResult(
        raw_data=rows,
        process_name="game.exe",
        duration_seconds=1,
        csv_path=__import__("pathlib").Path("unused.csv"),
        timestamp=datetime(2026, 6, 19, 0, 0, 0),
    )


def test_analyze_parses_presentmon_v2_column_casing():
    """PresentMon 2.x emits MsBetweenPresents (capital M)."""
    rows = [{"MsBetweenPresents": "4.0"} for _ in range(100)]
    analysis = FrameTimeBenchmark().analyze(_capture(rows))
    assert analysis.total_frames == 100
    assert round(analysis.avg_fps) == 250  # 1000 / 4ms


def test_analyze_parses_presentmon_v1_column_casing():
    """PresentMon 1.x emitted msBetweenPresents (lowercase m)."""
    rows = [{"msBetweenPresents": "8.0"} for _ in range(100)]
    analysis = FrameTimeBenchmark().analyze(_capture(rows))
    assert analysis.total_frames == 100
    assert round(analysis.avg_fps) == 125  # 1000 / 8ms


def test_analyze_counts_dropped_frames_any_casing():
    rows = [{"MsBetweenPresents": "4.0", "Dropped": "1"} for _ in range(5)]
    rows += [{"MsBetweenPresents": "4.0", "dropped": "0"} for _ in range(5)]
    analysis = FrameTimeBenchmark().analyze(_capture(rows))
    assert analysis.dropped_frame_count == 5
    assert analysis.total_frames == 10


def test_analyze_empty_capture_is_zeroed_not_crash():
    analysis = FrameTimeBenchmark().analyze(_capture([]))
    assert analysis.total_frames == 0
    assert analysis.avg_fps == 0.0
