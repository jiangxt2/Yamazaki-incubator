# Architecture Decision Records

Architecture decision records capture significant choices before implementation
and preserve why a direction was selected.

## When to Write an ADR

Use an ADR for decisions that materially affect multiple components, public
contracts, security boundaries, permissions, data flow, deployment topology, or
long-term operational cost.

Small documentation changes, isolated fixes, and reversible local implementation
details do not require an ADR.

## Status

Use one of these states:

- `Proposed`: open for review and not yet binding.
- `Accepted`: approved as the current decision.
- `Superseded`: replaced by a newer accepted decision.
- `Rejected`: considered and intentionally not adopted.

## Minimum Content

Each ADR should include:

- Context and the problem being decided.
- The decision and its current status.
- Alternatives considered.
- Security, compatibility, licensing, and operational consequences.
- Validation evidence or the evidence still required.
- An exit, rollback, or supersession path when applicable.

No ADRs have been accepted yet.
