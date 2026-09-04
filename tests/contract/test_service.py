"""Contract tests for the single Coordinator and degraded results."""

from datetime import UTC, datetime, timedelta

from tests.conftest import FakeAdapter, RawRecordFactory, make_target
from yamazaki.contracts import (
    DetectionResult,
    Diagnosis,
    EngineKind,
    EvidenceBundle,
    InvestigationRequest,
    InvestigationState,
    QueryRun,
    Recommendation,
)
from yamazaki.evidence_store import LocalEvidenceStore
from yamazaki.persistence import ControlStateRepository
from yamazaki.service import CancellationToken, YamazakiCoordinator


def request_for(*cluster_ids: str) -> InvestigationRequest:
    end = datetime.now(UTC)
    return InvestigationRequest(
        cluster_ids=cluster_ids,
        window_start=end - timedelta(days=365),
        window_end=end,
    )


def test_one_adapter_failure_preserves_the_other_path(
    repository: ControlStateRepository,
    evidence_store: LocalEvidenceStore,
    raw_record: RawRecordFactory,
) -> None:
    good = FakeAdapter(make_target(), (raw_record(),))
    failed = FakeAdapter(
        make_target(EngineKind.DORIS),
        (),
        failure=ConnectionError("not persisted"),
    )
    coordinator = YamazakiCoordinator(
        adapters=(good, failed),
        repository=repository,
        evidence_store=evidence_store,
    )
    result = coordinator.investigate(request_for("clickhouse-poc", "doris-poc"))
    assert result.state is InvestigationState.DEGRADED
    assert len(result.query_runs) == 1
    assert result.errors == {"doris-poc": "ConnectionError"}
    assert "not persisted" not in result.model_dump_json()


def test_model_failure_preserves_deterministic_diagnosis(
    repository: ControlStateRepository,
    evidence_store: LocalEvidenceStore,
    raw_record: RawRecordFactory,
) -> None:
    class FailingDiagnoser:
        def diagnose(
            self,
            query: QueryRun,
            detection: DetectionResult,
            evidence: EvidenceBundle,
        ) -> tuple[Diagnosis, Recommendation] | None:
            raise TimeoutError("model detail must not escape")

    coordinator = YamazakiCoordinator(
        adapters=(FakeAdapter(make_target(), (raw_record(),)),),
        repository=repository,
        evidence_store=evidence_store,
        agent_diagnoser=FailingDiagnoser(),
    )
    result = coordinator.investigate(request_for("clickhouse-poc"))
    assert result.state is InvestigationState.DEGRADED
    assert any(item.source.value == "deterministic" for item in result.diagnoses)
    assert "model detail" not in result.model_dump_json()


def test_model_budget_is_shared_across_anomalous_queries(
    repository: ControlStateRepository,
    evidence_store: LocalEvidenceStore,
    raw_record: RawRecordFactory,
) -> None:
    class CountingDiagnoser:
        calls = 0

        def diagnose(
            self,
            query: QueryRun,
            detection: DetectionResult,
            evidence: EvidenceBundle,
        ) -> tuple[Diagnosis, Recommendation] | None:
            self.calls += 1
            return None

    diagnoser = CountingDiagnoser()
    coordinator = YamazakiCoordinator(
        adapters=(
            FakeAdapter(
                make_target(),
                (raw_record(query_id="query-1"), raw_record(query_id="query-2")),
            ),
        ),
        repository=repository,
        evidence_store=evidence_store,
        agent_diagnoser=diagnoser,
    )
    result = coordinator.investigate(request_for("clickhouse-poc"))

    assert result.state is InvestigationState.SUCCEEDED
    assert len(result.query_runs) == 2
    assert diagnoser.calls == 1


def test_cancelled_run_stops_before_adapter_access(
    repository: ControlStateRepository,
    evidence_store: LocalEvidenceStore,
    raw_record: RawRecordFactory,
) -> None:
    cancellation = CancellationToken()
    cancellation.cancel()
    coordinator = YamazakiCoordinator(
        adapters=(FakeAdapter(make_target(), (raw_record(),)),),
        repository=repository,
        evidence_store=evidence_store,
        cancellation=cancellation,
    )
    result = coordinator.investigate(request_for("clickhouse-poc"))
    assert result.state is InvestigationState.CANCELLED
    assert result.query_runs == ()
