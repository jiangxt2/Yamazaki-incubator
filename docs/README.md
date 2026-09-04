# Yamazaki Documentation

Yamazaki is in early public incubation. These documents distinguish the
validated internal POC from planned and unsupported product capabilities.

Use the following status terms consistently:

- `Planned`: designed or proposed but not implemented.
- `Experimental`: implemented for evaluation without a support commitment.
- `Validated`: tested against an explicitly documented environment and scope.
- `Supported`: maintained within a published compatibility and support policy.

## Documentation Areas

- [Architecture](architecture/README.md): stable responsibilities, boundaries,
  and safety principles.
- [Architecture decision records](adr/README.md): how significant decisions are
  proposed and recorded.
- [Compatibility](compatibility/README.md): engine, deployment, and version
  evidence. The current entry is limited to the validated POC environment.
- [Test matrix](reference/test-matrix.md): exact POC suites, bound images, and
  validation results.
- [POC validation](reference/poc-validation.md): the validated internal
  read-only slow-query scope and its limitations.

Detailed research and evolving internal planning are intentionally not copied
into the public repository until their facts and status have been reviewed.
