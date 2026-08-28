# Yamazaki

> Status: `Planned` — early public incubation with no implemented runtime or
> supported release.

Yamazaki is an evidence-driven AIOps governance control plane planned for
ClickHouse and Apache Doris. It is intended to organize operational signals,
evidence, diagnosis, recommendations, controlled actions, and verification
without becoming part of the database query execution path.

## Current Status

The repository currently contains project governance and design documentation
only. It does not provide a runnable service, database integration, model
runtime, deployment package, or production support commitment.

The implementation language, agent framework, storage, messaging, workflow,
policy, model, and deployment technologies remain undecided.

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Small documentation changes do not need
an Issue, but every pull request must clearly describe the change and the checks
that actually ran.

## Security

Do not report vulnerabilities in public Issues. Follow
[SECURITY.md](SECURITY.md) to submit a private report.

## License

Yamazaki is licensed under the [Apache License 2.0](LICENSE).
