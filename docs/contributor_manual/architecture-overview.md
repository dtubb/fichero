(AI generated. Not reviewed.)

# Architecture Overview

## Table of Contents

- [Top-Level Shape](#top-level-shape)
- [Frontend Responsibilities](#frontend-responsibilities)
- [Backend Responsibilities](#backend-responsibilities)
- [Route Registration and Feature Tiers](#route-registration-and-feature-tiers)
- [One Engine, Many Surfaces](#one-engine-many-surfaces)

## Top-Level Shape

Fichero is a two-part system:

- `fichero/fichero/`: the native Apple SwiftUI app, with macOS as the primary surface today
- `fichero-server/src/fichero_server/`: the Python FastAPI engine

The Swift app is not the source of truth for data or AI behavior. It is a UI
layer that talks to the engine over a Unix domain socket locally, or pinned
HTTPS (`https://127.0.0.1:8765`) over the network. `EngineConfig` also supports
an explicit configured host, and iOS/iPadOS use that remote-host path rather
than starting a local engine.

## Frontend Responsibilities

The frontend owns:

- windows, panes, and navigation
- document browsing and selection state
- reading surfaces for images and PDFs
- inspector tabs for content, outline, annotations, notes, interpretation, entities, knowledge graph, citations, edits, and info
- workflow launch and activity display
- hand-written service wrappers around the generated OpenAPI client

The main window entry point is `LibraryWindow`, which either shows the welcome screen or injects per-library services into `DocumentTabView`. `ContentView` then manages the four-part workspace: sidebar, browser/content pane, reading pane, and inspector.

One important architectural detail from `LibraryManager` and `LibraryWindow`: each open library has its own service instances, and those instances are shared across the windows and tabs working against that library.

## Backend Responsibilities

The backend owns:

- file ingest
- document and folder persistence
- folded node-model persistence for saved searches, bookmark aliases, research workspaces, and research plan/task/step nodes
- annotations and notes APIs
- search and embedding logic
- entity and claim storage
- workflow execution, tasking, and activity logs
- provider and model configuration

`fichero_server.api.main` is the application entry point. `db.py` is the main storage
abstraction over DuckDB and LanceDB. Business features are exposed through
route modules under `fichero-server/src/fichero_server/api/routes/`.

## Route Registration and Feature Tiers

The engine does not always register the same route set. `register_tiered_routes`
in `api/main.py` chooses routers based on `FICHERO_FEATURE_TIER`.

Two practical tiers matter:

- `release`: the default route set used by the app and normal builds
- `dev`: `release` plus the currently dev-tier extras

The release tier carries a deliberately small route set; most knowledge-graph,
research, chains, and automation surfaces sit at beta or dev tier. The
generated `feature_tiers_generated.py` (from `features.yaml`) is the source of
truth — check `CUMULATIVE_ROUTE_PREFIXES` and `get_route_specs_for_tier`
rather than assuming what any tier includes.

## One Engine, Many Surfaces

The desktop app is the main user-facing client, but the engine is shared across more than one surface.

The same backend is also consumed by:

- the typed `python -m fichero_cli` CLI
- the generated Swift OpenAPI client plus hand-written service wrappers
- the `fichero_mcp.server` / `fichero-mcp` MCP server entrypoint
- iOS/iPadOS clients that connect to a configured remote engine host

That is why backend behavior should be explained in terms of routes and models, not in terms of one specific screen.
