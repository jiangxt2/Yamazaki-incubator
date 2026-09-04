"""Fixed read-only ClickHouse evidence adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from yamazaki.contracts import CapabilityProfile, ClusterTarget, EngineKind, QueryState
from yamazaki.engines.base import COLLECTOR_MARKER, RawEvidence, RawQueryRecord

_CAPABILITY_SQL = f"""
SELECT database, table, name
FROM system.columns
WHERE database = 'system' AND table IN ('query_log', 'processes')
/* {COLLECTOR_MARKER} */
""".strip()

_RUNNING_SQL = f"""
SELECT query_id, initial_query_id, normalized_query_hash, query_kind, query,
       elapsed, read_rows, memory_usage
FROM system.processes
WHERE user = currentUser()
  AND positionCaseInsensitive(query, '{COLLECTOR_MARKER}') = 0
LIMIT {{limit:UInt32}}
/* {COLLECTOR_MARKER} */
""".strip()

_COMPLETED_SQL = f"""
SELECT event_time, query_start_time, query_duration_ms, read_rows, result_rows,
       memory_usage, query_id, initial_query_id, normalized_query_hash, type,
       exception_code, query_kind, query
FROM system.query_log
WHERE event_time >= {{window_start:DateTime64(3)}}
  AND event_time <= {{window_end:DateTime64(3)}}
  AND user = currentUser()
  AND type != 'QueryStart'
  AND query_kind = 'Select'
  AND positionCaseInsensitive(query, '{COLLECTOR_MARKER}') = 0
  AND positionCaseInsensitive(http_user_agent, '{COLLECTOR_MARKER}') = 0
ORDER BY event_time, query_id
LIMIT {{limit:UInt32}}
/* {COLLECTOR_MARKER} */
""".strip()


class ClickHouseClient(Protocol):
    """Small injectable surface used by contract tests."""

    def query(
        self,
        query: str,
        *,
        parameters: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> Any: ...

    def close(self) -> None: ...


class ClickHouseAdapter:
    """Collect ClickHouse facts without accepting arbitrary SQL."""

    def __init__(
        self,
        target: ClusterTarget,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str = "default",
        secure: bool = False,
        client: ClickHouseClient | None = None,
    ) -> None:
        if target.engine is not EngineKind.CLICKHOUSE:
            raise ValueError("ClickHouseAdapter requires a ClickHouse target")
        self._target = target
        if client is None:
            import clickhouse_connect

            client = clickhouse_connect.get_client(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                secure=secure,
                client_name=COLLECTOR_MARKER,
                connect_timeout=10,
                send_receive_timeout=10,
            )
        self._client = client
        self._settings: dict[str, Any] = {
            "readonly": 1,
            "max_execution_time": 10,
            "max_result_rows": 1_000,
            "result_overflow_mode": "break",
        }

    @property
    def target(self) -> ClusterTarget:
        return self._target

    def probe_capabilities(self) -> CapabilityProfile:
        version_rows = self._rows(
            f"SELECT version() AS version /* {COLLECTOR_MARKER} */"
        )
        version = str(version_rows[0]["version"])
        columns = self._rows(_CAPABILITY_SQL)
        names = {(str(row["table"]), str(row["name"])) for row in columns}
        query_log = any(table == "query_log" for table, _ in names)
        processes = any(table == "processes" for table, _ in names)
        native_fingerprint = ("query_log", "normalized_query_hash") in names
        collector_identity = ("query_log", "http_user_agent") in names
        missing: list[str] = []
        if not query_log:
            missing.append("system.query_log")
        if not processes:
            missing.append("system.processes")
        if not native_fingerprint:
            missing.append("normalized_query_hash")
        if not collector_identity:
            missing.append("http_user_agent")
        return CapabilityProfile(
            cluster_id=self.target.cluster_id,
            engine=EngineKind.CLICKHOUSE,
            engine_version=version,
            supports_running_queries=processes,
            supports_completed_queries=query_log and collector_identity,
            supports_native_fingerprint=native_fingerprint,
            supports_profile=("query_log", "ProfileEvents") in names,
            missing_capabilities=tuple(missing),
        )

    def collect_running_queries(self, limit: int = 1_000) -> tuple[RawQueryRecord, ...]:
        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        now = datetime.now(UTC)
        records: list[RawQueryRecord] = []
        for row in self._rows(_RUNNING_SQL, parameters={"limit": limit}):
            elapsed = float(row.get("elapsed") or 0)
            records.append(
                RawQueryRecord(
                    engine=EngineKind.CLICKHOUSE,
                    cluster_id=self.target.cluster_id,
                    query_id=str(row["query_id"]),
                    fingerprint=_optional_string(row.get("normalized_query_hash")),
                    state=QueryState.RUNNING,
                    started_at=now - timedelta(seconds=elapsed),
                    finished_at=None,
                    observed_at=now,
                    duration_ms=max(0, round(elapsed * 1_000)),
                    peak_memory_bytes=_optional_int(row.get("memory_usage")),
                    scanned_rows=_optional_int(row.get("read_rows")),
                    progress=None,
                    raw_sql=_optional_string(row.get("query")),
                    native={
                        "initial_query_id": row.get("initial_query_id"),
                        "normalized_query_hash": row.get("normalized_query_hash"),
                        "query_kind": row.get("query_kind"),
                    },
                )
            )
        return tuple(records)

    def collect_completed_queries(
        self,
        *,
        window_start: object,
        window_end: object,
        limit: int = 1_000,
    ) -> tuple[RawQueryRecord, ...]:
        if not isinstance(window_start, datetime) or not isinstance(
            window_end, datetime
        ):
            raise TypeError("ClickHouse collection windows must be datetimes")
        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self._rows(
            _COMPLETED_SQL,
            parameters={
                "window_start": window_start,
                "window_end": window_end,
                "limit": limit,
            },
        )
        records: list[RawQueryRecord] = []
        for row in rows:
            started_at = _datetime(row["query_start_time"])
            finished_at = _datetime(row["event_time"])
            failed = int(row.get("exception_code") or 0) != 0 or "Exception" in str(
                row.get("type") or ""
            )
            records.append(
                RawQueryRecord(
                    engine=EngineKind.CLICKHOUSE,
                    cluster_id=self.target.cluster_id,
                    query_id=str(row["query_id"]),
                    fingerprint=_optional_string(row.get("normalized_query_hash")),
                    state=QueryState.FAILED if failed else QueryState.SUCCEEDED,
                    started_at=started_at,
                    finished_at=finished_at,
                    observed_at=datetime.now(UTC),
                    duration_ms=max(0, int(row.get("query_duration_ms") or 0)),
                    peak_memory_bytes=_optional_int(row.get("memory_usage")),
                    scanned_rows=_optional_int(row.get("read_rows")),
                    returned_rows=_optional_int(row.get("result_rows")),
                    raw_sql=_optional_string(row.get("query")),
                    native={
                        "initial_query_id": row.get("initial_query_id"),
                        "normalized_query_hash": row.get("normalized_query_hash"),
                        "query_kind": row.get("query_kind"),
                        "exception_code": row.get("exception_code"),
                    },
                )
            )
        return tuple(records)

    def collect_query_evidence(self, query_id: str) -> RawEvidence:
        if not query_id or len(query_id) > 256:
            raise ValueError("query_id is invalid")
        rows = self._rows(
            f"""
