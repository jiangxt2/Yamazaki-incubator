"""Optional one-call model diagnosis behind the single Coordinator."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from yamazaki.contracts import (
    DetectionResult,
    Diagnosis,
    DiagnosisSource,
    EvidenceBundle,
    InferenceKind,
    QueryRun,
    Recommendation,
    RootCause,
)

_INSTRUCTIONS = """
You are Yamazaki's optional read-only diagnosis assistant. Use only the supplied
redacted evidence. Return structured candidate causes and one review-only
recommendation. Every candidate cause must cite one or more supplied evidence
IDs. Do not invent measurements, execute tools, request credentials, or claim
that a recommendation has been applied.
""".strip()


class _CauseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    explanation: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)


class _DiagnosisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    causes: list[_CauseOutput]
    uncertainty: list[str] = Field(default_factory=list)
    recommendation: str
    prerequisites: list[str] = Field(default_factory=list)
    risk: str
    expected_benefit: str
    verification: str


class PydanticAIDiagnoser:
    """Use PydanticAI structured output without exposing any tools."""

    def __init__(
        self,
        model: Any,
        *,
        model_id: str | None = None,
        prompt_version: str = "yamazaki.prompt/v1",
    ) -> None:
        try:
            from pydantic_ai import Agent
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("install the agent extra to use PydanticAI") from exc
        self._agent = Agent(
            model,
            output_type=_DiagnosisOutput,
            instructions=_INSTRUCTIONS,
            retries=0,
        )
        self._model_id = model_id or type(model).__name__
        self._prompt_version = prompt_version

    def diagnose(
        self,
        query: QueryRun,
        detection: DetectionResult,
        evidence: EvidenceBundle,
    ) -> tuple[Diagnosis, Recommendation] | None:
        prompt = {
            "query": _prompt_query(query),
            "detection": detection.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
        }
        result = self._agent.run_sync(str(prompt))
        output = result.output
        if not isinstance(output, _DiagnosisOutput):
            raise TypeError("PydanticAI returned an unexpected output type")
        allowed = {str(item.evidence_id): item.evidence_id for item in evidence.items}
        causes: list[RootCause] = []
        for cause in output.causes:
            evidence_ids = tuple(
                allowed[identifier]
                for identifier in dict.fromkeys(cause.evidence_ids)
                if identifier in allowed
            )
            if not evidence_ids:
                continue
            causes.append(
                RootCause(
                    code=cause.code,
                    explanation=cause.explanation,
                    inference_kind=InferenceKind.MODEL,
                    evidence_ids=evidence_ids,
                    confidence=cause.confidence,
                )
            )
        if not causes:
            return None
        diagnosis = Diagnosis(
            query_run_id=query.query_run_id,
            source=DiagnosisSource.AGENT_ASSISTED,
            causes=tuple(causes),
            uncertainty=tuple(output.uncertainty),
            evidence_bundle_digest=evidence.digest,
            model_id=self._model_id,
            prompt_version=self._prompt_version,
        )
        recommendation = Recommendation(
            diagnosis_id=diagnosis.diagnosis_id,
            content=output.recommendation,
            prerequisites=tuple(output.prerequisites),
            risk=output.risk,
            expected_benefit=output.expected_benefit,
            verification=output.verification,
        )
        return diagnosis, recommendation


def openai_compatible_model(
    *,
    model_name: str,
    base_url: str,
    api_key: str,
) -> Any:
    """Build the one supported provider-neutral model endpoint adapter."""

    try:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("install the agent extra to configure a model") from exc
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )


def parse_evidence_id(value: str) -> UUID | None:
    """Parse model output without leaking validation details into prompts."""

    try:
        return UUID(value)
    except ValueError:
        return None


def _prompt_query(query: QueryRun) -> dict[str, Any]:
    """Project only non-identifying query facts into the model prompt."""

    return {
        "engine": query.engine,
        "state": query.state,
        "native_fingerprint": query.native_fingerprint,
        "duration_ms": query.duration_ms,
        "queue_time_ms": query.queue_time_ms,
        "cpu_time_ms": query.cpu_time_ms,
        "peak_memory_bytes": query.peak_memory_bytes,
        "scanned_rows": query.scanned_rows,
        "returned_rows": query.returned_rows,
        "shuffle_bytes": query.shuffle_bytes,
        "spill_bytes": query.spill_bytes,
        "progress": query.progress,
        "statement_type": query.statement_type,
        "redacted_structure": query.redacted_structure,
    }
