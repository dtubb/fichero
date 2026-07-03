# Developer Docs

This section is the short, code-grounded entry point for developers who need
to understand how the current Fichero app fits together before diving into the
deeper contributor reference.

## Start here

- [How Fichero Works](./how-fichero-works.md) — the runtime shape of the SwiftUI
  app, the FastAPI engine, storage, workflows, the KG extraction path, and
  curation.

## Then use the deeper reference

The detailed contributor manuals remain under `docs/contributor/`:

- [Contributor Overview](../contributor/README.md)
- [Architecture Overview](../contributor/architecture-overview.md)
- [OpenAPI and Generated Clients](../contributor/openapi-and-clients.md)
- [Data, Search, and Knowledge Graph](../contributor/data-search-and-kg.md)
- [Workflows, Activity, and Curation](../contributor/workflows-activity-and-curation.md)
- [Action Registry](../contributor/action-registry.md)
- [Security Model](../contributor/security-model.md)
- [Setup and Contributing](../contributor/setup-and-contributing.md)

The split is intentional:

- `docs/developer/` is the quick "how the shipped system works" layer
- `docs/contributor/` is the broader maintenance and implementation reference