SELECT query_id, query_duration_ms, read_rows, result_rows, memory_usage,
       exception_code, ProfileEvents
FROM system.query_log
WHERE query_id = {{query_id:String}} AND type != 'QueryStart'
ORDER BY event_time DESC LIMIT 1
/* {COLLECTOR_MARKER} */
""".strip(),
            parameters={"query_id": query_id},
        )
        if not rows:
            return RawEvidence(
                source_kind="clickhouse_query_log",
                summary="ClickHouse Query Log evidence is unavailable.",
                facts={"query_id": query_id, "available": False},
                available=False,
                gap="query_log_record_unavailable",
            )
        row = rows[0]
        facts: dict[str, int | float | str | bool | None] = {
            "query_id": query_id,
            "duration_ms": _optional_int(row.get("query_duration_ms")),
            "read_rows": _optional_int(row.get("read_rows")),
            "result_rows": _optional_int(row.get("result_rows")),
            "memory_usage": _optional_int(row.get("memory_usage")),
            "exception_code": _optional_int(row.get("exception_code")),
        }
        return RawEvidence(
            source_kind="clickhouse_query_log",
            summary="ClickHouse Query Log resource and status evidence.",
            facts=facts,
            restricted_payload={
                "facts": facts,
                "profile_events": row.get("ProfileEvents") or {},
            },
        )

    def close(self) -> None:
        self._client.close()

    def _rows(
        self,
        sql: str,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = self._client.query(
            sql,
            parameters=parameters,
            settings=self._settings,
        )
        return [dict(row) for row in result.named_results()]


def _datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("ClickHouse timestamp must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, (str, bytes, int, float)):
        raise TypeError("ClickHouse metric must be numeric")
    return max(0, int(value))


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)
