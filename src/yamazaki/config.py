"""JSON configuration and environment-only credential resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator

from yamazaki.contracts import ClusterTarget, EngineKind, FrozenContract


class ClusterConfig(FrozenContract):
    """Credential-free cluster connection configuration."""

    cluster_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    engine: EngineKind
    display_name: str = Field(min_length=1, max_length=128)
    environment: str = Field(default="poc", min_length=1, max_length=64)
    host: str = Field(min_length=1, max_length=255)
    sql_port: int = Field(ge=1, le=65535)
    http_port: int | None = Field(default=None, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128)
    password_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    database: str = Field(default="default", min_length=1, max_length=128)
    secure: bool = False

    def target(self) -> ClusterTarget:
        return ClusterTarget(
            cluster_id=self.cluster_id,
            engine=self.engine,
            display_name=self.display_name,
            environment=self.environment,
            credential_ref=f"env:{self.password_env}",
        )


class YamazakiConfig(FrozenContract):
    """Minimal configuration for a single-process read-only deployment."""

    schema_version: Literal[1] = 1
    clusters: tuple[ClusterConfig, ...]
    database_url_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    evidence_directory: Path
    api_token_env: str = Field(
        default="YAMAZAKI_API_TOKEN", pattern=r"^[A-Z][A-Z0-9_]*$"
    )
    api_host: Literal["127.0.0.1"] = "127.0.0.1"

    @model_validator(mode="after")
    def _validate_clusters(self) -> YamazakiConfig:
        identifiers = [cluster.cluster_id for cluster in self.clusters]
        if not identifiers or len(set(identifiers)) != len(identifiers):
            raise ValueError("clusters must be non-empty and unique")
        return self


class ResolvedCredential(FrozenContract):
    """A runtime-only secret that is excluded from representations."""

    username: str
    password: SecretStr = Field(repr=False)


def load_config(path: Path) -> YamazakiConfig:
    """Load the documented JSON-only configuration."""

    if path.suffix.lower() != ".json":
        raise ValueError("Yamazaki configuration must be JSON")
    return YamazakiConfig.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_credential(cluster: ClusterConfig) -> ResolvedCredential:
    """Resolve one password without copying it into persistent configuration."""

    password = os.environ.get(cluster.password_env)
    if not password:
        raise ValueError(
            f"required credential environment variable is unset: {cluster.password_env}"
        )
    return ResolvedCredential(username=cluster.username, password=SecretStr(password))


def resolve_database_url(config: YamazakiConfig) -> str:
    """Resolve the control-state URL from its environment reference."""

    value = os.environ.get(config.database_url_env)
    if not value:
        raise ValueError(
            "required database environment variable is unset: "
            f"{config.database_url_env}"
        )
    return value


def render_example_config() -> str:
    """Return a secret-free example used by the CLI and documentation."""

    payload = {
        "schema_version": 1,
        "clusters": [
            {
                "cluster_id": "clickhouse-poc",
                "engine": "clickhouse",
                "display_name": "ClickHouse POC",
                "environment": "poc",
                "host": "127.0.0.1",
                "sql_port": 8123,
                "http_port": None,
                "username": "yamazaki_reader",
                "password_env": "YAMAZAKI_CLICKHOUSE_PASSWORD",
                "database": "default",
                "secure": False,
            }
        ],
        "database_url_env": "YAMAZAKI_DATABASE_URL",
        "evidence_directory": ".local/evidence",
        "api_token_env": "YAMAZAKI_API_TOKEN",
        "api_host": "127.0.0.1",
    }
    return json.dumps(payload, indent=2, sort_keys=True)
