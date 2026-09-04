"""Composition root for the single-process POC."""

from __future__ import annotations

from dataclasses import dataclass

from yamazaki.config import (
    YamazakiConfig,
    resolve_credential,
    resolve_database_url,
)
from yamazaki.engines.clickhouse import ClickHouseAdapter
from yamazaki.engines.doris import DorisAdapter
from yamazaki.evidence_store import LocalEvidenceStore
from yamazaki.persistence import ControlStateRepository
from yamazaki.ports import EngineAdapter
from yamazaki.service import YamazakiCoordinator


@dataclass(slots=True)
class Runtime:
    """Owned adapters and services for one process."""

    coordinator: YamazakiCoordinator
    repository: ControlStateRepository
    adapters: tuple[EngineAdapter, ...]

    def close(self) -> None:
        for adapter in self.adapters:
            close = getattr(adapter, "close", None)
            if close is not None:
                close()
        self.repository.close()


def build_runtime(config: YamazakiConfig) -> Runtime:
    """Resolve trusted configuration outside Agent-controlled payloads."""

    adapters: list[EngineAdapter] = []
    for cluster in config.clusters:
        credential = resolve_credential(cluster)
        password = credential.password.get_secret_value()
        if cluster.engine.value == "clickhouse":
            adapters.append(
                ClickHouseAdapter(
                    cluster.target(),
                    host=cluster.host,
                    port=cluster.sql_port,
                    username=credential.username,
                    password=password,
                    database=cluster.database,
                    secure=cluster.secure,
                )
            )
        else:
            if cluster.http_port is None:
                raise ValueError("Doris requires an http_port")
            adapters.append(
                DorisAdapter(
                    cluster.target(),
                    host=cluster.host,
                    sql_port=cluster.sql_port,
                    http_port=cluster.http_port,
                    username=credential.username,
                    password=password,
                    database=cluster.database,
                )
            )
    repository = ControlStateRepository(resolve_database_url(config))
    coordinator = YamazakiCoordinator(
        adapters=tuple(adapters),
        repository=repository,
        evidence_store=LocalEvidenceStore(config.evidence_directory),
    )
    return Runtime(
        coordinator=coordinator,
        repository=repository,
        adapters=tuple(adapters),
    )
