"""End-to-end replay of normal, anomalous, missing, and dual-engine facts."""

from datetime import UTC, datetime, timedelta

from tests.conftest import FakeAdapter, RawRecordFactory, make_target
from yamazaki.contracts import EngineKind, InvestigationRequest, InvestigationState
from yamazaki.engines.base import RawEvidence
from yamazaki.evidence_store import LocalEvidenceStore
from yamazaki.persistence import ControlStateRepository
from yamazaki.service import YamazakiCoordinator


def test_dual_engine_replay_keeps_native_paths_and_evidence_gaps(
    repository: ControlStateRepository,
    evidence_store: LocalEvidenceStore,
    raw_record: RawRecordFactory,
) -> None:
    clickhouse = FakeAdapter(
        make_target(),
        (
            raw_record(query_id="ch-fast", duration_ms=100),
            raw_record(query_id="ch-slow", duration_ms=6_000),
        ),
    )
    doris = FakeAdapter(
        make_target(EngineKind.DORIS),
        (
            raw_record(
                engine=EngineKind.DORIS,
                query_id="doris-slow",
                duration_ms=6_500,
            ),
        ),
        evidence=RawEvidence(
            source_kind="doris_profile",
            summary="Doris profile unavailable.",
            facts={"available": False},
            available=False,
            gap="profile_unavailable",
        ),
    )
    coordinator = YamazakiCoordinator(
        adapters=(clickhouse, doris),
        repository=repository,
        evidence_store=evidence_store,
    )
    end = datetime.now(UTC)
    result = coordinator.investigate(
        InvestigationRequest(
            cluster_ids=("clickhouse-poc", "doris-poc"),
            window_start=end - timedelta(days=365),
            window_end=end,
        )
    )
    assert result.state is InvestigationState.SUCCEEDED
    assert {item.engine for item in result.query_runs} == {
        EngineKind.CLICKHOUSE,
        EngineKind.DORIS,
    }
    anomalies = [item for item in result.detections if item.anomaly]
    assert len(anomalies) == 2
    assert len(result.diagnoses) == 2
    assert all(not item.actionable for item in result.recommendations)
    persisted = repository.list_query_runs()
    assert len(persisted) == 3
    assert all("private.events" not in item.model_dump_json() for item in persisted)
