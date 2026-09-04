"""Contract tests for the local read API and configuration CLI."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_target
from yamazaki.api import create_app
from yamazaki.cli import main
from yamazaki.persistence import ControlStateRepository


def test_api_health_is_open_and_data_requires_token(
    repository: ControlStateRepository,
) -> None:
    repository.save_cluster(make_target())
    client = TestClient(create_app(repository, api_token="test-only-token"))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/clusters").status_code == 401
    response = client.get(
        "/clusters",
        headers={"Authorization": "Bearer test-only-token"},
    )
    assert response.status_code == 200
    assert response.json()[0]["cluster_id"] == "clickhouse-poc"


def test_cli_validate_checks_environment_without_printing_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = {
        "schema_version": 1,
        "clusters": [
            {
                "cluster_id": "clickhouse-poc",
                "engine": "clickhouse",
                "display_name": "ClickHouse",
                "environment": "poc",
                "host": "127.0.0.1",
                "sql_port": 8123,
                "http_port": None,
                "username": "reader",
                "password_env": "YAMAZAKI_CLICKHOUSE_PASSWORD",
                "database": "default",
                "secure": False,
            }
        ],
        "database_url_env": "YAMAZAKI_DATABASE_URL",
        "evidence_directory": str(tmp_path / "evidence"),
        "api_token_env": "YAMAZAKI_API_TOKEN",
        "api_host": "127.0.0.1",
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("YAMAZAKI_CLICKHOUSE_PASSWORD", "private-password")
    monkeypatch.setenv("YAMAZAKI_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("YAMAZAKI_API_TOKEN", "private-token")
    assert main(["validate", "--config", str(path)]) == 0
    output = capsys.readouterr().out
    assert '"status": "valid"' in output
    assert "private-password" not in output
    assert "private-token" not in output
