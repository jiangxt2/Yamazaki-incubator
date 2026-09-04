"""Single Coordinator and code-controlled read-only investigation pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Event
from time import monotonic

from yamazaki.contracts import (
    EvidenceBundle,
    InvestigationRequest,
    InvestigationResult,
    InvestigationState,
)
from yamazaki.diagnosis import RuleDiagnoser
from yamazaki.normalization import (
    normalize_query,
    persist_raw_evidence,
    query_summary_evidence,
)
from yamazaki.ports import (
    AgentDiagnoserPort,
    ControlStateRepositoryPort,
    EngineAdapter,
    EvidenceStorePort,
)
from yamazaki.slow_query import SlowQueryDetector

_MAX_RUNNING_QUERIES = 1_000


class CancellationToken:
    """Process-local stop mechanism for the synchronous POC runner."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class YamazakiCoordinator:
    """Own the final result while deterministic components own facts."""

    def __init__(
        self,
        *,
        adapters: tuple[EngineAdapter, ...],
        repository: ControlStateRepositoryPort,
        evidence_store: EvidenceStorePort,
        detector: SlowQueryDetector | None = None,
        rule_diagnoser: RuleDiagnoser | None = None,
        agent_diagnoser: AgentDiagnoserPort | None = None,
        cancellation: CancellationToken | None = None,
    ) -> None:
        self._adapters = {adapter.target.cluster_id: adapter for adapter in adapters}
        self._repository = repository
        self._evidence_store = evidence_store
        self._detector = detector or SlowQueryDetector()
        self._rule_diagnoser = rule_diagnoser or RuleDiagnoser()
        self._agent_diagnoser = agent_diagnoser
        self._cancellation = cancellation or CancellationToken()

    @property
    def cancellation(self) -> CancellationToken:
        return self._cancellation

    def investigate(self, request: InvestigationRequest) -> InvestigationResult:
        """Execute fixed stages and preserve partial results on adapter failure."""

        self._repository.save_investigation(request)
        started = monotonic()
        query_runs = []
        detections = []
        diagnoses = []
        recommendations = []
        errors: dict[str, str] = {}
        model_calls = 0

        for cluster_id in request.cluster_ids:
            if self._cancellation.cancelled:
                break
            if monotonic() - started > request.budget.deadline_seconds:
                errors[cluster_id] = "investigation_deadline_exceeded"
                break
            adapter = self._adapters.get(cluster_id)
            if adapter is None:
                errors[cluster_id] = "cluster_not_configured"
                continue
            try:
                self._repository.save_cluster(adapter.target)
                capability = adapter.probe_capabilities()
                self._repository.save_capability(capability)
                raw_queries = (
                    *adapter.collect_completed_queries(
                        window_start=request.window_start,
                        window_end=request.window_end,
                    ),
                    *adapter.collect_running_queries(limit=_MAX_RUNNING_QUERIES),
                )
                for raw in raw_queries:
                    if self._cancellation.cancelled:
                        break
                    query = self._repository.save_query_run(
                        normalize_query(raw, correlation_id=request.investigation_id)
                    )
                    query_runs.append(query)
                    summary = self._repository.save_evidence(
                        query_summary_evidence(query)
                    )
                    history = self._repository.list_query_history(query)
                    detection = self._detector.detect(
                        query,
                        history=history,
                        evidence=(summary,),
                    )
                    evidence_items = [summary]
                    if detection.anomaly:
                        raw_evidence = adapter.collect_query_evidence(
                            query.engine_query_id
                        )
                        detail = self._repository.save_evidence(
                            persist_raw_evidence(
                                query,
                                raw_evidence,
                                self._evidence_store,
                            )
                        )
                        evidence_items.append(detail)
                        detection = self._detector.detect(
                            query,
                            history=history,
                            evidence=tuple(evidence_items),
                        )
                    self._repository.save_detection(detection)
                    detections.append(detection)
                    if not detection.anomaly:
                        continue
                    bundle = EvidenceBundle(
                        items=tuple(evidence_items[: request.budget.max_evidence_items])
                    )
                    deterministic = self._rule_diagnoser.diagnose(
                        query,
                        detection,
                        bundle,
                    )
                    if deterministic is not None:
                        diagnosis, recommendation = deterministic
                        self._repository.save_diagnosis(diagnosis)
                        self._repository.save_recommendation(recommendation)
                        diagnoses.append(diagnosis)
                        recommendations.append(recommendation)
                    if (
                        self._agent_diagnoser is not None
                        and model_calls < request.budget.max_model_calls
                    ):
                        model_calls += 1
                        try:
                            assisted = self._agent_diagnoser.diagnose(
                                query,
                                detection,
                                bundle,
                            )
                        except Exception as exc:
                            errors[f"agent:{query.query_run_id}"] = type(exc).__name__
                        else:
                            if assisted is not None:
                                diagnosis, recommendation = assisted
                                self._repository.save_diagnosis(diagnosis)
                                self._repository.save_recommendation(recommendation)
                                diagnoses.append(diagnosis)
                                recommendations.append(recommendation)
            except Exception as exc:
                errors[cluster_id] = type(exc).__name__

        state = InvestigationState.SUCCEEDED
        if self._cancellation.cancelled:
            state = InvestigationState.CANCELLED
        elif errors and query_runs:
            state = InvestigationState.DEGRADED
        elif errors:
            state = InvestigationState.FAILED
        result = InvestigationResult(
            investigation_id=request.investigation_id,
            state=state,
            query_runs=tuple(query_runs),
            detections=tuple(detections),
            diagnoses=tuple(diagnoses),
            recommendations=tuple(recommendations),
            errors=errors,
        )
        self._repository.save_investigation(request, result)
        return result


def recent_request(
    cluster_ids: tuple[str, ...],
    *,
    minutes: int = 15,
) -> InvestigationRequest:
    """Create the bounded request used by the CLI."""

    from datetime import timedelta

    if not 1 <= minutes <= 1_440:
        raise ValueError("minutes must be between 1 and 1440")
    end = datetime.now(UTC)
    return InvestigationRequest(
        cluster_ids=cluster_ids,
        window_start=end - timedelta(minutes=minutes),
        window_end=end,
    )
