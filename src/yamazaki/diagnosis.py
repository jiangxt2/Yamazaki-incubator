"""Evidence-bound deterministic diagnosis and non-actionable recommendations."""

from __future__ import annotations

from yamazaki.contracts import (
    DetectionResult,
    Diagnosis,
    DiagnosisSource,
    EvidenceBundle,
    QueryRun,
    Recommendation,
    RootCause,
)

_CAUSES: dict[str, tuple[str, str]] = {
    "queue_time_threshold": (
        "workload_queue_contention",
        "A material share of elapsed time was spent waiting in a workload queue.",
    ),
    "scan_amplification": (
        "scan_amplification",
        "The query scanned substantially more rows than it returned.",
    ),
    "scanned_rows_threshold": (
        "large_scan",
        "The query crossed the configured scanned-row threshold.",
    ),
    "memory_threshold": (
        "memory_pressure",
        "Observed peak memory crossed the configured threshold.",
    ),
    "progress_stagnation": (
        "execution_stagnation",
        "Repeated running snapshots reported no progress.",
    ),
    "p95_regression": (
        "fingerprint_regression",
        "Duration regressed relative to the same cluster and native fingerprint.",
    ),
    "mad_regression": (
        "fingerprint_regression",
        "Duration is an outlier relative to the robust historical baseline.",
    ),
    "duration_threshold": (
        "duration_threshold",
        "The query crossed the configured absolute duration threshold.",
    ),
}


class RuleDiagnoser:
    """Map transparent detection signals to reviewable candidate causes."""

    def diagnose(
        self,
        query: QueryRun,
        detection: DetectionResult,
        evidence: EvidenceBundle,
    ) -> tuple[Diagnosis, Recommendation] | None:
        if not detection.anomaly:
            return None
        allowed = frozenset(item.evidence_id for item in evidence.items)
        referenced = tuple(
            identifier for identifier in detection.evidence_ids if identifier in allowed
        )
        causes: list[RootCause] = []
        seen: set[str] = set()
        for signal in detection.signals:
            code, explanation = _CAUSES[signal.code]
            if code in seen:
                continue
            seen.add(code)
            causes.append(
                RootCause(
                    code=code,
                    explanation=explanation,
                    inference_kind=signal.inference_kind,
                    evidence_ids=referenced,
                    confidence=detection.confidence,
                )
            )
        uncertainty = detection.evidence_gaps
        if not referenced:
            uncertainty = (*uncertainty, "no_persisted_evidence_reference")
        diagnosis = Diagnosis(
            query_run_id=query.query_run_id,
            source=DiagnosisSource.DETERMINISTIC,
            causes=tuple(causes),
            uncertainty=tuple(dict.fromkeys(uncertainty)),
            evidence_bundle_digest=evidence.digest,
        )
        recommendation = Recommendation(
            diagnosis_id=diagnosis.diagnosis_id,
            content=(
                "Review the referenced engine evidence and validate the highest-ranked "
                "cause with a non-executing EXPLAIN or an isolated replay before "
                "changing SQL, schema, settings, or workload policy."
            ),
            prerequisites=("Confirm the query owner and workload intent.",),
            risk="The evidence is observational and may be incomplete.",
            expected_benefit=(
                "A validated cause can guide a narrower optimization experiment."
            ),
            verification=(
                "Compare duration and resource evidence for the same native "
                "fingerprint after an independently reviewed change."
            ),
        )
        return diagnosis, recommendation
