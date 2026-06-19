"""Hermetic tests for benchmark artifact persistence + comparison.

No PresentMon or running game required: synthetic FrameTimeAnalysis objects are
fed through the store and round-tripped.
"""

from __future__ import annotations

import json
from datetime import datetime

from abso.core.benchmark import FrameTimeAnalysis, FrameTimeBenchmark, HistogramBucket
from abso.core.benchmark_store import (
    BenchmarkArtifactStore,
    analysis_from_dict,
    analysis_to_dict,
    summarize_comparison,
)

_TS = datetime(2026, 6, 19, 3, 14, 15)
_TS2 = datetime(2026, 6, 19, 3, 44, 15)


def _analysis(avg_fps: float, p1_low: float, p99_ft: float, stdev: float) -> FrameTimeAnalysis:
    return FrameTimeAnalysis(
        avg_fps=avg_fps,
        avg_frame_time_ms=round(1000.0 / avg_fps, 3),
        p99_frame_time_ms=p99_ft,
        p95_frame_time_ms=p99_ft - 0.5,
        p1_low_fps=p1_low,
        p01_low_fps=p1_low - 5,
        frame_time_stdev=stdev,
        dropped_frame_count=0,
        total_frames=10000,
        histogram_buckets=[
            HistogramBucket(lower_ms=0.0, upper_ms=4.0, count=9000, percentage=90.0),
            HistogramBucket(lower_ms=100.0, upper_ms=float("inf"), count=1000, percentage=10.0),
        ],
    )


def test_analysis_dict_round_trip_handles_inf_bucket():
    original = _analysis(276.0, 240.0, 4.2, 0.4)
    restored = analysis_from_dict(analysis_to_dict(original))
    assert restored.avg_fps == original.avg_fps
    assert restored.p1_low_fps == original.p1_low_fps
    # The inf overflow bucket survives the JSON-safe encode/decode.
    assert restored.histogram_buckets[-1].upper_ms == float("inf")


def test_save_capture_writes_artifact(tmp_path):
    store = BenchmarkArtifactStore(tmp_path)
    path = store.save_capture(
        profile_id="overwatch2-gsync-hdr",
        label="baseline",
        process_name="Overwatch.exe",
        duration_seconds=30,
        analysis=_analysis(276.0, 240.0, 4.2, 0.4),
        timestamp=_TS,
        presentmon_path=r"C:\PresentMon\PresentMon.exe",
        hardware={"gpu": "RTX 4070", "primary_refresh_hz": 300},
    )
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["kind"] == "capture"
    assert data["profile_id"] == "overwatch2-gsync-hdr"
    assert data["label"] == "baseline"
    assert data["hardware"]["primary_refresh_hz"] == 300
    assert data["analysis"]["avg_fps"] == 276.0
    # Stored under reports/benchmarks/<profile>/.
    assert path.parent.name == "overwatch2-gsync-hdr"
    assert path.parent.parent.name == "benchmarks"


def test_list_and_latest_capture_filtering(tmp_path):
    store = BenchmarkArtifactStore(tmp_path)
    store.save_capture(
        profile_id="deadlock-gsync",
        label="baseline",
        process_name="deadlock.exe",
        duration_seconds=30,
        analysis=_analysis(240.0, 200.0, 5.0, 0.6),
        timestamp=_TS,
    )
    store.save_capture(
        profile_id="deadlock-gsync",
        label="after",
        process_name="deadlock.exe",
        duration_seconds=30,
        analysis=_analysis(260.0, 230.0, 4.3, 0.4),
        timestamp=_TS2,
    )
    artifacts = store.list_artifacts("deadlock-gsync")
    assert len(artifacts) == 2
    # Newest first (after captured later than baseline).
    assert artifacts[0]["label"] == "after"
    assert store.latest_capture("deadlock-gsync", label="baseline")["label"] == "baseline"
    assert store.latest_capture("deadlock-gsync")["label"] == "after"
    assert store.list_artifacts("never-benchmarked") == []


def test_save_comparison_and_summary(tmp_path):
    store = BenchmarkArtifactStore(tmp_path)
    bench = FrameTimeBenchmark()
    before = _analysis(240.0, 200.0, 5.0, 0.7)
    after = _analysis(255.0, 235.0, 4.25, 0.4)  # higher fps, lower frame time, less variance
    comparison = bench.compare(before, after)

    path = store.save_comparison(
        profile_id="deadlock-gsync",
        comparison=comparison,
        baseline_ref="b.json",
        after_ref="a.json",
        timestamp=_TS2,
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["kind"] == "comparison"
    assert data["summary"]["verdict"] == "improved"
    assert data["summary"]["consistency_improved"] is True
    assert data["comparison"]["deltas"]["p1_low_fps"]["improved"] is True


def test_summarize_comparison_no_change():
    bench = FrameTimeBenchmark()
    same = _analysis(240.0, 200.0, 5.0, 0.5)
    summary = summarize_comparison(bench.compare(same, same))
    assert summary["verdict"] == "no measurable change"
    assert summary["improved_metrics"] == 0
    assert summary["regressed_metrics"] == 0
