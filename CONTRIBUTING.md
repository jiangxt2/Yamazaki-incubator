# Contributing to Yamazaki

Thank you for contributing to Yamazaki. The project is in early public
incubation and welcomes focused contributions to design, documentation,
testing, engine integration, diagnosis, and safety.

Proposals and experiments must identify their status clearly. A merged change
does not by itself establish production support.

## Before You Start

- Review the existing documentation and open Issues before starting overlapping
  work.
- Read [AGENTS.md](AGENTS.md) when using an automated coding or documentation
  agent.
- Report suspected vulnerabilities through the private process in
  [SECURITY.md](SECURITY.md), not a public Issue.
- Keep each change focused on one coherent purpose.

The repository does not yet define build, test, or deployment commands. Do not
invent or claim commands that are not present and verified in the repository.

## Issues

An Issue should explain:

- The background or problem.
- The expected outcome.
- The intended scope and explicit non-goals.
- Relevant versions, evidence, logs, links, or reproduction details when
  available.

An Issue is optional for a small documentation change or isolated fix.
User-facing behavior, public contracts, security policy, and production action
changes should reference an Issue, ADR, or design document when practical.

## Pull Requests

Keep pull requests concise and use the repository template:

- `Description`: what changed and why.
- `Testing`: checks that actually ran, or why a check did not run.
- `Additional information`: optional context such as related Issues, user-facing
  impact, compatibility, risks, screenshots, follow-ups, or AI assistance.

The title and description must be sufficient for a future contributor to
understand the purpose and scope of the change.

## Validation

Match validation effort to risk:

- Documentation and templates require documentation and link checks.
- Internal implementation changes require relevant static and unit checks once
  those tools exist.
- ClickHouse or Doris semantics require tests against the applicable real
  engine and supported version profile.
- Credential, permission, policy, or production action changes require negative
  security tests, audit verification, and controlled end-to-end validation.

Run the current documentation lint command for Markdown changes:

```bash
npx --yes markdownlint-cli2@0.23.2 "**/*.md"
```

Never skip, weaken, or misreport a check to create a passing result. State
unavailable infrastructure and unverified risks explicitly.

## Code and Documentation

- Use English for code, comments, public documentation, commit messages, Issues,
  and pull requests.
- Do not commit secrets, production data, internal endpoints, or machine-local
  absolute paths.
- Do not describe planned or experimental behavior as implemented, validated,
  supported, or production-ready.
- Avoid unrelated refactors, dependency changes, generated files, and formatting
  churn.

## AI Assistance

Disclose AI assistance in the pull request when used. The human contributor is
responsible for understanding, reviewing, and validating every submitted line.

## Review and Merge

The `master` branch is protected. Changes after the initial repository baseline
must be reviewed through a pull request. Reviewers may request additional
context, tests, risk analysis, or documentation before approval.

## License and Sign-off

Contributions are accepted under the [Apache License 2.0](LICENSE) and the
[Developer Certificate of Origin 1.1](https://developercertificate.org/).

Every commit, including documentation and configuration changes, must include a
valid `Signed-off-by` trailer from the actual contributor. For command-line Git,
use `git commit --signoff` or provide an equivalent valid trailer.

To check all commits in a proposed range locally, run:

```bash
./scripts/check-dco.sh <base-commit> <head-commit>
```
