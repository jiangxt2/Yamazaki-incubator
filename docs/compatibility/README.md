# Compatibility

> Status: `Validated` for the bounded POC environment below; no supported
> compatibility range is claimed.

Yamazaki has no supported ClickHouse or Apache Doris compatibility claims yet.
The compatibility matrix will be populated only after environment discovery and
reproducible validation.

The completed POC Gate is limited to the following cached image identities. It
establishes `Validated` evidence only for the documented POC behavior, not a
supported version range:

| Component | Validated POC Gate |
| --- | --- |
| PostgreSQL | `16.14@sha256:95206741a5b214807675e14165369d05b93a9cf692223b616d07cca227e74b0b` |
| ClickHouse | `25.3.2.39@sha256:8745843b17f92db1765025009772ec1d87dfdcaa95deabca6b802a66cb669d30` |
| Apache Doris FE | `4.0.6@sha256:830863e9ff8af4b354df5303b1235c11b2f822fa3125b83a1627e498c5c251cf` |
| Apache Doris BE | `4.0.6@sha256:72e58021c2fa110350269e587d6c74a28579d3c1ed563023cb784a3824f4ad87` |
| Host | Apple arm64, Docker Desktop |

Future entries must identify:

- Engine and exact version.
- Deployment mode and topology.
- Authentication and capability requirements.
- Scenario and feature scope.
- Validation environment and reproducible evidence.
- Known limitations and unsupported behavior.

Other engine versions, deployment modes, and capability combinations remain
unsupported until they have their own validated entry here.
