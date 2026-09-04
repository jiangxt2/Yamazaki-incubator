"""Deterministic slow-query detection for the first Yamazaki scenario."""

from __future__ import annotations

from math import ceil
from statistics import median
from typing import Literal

from pydantic import Field

from yamazaki.contracts import (
    DetectionResult,
    DetectionSignal,
    EvidenceRef,
    FrozenContract,
    InferenceKind,
    QueryRun,
    QueryState,
)
from yamazaki.ports import unique_evidence_ids


class SlowQueryThresholds(FrozenContract):
    """Transparent POC thresholds; deployments may replace these values."""

    duration_ms: int = Field(default=5_000, ge=1)
    queue_time_ms: int = Field(default=2_000, ge=1)
    peak_memory_bytes: int = Field(default=512 * 1024 * 1024, ge=1)
    scanned_rows: int = Field(default=1_000_000, ge=1)
    scan_amplification: float = Field(default=1_000, ge=1)
    baseline_samples: int = Field(default=5, ge=3)
    p95_multiplier: float = Field(default=1.5, gt=1)
    mad_multiplier: float = Field(default=6, gt=1)
    stagnation_samples: int = Field(default=3, ge=2)


class SlowQueryDetector:
    """Evaluate official query facts before any model is considered."""

    version = "yamazaki.slow-query/v1"

    def __init__(self, thresholds: SlowQueryThresholds | None = None) -> None:
        self._thresholds = thresholds or SlowQueryThresholds()

    def detect(
        self,
        query: QueryRun,
        *,
        history: tuple[QueryRun, ...] = (),
        evidence: tuple[EvidenceRef, ...] = (),
        progress_snapshots: tuple[QueryRun, ...] = (),
    ) -> DetectionResult:
        """Return signals and gaps rather than an opaque boolean."""

        signals: list[DetectionSignal] = []
        gaps: list[str] = []
        thresholds = self._thresholds

        if query.duration_ms >= thresholds.duration_ms:
            signals.append(
                DetectionSignal(
                    code="duration_threshold",
                    observed_value=float(query.duration_ms),
                    threshold=float(thresholds.duration_ms),
                    inference_kind=InferenceKind.RULE,
                )
            )
        if query.queue_time_ms is None:
            gaps.append("queue_time_unavailable")
        elif query.queue_time_ms >= thresholds.queue_time_ms:
            signals.append(
                DetectionSignal(
                    code="queue_time_threshold",
                    observed_value=float(query.queue_time_ms),
                    threshold=float(thresholds.queue_time_ms),
                    inference_kind=InferenceKind.RULE,
                )
            )
        if query.peak_memory_bytes is None:
            gaps.append("peak_memory_unavailable")
        elif query.peak_memory_bytes >= thresholds.peak_memory_bytes:
            signals.append(
                DetectionSignal(
                    code="memory_threshold",
                    observed_value=float(query.peak_memory_bytes),
                    threshold=float(thresholds.peak_memory_bytes),
                    inference_kind=InferenceKind.RULE,
                )
            )
        if query.scanned_rows is None:
            gaps.append("scanned_rows_unavailable")
        else:
            if query.scanned_rows >= thresholds.scanned_rows:
                signals.append(
                    DetectionSignal(
                        code="scanned_rows_threshold",
                        observed_value=float(query.scanned_rows),
                        threshold=float(thresholds.scanned_rows),
                        inference_kind=InferenceKind.RULE,
                    )
                )
            if query.returned_rows is None:
                gaps.append("returned_rows_unavailable")
            elif query.returned_rows > 0:
                amplification = query.scanned_rows / query.returned_rows
                if amplification >= thresholds.scan_amplification:
                    signals.append(
                        DetectionSignal(
                            code="scan_amplification",
                            observed_value=amplification,
                            threshold=thresholds.scan_amplification,
                            inference_kind=InferenceKind.STATISTICAL,
                        )
                    )

        comparable = tuple(
            item
            for item in history
            if item.cluster_id == query.cluster_id
            and item.native_fingerprint == query.native_fingerprint
            and item.query_run_id != query.query_run_id
            and item.state is QueryState.SUCCEEDED
        )
        if len(comparable) < thresholds.baseline_samples:
            gaps.append("history_baseline_insufficient")
        else:
            durations = sorted(item.duration_ms for item in comparable)
            p95 = durations[max(0, ceil(len(durations) * 0.95) - 1)]
            p95_threshold = p95 * thresholds.p95_multiplier
            if query.duration_ms >= p95_threshold:
                signals.append(
                    DetectionSignal(
                        code="p95_regression",
                        observed_value=float(query.duration_ms),
                        threshold=float(p95_threshold),
                        inference_kind=InferenceKind.STATISTICAL,
                    )
                )
            center = median(durations)
            mad = median(abs(value - center) for value in durations)
            if mad > 0:
                mad_threshold = center + thresholds.mad_multiplier * mad
                if query.duration_ms >= mad_threshold:
                    signals.append(
                        DetectionSignal(
                            code="mad_regression",
                            observed_value=float(query.duration_ms),
                            threshold=float(mad_threshold),
                            inference_kind=InferenceKind.STATISTICAL,
                        )
                    )

        snapshots = tuple(
            item
            for item in progress_snapshots
            if item.engine_query_id == query.engine_query_id
        )
        if (
            query.state is QueryState.RUNNING
            and len(snapshots) >= thresholds.stagnation_samples
        ):
            recent = snapshots[-thresholds.stagnation_samples :]
            progress = [item.progress for item in recent]
            if all(value is not None for value in progress) and len(set(progress)) == 1:
                signals.append(
                    DetectionSignal(
                        code="progress_stagnation",
                        observed_value=float(progress[-1] or 0),
                        threshold=float(progress[0] or 0),
                        inference_kind=InferenceKind.STATISTICAL,
                    )
                )

        anomaly = bool(signals)
        severity: Literal["none", "low", "medium", "high"] = "none"
        if anomaly:
            severity = (
                "high"
                if len(signals) >= 2 or query.duration_ms >= thresholds.duration_ms * 2
                else "medium"
            )
        confidence = 0.0 if not anomaly else max(0.55, 0.95 - 0.08 * len(gaps))
        return DetectionResult(
            query_run_id=query.query_run_id,
            detector_version=self.version,
            anomaly=anomaly,
            signals=tuple(signals),
            evidence_ids=unique_evidence_ids(evidence),
            severity=severity,
            confidence=confidence,
            evidence_gaps=tuple(dict.fromkeys(gaps)),
        )
