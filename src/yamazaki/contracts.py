"""Strict domain contracts for the read-only slow-query POC."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

_QUERY_NAMESPACE = UUID("879a5405-9849-4fa7-897b-bc1e5939499f")


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class FrozenContract(BaseModel):
    """Shared strict and immutable model configuration."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
        validate_default=True,
    )


class EngineKind(StrEnum):
    CLICKHOUSE = "clickhouse"
    DORIS = "doris"


class QueryState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class InvestigationState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEGRADED = "degraded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InferenceKind(StrEnum):
    FACT = "fact"
    RULE = "rule"
    STATISTICAL = "statistical"
    MODEL = "model"


class Sensitivity(StrEnum):
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class RedactionStatus(StrEnum):
    REDACTED = "redacted"
    OMITTED = "omitted"


class DiagnosisSource(StrEnum):
    DETERMINISTIC = "deterministic"
    AGENT_ASSISTED = "agent_assisted"


class ClusterTarget(FrozenContract):
    """A trusted logical cluster reference without embedded credentials."""

    schema_version: Literal[1] = 1
    cluster_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    engine: EngineKind
    display_name: str = Field(min_length=1, max_length=128)
    environment: str = Field(min_length=1, max_length=64)
    credential_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]*$")


class CapabilityProfile(FrozenContract):
    """Observed engine capabilities for one cluster and point in time."""

    schema_version: Literal[1] = 1
    capability_profile_id: UUID = Field(default_factory=uuid4)
    cluster_id: str
    engine: EngineKind
    engine_version: str = Field(min_length=1)
    deployment_mode: str = Field(default="single-node", min_length=1)
    supports_running_queries: bool
    supports_completed_queries: bool
    supports_native_fingerprint: bool
    supports_profile: bool
    missing_capabilities: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    captured_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_time(self) -> CapabilityProfile:
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        return self


class ClickHouseIdentity(FrozenContract):
    """ClickHouse-native identity retained by the common QueryRun."""

    kind: Literal[EngineKind.CLICKHOUSE] = EngineKind.CLICKHOUSE
    query_id: str = Field(min_length=1, max_length=256)
    initial_query_id: str | None = Field(default=None, max_length=256)
    normalized_query_hash: str | None = Field(default=None, max_length=64)
    query_kind: str | None = Field(default=None, max_length=64)


class DorisIdentity(FrozenContract):
    """Doris-native identity retained by the common QueryRun."""

    kind: Literal[EngineKind.DORIS] = EngineKind.DORIS
    query_id: str = Field(min_length=1, max_length=256)
    sql_digest: str | None = Field(default=None, max_length=256)
    frontend: str | None = Field(default=None, max_length=256)
    workload_group: str | None = Field(default=None, max_length=256)


NativeIdentity = Annotated[
    ClickHouseIdentity | DorisIdentity,
    Field(discriminator="kind"),
]


class QueryRun(FrozenContract):
    """Normalized query execution with engine-native identity."""

    schema_version: Literal[1] = 1
    query_run_id: UUID
    engine: EngineKind
    cluster_id: str
    engine_query_id: str = Field(min_length=1, max_length=256)
    native_fingerprint: str = Field(min_length=1, max_length=256)
    state: QueryState
    started_at: datetime
    finished_at: datetime | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    ingested_at: datetime = Field(default_factory=utc_now)
    duration_ms: int = Field(ge=0)
    queue_time_ms: int | None = Field(default=None, ge=0)
    cpu_time_ms: int | None = Field(default=None, ge=0)
    peak_memory_bytes: int | None = Field(default=None, ge=0)
    scanned_rows: int | None = Field(default=None, ge=0)
    returned_rows: int | None = Field(default=None, ge=0)
    shuffle_bytes: int | None = Field(default=None, ge=0)
    spill_bytes: int | None = Field(default=None, ge=0)
    progress: float | None = Field(default=None, ge=0, le=1)
    statement_type: str = Field(min_length=1, max_length=64)
    redacted_structure: str | None = Field(default=None, max_length=4_000)
    native: NativeIdentity
    correlation_id: UUID

    @model_validator(mode="after")
    def _validate_identity_and_time(self) -> QueryRun:
        for value in (self.started_at, self.observed_at, self.ingested_at):
            if value.tzinfo is None:
                raise ValueError("query timestamps must be timezone-aware")
        if self.finished_at is not None and self.finished_at.tzinfo is None:
            raise ValueError("finished_at must be timezone-aware")
        if self.native.kind is not self.engine:
            raise ValueError("native identity must match the query engine")
        return self

    @classmethod
    def stable_id(
        cls,
        *,
        engine: EngineKind,
        cluster_id: str,
        engine_query_id: str,
        started_at: datetime,
    ) -> UUID:
        """Build the idempotent identity for one execution attempt."""

        key = f"{engine}:{cluster_id}:{engine_query_id}:{started_at.isoformat()}"
        return uuid5(_QUERY_NAMESPACE, key)


