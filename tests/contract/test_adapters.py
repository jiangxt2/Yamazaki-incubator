"""Shared-contract tests for the fixed ClickHouse and Doris adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from tests.conftest import make_target
from yamazaki.contracts import EngineKind
from yamazaki.engines.base import COLLECTOR_MARKER
from yamazaki.engines.clickhouse import ClickHouseAdapter
from yamazaki.engines.doris import DorisAdapter


class FakeClickHouseResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def named_results(self) -> list[dict[str, Any]]:
        return self._rows


class FakeClickHouseClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = []

    def query(
        self,
        query: str,
        *,
        parameters: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> FakeClickHouseResult:
        self.calls.append((query, parameters, settings))
        if "version()" in query:
            return FakeClickHouseResult([{"version": "25.3.2.39"}])
        if "system.columns" in query:
            return FakeClickHouseResult(
                [
                    {"table": "query_log", "name": "normalized_query_hash"},
                    {"table": "query_log", "name": "ProfileEvents"},
                    {"table": "query_log", "name": "http_user_agent"},
                    {"table": "processes", "name": "query_id"},
                ]
            )
        if "system.processes" in query:
            return FakeClickHouseResult([])
        if "WHERE query_id" in query:
            return FakeClickHouseResult(
                [
                    {
                        "query_id": "query-1",
                        "query_duration_ms": 6_000,
                        "read_rows": 100,
                        "result_rows": 1,
                        "memory_usage": 1_024,
                        "exception_code": 0,
                        "ProfileEvents": {"SelectedRows": 100},
                    }
                ]
            )
        return FakeClickHouseResult(
            [
                {
                    "event_time": datetime(2026, 1, 1, 0, 0, 6, tzinfo=UTC),
                    "query_start_time": datetime(2026, 1, 1, tzinfo=UTC),
                    "query_duration_ms": 6_000,
                    "read_rows": 100,
                    "result_rows": 1,
                    "memory_usage": 1_024,
                    "query_id": "query-1",
                    "initial_query_id": "query-1",
                    "normalized_query_hash": 123,
                    "type": "QueryFinish",
                    "exception_code": 0,
                    "query_kind": "Select",
                    "query": "SELECT secret FROM table WHERE id = 42",
                }
            ]
        )

    def close(self) -> None:
        return None


class FakeDorisExecutor:
    def __init__(
        self,
        *,
        include_required_columns: bool = True,
        state: str = "EOF",
        error_code: int = 0,
    ) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._include_required_columns = include_required_columns
        self._state = state
        self._error_code = error_code

    def query(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> list[dict[str, Any]]:
        self.calls.append((sql, parameters))
        if "VERSION()" in sql:
            return [{"version": "4.0.6"}]
        if "information_schema.columns" in sql:
            columns = ["query_id", "query_time", "stmt", "time", "user", "is_query"]
            if not self._include_required_columns:
                columns.remove("user")
            columns.extend(
                ["sql_digest", "scan_rows", "return_rows", "state", "error_code"]
            )
            return [{"column_name": column} for column in columns]
        if "SHOW PROCESSLIST" in sql:
            return []
        return [
            {
                "query_id": "doris-query-1",
                "query_time": 6_000,
                "stmt": "SELECT secret FROM customer WHERE id = 42",
                "time": datetime(2026, 1, 1),
                "user": "reader",
                "is_query": 1,
                "sql_digest": "digest-1",
                "scan_rows": 100,
                "return_rows": 1,
                "state": self._state,
                "error_code": self._error_code,
            }
        ]

    def close(self) -> None:
        return None


def test_clickhouse_adapter_preserves_native_fields_and_read_limits() -> None:
    client = FakeClickHouseClient()
    adapter = ClickHouseAdapter(
        make_target(),
        host="unused",
        port=8123,
        username="reader",
        password="test-only",
        client=client,
    )
    capability = adapter.probe_capabilities()
    records = adapter.collect_completed_queries(
        window_start=datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime(2026, 1, 2, tzinfo=UTC),
    )
    evidence = adapter.collect_query_evidence("query-1")
    assert capability.engine_version == "25.3.2.39"
    assert capability.supports_completed_queries
    assert records[0].native["normalized_query_hash"] == 123
    assert evidence.facts["duration_ms"] == 6_000
    assert all(COLLECTOR_MARKER in sql for sql, _, _ in client.calls)
    assert "http_user_agent" in client.calls[-2][0]
    assert all(
        settings and settings["readonly"] == 1 for _, _, settings in client.calls
    )
    assert all(
        settings and settings["max_result_rows"] == 1_000
        for _, _, settings in client.calls
    )


def test_doris_adapter_uses_allowlisted_columns_and_profile_path() -> None:
    executor = FakeDorisExecutor()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/capability-probe"):
            return httpx.Response(404)
        assert request.url.path.endswith("/doris-query-1")
        return httpx.Response(200, json={"data": {"profile": "bounded"}})

    http = httpx.Client(
        base_url="http://unused",
        transport=httpx.MockTransport(handler),
    )
    adapter = DorisAdapter(
        make_target(EngineKind.DORIS),
        host="unused",
        sql_port=9030,
        http_port=8030,
        username="reader",
        password="test-only",
        executor=executor,
        http_client=http,
    )
    capability = adapter.probe_capabilities()
    records = adapter.collect_completed_queries(
        window_start=datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime(2026, 1, 2, tzinfo=UTC),
    )
    evidence = adapter.collect_query_evidence("doris-query-1")
    assert capability.supports_completed_queries
    assert records[0].native["sql_digest"] == "digest-1"
    assert records[0].state.value == "succeeded"
    assert evidence.available
    assert all(COLLECTOR_MARKER in sql for sql, _ in executor.calls)


def test_doris_adapter_fails_closed_when_required_audit_column_is_missing() -> None:
    executor = FakeDorisExecutor(include_required_columns=False)
    http = httpx.Client(
        base_url="http://unused",
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
    )
    adapter = DorisAdapter(
        make_target(EngineKind.DORIS),
        host="unused",
        sql_port=9030,
        http_port=8030,
        username="reader",
        password="test-only",
        executor=executor,
        http_client=http,
    )
    capability = adapter.probe_capabilities()
    assert not capability.supports_completed_queries
    assert "user" in capability.missing_capabilities
    assert (
        adapter.collect_completed_queries(
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 1, 2, tzinfo=UTC),
        )
        == ()
    )


def test_doris_profile_rejects_arbitrary_path_input() -> None:
    adapter = DorisAdapter(
        make_target(EngineKind.DORIS),
        host="unused",
        sql_port=9030,
        http_port=8030,
        username="reader",
        password="test-only",
        executor=FakeDorisExecutor(),
        http_client=httpx.Client(base_url="http://unused"),
    )
    try:
        adapter.collect_query_evidence("../../admin")
    except ValueError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("arbitrary profile path must be rejected")


def test_doris_profile_http_failure_becomes_unavailable_evidence() -> None:
    http = httpx.Client(
        base_url="http://unused",
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    adapter = DorisAdapter(
        make_target(EngineKind.DORIS),
        host="unused",
        sql_port=9030,
        http_port=8030,
        username="reader",
        password="test-only",
        executor=FakeDorisExecutor(),
        http_client=http,
    )
    evidence = adapter.collect_query_evidence("doris-query-1")
    assert not evidence.available
    assert evidence.gap == "profile_http_503"


def test_doris_adapter_marks_error_state_failed() -> None:
    adapter = DorisAdapter(
        make_target(EngineKind.DORIS),
        host="unused",
        sql_port=9030,
        http_port=8030,
        username="reader",
        password="test-only",
        executor=FakeDorisExecutor(state="ERR", error_code=1105),
        http_client=httpx.Client(base_url="http://unused"),
    )
    records = adapter.collect_completed_queries(
        window_start=datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert records[0].state.value == "failed"


def test_doris_adapter_marks_unknown_state_failed() -> None:
    adapter = DorisAdapter(
        make_target(EngineKind.DORIS),
        host="unused",
        sql_port=9030,
        http_port=8030,
        username="reader",
        password="test-only",
        executor=FakeDorisExecutor(state="UNKNOWN"),
        http_client=httpx.Client(base_url="http://unused"),
    )
    records = adapter.collect_completed_queries(
        window_start=datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert records[0].state.value == "failed"
