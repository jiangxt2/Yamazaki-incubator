"""One real-infrastructure Gate for PostgreSQL, ClickHouse, and Doris."""

from __future__ import annotations

import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import clickhouse_connect
import pymysql
import pytest
from clickhouse_connect.driver.exceptions import ClickHouseError

from yamazaki.contracts import (
    ClusterTarget,
    EngineKind,
    InvestigationRequest,
    QueryState,
)
from yamazaki.engines.clickhouse import ClickHouseAdapter
from yamazaki.engines.doris import DorisAdapter
from yamazaki.evidence_store import LocalEvidenceStore
from yamazaki.persistence import ControlStateRepository
from yamazaki.service import YamazakiCoordinator

pytestmark = pytest.mark.integration
_SAFE_SECRET = re.compile(r"^[0-9a-f]{48}$")


def _clickhouse_admin() -> Any:
    return clickhouse_connect.get_client(
        host="127.0.0.1",
        port=18124,
        username="admin",
        password=os.environ["YAMAZAKI_IT_CLICKHOUSE_ADMIN_PASSWORD"],
    )


def _doris_connection(*, user: str, password: str) -> Any:
    return pymysql.connect(
        host="127.0.0.1",
        port=19031,
        user=user,
        password=password,
        connect_timeout=10,
        read_timeout=15,
        write_timeout=15,
        autocommit=True,
    )


def _seed_clickhouse() -> str:
    reader_password = os.environ["YAMAZAKI_IT_CLICKHOUSE_READER_PASSWORD"]
    assert _SAFE_SECRET.fullmatch(reader_password)
    admin = _clickhouse_admin()
    try:
        admin.command("CREATE DATABASE IF NOT EXISTS yamazaki_it")
        admin.command(
            """
CREATE TABLE yamazaki_it.events (id UInt64, value String)
ENGINE = MergeTree ORDER BY id
"""
        )
        admin.command(
            "INSERT INTO yamazaki_it.events "
            "SELECT number, toString(number) FROM numbers(100000)"
        )
        admin.command(
            "CREATE USER yamazaki_reader IDENTIFIED WITH sha256_password BY "
            f"'{reader_password}' SETTINGS readonly = 1, max_execution_time = 10, "
            "max_result_rows = 1000, result_overflow_mode = 'break', "
            "max_block_size = 100"
        )
        admin.command("GRANT SELECT ON system.* TO yamazaki_reader")
        admin.command("GRANT SELECT ON yamazaki_it.* TO yamazaki_reader")
    finally:
        admin.close()

    reader = clickhouse_connect.get_client(
        host="127.0.0.1",
        port=18124,
        username="yamazaki_reader",
        password=reader_password,
    )
    try:
        for _ in range(6):
            reader.query(
                "SELECT count() FROM yamazaki_it.events /* yamazaki-it-fast */"
            )
        started = time.monotonic()
        reader.query(
            "SELECT sum(sleepEachRow(0.006)) FROM numbers(1000) /* yamazaki-it-slow */",
            settings={"max_execution_time": 10},
        )
        assert time.monotonic() - started >= 5.5
        with pytest.raises(ClickHouseError):
            reader.command("DROP TABLE yamazaki_it.events")
    finally:
        reader.close()
    admin = _clickhouse_admin()
    try:
        admin.command("SYSTEM FLUSH LOGS")
    finally:
        admin.close()
    return reader_password


