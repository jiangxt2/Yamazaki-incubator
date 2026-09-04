# Read-only Slow-query POC

> Status: `Accepted`
>
> Scope: internal, controlled-network, single-tenant experimental POC only.

## Context

Yamazaki needs one narrow implementation slice that proves evidence-driven slow
query investigation for ClickHouse and Apache Doris. The slice must remain
useful without a language model and must not introduce a database action path.

The earlier isolated POC validated ClickHouse 25.3.2.39, Doris 4.0.6, and
PostgreSQL 16.14 on Apple arm64. Those exact images are already present in the
local Docker cache. No evidence currently requires a message bus, durable
workflow engine, policy service, multi-agent runtime, or separate deployment
services.

## Decision

- Use Python 3.13, uv, Hatchling, strict immutable Pydantic contracts, and JSON
  configuration.
- Build one modular process with one code-controlled Coordinator.
- Keep ClickHouse and Doris behavior behind separate adapters with fixed
  read-only methods. Preserve native identities and capability gaps.
- Run deterministic detection and rule diagnosis for every collected query.
  PydanticAI is an optional one-call structured diagnosis adapter with no tools.
- Store control state in PostgreSQL through SQLAlchemy and Alembic. Use
  PostgreSQL 16.14 for this POC Gate because it is the locally cached and
  previously validated baseline; this is not a production support commitment.
- Store restricted development evidence in owner-only local files and persist
  only references, hashes, and bounded summaries in PostgreSQL.
- Expose a minimal CLI and localhost-only read API. No action API, arbitrary SQL,
  arbitrary URL, shell, cancellation of database queries, or write credential
  exists in the runtime.
- Validate all real infrastructure in one project-owned Docker Compose suite
  using cached digest-pinned images and no build or pull operation.

## Alternatives

- Python 3.12 remains a fallback if a verified dependency blocks Python 3.13.
- PostgreSQL 17 remains a future candidate; upgrading the POC without a concrete
  need would add an unnecessary version variable.
- Kafka, Temporal, OPA, OpenFGA, an object store, Kubernetes, multi-agent
  orchestration, and a dedicated UI are deferred until the documented trigger
  for each capability occurs.
- A generic plugin marketplace and remote tool protocol are outside this POC.

## Consequences

The implementation is intentionally small and synchronous. It can preserve
partial results when one engine adapter fails, but it does not promise high
availability, multi-process task takeover, long-term evidence retention, or
multi-tenant isolation.

The database remains the source of truth. Model output cannot change a
deterministic detection and every accepted model cause must cite an existing
evidence identifier.

## Validation

- Unit tests cover contracts, redaction, evidence storage, statistics, diagnosis,
  cancellation, and optional Agent filtering.
- Contract and replay tests cover adapters, persistence, API authentication,
  idempotency, dual-engine isolation, and deterministic degradation.
- One real Docker Gate covers Alembic, PostgreSQL, ClickHouse, Doris, slow-query
  collection, write rejection, evidence, diagnosis, and exact cleanup.

The exact commands and results are recorded in
[`docs/reference/test-matrix.md`](../reference/test-matrix.md).

## Exit Path

Framework and infrastructure types do not enter the core contracts. An adapter,
state store, or model implementation can be replaced behind its narrow port. A
new cross-process or action requirement must be reviewed in a separate ADR
instead of expanding this decision silently.
