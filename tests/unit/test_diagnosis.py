"""Tests for evidence-bound deterministic diagnosis."""

from tests.conftest import make_query
from yamazaki.contracts import EvidenceBundle
from yamazaki.diagnosis import RuleDiagnoser
from yamazaki.normalization import query_summary_evidence
from yamazaki.slow_query import SlowQueryDetector


def test_rule_diagnosis_references_only_supplied_evidence() -> None:
    query = make_query(duration_ms=6_000)
    evidence = query_summary_evidence(query)
    detection = SlowQueryDetector().detect(query, evidence=(evidence,))
    outcome = RuleDiagnoser().diagnose(
        query,
        detection,
        EvidenceBundle(items=(evidence,)),
    )
    assert outcome is not None
    diagnosis, recommendation = outcome
    assert diagnosis.causes
    assert all(
        cause.evidence_ids == (evidence.evidence_id,) for cause in diagnosis.causes
    )
    assert recommendation.actionable is False


def test_normal_query_has_no_diagnosis() -> None:
    query = make_query(duration_ms=100)
    evidence = query_summary_evidence(query)
    detection = SlowQueryDetector().detect(query, evidence=(evidence,))
    assert (
        RuleDiagnoser().diagnose(
            query,
            detection,
            EvidenceBundle(items=(evidence,)),
        )
        is None
    )
