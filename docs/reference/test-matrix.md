# Test Matrix

> Status: `Validated`

This ledger prevents duplicate long-running validation. A complete Docker suite
must not be repeated against unchanged code, tests, configuration, images, and
environment.

| Suite | Coverage | Infrastructure | Code state | Reason | Result |
| --- | --- | --- | --- | --- | --- |
| Fast quality | lock, dependencies, formatting, lint, typing, 43 unit/contract/replay tests, build, Markdown, ShellCheck | None | Source/test/script fingerprint `6a3027eef5c134b36ce2334be2144b5be79aced14d837032835ceb153b2f06a7` | Validate deterministic behavior before infrastructure | Passed; Python 3.13.7, 43 tests, 85% measured coverage |
| Dual-engine IT | PostgreSQL migration, ClickHouse 25.3.2.39, Doris 4.0.6, read-only rejection, collection, diagnosis, idempotency, cleanup | Project-owned Docker Compose | Source/test/script fingerprint `6a3027eef5c134b36ce2334be2144b5be79aced14d837032835ceb153b2f06a7`; Compose fingerprint `31a845fc352b9443961e48b83726ecaf336222cf64c6fd222142c608acf52be4` | Engine Gate remains valid for the unchanged model-disabled path; optional Agent budget fix was fast-tested | Passed; 1 integration test in 22.11s before the optional Agent budget fix. No model-enabled IT rerun was performed. Docker resources owned by the exact Compose project were cleaned up. |

## Bound Images

- `postgres:16.14@sha256:95206741a5b214807675e14165369d05b93a9cf692223b616d07cca227e74b0b`
- `clickhouse/clickhouse-server:25.3.2.39@sha256:8745843b17f92db1765025009772ec1d87dfdcaa95deabca6b802a66cb669d30`
- `apache/doris:fe-4.0.6@sha256:830863e9ff8af4b354df5303b1235c11b2f822fa3125b83a1627e498c5c251cf`
- `apache/doris:be-4.0.6@sha256:72e58021c2fa110350269e587d6c74a28579d3c1ed563023cb784a3824f4ad87`

The Docker entrypoint uses `pull_policy: never`, `--no-build`, and `--pull never`.
It records the pre-existing dangling-image baseline and removes only resources
owned by the `yamazaki-it-read-only` Compose project.
