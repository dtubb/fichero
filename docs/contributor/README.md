# Fichero Developer Docs

This section explains how the current Fichero codebase works for contributors. It is grounded in the live SwiftUI client under `fichero/fichero/`, the FastAPI engine under `fichero-engine/src/fichero/`, and the architecture notes already present in `docs/architecture/`.

## Table of Contents

- [Architecture Overview](./architecture-overview.md)
- [OpenAPI and Generated Clients](./openapi-and-clients.md)
- [Data Layer, Search, and Knowledge Graph Storage](./data-search-and-kg.md)
- [Workflows, Activity, and Curation](./workflows-activity-and-curation.md)
- [Action Registry](./action-registry.md)
- [Security Model](./security-model.md)
- [Tailscale Private Transport](../remote-backend-tailscale.md)
- [Setup and Contributing](./setup-and-contributing.md)

## Read This First

Fichero is not a single-process desktop app. The macOS app is a native SwiftUI app over a local fichero-engine server (Python, FastAPI).

The shortest accurate picture is:

```text
SwiftUI app -> pinned HTTPS loopback -> FastAPI engine -> DuckDB + LanceDB
                                                     -> LangGraph workflows
                                                     -> LLM providers via LangChain integrations
```

That architecture shapes almost every contributor task:

- UI work usually means changing SwiftUI views and hand-written service wrappers.
- data, AI, ingest, and search work usually means changing FastAPI routes and backend modules.
- contract changes require an OpenAPI sync so the Swift side compiles again.

## Contributing

For environment setup, build commands, and branch discipline, see [Setup and Contributing](./setup-and-contributing.md). The key mechanics: commit directly to the milestone branch, register new Swift files with `scripts/add-swift-file.rb`, use conventional commits with issue references, and never push to `main` without a PR.

For all backend mutations, the starting point is the action registry. Every write goes through `registry.invoke` rather than directly to DuckDB. See [Action Registry](./action-registry.md) for how to define actions, write the required tests, and use the generic invocation endpoint. The [Security Model](./security-model.md) covers the shared-secret token, multi-user ACL, Tailscale transport, and audit attribution.

## Core Reference Material In This Repo

- Detailed architecture + dev guide: [../CLAUDE.md](../CLAUDE.md)
- Operational rules: [../../AGENTS.md](../../AGENTS.md)
- Backend overview: [../architecture/api/overview.md](../architecture/api/overview.md)
- SwiftUI overview: [../architecture/swiftui/overview.md](../architecture/swiftui/overview.md)
- API client contract notes: [../architecture/swiftui/api_client.md](../architecture/swiftui/api_client.md)
