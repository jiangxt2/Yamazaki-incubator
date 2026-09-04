"""Shared deterministic fixtures and test adapters."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from yamazaki.contracts import (
    CapabilityProfile,
    ClickHouseIdentity,
    ClusterTarget,
    EngineKind,
    QueryRun,
    QueryState,
)
from yamazaki.engines.base import RawEvidence, RawQueryRecord
from yamazaki.evidence_store import LocalEvidenceStore
from yamazaki.persistence import ControlStateRepository


def make_target(
    engine: EngineKind = EngineKind.CLICKHOUSE,
    *,
    cluster_id: str | None = None,
) -> ClusterTarget:
    identifier = cluster_id or f"{engine.value}-poc"
    return ClusterTarget(
        cluster_id=identifier,
        engine=engine,
        display_name=f"{engine.value.title()} POC",
        environment="poc",
        credential_ref=f"env:YAMAZAKI_{engine.value.upper()}_PASSWORD",
    )


def make_query(
    *,
    duration_ms: int = 6_000,
    query_id: str = "query-1",
    fingerprint: str = "fingerprint-1",
    started_at: datetime | None = None,
    cluster_id: str = "clickhouse-poc",
    peak_memory_bytes: int | None = 1_024,
    scanned_rows: int | None = 100,
    returned_rows: int | None = 10,
    queue_time_ms: int | None = 0,
    progress: float | None = None,
    state: QueryState = QueryState.SUCCEEDED,
) -> QueryRun:
    start = started_at or datetime(2026, 1, 1, tzinfo=UTC)
    return QueryRun(
        query_run_id=QueryRun.stable_id(
            engine=EngineKind.CLICKHOUSE,
            cluster_id=cluster_id,
            engine_query_id=query_id,
            started_at=start,
        ),
        engine=EngineKind.CLICKHOUSE,
        cluster_id=cluster_id,
        engine_query_id=query_id,
        native_fingerprint=fingerprint,
        state=state,
        started_at=start,
        finished_at=(
            start + timedelta(milliseconds=duration_ms)
            if state is not QueryState.RUNNING
            else None
        ),
        observed_at=start + timedelta(milliseconds=duration_ms),
        ingested_at=start + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        queue_time_ms=queue_time_ms,
        peak_memory_bytes=peak_memory_bytes,
        scanned_rows=scanned_rows,
        returned_rows=returned_rows,
        progress=progress,
        statement_type="SELECT",
        redacted_structure="SELECT identifier FROM identifier",
        native=ClickHouseIdentity(
            query_id=query_id,
            initial_query_id=query_id,
            normalized_query_hash=fingerprint,
            query_kind="Select",
        ),
        correlation_id=uuid4(),
    )


class FakeAdapter:
    """Configurable fixed adapter used by service and replay tests."""

    def __init__(
        self,
        target: ClusterTarget,
        records: tuple[RawQueryRecord, ...],
        *,
        failure: Exception | None = None,
        evidence: RawEvidence | None = None,
    ) -> None:
        self._target = target
        self._records = records
        self._failure = failure
        self._evidence = evidence or RawEvidence(
            source_kind=f"{target.engine.value}_detail",
            summary="Bounded engine evidence.",
            facts={"available": True},
            restricted_payload={"metric": 1},
        )

    @property
    def target(self) -> ClusterTarget:
        return self._target

    def probe_capabilities(self) -> CapabilityProfile:
        if self._failure is not None:
            raise self._failure
        return CapabilityProfile(
            cluster_id=self.target.cluster_id,
            engine=self.target.engine,
            engine_version="test",
            supports_running_queries=True,
            supports_completed_queries=True,
            supports_native_fingerprint=True,
            supports_profile=True,
        )

    def collect_running_queries(self, limit: int = 1_000) -> tuple[RawQueryRecord, ...]:
        return ()

    def collect_completed_queries(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        limit: int = 1_000,
    ) -> tuple[RawQueryRecord, ...]:
        return self._records[:limit]

    def collect_query_evidence(self, query_id: str) -> RawEvidence:
        return self._evidence


@pytest.fixture
def repository() -> Iterator[ControlStateRepository]:
    value = ControlStateRepository(
        "sqlite+pysqlite:///:memory:",
        create_schema_for_tests=True,
    )
    yield value
    value.close()


@pytest.fixture
def evidence_store(tmp_path: Path) -> LocalEvidenceStore:
    return LocalEvidenceStore(tmp_path / "evidence")


@pytest.fixture
def correlation_id() -> UUID:
    return UUID("ec860264-4e87-47b5-93b4-a584a26bc054")


RawRecordFactory = Callable[..., RawQueryRecord]


@pytest.fixture
def raw_record() -> RawRecordFactory:
    def factory(
        *,
        engine: EngineKind = EngineKind.CLICKHOUSE,
        cluster_id: str | None = None,
        query_id: str = "query-1",
        duration_ms: int = 6_000,
        fingerprint: str | None = "fingerprint-1",
        raw_sql: str = "SELECT count(*) FROM private.events WHERE id = 42",
    ) -> RawQueryRecord:
        started = datetime(2026, 1, 1, tzinfo=UTC)
        return RawQueryRecord(
            engine=engine,
            cluster_id=cluster_id or f"{engine.value}-poc",
            query_id=query_id,
            fingerprint=fingerprint,
            state=QueryState.SUCCEEDED,
            started_at=started,
            finished_at=started + timedelta(milliseconds=duration_ms),
            observed_at=started + timedelta(milliseconds=duration_ms),
            duration_ms=duration_ms,
            queue_time_ms=0,
            peak_memory_bytes=1_024,
            scanned_rows=100,
            returned_rows=10,
            raw_sql=raw_sql,
            native=(
                {
                    "initial_query_id": query_id,
                    "normalized_query_hash": fingerprint,
                    "query_kind": "Select",
                }
                if engine is EngineKind.CLICKHOUSE
                else {
                    "sql_digest": fingerprint,
                    "frontend": "fe-test",
                    "workload_group": "normal",
                }
            ),
        )

    return factory
