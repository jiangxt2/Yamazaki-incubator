"""Tests for optional one-call model diagnosis and evidence filtering."""

from pydantic_ai.models.test import TestModel

from tests.conftest import make_query
from yamazaki.agent import PydanticAIDiagnoser, _prompt_query
from yamazaki.contracts import EvidenceBundle
from yamazaki.normalization import query_summary_evidence
from yamazaki.slow_query import SlowQueryDetector


def test_agent_discards_unknown_evidence_ids() -> None:
    query = make_query()
    evidence = query_summary_evidence(query)
    detection = SlowQueryDetector().detect(query, evidence=(evidence,))
    model = TestModel(
        custom_output_args={
            "causes": [
                {
                    "code": "unsupported_claim",
                    "explanation": "No valid evidence.",
                    "evidence_ids": ["00000000-0000-0000-0000-000000000000"],
                    "confidence": 0.9,
                }
            ],
            "uncertainty": [],
            "recommendation": "Review evidence.",
            "prerequisites": [],
            "risk": "Unknown.",
            "expected_benefit": "Unknown.",
            "verification": "Replay safely.",
        }
    )
    diagnoser = PydanticAIDiagnoser(model)
    assert (
        diagnoser.diagnose(query, detection, EvidenceBundle(items=(evidence,))) is None
    )


def test_real_pydantic_ai_test_model_returns_evidence_bound_output() -> None:
    query = make_query()
    evidence = query_summary_evidence(query)
    detection = SlowQueryDetector().detect(query, evidence=(evidence,))
    model = TestModel(
        custom_output_args={
            "causes": [
                {
                    "code": "duration_threshold",
                    "explanation": "Duration exceeded the configured threshold.",
                    "evidence_ids": [str(evidence.evidence_id)],
                    "confidence": 0.8,
                }
            ],
            "uncertainty": [],
            "recommendation": "Review the engine evidence.",
            "prerequisites": [],
            "risk": "Evidence may be incomplete.",
            "expected_benefit": "A narrower investigation.",
            "verification": "Use an isolated replay.",
        }
    )
    outcome = PydanticAIDiagnoser(model).diagnose(
        query,
        detection,
        EvidenceBundle(items=(evidence,)),
    )
    assert outcome is not None
    diagnosis, recommendation = outcome
    assert diagnosis.causes[0].evidence_ids == (evidence.evidence_id,)
    assert diagnosis.model_id == "TestModel"
    assert diagnosis.prompt_version == "yamazaki.prompt/v1"
    assert recommendation.actionable is False


def test_agent_prompt_projection_omits_operational_identity() -> None:
    query = make_query()
    prompt = _prompt_query(query)
    assert "cluster_id" not in prompt
    assert "query_run_id" not in prompt
    assert "frontend" not in prompt
    assert "workload_group" not in prompt
