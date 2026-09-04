"""Tests for JSON-only configuration and secret resolution."""

from pathlib import Path

import pytest

from yamazaki.config import (
    ClusterConfig,
    load_config,
    render_example_config,
    resolve_credential,
)
from yamazaki.contracts import EngineKind


def test_load_config_rejects_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("clusters: []", encoding="utf-8")
    with pytest.raises(ValueError, match="must be JSON"):
        load_config(path)


def test_credential_is_environment_only_and_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = ClusterConfig(
        cluster_id="clickhouse-poc",
        engine=EngineKind.CLICKHOUSE,
        display_name="ClickHouse",
        host="127.0.0.1",
        sql_port=8123,
        username="reader",
        password_env="YAMAZAKI_CLICKHOUSE_PASSWORD",
    )
    monkeypatch.setenv("YAMAZAKI_CLICKHOUSE_PASSWORD", "sensitive-value")
    credential = resolve_credential(config)
    assert credential.password.get_secret_value() == "sensitive-value"
    assert "sensitive-value" not in repr(credential)
    assert "sensitive-value" not in config.model_dump_json()


def test_example_configuration_contains_no_secret() -> None:
    example = render_example_config()
    assert "password_env" in example
    assert '"password"' not in example
