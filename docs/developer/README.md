# Fichero Developer Docs

This section explains how the current Fichero codebase works for contributors. It is grounded in the live SwiftUI client under `fichero/fichero/`, the FastAPI engine under `fichero-engine/src/fichero/`, and the architecture notes already present in `docs/architecture/`.

## Table of Contents

- [Architecture Overview](./architecture-overview.md)
- [OpenAPI and Generated Clients](./openapi-and-clients.md)
- [Data Layer, Search, and Knowledge Graph Storage](./data-search-and-kg.md)
- [Workflows, Activity, and Curation](./workflows-activity-and-curation.md)
- [Setup and Contributing](./setup-and-contributing.md)

## Read This First

Fichero is not a single-process desktop app. The macOS app is a native SwiftUI frontend over a local Python backend.

The shortest accurate picture is:

```text
SwiftUI app -> localhost HTTP API -> FastAPI engine -> DuckDB + LanceDB
                                               -> LangGraph workflows
                                               -> LLM providers via LiteLLM
```

That architecture shapes almost every contributor task:

- UI work usually means changing SwiftUI views and hand-written service wrappers.
- data, AI, ingest, and search work usually means changing FastAPI routes and backend modules.
- contract changes require an OpenAPI sync so the Swift side compiles again.

## Core Reference Material In This Repo

- Root guidance: [../CLAUDE.md](../CLAUDE.md)
- Operational rules: [../../AGENTS.md](../../AGENTS.md)
- Backend overview: [../architecture/api/overview.md](../architecture/api/overview.md)
- SwiftUI overview: [../architecture/swiftui/overview.md](../architecture/swiftui/overview.md)
- API client contract notes: [../architecture/swiftui/api_client.md](../architecture/swiftui/api_client.md)
