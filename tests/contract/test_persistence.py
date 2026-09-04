"""Contract tests for idempotent control-state persistence."""

from datetime import UTC, datetime, timedelta

from tests.conftest import make_query, make_target
from yamazaki.contracts import (
    InvestigationRequest,
    InvestigationResult,
    InvestigationState,
)
from yamazaki.normalization import query_summary_evidence
from yamazaki.persistence import ControlStateRepository


def test_query_and_evidence_saves_are_idempotent(
    repository: ControlStateRepository,
) -> None:
    query = make_query()
    repository.save_cluster(make_target())
    assert repository.save_query_run(query) == query
    assert repository.save_query_run(query) == query
    evidence = query_summary_evidence(query)
    assert repository.save_evidence(evidence) == evidence
    assert repository.save_evidence(evidence) == evidence
    assert repository.list_query_runs() == (query,)


def test_history_is_isolated_by_cluster_and_fingerprint(
    repository: ControlStateRepository,
) -> None:
    repository.save_cluster(make_target(cluster_id="clickhouse-poc"))
    repository.save_cluster(make_target(cluster_id="clickhouse-other"))
    query = make_query(query_id="current")
    same = make_query(
        query_id="same",
        started_at=datetime(2025, 12, 31, tzinfo=UTC),
    )
    other_cluster = make_query(
        query_id="other-cluster",
        cluster_id="clickhouse-other",
    )
    other_fingerprint = make_query(
        query_id="other-fingerprint",
        fingerprint="different",
    )
    for item in (query, same, other_cluster, other_fingerprint):
        repository.save_query_run(item)
    assert set(repository.list_query_history(query)) == {query, same}


def test_investigation_current_state_can_be_updated(
    repository: ControlStateRepository,
) -> None:
    start = datetime.now(UTC)
    request = InvestigationRequest(
        cluster_ids=("clickhouse-poc",),
        window_start=start - timedelta(minutes=5),
        window_end=start,
    )
    repository.save_investigation(request)
    result = InvestigationResult(
        investigation_id=request.investigation_id,
        state=InvestigationState.SUCCEEDED,
        query_runs=(),
        detections=(),
        diagnoses=(),
        recommendations=(),
    )
    repository.save_investigation(request, result)