class EvidenceRef(FrozenContract):
    """Bounded, redacted evidence made available to diagnosis."""

    schema_version: Literal[1] = 1
    evidence_id: UUID = Field(default_factory=uuid4)
    query_run_id: UUID
    source_kind: str = Field(min_length=1, max_length=128)
    engine: EngineKind
    collected_at: datetime = Field(default_factory=utc_now)
    summary: str = Field(min_length=1, max_length=500)
    facts: dict[str, int | float | str | bool | None] = Field(default_factory=dict)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    storage_locator: str | None = Field(default=None, max_length=256)
    redaction_status: RedactionStatus = RedactionStatus.REDACTED

    @classmethod
    def stable_id(
        cls,
        *,
        query_run_id: UUID,
        source_kind: str,
        content_hash: str,
    ) -> UUID:
        """Build an idempotent identity for one evidence value."""

        return uuid5(_QUERY_NAMESPACE, f"{query_run_id}:{source_kind}:{content_hash}")


class EvidenceBundle(FrozenContract):
    """Bounded evidence passed to deterministic or model diagnosis."""

    schema_version: Literal[1] = 1
    items: tuple[EvidenceRef, ...]

    @model_validator(mode="after")
    def _validate_items(self) -> EvidenceBundle:
        if len(self.items) > 12:
            raise ValueError("an evidence bundle may contain at most 12 items")
        identifiers = [item.evidence_id for item in self.items]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("evidence identifiers must be unique")
        return self

    @property
    def digest(self) -> str:
        return sha256(self.model_dump_json().encode()).hexdigest()


class DetectionSignal(FrozenContract):
    """One transparent reason a query was considered anomalous."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    observed_value: float
    threshold: float
    inference_kind: InferenceKind


class DetectionResult(FrozenContract):
    """Deterministic anomaly decision with evidence and uncertainty."""

    schema_version: Literal[1] = 1
    detection_id: UUID = Field(default_factory=uuid4)
    query_run_id: UUID
    detector_version: str = Field(min_length=1)
    anomaly: bool
    signals: tuple[DetectionSignal, ...] = ()
    evidence_ids: tuple[UUID, ...] = ()
    severity: Literal["none", "low", "medium", "high"] = "none"
    confidence: float = Field(ge=0, le=1)
    evidence_gaps: tuple[str, ...] = ()


class RootCause(FrozenContract):
    """One evidence-bound candidate cause."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    explanation: str = Field(min_length=1, max_length=2_000)
    inference_kind: InferenceKind
    evidence_ids: tuple[UUID, ...]
    confidence: float = Field(ge=0, le=1)


class Diagnosis(FrozenContract):
    """Structured diagnosis that cannot replace engine facts."""

    schema_version: Literal[1] = 1
    diagnosis_id: UUID = Field(default_factory=uuid4)
    query_run_id: UUID
    source: DiagnosisSource
    causes: tuple[RootCause, ...]
    uncertainty: tuple[str, ...] = ()
    evidence_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_id: str | None = Field(default=None, max_length=256)
    prompt_version: str | None = Field(default=None, max_length=128)


class Recommendation(FrozenContract):
    """A review-only recommendation with no execution authority."""

    schema_version: Literal[1] = 1
    recommendation_id: UUID = Field(default_factory=uuid4)
    diagnosis_id: UUID
    actionable: Literal[False] = False
    content: str = Field(min_length=1, max_length=4_000)
    prerequisites: tuple[str, ...] = ()
    risk: str = Field(min_length=1, max_length=1_000)
    expected_benefit: str = Field(min_length=1, max_length=1_000)
    verification: str = Field(min_length=1, max_length=2_000)


class AgentBudget(FrozenContract):
    """Small shared limits for one read-only investigation."""

    max_evidence_items: int = Field(default=12, ge=1, le=12)
    max_model_calls: int = Field(default=1, ge=0, le=1)
    deadline_seconds: int = Field(default=30, ge=1, le=300)


class InvestigationRequest(FrozenContract):
    """One bounded request handled by the single Coordinator."""

    schema_version: Literal[1] = 1
    investigation_id: UUID = Field(default_factory=uuid4)
    cluster_ids: tuple[str, ...]
    window_start: datetime
    window_end: datetime
    budget: AgentBudget = Field(default_factory=AgentBudget)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_request(self) -> InvestigationRequest:
        if not self.cluster_ids or len(set(self.cluster_ids)) != len(self.cluster_ids):
            raise ValueError("cluster_ids must be non-empty and unique")
        if self.window_start.tzinfo is None or self.window_end.tzinfo is None:
            raise ValueError("investigation window must be timezone-aware")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class InvestigationResult(FrozenContract):
    """Coordinator result with partial failure visibility."""

    schema_version: Literal[1] = 1
    investigation_id: UUID
    state: InvestigationState
    query_runs: tuple[QueryRun, ...]
    detections: tuple[DetectionResult, ...]
    diagnoses: tuple[Diagnosis, ...]
    recommendations: tuple[Recommendation, ...]
    errors: dict[str, str] = Field(default_factory=dict)


def content_digest(value: Any) -> str:
    """Hash a JSON-compatible value without logging its content."""

    if isinstance(value, BaseModel):
        payload = value.model_dump_json()
    else:
        from json import dumps

        payload = dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode()).hexdigest()
