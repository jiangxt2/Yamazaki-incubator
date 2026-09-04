"""Normalization from transient engine records to persistent safe contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from yamazaki.contracts import (
    ClickHouseIdentity,
    DorisIdentity,
    EngineKind,
    EvidenceRef,
    NativeIdentity,
    QueryRun,
    RedactionStatus,
    Sensitivity,
    content_digest,
    utc_now,
)
from yamazaki.engines.base import RawEvidence, RawQueryRecord
from yamazaki.ports import EvidenceStorePort
from yamazaki.redaction import redact_sql


def normalize_query(raw: RawQueryRecord, *, correlation_id: object) -> QueryRun:
    """Remove raw SQL and preserve the engine-native identity."""

    from uuid import UUID

    if not isinstance(correlation_id, UUID):
        raise TypeError("correlation_id must be a UUID")
    started_at = _aware(raw.started_at)
    observed_at = _aware(raw.observed_at)
    finished_at = _aware(raw.finished_at) if raw.finished_at is not None else None
    redaction = redact_sql(
        raw.raw_sql or "SELECT identifier",
        dialect="clickhouse" if raw.engine is EngineKind.CLICKHOUSE else "mysql",
    )
    fingerprint = raw.fingerprint or content_digest(
        {
            "engine": raw.engine,
            "statement_type": redaction.statement_type,
            "structure": redaction.structure,
        }
    )
    native: NativeIdentity
    if raw.engine is EngineKind.CLICKHOUSE:
        native = ClickHouseIdentity(
            query_id=raw.query_id,
            initial_query_id=_string(raw.native.get("initial_query_id")),
            normalized_query_hash=_string(raw.native.get("normalized_query_hash")),
            query_kind=_string(raw.native.get("query_kind")),
        )
    else:
        native = DorisIdentity(
            query_id=raw.query_id,
            sql_digest=_string(raw.native.get("sql_digest")),
            frontend=_string(raw.native.get("frontend")),
            workload_group=_string(raw.native.get("workload_group")),
        )
    return QueryRun(
        query_run_id=QueryRun.stable_id(
            engine=raw.engine,
            cluster_id=raw.cluster_id,
            engine_query_id=raw.query_id,
            started_at=started_at,
        ),
        engine=raw.engine,
        cluster_id=raw.cluster_id,
        engine_query_id=raw.query_id,
        native_fingerprint=str(fingerprint),
        state=raw.state,
        started_at=started_at,
        finished_at=finished_at,
        observed_at=observed_at,
        ingested_at=utc_now(),
        duration_ms=max(0, raw.duration_ms),
        queue_time_ms=raw.queue_time_ms,
        cpu_time_ms=raw.cpu_time_ms,
        peak_memory_bytes=raw.peak_memory_bytes,
        scanned_rows=raw.scanned_rows,
        returned_rows=raw.returned_rows,
        shuffle_bytes=raw.shuffle_bytes,
        spill_bytes=raw.spill_bytes,
        progress=raw.progress,
        statement_type=redaction.statement_type,
        redacted_structure=redaction.structure,
        native=native,
        correlation_id=correlation_id,
    )


def query_summary_evidence(query: QueryRun) -> EvidenceRef:
    """Create the minimum official-fact summary used by all diagnoses."""

    facts: dict[str, int | float | str | bool | None] = {
        "duration_ms": query.duration_ms,
        "queue_time_ms": query.queue_time_ms,
        "cpu_time_ms": query.cpu_time_ms,
        "peak_memory_bytes": query.peak_memory_bytes,
        "scanned_rows": query.scanned_rows,
        "returned_rows": query.returned_rows,
        "shuffle_bytes": query.shuffle_bytes,
        "spill_bytes": query.spill_bytes,
        "state": query.state,
        "native_fingerprint": query.native_fingerprint,
    }
    digest = content_digest(facts)
    return EvidenceRef(
        evidence_id=EvidenceRef.stable_id(
            query_run_id=query.query_run_id,
            source_kind="query_summary",
            content_hash=digest,
        ),
        query_run_id=query.query_run_id,
        source_kind="query_summary",
        engine=query.engine,
        summary=(
            f"{query.engine} query {query.engine_query_id} completed with state "
            f"{query.state} in {query.duration_ms} ms."
        ),
        facts=facts,
        content_hash=digest,
    )


def persist_raw_evidence(
    query: QueryRun,
    raw: RawEvidence,
    store: EvidenceStorePort,
) -> EvidenceRef:
    """Persist restricted evidence before exposing only its bounded summary."""

    digest = content_digest(raw.restricted_payload or raw.facts)
    evidence_id = EvidenceRef.stable_id(
        query_run_id=query.query_run_id,
        source_kind=raw.source_kind,
        content_hash=digest,
    )
    locator: str | None = None
    status = RedactionStatus.REDACTED
    if raw.restricted_payload:
        locator, digest = store.write(evidence_id, raw.restricted_payload)
    if not raw.available:
        status = RedactionStatus.OMITTED
    return EvidenceRef(
        evidence_id=evidence_id,
        query_run_id=query.query_run_id,
        source_kind=raw.source_kind,
        engine=query.engine,
        summary=raw.summary,
        facts=raw.facts,
        content_hash=digest,
        sensitivity=(
            Sensitivity.RESTRICTED if raw.restricted_payload else Sensitivity.INTERNAL
        ),
        storage_locator=locator,
        redaction_status=status,
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
