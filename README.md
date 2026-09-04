# Yamazaki

> Status: `Validated` — the internal, controlled-network read-only POC has
> passed its bounded validation Gate. There is no supported release.

Yamazaki is an evidence-driven AIOps governance control plane planned for
ClickHouse and Apache Doris. It is intended to organize operational signals,
evidence, diagnosis, recommendations, controlled actions, and verification
without becoming part of the database query execution path.

## Current Status

The worktree implementation provides a single-process Coordinator, deterministic
slow-query detection and diagnosis, fixed read-only ClickHouse and Doris
adapters, PostgreSQL control state, a local evidence store, a CLI, and an
optional localhost read API. These capabilities are validated only for the
bounded POC environment and behavior recorded in the test matrix; this is not a
production support claim.

No database action path, multi-agent runtime, message bus, durable workflow,
policy service, high-availability deployment, or production support commitment
is included.

## Development

Use Python 3.13 and the locked environment:

```bash
uv sync --locked --all-extras --group dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest tests/unit tests/contract tests/replay
```

The real infrastructure Gate uses only the cached, digest-pinned images recorded
in [the test matrix](docs/reference/test-matrix.md):

```bash
./scripts/run_dual_engine_it.sh
```

Do not run the Docker Gate repeatedly against unchanged code and infrastructure.

## Planned Scope

Slow-query governance is the first planned scenario. Future candidate scenarios
include cluster health, workload governance, capacity and cost, and
configuration or change risk.

Each scenario must begin with official ClickHouse or Doris evidence, preserve
engine-specific semantics, and pass its own validation before its status can
advance beyond `Planned` or `Experimental`.

## Non-goals

Yamazaki is not intended to be:

- A database or query execution engine.
- A transparent query proxy or synchronous dependency for business queries.
- A generic monitoring data store.
- An unrestricted administrative agent with arbitrary SQL or shell access.
- A claim of compatibility with untested ClickHouse or Doris versions.

## Project Principles

- Prefer official engine facts over model inference.
- Keep diagnosis read-only by default.
- Separate analysis from policy-controlled execution.
- Preserve evidence references, uncertainty, and auditability.
- Match validation effort to operational risk.
- Distinguish planned, experimental, validated, and supported capabilities.

## Documentation

- [Documentation index](docs/README.md)
- [Architecture boundaries](docs/architecture/README.md)
- [Architecture decision records](docs/adr/README.md)
- [Compatibility status](docs/compatibility/README.md)
- [POC test matrix](docs/reference/test-matrix.md)
- [Release policy](RELEASING.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Small documentation changes do not need
an Issue, but every pull request must clearly describe the change and the checks
that actually ran.

## Security

Do not report vulnerabilities in public Issues. Follow
[SECURITY.md](SECURITY.md) to submit a private report.

## License

Yamazaki is licensed under the [Apache License 2.0](LICENSE).
