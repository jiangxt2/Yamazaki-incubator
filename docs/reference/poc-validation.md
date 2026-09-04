# Read-only POC Validation

> Status: `Validated` for the bounded POC Gate; this is not a production
> support claim.

The Yamazaki internal read-only slow-query POC passed a complete
real-infrastructure Gate in the `feat/read-only-slow-query-agent` worktree.
Validation is limited to the environment, code state, and behavior documented
below; it is not a production support claim.

## Scope

- Apple arm64 host with Docker Desktop.
- One ClickHouse 25.3.2.39 test service and one Doris FE/BE 4.0.6 test service.
- PostgreSQL 16.14 control state.
- One single-process Coordinator and fixed read-only adapters.
- Synthetic test data and generated ephemeral credentials only.
- No database action API, multi-tenant deployment, HA, or long-term evidence
  retention.

## Evidence

| Check | Result |
| --- | --- |
| Python and dependency lock | Python 3.13.7; `uv lock --check`; `uv pip check` |
| Static quality | Ruff format/lint, strict Mypy, ShellCheck and Markdown lint passed |
| Fast tests | 43 unit/contract/replay tests passed; measured coverage 85% |
| Package build | sdist and wheel built successfully with `uv build` |
| Database migration | Alembic revision `0001_control_state` applied to PostgreSQL |
| ClickHouse | 25.3.2.39 slow query collected from Query Log and classified as an anomaly |
| Doris | FE/BE 4.0.6 slow query collected from Audit Log and classified as an anomaly |
| Read-only enforcement | Both generated reader accounts rejected `DROP TABLE` |
| Diagnosis | Deterministic diagnoses and non-actionable recommendations persisted |
| Idempotency | Repeating the same investigation did not create duplicate logical QueryRun records |
| Complete dual-engine Gate | 1 integration test passed in 22.11s for the model-disabled engine path; the optional Agent budget fix was verified by the fast suite |
| Cleanup | The exact Compose project, networks and volumes were removed; no global prune was used |

The complete command, image digests, code fingerprints, failed-attempt history,
and limitations are recorded in
[`docs/reference/test-matrix.md`](test-matrix.md).

## Limitations

The Gate does not validate other engine versions, multiple production clusters,
FE failover, running-query observation under load, deep Profile/Trace semantics,
real-time model quality, high availability, multi-tenant authorization, or any
database action. These remain `Planned` or `Experimental` until separately
scoped and tested.
