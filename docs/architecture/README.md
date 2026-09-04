# Architecture Boundaries

> Status: `Validated`

This document records stable design boundaries for Yamazaki. The validated
status applies only to the internal read-only POC; it does not establish a
production platform or require a message bus, workflow engine, policy engine,
multi-agent runtime, or deployment platform.

## Purpose

Yamazaki is planned as an AIOps governance control plane for ClickHouse and
Apache Doris. It should organize operational evidence, diagnosis,
recommendations, controlled action proposals, and outcome verification without
becoming a synchronous dependency in database query execution.

## Stable Boundaries

- The database remains the source of truth for execution state and engine
  behavior.
- Collection and diagnosis are read-only by default.
- ClickHouse and Doris adapters preserve native evidence and capability
  differences.
- Scenario-specific detection, evidence, diagnosis, policy, action, and
  verification remain outside the shared core.
- Model output is inference, not deterministic evidence.
- Analysis is separated from policy-controlled execution.
- Credentials and sensitive operational data are redacted before entering
  prompts, logs, telemetry, or durable stores.

## Conceptual Responsibilities

The planned architecture may contain the following responsibilities without
implying separate services or a chosen framework:

- Engine collection and capability discovery.
- Versioned operational entities, events, and evidence references.
- Scenario detection and evidence assembly.
- Structured diagnosis and recommendations with uncertainty.
- Policy evaluation and approval for fixed action types.
- Action execution through least-privilege engine interfaces.
- Post-action verification, audit, and safe degradation.

## Experimental POC Structure

The current implementation keeps one code-controlled path:

```text
InvestigationRequest
  -> Coordinator
  -> ClickHouse/Doris fixed read-only adapters
  -> QueryRun and EvidenceRef
  -> deterministic SlowQueryDetector
  -> RuleDiagnoser
  -> optional one-call model diagnosis
  -> non-actionable Recommendation
```

The optional model receives bounded redacted evidence and has no tools. Adapter,
scenario, persistence, API, and model dependencies point toward narrow core
contracts; core contracts do not import their implementations.

## Decision Boundary

Any major technology or deployment choice requires a reviewed architecture
decision record covering alternatives, licensing, operational cost,
compatibility, validation evidence, and an exit path.
