# Yamazaki Agent Guidelines

Yamazaki is an early-stage, public incubation project for an evidence-driven
AIOps governance control plane for ClickHouse and Apache Doris. These
instructions apply to the entire repository unless a more specific directory
guide says otherwise.

## Instruction Loading

Before doing any work in this repository:

- Starting from the current working directory, walk upward through every parent
  directory and read each existing `AGENTS.md` and `CLAUDE.md` in full. This
  includes files in the repository root and directories above the repository.
- If both files exist in a directory, read both. Automatic discovery, memory,
  summaries, and previous sessions are not substitutes for reading them.
- More-specific directory instructions take precedence over broader parent
  instructions when they conflict. If instructions at the same level conflict,
  stop and report the conflict instead of choosing silently.
- If an applicable or referenced instruction file cannot be located or read
  completely, stop before modifying files or running project commands.
- Before modifying files or running Git operations, confirm the actual
  repository root with `git rev-parse --show-toplevel`.

## Project Status and Scope

- The repository is being initialized and has no implemented product, supported
  deployment, or verified production capability yet.
- Slow-query governance is the first planned scenario. Cluster health,
  workload governance, capacity and cost, and configuration risk are future
  candidate scenarios.
- The implementation language, agent runtime, workflow engine, policy engine,
  storage, messaging, model, and deployment stack are not decided.
- Documentation must distinguish `Planned`, `Experimental`, `Validated`, and
  `Supported` claims. Never describe a proposal or experiment as an implemented
  or production-ready capability.
- Keep public incubation in this repository separate from any possible future
  upstream or final project destination.

## Architecture and Safety Invariants

- Yamazaki is a control plane, not a database, query proxy, or synchronous
  dependency in the query execution path.
- Keep engine-specific behavior behind ClickHouse and Doris adapters. Preserve
  native engine evidence and capability differences instead of forcing false
  equivalence.
- Keep scenario-specific detection, evidence, diagnosis, policy, action, and
  verification behavior out of the shared core.
- Prefer official engine facts such as system tables, audit records, EXPLAIN,
  profiles, traces, runtime metrics, and server errors over rules, statistics,
  and model inference. Conclusions must retain evidence references and clearly
  identify uncertainty.
- Use versioned, traceable contracts between components. Do not select a wire
  format or programming framework until that decision is reviewed.
- Collection and diagnosis are read-only by default. An agent must never hold
  unrestricted production credentials or execute arbitrary SQL, shell commands,
  URLs, or administrative operations.
- Any future action path must use fixed action types, least privilege, policy
  evaluation, approval where required, idempotency, timeouts, audit records,
  and post-action verification or safe degradation.
- Credentials, sensitive SQL literals, business identifiers, profiles, and
  traces must be redacted before entering prompts, logs, telemetry, or durable
  stores.

## Development and Validation

- Do not invent build, test, lint, deployment, or release commands. Add commands
  here only after the repository contains a working, verified entry point.
- Keep code, comments, public documentation, commit messages, Issue content, and
  pull request content in English.
- Keep changes focused. Do not combine initialization or feature work with
  unrelated refactors, dependency additions, formatting, or generated files.
- Record major cross-component or security decisions before implementation.
  Technology choices must include alternatives, licensing, operational cost,
  compatibility, validation evidence, and an exit path.
- Match validation effort to risk. Documentation changes need documentation
  checks; engine semantics require real ClickHouse or Doris validation; access,
  credential, or production action changes require negative security tests and
  controlled end-to-end verification.
- Every independently verifiable behavior must have corresponding tests once
  implementation begins. Never skip or weaken tests to manufacture a passing
  result.
- Report only checks that actually ran, including failures, unavailable
  infrastructure, and unverified risks.
- Do not commit secrets, production data, internal endpoints, or machine-local
  absolute paths.

## Contributions

- The project is licensed under Apache License 2.0.
- Every commit, including documentation and configuration changes, must comply
  with Developer Certificate of Origin 1.1 and include a valid `Signed-off-by`
  trailer from the actual contributor.
- Keep pull requests concise. Use `Description`, `Testing`, and
  `Additional information`; the last section is optional when there is nothing
  relevant to add.
- An Issue is not required for a small documentation change or isolated fix.
  User-facing behavior, public contracts, security policies, and production
  actions should reference an Issue, ADR, or design document when practical.
- Disclose AI assistance when used. The human contributor remains responsible
  for understanding, reviewing, and validating every submitted change.
- Do not create commits, push branches, open or edit Issues or pull requests,
  publish releases, or change external repository settings unless the current
  task explicitly authorizes that operation.

## Common Pitfalls

- Treating planned architecture as current capability.
- Treating model output as deterministic evidence.
- Using MCP or an interactive tool as a continuous collection system.
- Granting an agent direct production write access.
- Claiming engine or version compatibility without capability checks and real
  environment evidence.
- Relying only on mocks for engine behavior, permissions, or action safety.
- Reporting an action as successful without post-action verification.
