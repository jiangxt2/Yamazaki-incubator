"""Tests for strict state and evidence contracts."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tests.conftest import make_query
from yamazaki.contracts import (
    AgentBudget,
    ClusterTarget,
    DorisIdentity,
    EvidenceBundle,
    EvidenceRef,
    InvestigationRequest,
    QueryRun,
    Recommendation,
    content_digest,
)


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ClusterTarget.model_validate(
            {
                "cluster_id": "clickhouse-poc",
                "engine": "clickhouse",
                "display_name": "ClickHouse",
                "environment": "poc",
                "credential_ref": "env:YAMAZAKI_PASSWORD",
                "password": "must-not-be-accepted",
            }
        )


def test_query_rejects_native_identity_from_another_engine() -> None:
    query = make_query()
    payload = query.model_dump()
    payload["native"] = DorisIdentity(
        query_id="query-1",
        sql_digest="digest",
    )
    with pytest.raises(ValidationError, match="native identity"):
        QueryRun.model_validate(payload)


def test_query_and_evidence_identity_are_stable() -> None:
    query = make_query()
    assert query.query_run_id == QueryRun.stable_id(
        engine=query.engine,
        cluster_id=query.cluster_id,
        engine_query_id=query.engine_query_id,
        started_at=query.started_at,
    )
    digest = content_digest({"duration_ms": query.duration_ms})
    assert EvidenceRef.stable_id(
        query_run_id=query.query_run_id,
        source_kind="query_summary",
        content_hash=digest,
    ) == EvidenceRef.stable_id(
        query_run_id=query.query_run_id,
        source_kind="query_summary",
        content_hash=digest,
    )


def test_evidence_bundle_is_bounded_and_unique() -> None:
    query = make_query()
    digest = "a" * 64
    item = EvidenceRef(
        query_run_id=query.query_run_id,
        source_kind="summary",
        engine=query.engine,
        summary="summary",
        content_hash=digest,
    )
    with pytest.raises(ValidationError, match="unique"):
        EvidenceBundle(items=(item, item))
    with pytest.raises(ValidationError, match="at most 12"):
        EvidenceBundle(
            items=tuple(
                item.model_copy(update={"evidence_id": uuid4()}) for _ in range(13)
            )
        )


def test_recommendation_cannot_become_actionable() -> None:
    with pytest.raises(ValidationError):
        Recommendation.model_validate(
            {
                "diagnosis_id": str(uuid4()),
                "actionable": True,
                "content": "unsafe",
                "risk": "unknown",
                "expected_benefit": "unknown",
                "verification": "none",
            }
        )


def test_investigation_requires_unique_clusters_and_aware_window() -> None:
    with pytest.raises(ValidationError, match="unique"):
        InvestigationRequest(
            cluster_ids=("one", "one"),
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 1, 2, tzinfo=UTC),
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        InvestigationRequest(
            cluster_ids=("one",),
            window_start=datetime(2026, 1, 1),
            window_end=datetime(2026, 1, 2),
        )


def test_poc_budget_rejects_unbounded_values() -> None:
    with pytest.raises(ValidationError):
        AgentBudget(max_model_calls=2)
