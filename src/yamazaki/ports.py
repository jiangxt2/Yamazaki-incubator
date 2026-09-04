"""Small ports that keep domain logic independent from infrastructure."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from yamazaki.contracts import (
    CapabilityProfile,
    ClusterTarget,
    DetectionResult,
    Diagnosis,
    EvidenceBundle,
    EvidenceRef,
    InvestigationRequest,
    InvestigationResult,
    QueryRun,
    Recommendation,
)
from yamazaki.engines.base import RawEvidence, RawQueryRecord


class EngineAdapter(Protocol):
    """Expose only reviewed read-only engine operations."""

    @property
    def target(self) -> ClusterTarget: ...

    def probe_capabilities(self) -> CapabilityProfile: ...

    def collect_running_queries(
        self, limit: int = 1_000
    ) -> tuple[RawQueryRecord, ...]: ...

    def collect_completed_queries(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        limit: int = 1_000,
    ) -> tuple[RawQueryRecord, ...]: ...

    def collect_query_evidence(self, query_id: str) -> RawEvidence: ...


class EvidenceStorePort(Protocol):
    """Store restricted raw evidence by opaque identifier."""

    def write(self, evidence_id: UUID, payload: dict[str, Any]) -> tuple[str, str]: ...

    def read(self, locator: str) -> dict[str, Any]: ...


class ControlStateRepositoryPort(Protocol):
    """Persist idempotent control-plane records."""

    def save_cluster(self, target: ClusterTarget) -> None: ...

    def save_capability(self, profile: CapabilityProfile) -> None: ...

    def save_query_run(self, query: QueryRun) -> QueryRun: ...

    def list_query_history(
        self, query: QueryRun, limit: int = 100
    ) -> tuple[QueryRun, ...]: ...

    def save_evidence(self, evidence: EvidenceRef) -> EvidenceRef: ...

    def save_detection(self, detection: DetectionResult) -> None: ...

    def save_diagnosis(self, diagnosis: Diagnosis) -> None: ...

    def save_recommendation(self, recommendation: Recommendation) -> None: ...

    def save_investigation(
        self,
        request: InvestigationRequest,
        result: InvestigationResult | None = None,
    ) -> None: ...

    def list_clusters(self) -> tuple[ClusterTarget, ...]: ...

    def list_query_runs(self, limit: int = 100) -> tuple[QueryRun, ...]: ...

    def list_detections(self, limit: int = 100) -> tuple[DetectionResult, ...]: ...

    def list_diagnoses(self, limit: int = 100) -> tuple[Diagnosis, ...]: ...

    def close(self) -> None: ...


class AgentDiagnoserPort(Protocol):
    """Optionally refine a diagnosis from bounded redacted evidence."""

    def diagnose(
        self,
        query: QueryRun,
        detection: DetectionResult,
        evidence: EvidenceBundle,
    ) -> tuple[Diagnosis, Recommendation] | None: ...


class CoordinatorPort(Protocol):
    """Run one bounded investigation."""

    def investigate(self, request: InvestigationRequest) -> InvestigationResult: ...


def unique_evidence_ids(items: Sequence[EvidenceRef]) -> tuple[UUID, ...]:
    """Return stable unique identifiers in input order."""

    return tuple(dict.fromkeys(item.evidence_id for item in items))
