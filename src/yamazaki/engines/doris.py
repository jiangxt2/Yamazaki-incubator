"""Fixed read-only Apache Doris evidence adapter."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
import pymysql
from pymysql.cursors import DictCursor

from yamazaki.contracts import CapabilityProfile, ClusterTarget, EngineKind, QueryState
from yamazaki.engines.base import COLLECTOR_MARKER, RawEvidence, RawQueryRecord

_QUERY_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_PROFILE_PREFIX = "/rest/v2/manager/query/profile/json/"

_AUDIT_COLUMNS_SQL = f"""
SELECT column_name
FROM information_schema.columns
WHERE table_schema = '__internal_schema' AND table_name = 'audit_log'
/* {COLLECTOR_MARKER} */
""".strip()

_REQUIRED_AUDIT_COLUMNS = frozenset(
    {"query_id", "query_time", "stmt", "time", "user", "is_query"}
)
_OPTIONAL_AUDIT_COLUMNS = (
    "sql_digest",
    "error_code",
    "scan_rows",
    "return_rows",
    "cpu_time_ms",
    "peak_memory_bytes",
    "shuffle_bytes",
    "spill_bytes",
    "state",
    "frontend_ip",
    "workload_group",
)


class DorisSqlExecutor(Protocol):
    def query(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


class PyMySqlExecutor:
    """Small synchronous executor with one connection per read operation."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._database = database

    def query(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> list[dict[str, Any]]:
        connection = pymysql.connect(
            host=self._host,
            port=self._port,
            user=self._username,
            password=self._password,
            database=self._database,
            connect_timeout=10,
            read_timeout=10,
            write_timeout=10,
            cursorclass=DictCursor,
            autocommit=True,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, parameters)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        finally:
            connection.close()

    def close(self) -> None:
        return None


class DorisAdapter:
    """Collect Doris Audit/Profile facts through fixed SQL and URL prefixes."""

    def __init__(
        self,
        target: ClusterTarget,
        *,
        host: str,
        sql_port: int,
        http_port: int,
        username: str,
        password: str,
        database: str = "information_schema",
        executor: DorisSqlExecutor | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if target.engine is not EngineKind.DORIS:
            raise ValueError("DorisAdapter requires a Doris target")
        self._target = target
        self._username = username
        self._executor = executor or PyMySqlExecutor(
            host=host,
            port=sql_port,
            username=username,
            password=password,
            database=database,
        )
        self._http = http_client or httpx.Client(
            base_url=f"http://{host}:{http_port}",
            auth=(username, password),
            timeout=10,
        )
        self._owns_http = http_client is None
        self._audit_columns: frozenset[str] = frozenset()

    @property
    def target(self) -> ClusterTarget:
        return self._target

    def probe_capabilities(self) -> CapabilityProfile:
        version_rows = self._executor.query(
            f"SELECT VERSION() AS version /* {COLLECTOR_MARKER} */"
        )
        version = str(version_rows[0]["version"])
        columns = self._executor.query(_AUDIT_COLUMNS_SQL)
        self._audit_columns = frozenset(
            str(row.get("column_name") or row.get("COLUMN_NAME") or "").lower()
            for row in columns
        )
        missing = sorted(_REQUIRED_AUDIT_COLUMNS - self._audit_columns)
        processlist_available = True
        try:
            self._executor.query(f"SHOW PROCESSLIST /* {COLLECTOR_MARKER} */")
        except Exception:
            processlist_available = False
            missing.append("show_processlist")
        profile_available = self._profile_endpoint_available()
        if not profile_available:
            missing.append("query_profile_http")
        return CapabilityProfile(
            cluster_id=self.target.cluster_id,
            engine=EngineKind.DORIS,
            engine_version=version,
            supports_running_queries=processlist_available,
            supports_completed_queries=not bool(
                _REQUIRED_AUDIT_COLUMNS - self._audit_columns
            ),
            supports_native_fingerprint="sql_digest" in self._audit_columns,
            supports_profile=profile_available,
            missing_capabilities=tuple(missing),
        )

    def collect_running_queries(self, limit: int = 1_000) -> tuple[RawQueryRecord, ...]:
        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self._executor.query(f"SHOW PROCESSLIST /* {COLLECTOR_MARKER} */")
        now = datetime.now(UTC)
        records: list[RawQueryRecord] = []
        for original in rows[:limit]:
            row = {str(key).lower(): value for key, value in original.items()}
            if str(row.get("user") or "") != self._username:
                continue
            statement = str(row.get("info") or "")
            if not statement or COLLECTOR_MARKER.lower() in statement.lower():
                continue
            elapsed_seconds = int(row.get("time") or 0)
            query_id = str(row.get("queryid") or row.get("query_id") or row.get("id"))
            records.append(
                RawQueryRecord(
                    engine=EngineKind.DORIS,
                    cluster_id=self.target.cluster_id,
                    query_id=query_id,
                    fingerprint=None,
                    state=QueryState.RUNNING,
                    started_at=now - timedelta(seconds=elapsed_seconds),
                    finished_at=None,
                    observed_at=now,
                    duration_ms=max(0, elapsed_seconds * 1_000),
                    raw_sql=statement,
                    native={
                        "frontend": row.get("frontend"),
                        "workload_group": row.get("workloadgroup"),
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
            raise TypeError("Doris collection windows must be datetimes")
        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        if not self._audit_columns:
            self.probe_capabilities()
        missing = _REQUIRED_AUDIT_COLUMNS - self._audit_columns
        if missing:
            return ()
        selected = [*_REQUIRED_AUDIT_COLUMNS]
        selected.extend(
            column
            for column in _OPTIONAL_AUDIT_COLUMNS
            if column in self._audit_columns
        )
        columns = ", ".join(f"`{column}`" for column in sorted(selected))
        sql = f"""
SELECT {columns}
FROM __internal_schema.audit_log
WHERE `time` >= %s AND `time` <= %s
  AND `user` = %s AND `is_query` = 1
  AND LOWER(`stmt`) NOT LIKE %s
ORDER BY `time`, `query_id`
LIMIT {int(limit)}
/* {COLLECTOR_MARKER} */
""".strip()
        rows = self._executor.query(
            sql,
            (
                window_start.replace(tzinfo=None),
                window_end.replace(tzinfo=None),
                self._username,
                f"%{COLLECTOR_MARKER.lower()}%",
            ),
        )
        records: list[RawQueryRecord] = []
        for original in rows:
            row = {str(key).lower(): value for key, value in original.items()}
            started_at = _datetime(row["time"])
            duration_ms = max(0, int(row.get("query_time") or 0))
            state = str(row.get("state") or "").upper()
            error_code = _optional_int(row.get("error_code")) or 0
            failed = error_code != 0 or state not in {
                "OK",
                "EOF",
                "FINISHED",
                "SUCCESS",
            }
            records.append(
                RawQueryRecord(
                    engine=EngineKind.DORIS,
                    cluster_id=self.target.cluster_id,
                    query_id=str(row["query_id"]),
                    fingerprint=_optional_string(row.get("sql_digest")),
                    state=QueryState.FAILED if failed else QueryState.SUCCEEDED,
                    started_at=started_at,
                    finished_at=started_at + timedelta(milliseconds=duration_ms),
                    observed_at=datetime.now(UTC),
                    duration_ms=duration_ms,
                    cpu_time_ms=_optional_int(row.get("cpu_time_ms")),
                    peak_memory_bytes=_optional_int(row.get("peak_memory_bytes")),
                    scanned_rows=_optional_int(row.get("scan_rows")),
                    returned_rows=_optional_int(row.get("return_rows")),
                    shuffle_bytes=_optional_int(row.get("shuffle_bytes")),
                    spill_bytes=_optional_int(row.get("spill_bytes")),
                    raw_sql=_optional_string(row.get("stmt")),
                    native={
                        "sql_digest": row.get("sql_digest"),
                        "frontend": row.get("frontend_ip"),
                        "workload_group": row.get("workload_group"),
                        "error_code": row.get("error_code"),
                    },
                )
            )
        return tuple(records)

    def collect_query_evidence(self, query_id: str) -> RawEvidence:
        if not _QUERY_ID.fullmatch(query_id):
            raise ValueError("query_id is invalid")
        path = f"{_PROFILE_PREFIX}{query_id}"
        if not path.startswith(_PROFILE_PREFIX):
            raise ValueError("profile URL is not allowed")
        try:
            response = self._http.get(path)
        except httpx.HTTPError:
            return RawEvidence(
                source_kind="doris_profile",
                summary="Doris profile evidence could not be reached.",
                facts={"query_id": query_id, "available": False},
                available=False,
                gap="profile_http_unavailable",
            )
        if response.status_code == 404:
            return RawEvidence(
                source_kind="doris_profile",
                summary="Doris profile evidence is unavailable.",
                facts={"query_id": query_id, "available": False},
                available=False,
                gap="profile_unavailable",
            )
        if response.status_code != 200:
            return RawEvidence(
                source_kind="doris_profile",
                summary="Doris profile evidence was rejected by the endpoint.",
                facts={
                    "query_id": query_id,
                    "available": False,
                    "status_code": response.status_code,
                },
                available=False,
                gap=f"profile_http_{response.status_code}",
            )
        if len(response.content) > 2 * 1024 * 1024:
            return RawEvidence(
                source_kind="doris_profile",
                summary="Doris profile evidence exceeded the POC size limit.",
                facts={"query_id": query_id, "available": False},
                available=False,
                gap="profile_response_too_large",
            )
        try:
            payload = response.json()
        except ValueError:
            return RawEvidence(
                source_kind="doris_profile",
                summary="Doris profile evidence was not valid JSON.",
                facts={"query_id": query_id, "available": False},
                available=False,
                gap="profile_invalid_json",
            )
        return RawEvidence(
            source_kind="doris_profile",
            summary="Doris profile endpoint returned evidence for the query.",
            facts={"query_id": query_id, "available": True},
            restricted_payload={"query_id": query_id, "profile": payload},
        )

    def close(self) -> None:
        self._executor.close()
        if self._owns_http:
            self._http.close()

    def _profile_endpoint_available(self) -> bool:
        """Check the fixed profile route without requiring a real query id."""

        try:
            response = self._http.get(f"{_PROFILE_PREFIX}capability-probe")
        except httpx.HTTPError:
            return False
        return response.status_code in {200, 404}


def _datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("Doris timestamp must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, (str, bytes, int, float)):
        raise TypeError("Doris metric must be numeric")
    return max(0, int(value))


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)
