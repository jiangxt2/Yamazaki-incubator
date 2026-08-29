# Releasing Yamazaki

> Current status: Yamazaki has no released version, supported artifact, stable
> API, or production support commitment.

This document defines the release policy that will apply after the project has
an approved public artifact and a verified build and validation path. It does
not authorize a release or imply that an initial version already exists.

## When Versioning Starts

Versioning starts only after an architecture decision identifies the first
public artifact, its users, distribution channel, compatibility contract, and
validation requirements. Until then, do not create a version tag or GitHub
Release.

The first release implementation must also establish one authoritative version
source and verify that it agrees with package metadata, release notes, and the
Git tag.

## Versioning

Yamazaki will use [Semantic Versioning 2.0.0](https://semver.org/) after
versioning is activated.

- Stable release tags use `vX.Y.Z`.
- Prerelease tags may use `vX.Y.Z-alpha.N`, `vX.Y.Z-beta.N`, or
  `vX.Y.Z-rc.N`.
- During `0.y.z` development, incompatible changes must still be identified in
  release notes and migration guidance when applicable.
- One version identifies one immutable commit and one traceable set of
  artifacts.

Creating a GitHub Release does not change a capability from `Planned` or
`Experimental` to `Validated` or `Supported`. Those states require their own
documented evidence.

## Release Prerequisites

Before creating a version tag:

- The release commit must be on the protected `master` branch.
- The change producing the release commit must have passed all required merge
  checks, and checks configured for `master` must be green.
- The release commit must comply with the Developer Certificate of Origin 1.1
  and contain a valid `Signed-off-by` trailer.
- The version source, package metadata, release notes, compatibility claims,
  and artifact metadata must agree once those files exist.
- Every artifact must pass its defined build, test, installation, and minimum
  runtime verification. Unverified artifacts must not be attached to a
  release.
- Security, license, dependency, and sensitive-information checks must pass.
- Release notes must distinguish `Experimental`, `Validated`, and `Supported`
  claims and identify relevant compatibility or migration risks.

Only a maintainer with explicit release authorization may create a version tag
or publish a GitHub Release.

## Publishing

The artifact type and registry are not selected. A future release workflow must
be reviewed separately after the build and validation path is working.

Registry publishing should use OpenID Connect or trusted publishing with a
protected GitHub Environment and least-privilege permissions. Do not store a
long-lived publishing token in the repository or workflow configuration.

Release automation must pin third-party actions to immutable commits and define
approval, timeout, failure recovery, artifact integrity, and audit behavior.
Signing, provenance, and software bill of materials requirements must be chosen
for the actual artifact rather than added as placeholders.

## Correcting a Release

Published version tags are immutable. Do not move, overwrite, or delete an
existing version tag. Correct a release by publishing a new version with clear
release notes and by applying ecosystem-specific withdrawal or yanking controls
when necessary.

Report release-related vulnerabilities through the private process in
[SECURITY.md](SECURITY.md), not a public Issue.