def _seed_doris() -> str:
    reader_password = os.environ["YAMAZAKI_IT_DORIS_READER_PASSWORD"]
    assert _SAFE_SECRET.fullmatch(reader_password)
    admin = _doris_connection(user="root", password="")
    try:
        with admin.cursor() as cursor:
            cursor.execute("SET GLOBAL enable_audit_plugin = true")
            cursor.execute("SET GLOBAL audit_plugin_max_batch_interval_sec = 1")
            cursor.execute("CREATE DATABASE IF NOT EXISTS yamazaki_it")
            cursor.execute(
                """
CREATE TABLE yamazaki_it.events (
  id BIGINT,
  value VARCHAR(32)
)
DUPLICATE KEY(id)
DISTRIBUTED BY HASH(id) BUCKETS 1
PROPERTIES ('replication_num' = '1')
"""
            )
            cursor.execute(
                "INSERT INTO yamazaki_it.events VALUES (1, 'a'), (2, 'b'), (3, 'c')"
            )
            cursor.execute(
                f"CREATE USER 'yamazaki_reader' IDENTIFIED BY '{reader_password}'"
            )
            cursor.execute("GRANT SELECT_PRIV ON *.* TO 'yamazaki_reader'")
    finally:
        admin.close()

    reader = _doris_connection(user="yamazaki_reader", password=reader_password)
    try:
        with reader.cursor() as cursor:
            for _ in range(6):
                cursor.execute(
                    "SELECT count(*) FROM yamazaki_it.events /* yamazaki-it-fast */"
                )
                cursor.fetchall()
            started = time.monotonic()
            cursor.execute("SELECT SLEEP(6) /* yamazaki-it-slow */")
            cursor.fetchall()
            assert time.monotonic() - started >= 5.5
            with pytest.raises(pymysql.MySQLError):
                cursor.execute("DROP TABLE yamazaki_it.events")
    finally:
        reader.close()

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        admin = _doris_connection(user="root", password="")
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    """
SELECT COUNT(*) FROM __internal_schema.audit_log
WHERE user = 'yamazaki_reader' AND is_query = 1
  AND LOWER(stmt) LIKE '%yamazaki-it-slow%'
"""
                )
                if int(cursor.fetchone()[0]) >= 1:
                    return reader_password
        finally:
            admin.close()
        time.sleep(1)
    raise AssertionError("Doris slow-query Audit record did not become visible")


def test_real_dual_engine_read_only_investigation() -> None:
    clickhouse_password = _seed_clickhouse()
    doris_password = _seed_doris()
    repository = ControlStateRepository(os.environ["YAMAZAKI_DATABASE_URL"])
    clickhouse = ClickHouseAdapter(
        ClusterTarget(
            cluster_id="clickhouse-poc",
            engine=EngineKind.CLICKHOUSE,
            display_name="ClickHouse POC",
            environment="poc",
            credential_ref="env:YAMAZAKI_IT_CLICKHOUSE_READER_PASSWORD",
        ),
        host="127.0.0.1",
        port=18124,
        username="yamazaki_reader",
        password=clickhouse_password,
    )
    doris = DorisAdapter(
        ClusterTarget(
            cluster_id="doris-poc",
            engine=EngineKind.DORIS,
            display_name="Doris POC",
            environment="poc",
            credential_ref="env:YAMAZAKI_IT_DORIS_READER_PASSWORD",
        ),
        host="127.0.0.1",
        sql_port=19031,
        http_port=18031,
        username="yamazaki_reader",
        password=doris_password,
        database="information_schema",
    )
    evidence_store = LocalEvidenceStore(Path(os.environ["YAMAZAKI_IT_EVIDENCE_DIR"]))
    coordinator = YamazakiCoordinator(
        adapters=(clickhouse, doris),
        repository=repository,
        evidence_store=evidence_store,
    )
    end = datetime.now(UTC)
    request = InvestigationRequest(
        cluster_ids=("clickhouse-poc", "doris-poc"),
        window_start=end - timedelta(minutes=10),
        window_end=end,
    )
    try:
        first = coordinator.investigate(request)
        count_after_first = len(repository.list_query_runs(limit=1_000))
        second = coordinator.investigate(request)
        count_after_second = len(repository.list_query_runs(limit=1_000))
    finally:
        clickhouse.close()
        doris.close()
        repository.close()

    assert first.state.value == "succeeded"
    assert first.errors == {}
    anomaly_engines = {
        query.engine
        for query in first.query_runs
        if any(
            detection.query_run_id == query.query_run_id and detection.anomaly
            for detection in first.detections
        )
    }
    assert anomaly_engines == {EngineKind.CLICKHOUSE, EngineKind.DORIS}
    assert {
        query.engine
        for query in first.query_runs
        if query.duration_ms >= 5_000 and query.state is QueryState.SUCCEEDED
    } == {EngineKind.CLICKHOUSE, EngineKind.DORIS}
    assert first.diagnoses
    assert all(not item.actionable for item in first.recommendations)
    assert count_after_first == count_after_second
    assert second.errors == {}
    assert all(
        "yamazaki-it-slow" not in query.model_dump_json() for query in first.query_runs
    )
