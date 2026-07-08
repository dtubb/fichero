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
- `fichero-engine/src/fichero/`: the Python FastAPI engine

The Swift app is not the source of truth for data or AI behavior. It is a UI
layer that talks to the engine over pinned HTTPS. On macOS, the embedded-engine
path defaults to `https://127.0.0.1:8765`; `EngineConfig` also supports an
explicit configured host, and iOS/iPadOS use that remote-host path rather than
starting a local engine.

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

`fichero.api.main` is the application entry point. `db.py` is the main storage
abstraction over DuckDB and LanceDB. Business features are exposed through
route modules under `fichero-engine/src/fichero/api/routes/`.

## Route Registration and Feature Tiers

The engine does not always register the same route set. `register_tiered_routes`
in `api/main.py` chooses routers based on `FICHERO_FEATURE_TIER`.

Two practical tiers matter:

- `release`: the default route set used by the app and normal builds
- `dev`: `release` plus the currently dev-tier extras

As of the current `api/main.py`, most knowledge-graph, research, action,
chains, model-comparison, and automation-related surfaces are already in the
core route list. The remaining dev-tier surface is small; contributors should
check `get_route_specs_for_tier` in `fichero.api.main` rather than assuming KG
or research routes are dev-only.

## One Engine, Many Surfaces

The desktop app is the main user-facing client, but the engine is shared across more than one surface.

The same backend is also consumed by:

- the typed `python -m fichero` CLI
- the generated Swift OpenAPI client plus hand-written service wrappers
- the `fichero.mcp_server` / `fichero-mcp` MCP server entrypoint
- iOS/iPadOS clients that connect to a configured remote engine host

That is why backend behavior should be explained in terms of routes and models, not in terms of one specific screen.
