# Architecture Overview

## Table of Contents

- [Top-Level Shape](#top-level-shape)
- [Frontend Responsibilities](#frontend-responsibilities)
- [Backend Responsibilities](#backend-responsibilities)
- [Route Registration and Feature Tiers](#route-registration-and-feature-tiers)
- [One Engine, Many Surfaces](#one-engine-many-surfaces)

## Top-Level Shape

Fichero is a two-part system:

- `fichero/fichero/`: the native macOS SwiftUI app
- `fichero-engine/src/fichero/`: the Python FastAPI engine

The Swift app is not the source of truth for data or AI behavior. It is a UI layer that talks to the engine over HTTP on `localhost:8765`.

## Frontend Responsibilities

The frontend owns:

- windows, panes, and navigation
- document browsing and selection state
- reading surfaces for images and PDFs
- inspector tabs for content, notes, annotations, entities, KG, artifacts, and info
- workflow launch and activity display
- hand-written service wrappers around the generated OpenAPI client

The main window entry point is `LibraryWindow`, which either shows the welcome screen or injects per-library services into `DocumentTabView`. `ContentView` then manages the four-part workspace: sidebar, browser/content pane, reading pane, and inspector.

One important architectural detail from `LibraryManager` and `LibraryWindow`: each open library has its own service instances, and those instances are shared across the windows and tabs working against that library.

## Backend Responsibilities

The backend owns:

- file ingest
- document and folder persistence
- annotations and notes APIs
- search and embedding logic
- entity and claim storage
- workflow execution, tasking, and activity logs
- provider and model configuration

`fichero.api.main` is the application entry point. `db.py` is the main storage abstraction over DuckDB and LanceDB. Business features are exposed through route modules under `fichero/api/routes/`.

## Route Registration and Feature Tiers

The engine does not always register the same route set. `register_tiered_routes` in `api/main.py` chooses routers based on `FICHERO_FEATURE_TIER`.

Two practical tiers matter:

- `release`: stable core routes
- `dev`: adds staged KG, research, graph, and other experimental or not-yet-promoted surfaces

Core routes include activity, annotations, documents, entities, folders, ingest, providers, search, tasks, workflow execution, and workflows. Dev-tier routes add the `/api/kg/*` family plus related graph and research surfaces.

## One Engine, Many Surfaces

The desktop app is the main user-facing client, but the engine is shared across more than one surface.

The same backend is also consumed by:

- the typed `python -m fichero` CLI
- generated Swift service layers
- web-oriented or research-oriented surfaces in development

That is why backend behavior should be explained in terms of routes and models, not in terms of one specific screen.
