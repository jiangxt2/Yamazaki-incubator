"""Tests for each deterministic slow-query signal and evidence gap."""

from datetime import UTC, datetime, timedelta

from tests.conftest import make_query
from yamazaki.contracts import QueryState
from yamazaki.slow_query import SlowQueryDetector


def test_fast_query_is_not_anomaly_and_reports_missing_baseline() -> None:
    result = SlowQueryDetector().detect(make_query(duration_ms=100))
    assert not result.anomaly
    assert result.severity == "none"
    assert "history_baseline_insufficient" in result.evidence_gaps


def test_absolute_queue_memory_scan_and_amplification_signals() -> None:
    query = make_query(
        duration_ms=10_000,
        queue_time_ms=3_000,
        peak_memory_bytes=600 * 1024 * 1024,
        scanned_rows=2_000_000,
        returned_rows=1,
    )
    result = SlowQueryDetector().detect(query)
    codes = {signal.code for signal in result.signals}
    assert {
        "duration_threshold",
        "queue_time_threshold",
        "memory_threshold",
        "scanned_rows_threshold",
        "scan_amplification",
    } <= codes
    assert result.severity == "high"


def test_p95_and_mad_regressions_use_same_cluster_and_fingerprint() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    durations = (100, 105, 95, 110, 90, 100)
    history = tuple(
        make_query(
            duration_ms=value,
            query_id=f"history-{index}",
            started_at=start + timedelta(minutes=index),
        )
        for index, value in enumerate(durations)
    )
    query = make_query(duration_ms=1_000, query_id="regression")
    result = SlowQueryDetector().detect(query, history=history)
    codes = {signal.code for signal in result.signals}
    assert "p95_regression" in codes
    assert "mad_regression" in codes


def test_running_query_stagnation_requires_three_equal_snapshots() -> None:
    query = make_query(
        duration_ms=6_000,
        state=QueryState.RUNNING,
        progress=0.25,
    )
    snapshots = tuple(
        make_query(
            duration_ms=duration,
            state=QueryState.RUNNING,
            progress=0.25,
        )
        for duration in (4_000, 5_000, 6_000)
    )
    result = SlowQueryDetector().detect(query, progress_snapshots=snapshots)
    assert "progress_stagnation" in {signal.code for signal in result.signals}


def test_missing_resource_fields_reduce_confidence_without_inventing_values() -> None:
    query = make_query(
        duration_ms=6_000,
        queue_time_ms=None,
        peak_memory_bytes=None,
        scanned_rows=None,
        returned_rows=None,
    )
    result = SlowQueryDetector().detect(query)
    assert result.anomaly
    assert result.confidence < 0.95
    assert "peak_memory_unavailable" in result.evidence_gaps
    assert "scanned_rows_unavailable" in result.evidence_gaps


def test_missing_returned_rows_does_not_create_scan_amplification() -> None:
    query = make_query(
        duration_ms=100,
        scanned_rows=2_000_000,
        returned_rows=None,
    )
    result = SlowQueryDetector().detect(query)
    assert "scan_amplification" not in {signal.code for signal in result.signals}
    assert "returned_rows_unavailable" in result.evidence_gaps
