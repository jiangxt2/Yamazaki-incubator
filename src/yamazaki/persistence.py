"""SQLAlchemy control-state repository for the read-only POC."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.pool import StaticPool

from yamazaki.contracts import (
    CapabilityProfile,
    ClusterTarget,
    DetectionResult,
    Diagnosis,
    EvidenceRef,
    InvestigationRequest,
    InvestigationResult,
    QueryRun,
    Recommendation,
)

metadata = MetaData()

clusters = Table(
    "clusters",
    metadata,
    Column("cluster_id", String(64), primary_key=True),
    Column("engine", String(32), nullable=False),
    Column("payload", JSON, nullable=False),
)

capability_profiles = Table(
    "capability_profiles",
    metadata,
    Column("capability_profile_id", String(36), primary_key=True),
    Column("cluster_id", ForeignKey("clusters.cluster_id"), nullable=False, index=True),
    Column("captured_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
)

query_runs = Table(
    "query_runs",
    metadata,
    Column("query_run_id", String(36), primary_key=True),
    Column("engine", String(32), nullable=False),
    Column("cluster_id", ForeignKey("clusters.cluster_id"), nullable=False, index=True),
    Column("engine_query_id", String(256), nullable=False),
    Column("native_fingerprint", String(256), nullable=False, index=True),
    Column("started_at", DateTime(timezone=True), nullable=False, index=True),
    Column("payload", JSON, nullable=False),
    UniqueConstraint(
        "engine",
        "cluster_id",
        "engine_query_id",
        "started_at",
        name="uq_query_execution_attempt",
    ),
)

evidence_refs = Table(
    "evidence_refs",
    metadata,
    Column("evidence_id", String(36), primary_key=True),
    Column(
        "query_run_id",
        ForeignKey("query_runs.query_run_id"),
        nullable=False,
        index=True,
    ),
    Column("source_kind", String(128), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("payload", JSON, nullable=False),
    UniqueConstraint(
        "query_run_id",
        "source_kind",
        "content_hash",
        name="uq_query_evidence_content",
    ),
)

detections = Table(
    "detections",
    metadata,
    Column("detection_id", String(36), primary_key=True),
    Column(
        "query_run_id",
        ForeignKey("query_runs.query_run_id"),
        nullable=False,
        index=True,
    ),
    Column("payload", JSON, nullable=False),
)

diagnoses = Table(
    "diagnoses",
    metadata,
    Column("diagnosis_id", String(36), primary_key=True),
    Column(
        "query_run_id",
        ForeignKey("query_runs.query_run_id"),
        nullable=False,
        index=True,
    ),
    Column("source", String(32), nullable=False),
    Column("payload", JSON, nullable=False),
)

recommendations = Table(
    "recommendations",
    metadata,
    Column("recommendation_id", String(36), primary_key=True),
    Column(
        "diagnosis_id", ForeignKey("diagnoses.diagnosis_id"), nullable=False, index=True
    ),
    Column("payload", JSON, nullable=False),
)

investigations = Table(
    "investigations",
    metadata,
    Column("investigation_id", String(36), primary_key=True),
    Column("state", String(32), nullable=False),
    Column("request_payload", JSON, nullable=False),
    Column("result_payload", JSON, nullable=True),
    Column("version", Integer, nullable=False, default=0),
)


class ControlStateRepository:
    """Persist current POC state without storing raw SQL or credentials."""

    def __init__(
        self, database_url: str, *, create_schema_for_tests: bool = False
    ) -> None:
        options: dict[str, Any] = {"pool_pre_ping": True}
        if database_url == "sqlite+pysqlite:///:memory:":
            options.update(
                {
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                }
            )
        self._engine = create_engine(database_url, **options)
        if create_schema_for_tests:
            metadata.create_all(self._engine)

    @property
    def engine(self) -> Engine:
        return self._engine

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        with self._engine.begin() as connection:
            yield connection

    def save_cluster(self, target: ClusterTarget) -> None:
        payload = target.model_dump(mode="json")
        with self._connection() as connection:
            existing = connection.execute(
                select(clusters.c.cluster_id).where(
                    clusters.c.cluster_id == target.cluster_id
                )
            ).first()
            if existing is None:
                connection.execute(
                    insert(clusters).values(
                        cluster_id=target.cluster_id,
                        engine=target.engine,
                        payload=payload,
                    )
                )
            else:
                connection.execute(
                    update(clusters)
                    .where(clusters.c.cluster_id == target.cluster_id)
                    .values(engine=target.engine, payload=payload)
                )

    def save_capability(self, profile: CapabilityProfile) -> None:
        self._insert_once(
            capability_profiles,
            "capability_profile_id",
            str(profile.capability_profile_id),
            {
                "capability_profile_id": str(profile.capability_profile_id),
                "cluster_id": profile.cluster_id,
                "captured_at": profile.captured_at,
                "payload": profile.model_dump(mode="json"),
            },
        )

    def save_query_run(self, query: QueryRun) -> QueryRun:
        payload = query.model_dump(mode="json")
        with self._connection() as connection:
            existing = connection.execute(
                select(query_runs.c.payload).where(
                    query_runs.c.query_run_id == str(query.query_run_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _load_contract(QueryRun, existing)
            connection.execute(
                insert(query_runs).values(
                    query_run_id=str(query.query_run_id),
                    engine=query.engine,
                    cluster_id=query.cluster_id,
                    engine_query_id=query.engine_query_id,
                    native_fingerprint=query.native_fingerprint,
                    started_at=query.started_at,
                    payload=payload,
                )
            )
        return query

    def list_query_history(
        self, query: QueryRun, limit: int = 100
    ) -> tuple[QueryRun, ...]:
        statement = (
            select(query_runs.c.payload)
            .where(query_runs.c.cluster_id == query.cluster_id)
            .where(query_runs.c.native_fingerprint == query.native_fingerprint)
            .order_by(query_runs.c.started_at.desc())
            .limit(limit)
        )
        with self._connection() as connection:
            return tuple(
                _load_contract(QueryRun, payload)
                for payload in connection.execute(statement).scalars()
            )

    def save_evidence(self, evidence: EvidenceRef) -> EvidenceRef:
        payload = evidence.model_dump(mode="json")
        with self._connection() as connection:
            existing = connection.execute(
                select(evidence_refs.c.payload).where(
                    evidence_refs.c.evidence_id == str(evidence.evidence_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _load_contract(EvidenceRef, existing)
            connection.execute(
                insert(evidence_refs).values(
                    evidence_id=str(evidence.evidence_id),
                    query_run_id=str(evidence.query_run_id),
                    source_kind=evidence.source_kind,
                    content_hash=evidence.content_hash,
                    payload=payload,
                )
            )
        return evidence

    def save_detection(self, detection: DetectionResult) -> None:
        self._insert_once(
            detections,
            "detection_id",
            str(detection.detection_id),
            {
                "detection_id": str(detection.detection_id),
                "query_run_id": str(detection.query_run_id),
                "payload": detection.model_dump(mode="json"),
            },
        )

    def save_diagnosis(self, diagnosis: Diagnosis) -> None:
        self._insert_once(
            diagnoses,
            "diagnosis_id",
            str(diagnosis.diagnosis_id),
            {
                "diagnosis_id": str(diagnosis.diagnosis_id),
                "query_run_id": str(diagnosis.query_run_id),
                "source": diagnosis.source,
                "payload": diagnosis.model_dump(mode="json"),
            },
        )

    def save_recommendation(self, recommendation: Recommendation) -> None:
        self._insert_once(
            recommendations,
            "recommendation_id",
            str(recommendation.recommendation_id),
            {
                "recommendation_id": str(recommendation.recommendation_id),
                "diagnosis_id": str(recommendation.diagnosis_id),
                "payload": recommendation.model_dump(mode="json"),
            },
        )

    def save_investigation(
        self,
        request: InvestigationRequest,
        result: InvestigationResult | None = None,
    ) -> None:
        identifier = str(request.investigation_id)
        state = result.state if result is not None else "running"
        result_payload = result.model_dump(mode="json") if result is not None else None
        with self._connection() as connection:
            existing = connection.execute(
                select(investigations.c.version).where(
                    investigations.c.investigation_id == identifier
                )
            ).scalar_one_or_none()
            if existing is None:
                connection.execute(
                    insert(investigations).values(
                        investigation_id=identifier,
                        state=state,
                        request_payload=request.model_dump(mode="json"),
                        result_payload=result_payload,
                        version=0,
                    )
                )
            else:
                connection.execute(
                    update(investigations)
                    .where(investigations.c.investigation_id == identifier)
                    .values(
                        state=state,
                        result_payload=result_payload,
                        version=int(existing) + 1,
                    )
                )

    def list_clusters(self) -> tuple[ClusterTarget, ...]:
        return self._list(clusters, ClusterTarget, limit=1_000)

    def list_query_runs(self, limit: int = 100) -> tuple[QueryRun, ...]:
        return self._list(query_runs, QueryRun, limit=limit)

    def list_detections(self, limit: int = 100) -> tuple[DetectionResult, ...]:
        return self._list(detections, DetectionResult, limit=limit)

    def list_diagnoses(self, limit: int = 100) -> tuple[Diagnosis, ...]:
        return self._list(diagnoses, Diagnosis, limit=limit)

    def clear_for_tests(self) -> None:
        """Remove only records from an isolated test database."""

        with self._connection() as connection:
            for table in (
                recommendations,
                diagnoses,
                detections,
                evidence_refs,
                query_runs,
                capability_profiles,
                investigations,
                clusters,
            ):
                connection.execute(delete(table))

    def close(self) -> None:
        self._engine.dispose()

    def _insert_once(
        self,
        table: Table,
        key_name: str,
        key_value: str,
        values: dict[str, Any],
    ) -> None:
        key = table.c[key_name]
        with self._connection() as connection:
            if connection.execute(select(key).where(key == key_value)).first() is None:
                connection.execute(insert(table).values(**values))

    def _list[ModelT: BaseModel](
        self,
        table: Table,
        model: type[ModelT],
        *,
        limit: int,
    ) -> tuple[ModelT, ...]:
        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        statement = select(table.c.payload).limit(limit)
        with self._connection() as connection:
            return tuple(
                _load_contract(model, value)
                for value in connection.execute(statement).scalars()
            )


def _load_contract[ModelT: BaseModel](
    model: type[ModelT],
    payload: object,
) -> ModelT:
    """Validate JSON storage through Pydantic's strict JSON mode."""

    return model.model_validate_json(json.dumps(payload, default=str))
